# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

import os, string, bpy

CM_TO_INCH = 0.3937007874
INCH_TO_CM = 2.54000000001016 # 1 / CM_TO_INCH 

plugin_preferences = None
warning_messages: list[ str ] = []

units_of_time = (
	( 'weeks',	604_800	),
	( 'days',	86400	),
	( 'hours',	3600	),
	( 'mins',	60		),
	( 'secs',	1		),
	( 'ms',		10**-3	),
	( 'μs',		10**-6	),
	( 'ns',		10**-9	)
)

def timef( seconds: float, granularity = 2 ):
	"""Formats the given time from seconds into a readable string.

	E.g.:
	- 180 (w/ a granularity of 2) would return "3 mins"
	- 192.152 (w/ a granularity of 2) would return "3 mins, 12 secs"
	- 192.152 (w/ a granularity of 3) would return "3 mins, 12 secs, 151 ms"
	- 4825 (w/ a granularity of 2) would return "1 hour, 20 mins"
	- 4825 (w/ a granularity of 3) would return "1 hour, 20 mins, 25 secs"
	"""
	result = []

	for name, count in units_of_time:
		value = seconds // count
		if value:
			seconds -= value * count
			if value == 1:
				name = name.rstrip( 's' )
			result.append( "%i %s" % ( int( value ), name ) )
	
	if not result:
		result = [ "0 secs" ]

	return ', '.join( result[ :granularity ] )

# Exportables

def uv_layer_is_empty(uv_layer):
	return all(_lyr.uv.length_squared == 0.0 for _lyr in uv_layer.data)

def gather_exportable_objects(self, context, use_selection, use_armature, use_armature_filter=True):
    objs = context.selected_objects if use_selection else bpy.data.objects

    if use_selection and len(objs) == 1 and objs[0].type == 'ARMATURE':
        print(f"[ DEBUG ] Only armature '{objs[0].name}' selected; exporting only the armature.")
        return objs[0], []

    def is_enabled(obj):
        if obj.hide_get() or obj.hide_viewport or obj.hide_render:
            return False
        def find_collection(layer_coll, target):
            if layer_coll.collection == target:
                return layer_coll
            for child in layer_coll.children:
                found = find_collection(child, target)
                if found:
                    return found
            return None
        return any(
            (layer := find_collection(context.view_layer.layer_collection, coll)) and
            not layer.exclude and not layer.hide_viewport
            for coll in obj.users_collection
        )

    def has_arm_mod(obj, arm):
        return any(mod.type == 'ARMATURE' and mod.object == arm for mod in obj.modifiers)

    def is_parented(obj, arm):
        return obj.parent == arm

    def valid_mesh(obj, arm=None):
        if obj.type != 'MESH' or not is_enabled(obj):
            return False
        if not obj.material_slots:
            add_warning(f"Object '{obj.name}' has no materials assigned. Skipping.")
            return False
        uv_layer = obj.data.uv_layers.active
        if not uv_layer or uv_layer_is_empty(uv_layer):
            add_warning(f"Mesh '{obj.data.name}' has no UVs. Skipping.")
            return False
        if arm and use_armature_filter and not (has_arm_mod(obj, arm) or is_parented(obj, arm)):
            return False
        return True

    def find_armature(candidates):
        return next(
            (mod.object for obj in candidates if obj.type == 'MESH'
             for mod in obj.modifiers if mod.type == 'ARMATURE' and mod.object and mod.object.data.bones),
            None
        )

    armature = None
    exportable_objs = []

    if use_armature:
        active = context.active_object
        if active and active.type == 'ARMATURE' and active.data.bones:
            armature = active
            exportable_objs = [obj for obj in objs if valid_mesh(obj, armature)]

    if not armature or not exportable_objs:
        armature = None
        candidates = objs if use_selection else bpy.data.objects
        armature = find_armature(candidates)
        if not armature and not use_selection:
            active = context.active_object
            if active and active.type == 'ARMATURE' and active.data.bones:
                armature = active
            else:
                armature = next((obj for obj in bpy.data.objects if obj.type == 'ARMATURE' and obj.data.bones), None)
        exportable_objs = [obj for obj in objs if valid_mesh(obj, armature)]

    print(f"[ DEBUG ] Found {len(exportable_objs)} exportable object(s) linked to armature '{armature.name if armature else 'None'}'")
    return armature, exportable_objs

def apply_cm_to_inch_scale(scale):
    """
    Returns the scaled value converting centimeters to inches,
    multiplying 'scale' by CM_TO_INCH.
    """
    return scale * CM_TO_INCH


def apply_inch_to_cm_scale(scale):
    """
    Returns the scaled value converting inches to centimeters,
    multiplying 'scale' by INCH_TO_CM.
    """
    return scale * INCH_TO_CM

def process_filepath(filepath, target_format_key='target_format', default_format='XANIM_BIN', **kwargs):
    if not filepath:
        raise ValueError("Filepath cannot be empty")

    # Extract path components
    directory = os.path.dirname(filepath) or os.getcwd()
    base_name, ext = os.path.splitext(os.path.basename(filepath))
    base_name = base_name.lower()  # Sanitize base_name to lowercase
    target_format = kwargs.get(target_format_key, default_format).upper()

    # Define valid formats and extensions
    EXTENSIONS = {
        'XANIM_BIN': '.xanim_bin',
        'XANIM_EXPORT': '.xanim_export',
        'XMODEL_BIN': '.xmodel_bin',
        'XMODEL_EXPORT': '.xmodel_export'
    }

    # Validate target format
    if target_format not in EXTENSIONS:
        raise ValueError(f"Invalid target format. Must be one of: {', '.join(EXTENSIONS)}")

    # Set extension if none provided
    ext = ext.lower() or EXTENSIONS[target_format]
    formatted_filepath = os.path.join(directory, f"{base_name}{ext}")

    # Create filename template
    filename_template = string.Template("${action}")
    filename_template.delimiter = '%'

    return directory, base_name, ext, formatted_filepath, filename_template

def get_metadata_string(filepath):
    msg = "// Exported using Blender v%s\n" % bpy.app.version_string
    msg += "// Export filename: '%s'\n" % filepath.replace("\\", "/")
    if bpy.data.filepath is None:
        source_file = "<none>"
    else:
        source_file = bpy.data.filepath.replace('\\', '/')
    msg += "// Source filename: '%s'\n" % source_file
    return msg

def raise_error( message ):
	class ErrorOperator( bpy.types.Operator ):
		bl_idname = "wm.error_operator"
		bl_label = "pv_blender_cod Error"

		message: bpy.props.StringProperty(
			name="Error Message"
		) # type: ignore

		def execute( self, context ):
			self.report( {'ERROR'}, self.message )
			return { 'FINISHED' }

	# Register the operator if not already registered
	if "wm.error_operator" not in bpy.types.Operator.__dict__:
		bpy.utils.register_class( ErrorOperator )

	bpy.ops.wm.error_operator( 'INVOKE_DEFAULT', message = message )

class PV_OT_message_list_popup(bpy.types.Operator): # Proventus stuff
	bl_idname = "wm.pv_message_list_popup"
	bl_label = "Warnings occured during export!"

	messages: bpy.props.StringProperty() # type: ignore

	def execute(self, context):
		return {'FINISHED'}

	def invoke(self, context, event):
		return context.window_manager.invoke_props_dialog( self, width=600 )

	def draw(self, context):
		layout = self.layout
		col = layout.column()

		lines = self.messages.split('\n')
		display_lines = lines[:5]
		for line in display_lines:
			col.label(text=line)

		remaining = len(lines) - len(display_lines)
		if remaining > 0:
			col.label( text = f"... + {remaining} more." )

		col.separator()

		col.label(
			text = "Go to Window --> Toggle System Console for more info.",
			icon = 'INFO'
		)

def show_warnings():
	global warning_messages

	# Only show dialog if there are messages to show
	if not warning_messages.__len__(): return

	msg_str = "\n".join( warning_messages )
	warning_messages = []
	# print( "[ DEBUG ] Showing warnings dialog..." )
	bpy.ops.wm.pv_message_list_popup( 'INVOKE_DEFAULT', messages = msg_str )

def add_warning(_msg: str):
	global warning_messages
	
	print( '[ WARNING ]', _msg )
	warning_messages.append( '--> ' + _msg )