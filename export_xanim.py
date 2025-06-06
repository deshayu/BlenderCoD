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
import os, bpy

from . import shared
from .PyCoD import xanim as XAnim

# Pre-define TAG_ALIGN constants
TAG_ALIGN_MATRIX = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
TAG_ALIGN_OFFSET = (0, 0, 0)

# XANIM SETTINGS
XANIM_VERSION = 3

def save(self, context, filepath, **kwargs):

    # check 'cos blender's a whiny shit
    obj = bpy.context.object # da object
    if not (obj := bpy.context.object):
        return "Error: No object selected!"
    if obj.type != 'ARMATURE':
        return "Error: Selected object must be an armature!"
    if not obj.animation_data:
        return "Error: Armature has no animation data!"
    
    # Pre-fetch context and scene properties
    scene = bpy.context.scene
    original_frame = scene.frame_current
    original_action = obj.animation_data.action

    # Process filepath
    try:
        directory, base_name, ext, filepath, filename_template = shared.process_filepath(filepath, target_format_key='target_format', default_format='XMODEL_BIN', **kwargs)
    except ValueError as e:
        shared.add_warning(str(e))
        return str(e)
    target_format = kwargs.get('target_format', 'XANIM_BIN').upper()

    # Get actions and pose bones
    actions = bpy.data.actions if kwargs.get('use_all_actions', False) else [obj.animation_data.action]
    pose_bones = bpy.context.selected_pose_bones if kwargs.get('use_selection', True) else obj.pose.bones

    # Framerate
    framerate = kwargs.get('use_framerate', 30) if kwargs.get('use_custom_framerate', False) else scene.render.fps
    frame_start = kwargs.get('frame_start', 1)
    frame_end = kwargs.get('frame_end', 250)
    use_frame_range_mode = kwargs.get('use_frame_range_mode', 'ACTION')

    # Precompute these too
    global_scale =  kwargs.get('global_scale', 1.0)
    use_all_actions = kwargs.get('use_all_actions', False)
    write_tag_align = kwargs.get('write_tag_align', False)
    use_notetracks = kwargs.get('use_notetracks', True)
    use_notetrack_file = kwargs.get('use_notetrack_file', False)
    use_notetrack_mode = kwargs.get('use_notetrack_mode', 'ACTION')

    # Update figured it out
    if kwargs.get('apply_unit_scale', True):
        global_scale = shared.apply_cm_to_inch_scale(kwargs.get('global_scale', 1.0))

    for index, action in enumerate(actions):
        # Setup action-specific file path
        if use_all_actions:
            filename = filename_template.substitute(action=action.name, base=base_name, number=index)
            action_filepath = os.path.join(directory, f"{filename}{ext}")
            obj.animation_data.action = action
        else:
            action_filepath = filepath

        # Initialize the animation with version, framerate, and pose bones as parts
        anim = XAnim.Anim()
        anim.version = 3
        anim.framerate = framerate
        anim.parts.extend(XAnim.PartInfo(bone.name) for bone in pose_bones)

        if write_tag_align:
            anim.parts.append(XAnim.PartInfo("TAG_ALIGN"))

        # Determine frame range
        if use_frame_range_mode == 'ACTION':
            frames = [kp.co[0] for fc in action.fcurves for kp in fc.keyframe_points]
            frame_start, frame_end = (min(frames), max(frames)) if frames else (0, 0)
        elif use_frame_range_mode == 'SCENE':
            frame_start, frame_end = scene.frame_start, scene.frame_end
        elif use_frame_range_mode == 'CUSTOM':
            frame_start, frame_end = self.frame_start, self.frame_end

        # Process frames
        for frame_num in range(int(frame_start), int(frame_end) + 1):
            bpy.context.scene.frame_set(frame_num)
            frame = XAnim.Frame(frame_num)
            for bone in pose_bones:
                offset = tuple(bone.head * global_scale)
                matrix = [tuple(row) for row in bone.matrix.to_3x3().transposed()]
                frame.parts.append(XAnim.FramePart(offset, matrix))
            
            # Write TAG_ALIGN if enabled
            if write_tag_align:
                frame.parts.append(XAnim.FramePart(TAG_ALIGN_OFFSET, TAG_ALIGN_MATRIX))
            
            anim.frames.append(frame)

        # Process notetracks
        if use_notetracks:
            if use_notetrack_mode == 'SCENE':
                markers = bpy.context.scene.timeline_markers
            elif use_notetrack_mode == 'ACTION':
                markers = action.pose_markers
            else:
                markers = []

            anim.notes.extend(XAnim.Note(marker.frame, marker.name) for marker in markers)

        # Metadata, everything is in shared
        metadata = shared.get_metadata_string(action_filepath)
        if target_format == 'XANIM_BIN':
            anim.WriteFile_Bin(action_filepath, header_message=metadata)
        else:
            anim.WriteFile_Raw(action_filepath, header_message=metadata, embed_notes=not use_notetrack_file)

    # Restore original state
    obj.animation_data.action = original_action
    bpy.context.scene.frame_set(original_frame)