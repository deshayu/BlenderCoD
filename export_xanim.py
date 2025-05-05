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
import os
import bpy

from . import shared
from string import Template
from .PyCoD import xanim as XAnim

# Pre-define TAG_ALIGN constants
TAG_ALIGN_MATRIX = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
TAG_ALIGN_OFFSET = (0, 0, 0)

# XANIM SETTINGS
XANIM_VERSION = 3

def save(self, context,
         filepath,
         target_format='XANIM_BIN',
         use_selection=True,
         global_scale=1.0,
         apply_unit_scale=False,
         use_all_actions=False,
         filename_format="%action",
         use_notetracks=True,
         use_notetrack_file=False,
         use_notetrack_mode='ACTION',
         use_frame_range_mode='ACTION',
         frame_start=1,
         frame_end=250,
         use_custom_framerate=False,
         use_framerate=30,
         write_tag_align=False): # Added this for TAG_ALIGN
    
    # Pre-fetch context and scene properties
    ob = bpy.context.object # da object
    scene = bpy.context.scene
    original_frame = scene.frame_current
    original_action = ob.animation_data.action
    
    # check 'cos blender's a whiny shit
    if not (ob := bpy.context.object):
        return "Error: No object selected!"
    if ob.type != 'ARMATURE':
        return "Error: Selected object must be an armature!"
    if not ob.animation_data:
        return "Error: Armature has no animation data!"

    # Still Don't know why the addon has this
    if apply_unit_scale:
        global_scale /= shared.calculate_unit_scale_factor(bpy.context.scene)

    # Precompute common values for framerate, filename template, and filepath handling
    framerate = use_framerate if use_custom_framerate else scene.render.fps
    filename_template = Template(filename_format)
    filename_template.delimiter = '%'

    # Get the file path and base name, ensuring it has the appropriate extension
    path = os.path.dirname(filepath) + os.sep
    base_name, ext = os.path.splitext(os.path.basename(filepath))

    # If no extension is provided, append the correct one based on target format
    if not ext:
        ext = '.xanim_bin' if target_format == 'XANIM_BIN' else '.xanim_export'
        filepath = f"{filepath}{ext}"

    # Precompute this to help if use_all_actions.
    target_format_lower = target_format.lower()

    # Get actions and pose bones
    actions = bpy.data.actions if use_all_actions else [ob.animation_data.action]
    pose_bones = bpy.context.selected_pose_bones if use_selection else ob.pose.bones

    for index, action in enumerate(actions):
        # Setup action-specific file path
        if use_all_actions:
            filename = filename_template.substitute(action=action.name, base=base_name, number=index)
            action_filepath = f"{path}{filename}.{target_format_lower}"
            ob.animation_data.action = action
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
    ob.animation_data.action = original_action
    bpy.context.scene.frame_set(original_frame)