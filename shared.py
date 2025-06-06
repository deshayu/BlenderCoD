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