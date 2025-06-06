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
import os, time, importlib

import bpy
from bpy.types import Operator, AddonPreferences
from bpy.props import BoolProperty, IntProperty, FloatProperty, StringProperty, EnumProperty, CollectionProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.utils import register_class, unregister_class

from . import shared

# List of modules to be reloaded/imported
modules = ['shared', 'import_xmodel', 'import_xanim', 'export_xmodel', 'export_xanim']

for module in modules:
    if module not in globals():
        globals()[module] = importlib.import_module(f".{module}", package=__name__)
    # Reload the module
    importlib.reload(globals()[module])

bl_info = {
    "name": "BlenderCoD",
    "author": "Ma_rv, CoDEmanX, Flybynyt, SE2Dev, shiversoftdev, tupivere_",
    "version": (1, 0, 2),
    "blender": (4, 0, 0),
    "location": "File > Import/Export",
    "description": "Import/Export Call of Duty XModels and XAnims",
    "wiki_url": "https://github.com/deshayu/BlenderCoD/wiki",
    "tracker_url": "https://github.com/marv7000/BetterBlenderCOD/issues",
    "support": "COMMUNITY", 
    "category": "Import-Export",
    "warning": "",  # For Deprecations
}

def update_submenu_mode(self, context):
    try:
        unregister()
    except:
        pass
    register()

def update_scale_length(self, context):
    unit_map = {
        'CENTI':    0.01,
        'MILLI':    0.001,
        'METER':    1.0,
        'KILO':     1000.0,
        'INCH':     0.0254,
        'FOOT':     0.3048,
        'YARD':     0.9144,
        'MILE':     1609.343994,
    }

    if self.unit_enum in unit_map:
        self.scale_length = unit_map[self.unit_enum]


class BlenderCoD_Preferences(AddonPreferences):
    bl_idname = __name__

    use_submenu: BoolProperty(
        name="Group Import/Export Buttons",
        default=False,
        update=update_submenu_mode
    )

    def draw(self, context):
        layout = self.layout
        
        # Main toggle option
        row = layout.row()
        row.prop(self, "use_submenu")

class COD_MT_import_xmodel(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.xmodel"
    bl_label = "Import XModel"
    bl_description = "Import a CoD XMODEL_EXPORT / XMODEL_BIN File"
    bl_options = {'PRESET'}

    filename_ext = ".XMODEL_EXPORT;.XMODEL_BIN"
    filter_glob: StringProperty(
        default="*.XMODEL_EXPORT;*.XMODEL_BIN",
        options={'HIDDEN'}
    )

    ui_tab: EnumProperty(
        items=(('MAIN', "Main", "Main basic settings"),
               ('ARMATURE', "Armature", "Armature-related settings"),
               ),
        name="ui_tab",
        description="Import options categories",
        default='MAIN'
    )

    global_scale: FloatProperty(
        name="Scale",
        min=0.001, max=1000.0,
        default=1.0,
    )

    apply_unit_scale: BoolProperty(
        name="Apply Unit Scale",
        description=(
            "Enable to automatically scale units for Call of Duty:\n"
            "- Export: converts centimeters to inches (default CoD units).\n"
            "- Import: converts inches to centimeters.\n"
            "Disable this for older projects that already use inches; exporting then will scale them down further."
        ),
        default=True,
    )

    use_single_mesh: BoolProperty(
        name="Combine Meshes",
        description="Combine all meshes in the file into a single object",  # nopep8
        default=False
    )

    use_dup_tris: BoolProperty(
        name="Import Duplicate Tris",
        description=("Import tris that reuse the same vertices as another tri "
                     "(otherwise they are discarded)"),
        default=True
    )

    use_custom_normals: BoolProperty(
        name="Import Normals",
        description=("Import custom normals, if available "
                     "(otherwise Blender will recompute them)"),
        default=True
    )

    use_vertex_colors: BoolProperty(
        name="Import Vertex Colors",
        default=True
    )

    use_armature: BoolProperty(
        name="Import Armature",
        description="Import the skeleton",
        default=True
    )

    use_parents: BoolProperty(
        name="Import Relationships",
        description="Import the parent / child bone relationships",
        default=True
    )

    use_image_search: BoolProperty(
        name="Image Search",
        description=("Search subdirs for any associated images "
                     "(Warning, may be slow)"),
        default=True
    )

    def execute(self, context):
        self.report({'INFO'}, "Importing XModel...")

        from . import import_xmodel
        start_time = time.perf_counter()

        keywords = self.as_keywords(ignore=("filter_glob", "check_existing", "ui_tab"))

        result = import_xmodel.load(self, context, **keywords)

        if not result:
            self.report({'INFO'}, "Import finished in %s." % shared.timef(time.perf_counter() - start_time))
            _ret_val = {'FINISHED'}
        else:
            self.report({'ERROR'}, result)
            _ret_val = {'CANCELLED'}

        shared.show_warnings()
        return _ret_val

    @classmethod
    def poll(self, context):
        return (context.scene is not None)

    def draw(self, context):
        layout = self.layout

        # ===== Scale Options =====
        scale_box = layout.box()
        scale_box.label(text="Scale Options", icon='FULLSCREEN_ENTER')

        scale_row = scale_box.row(align=True)
        scale_row.prop(self, "global_scale")
        icon = 'SNAP_INCREMENT' if self.apply_unit_scale else 'SNAP_GRID'
        scale_row.prop(self, "apply_unit_scale", text="Apply Unit Scale", icon=icon)

        # ===== General Options =====
        gen_box = layout.box()
        gen_box.label(text="General", icon='OPTIONS')
        gen_box.prop(self, 'use_single_mesh')
        gen_box.prop(self, 'use_custom_normals')
        gen_box.prop(self, 'use_vertex_colors')
        gen_box.prop(self, 'use_dup_tris')
        gen_box.prop(self, 'use_image_search')
        gen_box.prop(self, 'use_armature')

        # ===== Armature Options =====
        if self.use_armature:
            abox = layout.box()
            abox.label(text="Armature Options", icon='ARMATURE_DATA')
            abox.prop(self, 'use_parents')


class COD_MT_import_xanim(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.xanim"
    bl_label = "Import XAnim"
    bl_description = "Import a CoD XANIM_EXPORT / XANIM_BIN File"
    bl_options = {'PRESET'}

    filename_ext = ".XANIM_EXPORT;.NT_EXPORT;.XANIM_BIN"
    filter_glob: StringProperty(
        default="*.XANIM_EXPORT;*.NT_EXPORT;*.XANIM_BIN",
        options={'HIDDEN'}
    )

    files: CollectionProperty(type=bpy.types.PropertyGroup)

    global_scale: FloatProperty(
        name="Scale",
        min=0.001, max=1000.0,
        default=1.0,
    )

    apply_unit_scale: BoolProperty(
        name="Apply Unit",
        description="Scale all data according to current Blender size,"
                    " to match CoD units",
        default=True,
    )

    use_notetracks: BoolProperty(
        name="Import Notetracks",
        description=("Import notes to scene timeline markers "
                     "(or action pose markers if 'Import as Action' is enabled)"),  # nopep8
        default=True
    )

    use_notetrack_file: BoolProperty(
        name="Import NT_EXPORT File",
        description=("Automatically import the matching NT_EXPORT file "
                     "(if present) for each XANIM_EXPORT"),
        default=False
    )

    fps_scale_type: EnumProperty(
        name="Scale FPS",
        description="Automatically convert all imported animation(s) to the specified framerate",   # nopep8
        items=(('DISABLED', "Disabled", "No framerate adjustments are applied"),   # nopep8
               ('ACTION', "Action", "Use the animation's framerate"),
               ('CUSTOM', "Custom", "Use custom framerate")
               ),
        default='ACTION',
    )

    fps_scale_target_fps: FloatProperty(
        name="Target FPS",
        description=("Custom framerate that all imported anims "
                     "will be adjusted to use"),
        default=30,
        min=1,
        max=120
    )

    update_scene_fps: BoolProperty(
        name="Update Scene FPS",
        description=("Set the scene framerate to match the framerate "
                     "found in the first imported animation"),
        default=True
    )

    update_frame_range: BoolProperty(
    name="Update Frame Range",
    description=("Set the frame range to match the action "
                    "found in the imported animation"),
    default=True
    )

    def execute(self, context):
        self.report({'INFO'}, "Importing XAnim...")

        from . import import_xanim
        start_time = time.perf_counter()

        ignored_properties = ("filter_glob", "files")
        result = import_xanim.load(self, context, **self.as_keywords(ignore=ignored_properties))

        if not result:
            self.report({'INFO'}, "Import finished in %s." % shared.timef(time.perf_counter() - start_time))
            _ret_val = {'FINISHED'}
        else:
            self.report({'ERROR'}, result)
            _ret_val = {'CANCELLED'}

        shared.show_warnings()
        return _ret_val

    @classmethod
    def poll(self, context):
        return (context.scene is not None)

    def draw(self, context):
        layout = self.layout

        # ===== Scale Options =====
        scale_box = layout.box()
        scale_box.label(text="Scale Options", icon='FULLSCREEN_ENTER')

        scale_row = scale_box.row(align=True)
        scale_row.prop(self, "global_scale")
        icon = 'SNAP_INCREMENT' if self.apply_unit_scale else 'SNAP_GRID'
        scale_row.prop(self, "apply_unit_scale", text="Apply Unit Scale", icon=icon)

        # ===== Notetracks Settings =====
        box = layout.box()
        box.label(text="Notetrack Settings", icon='MARKER_HLT')
        row = box.row()
        row.prop(self, 'use_notetracks', text="Import Notetracks")
        row = box.row()
        row.enabled = self.use_notetracks
        row.prop(self, 'use_notetrack_file', text="Load From .NT_EXPORT")

        # ===== Framerate Settings =====
        box = layout.box()
        box.label(text="Frame Rate Settings", icon='RENDER_ANIMATION')
        
        row = box.row()
        row.label(text="Framerate:")
        row.prop(self, 'fps_scale_type', expand=True)
        
        if self.fps_scale_type == 'CUSTOM':
            box.prop(self, 'fps_scale_target_fps', text="Custom Target FPS")

        box = layout.box()
        box.label(text="Frame Range", icon='PREVIEW_RANGE')
        box.prop(self, "update_frame_range", text="Update Timeline Range")

class COD_MT_export_xmodel(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.xmodel"
    bl_label = 'Export XModel'
    bl_description = "Export a CoD XMODEL_EXPORT / XMODEL_BIN File"
    bl_options = {'PRESET'}

    filename_ext = ".XMODEL_EXPORT"
    filter_glob: StringProperty(
        default="*.XMODEL_EXPORT;*.XMODEL_BIN", options={'HIDDEN'})

    # Used to map target_format values to actual file extensions
    format_ext_map = {
        'XMODEL_EXPORT': '.XMODEL_EXPORT',
        'XMODEL_BIN': '.XMODEL_BIN'
    }

    target_format: EnumProperty(
        name="Format",
        description="The target format to export to",
        items=(('XMODEL_EXPORT', "XMODEL_EXPORT",
                "Raw text format used from CoD1-CoD:BO"),
               ('XMODEL_BIN', "XMODEL_BIN",
                "Binary model format used by CoD:BO3")),
        default='XMODEL_BIN'
    )

    format_version: EnumProperty(
        name="Format Version",
        description="XMODEL_EXPORT format version for export",
        items=(('5', "Version 5", "vCoD, CoD:UO"),
               ('6', "Version 6", "CoD2, CoD4, CoD:WaW, CoD:BO"),
               ('7', "Version 7", "CoD:BO3")),
        default='7'
    )

    use_selection: BoolProperty(
        name="Selection only",
        description=("Export selected meshes only "
                     "(object or weight paint mode)"),
        default=False
    )

    global_scale: FloatProperty(
        name="Scale",
        min=0.001, max=1000.0,
        default=1.0,
    )

    apply_unit_scale: BoolProperty(
        name="Apply Unit",
        description="Scale all data according to current Blender size,"
                    " to match CoD units",
        default=True,
    )

    use_vertex_colors: BoolProperty(
        name="Vertex Colors",
        description=("Export vertex colors "
                     "(if disabled, white color will be used)"),
        default=True
    )

    #  White is 1 (opaque), black 0 (invisible)
    use_vertex_colors_alpha: BoolProperty(
        name="Calculate Alpha",
        description=("Automatically calculate alpha channel for vertex colors "
                     "by averaging the RGB color values together "
                     "(if disabled, 1.0 is used)"),
        default=True
    )

    use_vertex_colors_alpha_mode: EnumProperty(
        name="Vertex Alpha Source Layer",
        description="The target vertex color layer to use for calculating the alpha values",  # nopep8
        items=(('PRIMARY', "Active Layer",
                "Use the active vertex color layer to calculate alpha"),
               ('SECONDARY', "Secondary Layer",
                ("Use the secondary (first inactive) vertex color layer to calculate alpha "  # nopep8
                 "(If only one layer is present, the active layer is used)")),
               ),
        default='PRIMARY'
    )

    use_vertex_cleanup: BoolProperty(
        name="Clean Up Vertices",
        description=("Try this if you have problems converting to xmodel. "
                     "Skips vertices which aren't used by any face "
                     "and updates references."),
        default=False
    )

    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply all mesh modifiers (except Armature)",
        default=False
    )

    modifier_quality: EnumProperty(
        name="Modifier Quality",
        description="The quality at which to apply mesh modifiers",
        items=(('PREVIEW', "Preview", ""),
               ('RENDER', "Render", ""),
               ),
        default='PREVIEW'
    )

    use_armature: BoolProperty(
        name="Armature",
        description=("Export bones "
                     "(if disabled, only a 'tag_origin' bone will be written)"),  # nopep8
        default=True
    )

    use_weight_min: BoolProperty(
        name="Minimum Bone Weight",
        description=("Try this if you get 'too small weight' "
                     "errors when converting"),
        default=False,
    )

    use_weight_min_threshold: FloatProperty(
        name="Threshold",
        description="Smallest allowed weight (minimum value)",
        default=0.010097,
        min=0.0,
        max=1.0,
        precision=6
    )

    def execute(self, context):
        self.report({'INFO'}, "Exporting XModel...")

        from . import export_xmodel
        start_time = time.perf_counter()

        ignore = ("filter_glob", "check_existing")
        result = None
        try:
            result = export_xmodel.save(self, context, **self.as_keywords(ignore=ignore))
        except Exception as _e:
            shared.add_warning(
                "An error occurred while exporting the XModel!\n"
                "Error:\n" + str(_e)
            )
            return {'CANCELLED'}

        if not result:
            self.report({'INFO'}, f"Export finished in {shared.timef(time.perf_counter() - start_time)}.")
            _ret_val = {'FINISHED'}
        else:
            self.report({'INFO'}, result)
            _ret_val = {'CANCELLED'}

        shared.show_warnings()
        return _ret_val

    @classmethod
    def poll(self, context):
        return (context.scene is not None)

    def check(self, context):
        from bpy_extras.io_utils import _check_axis_conversion

        change_ext = False
        change_axis = _check_axis_conversion(self)

        if self.check_extension is not None:
            filepath = self.filepath
            base, ext = os.path.splitext(filepath)

            if os.path.basename(filepath) and ext[1:] in self.format_ext_map:
                target_ext = self.format_ext_map[self.target_format]
                new_filepath = bpy.path.ensure_ext(base, target_ext if self.check_extension else "")
                
                if new_filepath != filepath:
                    self.filepath = new_filepath
                    change_ext = True

        return change_ext or change_axis

    def draw(self, context):
        layout = self.layout

        # ===== Export Format & Version =====
        box = layout.box()
        box.label(text="Export Format & Version", icon='EXPORT')
        box.prop(self, 'target_format', expand=True)
        box.label(text="Format Version")
        box.prop(self, 'format_version', text="")

        if context.mode in {'OBJECT', 'PAINT_WEIGHT'}:
            meshes_selected = sum(1 for obj in context.selected_objects if obj.type == 'MESH')
        else:
            meshes_selected = 0

        box.prop(self, 'use_selection', text=f"Selected Only ({meshes_selected} mesh{'es' if meshes_selected != 1 else ''})")

        # ===== Scale Options =====
        scale_box = layout.box()
        scale_box.label(text="Scale Options", icon='FULLSCREEN_ENTER')
        scale_row = scale_box.row(align=True)
        scale_row.prop(self, "global_scale")
        icon = 'SNAP_INCREMENT' if self.apply_unit_scale else 'SNAP_GRID'
        scale_row.prop(self, "apply_unit_scale", text="Apply Unit Scale", icon=icon)

        # ===== General Options =====
        gen_box = layout.box()
        gen_box.label(text="General", icon='OPTIONS')
        gen_box.prop(self, 'use_vertex_cleanup')
        if int(self.format_version) >= 6:
            gen_box.prop(self, 'use_vertex_colors')
        gen_box.prop(self, 'apply_modifiers')
        gen_box.prop(self, 'use_armature')

        # ===== Vertex Color Options =====
        if self.use_vertex_colors and int(self.format_version) >= 6:
            vbox = layout.box()
            vbox.label(text="Vertex Color Options", icon='GROUP_VCOL')
            vbox.prop(self, 'use_vertex_colors_alpha')
            if self.use_vertex_colors_alpha:
                row = vbox.row()
                row.label(text="Alpha Layer")
                row.prop(self, 'use_vertex_colors_alpha_mode', text="")

        # ===== Modifier Options =====
        if self.apply_modifiers:
            mod_box = layout.box()
            mod_box.label(text="Modifier Options", icon='MODIFIER')
            mod_box.prop(self, 'modifier_quality', expand=True)

        # ===== Armature Options =====
        if self.use_armature:
            abox = layout.box()
            abox.label(text="Armature Options", icon='ARMATURE_DATA')
            abox.prop(self, 'use_weight_min')
            if self.use_weight_min:
                abox.prop(self, 'use_weight_min_threshold')

class COD_MT_export_xanim(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.xanim"
    bl_label = 'Export XAnim'
    bl_description = "Export a CoD XANIM_EXPORT / XANIM_BIN File"
    bl_options = {'PRESET'}

    filename_ext = ".XANIM_EXPORT"
    filter_glob: StringProperty(
        default="*.XANIM_EXPORT;*.XANIM_BIN", options={'HIDDEN'})

    # Used to map target_format values to actual file extensions
    format_ext_map = {
        'XANIM_EXPORT': '.XANIM_EXPORT',
        'XANIM_BIN': '.XANIM_BIN'
    }

    target_format: EnumProperty(
        name="Format",
        description="The target format to export to",
        items=(('XANIM_EXPORT', "XANIM_EXPORT",
                "Raw text format used from CoD1-CoD:BO"),
               ('XANIM_BIN', "XANIM_BIN",
                "Binary animation format used by CoD:BO3")),
        default='XANIM_BIN'
    )

    use_selection: BoolProperty(
        name="Selection Only",
        description="Export selected bones only (pose mode)",
        default=True
    )

    global_scale: FloatProperty(
        name="Scale",
        min=0.001, max=1000.0,
        default=1.0,
    )

    apply_unit_scale: BoolProperty(
        name="Apply Unit",
        description="Scale all data according to current Blender size,"
                    " to match CoD units",
        default=True,
    )

    use_all_actions: BoolProperty(
        name="Export All Actions",
        description="Export *all* actions rather than just the active one",
        default=False
    )

    filename_format: StringProperty(
        name="Format",
        description=("The format string for the filenames when exporting multiple actions\n"  # nopep8
                     "%action, %s - The action name\n"
                     "%number, %d - The action number\n"
                     "%base,   %b - The base filename (at the top of the export window)\n"  # nopep8
                     ""),
        default="%action"
    )

    use_notetracks: BoolProperty(
        name="Notetracks",
        description="Export notetracks",
        default=True
    )

    use_notetrack_mode: EnumProperty(
        name="Notetrack Mode",
        description="Notetrack format to use. Always set 'CoD 7' for Black Ops, even if not using notetrack!",   # nopep8
        items=(('SCENE', "Scene",
                "Separate NT_EXPORT notetrack file for 'World at War'"),
               ('ACTION', "Action",
                "Separate NT_EXPORT notetrack file for 'Black Ops'")),
        default='ACTION'
    )

    use_notetrack_file: BoolProperty(
        name="Write NT_EXPORT",
        description=("Create an NT_EXPORT file for "
                     "the exported XANIM_EXPORT file(s)"),
        default=False
    )

    use_frame_range_mode: EnumProperty(
        name="Frame Range Mode",
        description="Decides what to use for the frame range",
        items=(('SCENE', "Scene", "Use the scene's frame range"),
               ('ACTION', "Action", "Use the frame range from each action"),
               ('CUSTOM', "Custom", "Use a user-defined frame range")),
        default='ACTION'
    )

    frame_start: IntProperty(
        name="Start",
        description="First frame to export",
        min=0,
        default=1
    )

    frame_end: IntProperty(
        name="End",
        description="Last frame to export",
        min=0,
        default=250
    )

    use_custom_framerate: BoolProperty(
        name="Custom Framerate",
        description=("Force all written files to use a user defined "
                     "custom framerate rather than the scene's framerate"),
        default=False
    )

    use_framerate: IntProperty(
        name="Framerate",
        description=("Set frames per second for export, "
                     "30 fps is commonly used."),
        default=30,
        min=1,
        max=1000
    )

    write_tag_align: BoolProperty(
        name="Write TAG_ALIGN",
        description=("Check this if you want to export TAG_ALIGN with the animation, required for some animations (Not needed for Viewmodel Animations)"),
        default=False
    )

    def execute(self, context):
        self.report({'INFO'}, "Exporting XAnim...")

        from . import export_xanim
        start_time = time.perf_counter()
        result = export_xanim.save(self, context, **self.as_keywords(ignore=("filter_glob", "check_existing")))

        if not result:
            msg = "Export finished in %s." % shared.timef(time.perf_counter() - start_time)
            self.report({'INFO'}, msg)
            _ret_val = {'FINISHED'}
        else:
            self.report({'ERROR'}, result)
            _ret_val = {'CANCELLED'}

        shared.show_warnings()
        return _ret_val

    @classmethod
    def poll(self, context):
        return (context.scene is not None)

    def check(self, context):
        from bpy_extras.io_utils import _check_axis_conversion

        change_ext = False
        change_axis = _check_axis_conversion(self)

        if self.check_extension is not None:
            filepath = self.filepath
            base, ext = os.path.splitext(filepath)

            if os.path.basename(filepath) and ext[1:] in self.format_ext_map:
                target_ext = self.format_ext_map[self.target_format]
                new_filepath = bpy.path.ensure_ext(base, target_ext if self.check_extension else "")
                
                if new_filepath != filepath:
                    self.filepath = new_filepath
                    change_ext = True

        return change_ext or change_axis

    def draw(self, context):
        layout = self.layout

        # ===== Export Format & Version =====
        box = layout.box()
        box.label(text="Export Format & Version", icon='EXPORT')
        box.prop(self, 'target_format', expand=True)
        box.prop(self, 'use_selection', text="Export Selected Bones Only")

        # ===== Scale Options =====
        scale_box = layout.box()
        scale_box.label(text="Scale Options", icon='FULLSCREEN_ENTER')
        scale_row = scale_box.row(align=True)
        scale_row.prop(self, "global_scale")
        icon = 'SNAP_INCREMENT' if self.apply_unit_scale else 'SNAP_GRID'
        scale_row.prop(self, "apply_unit_scale", text="Apply Unit Scale", icon=icon)

        # ===== General Options =====
        gen_box = layout.box()
        gen_box.label(text="General", icon='OPTIONS')
        gen_box.prop(self, 'use_all_actions', text="Export All Actions")

        # Actions info (nested directly under toggle for visibility)
        if self.use_all_actions:
            action_count = len(bpy.data.actions)
            row = gen_box.row()
            row.enabled = action_count > 0
            row.label(text=f"Detected {action_count} action{'s' if action_count != 1 else ''}", icon='ACTION')

        gen_box.prop(self, 'use_notetracks', text="Export Notetracks")
        gen_box.prop(self, 'use_custom_framerate', text="Override Scene Framerate")
        gen_box.prop(self, 'use_frame_range_mode', expand=True)
        gen_box.prop(self, 'write_tag_align', text="Write TAG_ALIGN", icon='ALIGN_CENTER')

        # ===== Notetrack Options =====
        if self.use_notetracks:
            note_box = layout.box()
            note_box.label(text="Notetrack Options", icon='MARKER_HLT')
            note_box.prop(self, 'use_notetrack_mode', expand=True)

            if self.target_format == 'XANIM_EXPORT':
                note_box.prop(
                    self,
                    'use_notetrack_file',
                    text="Export to .NT_EXPORT",
                    icon='FILE_TEXT' if self.use_notetrack_file else 'DOT'
                )

        # ===== Framerate Options =====
        if self.use_custom_framerate:
            framerate_box = layout.box()
            framerate_box.label(text="Framerate", icon='TIME')
            row = framerate_box.row()
            row.prop(self, 'use_framerate', text="Framerate")
            if self.use_framerate <= 0:
                row.alert = True
                framerate_box.label(text="Invalid framerate (must be > 0)", icon='ERROR')

        # ===== Frame Range =====
        if self.use_frame_range_mode == 'CUSTOM':
            frame_box = layout.box()
            frame_box.label(text="Custom Frame Range", icon='ARROW_LEFTRIGHT')
            row = frame_box.row(align=True)
            row.prop(self, 'frame_start', text="Start")
            row.prop(self, 'frame_end', text="End")

            if self.frame_start > self.frame_end:
                frame_box.label(text="Warning: Start frame > End frame", icon='ERROR')

class COD_MT_import_submenu(bpy.types.Menu):
    bl_idname = "COD_MT_import_submenu"
    bl_label = "Call of Duty"

    def draw(self, context):
        menu_func_xmodel_import(self, context)
        menu_func_xanim_import(self, context)


class COD_MT_export_submenu(bpy.types.Menu):
    bl_idname = "COD_MT_export_submenu"
    bl_label = "Call of Duty"

    def draw(self, context):
        menu_func_xmodel_export(self, context)
        menu_func_xanim_export(self, context)


def menu_func_xmodel_import(self, context):
    self.layout.operator(COD_MT_import_xmodel.bl_idname,
                         text="CoD XModel (.XMODEL_EXPORT, .XMODEL_BIN)")


def menu_func_xanim_import(self, context):
    self.layout.operator(COD_MT_import_xanim.bl_idname,
                         text="CoD XAnim (.XANIM_EXPORT, .XANIM_BIN)")


def menu_func_xmodel_export(self, context):
    self.layout.operator(COD_MT_export_xmodel.bl_idname,
                         text="CoD XModel (.XMODEL_EXPORT, .XMODEL_BIN)")


def menu_func_xanim_export(self, context):
    self.layout.operator(COD_MT_export_xanim.bl_idname,
                         text="CoD XAnim (.XANIM_EXPORT, .XANIM_BIN)")


def menu_func_import_submenu(self, context):
    self.layout.menu(COD_MT_import_submenu.bl_idname, text="Call of Duty")


def menu_func_export_submenu(self, context):
    self.layout.menu(COD_MT_export_submenu.bl_idname, text="Call of Duty")

classes = (
    BlenderCoD_Preferences,
    COD_MT_import_xmodel,
    COD_MT_import_xanim,
    COD_MT_export_xmodel,
    COD_MT_export_xanim,
    COD_MT_import_submenu,
    COD_MT_export_submenu
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Get preferences from the addon (same as package name 'io_scene_cod')
    preferences = bpy.context.preferences.addons[__name__].preferences

    # Add menu functions to file import/export depending on preferences
    if not preferences.use_submenu:
        bpy.types.TOPBAR_MT_file_import.append(menu_func_xmodel_import)
        bpy.types.TOPBAR_MT_file_import.append(menu_func_xanim_import)
        bpy.types.TOPBAR_MT_file_export.append(menu_func_xmodel_export)
        bpy.types.TOPBAR_MT_file_export.append(menu_func_xanim_export)
    else:
        bpy.types.TOPBAR_MT_file_import.append(menu_func_import_submenu)
        bpy.types.TOPBAR_MT_file_export.append(menu_func_export_submenu)

    # Set the global 'plugin_preferences' variable for use across the module
    shared.plugin_preferences = preferences


def unregister():
    # You have to try to unregister both types of the menus here because
    # the preferences will have already been changed by the time this func runs
    if not bpy.context.preferences.addons[__name__].preferences.use_submenu:
        try:
            bpy.types.TOPBAR_MT_file_import.remove(menu_func_xmodel_import)
            bpy.types.TOPBAR_MT_file_import.remove(menu_func_xanim_import)
            bpy.types.TOPBAR_MT_file_export.remove(menu_func_xmodel_export)
            bpy.types.TOPBAR_MT_file_export.remove(menu_func_xanim_export)
        except ValueError:
            pass  # Handle the case where the menu item wasn't added

    else:
        try:
            bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_submenu)
            bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_submenu)
        except ValueError:
            pass  # Handle the case where the menu item wasn't added

    for cls in classes:
        bpy.utils.unregister_class(cls)