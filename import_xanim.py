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

from . import shared as shared
from .PyCoD import xanim as XAnim
from mathutils import Matrix, Vector

def find_active_armature(context):
    obj = context.active_object
    return obj.find_armature() if obj and obj.type != 'ARMATURE' else obj

def load(self, context, apply_unit_scale=False, **keywords):
    if not (armature := find_active_armature(context)):
        return "No active armature found"
    
    keywords['use_notetrack_file'] = keywords.pop('use_notetracks', True)
    apply_unit_scale and keywords.update(global_scale=keywords.get('global_scale', 1.0) * shared.calculate_unit_scale_factor(context.scene))
    
    path = os.path.dirname(keywords['filepath'])
    for f in self.files:
        load_anim(self, context, armature, **{**keywords, 'filepath': os.path.join(path, f.name)})

def load_anim(self, context, armature, filepath, global_scale=1.0, use_notetracks=True, 
             use_notetrack_file=True, fps_scale_type='ACTION', fps_scale_target_fps=30, 
             update_frame_range=True, update_scene_fps=True):

    anim = XAnim.Anim()
    ext = os.path.splitext(filepath)[-1].upper()
    anim.LoadFile_Bin(filepath) if ext == '.XANIM_BIN' else anim.LoadFile_Raw(filepath, use_notetrack_file)

    scene = context.scene
    ob = armature

    # Create action using the filename (without extension)
    action = bpy.data.actions.new(os.path.basename(filepath).rsplit('.', 1)[0])
    ob.animation_data_create().action = action
    ob.animation_data.action.use_fake_user = True

    # What the variable says
    if update_scene_fps:
        scene.render.fps = int(anim.framerate)
        
    frame_scale = fps_scale_target_fps / anim.framerate if fps_scale_type == 'CUSTOM' else 1.0

    # Crazy (I was crazy once...)
    if update_frame_range:
        frames = [f.frame for f in anim.frames]
        scene.frame_start = int(round(min(frames) * frame_scale))
        scene.frame_end = int(round(max(frames) * frame_scale))

    # Bone mapping
    part_indices = {p.name.lower(): i for i, p in enumerate(anim.parts)}
    pose_bones = ob.pose.bones
    
    bone_map = {
        bone.name: {
            'bone': bone,
            'part_index': part_indices[bone_name_lower], # To avoid calling it twice
            'matrix_local': bone.bone.matrix_local,
            'parent': None
        }
        for bone in pose_bones if (bone_name_lower := bone.name.lower()) in part_indices
    }

    # Set parent relationships
    for bone_data in bone_map.values():
        parent = bone_data['bone'].parent
        if parent and (parent_name := parent.name) in bone_map:
            bone_data['parent'] = bone_map[parent_name]

    # Keyframe insertion
    for frame in anim.frames:
        f = frame.frame * frame_scale
        for bone_data in bone_map.values():
            parent_matrix = bone_data['parent']['matrix'] if bone_data['parent'] else Matrix()
            part = frame.parts[bone_data['part_index']]
            
            mtx = Matrix(part.matrix).transposed().to_4x4()
            mtx.translation = Vector(part.offset) * global_scale
            bone_data['matrix'] = mtx
            
            bone = bone_data['bone']
            bone.matrix_basis = calc_basis(bone, mtx, parent_matrix, bone_data['matrix_local'])
            bone.keyframe_insert("location", frame=f)
            bone.keyframe_insert("rotation_quaternion", frame=f)

    # Handle Notetracks (They aren't visible as markers)
    if use_notetracks:
        markers = action.pose_markers
        for note in anim.notes:
            markers.new(note.string).frame = int(note.frame * frame_scale)

    context.view_layer.update()
    return anim

def get_mat_rest(pose_bone, parent_pose_matrix, parent_rest_matrix):
    bone = pose_bone.bone
    
    if not pose_bone.parent:
        return bone.matrix_local.copy(), bone.matrix_local.copy()

    # Calculate bone's offset matrix
    mat_offs = bone.matrix.to_4x4()
    mat_offs.translation = bone.head + Vector((0, bone.parent.length, 0))

    # Determine if rotation and scale should be inherited
    rot_off = not bone.use_inherit_rotation
    scl_off = not bone.inherit_scale

    # Rotation/scale matrix calculation
    mat_rotscale = (
        parent_rest_matrix @ mat_offs if rot_off and scl_off else
        Matrix.Diagonal([v.length for v in parent_pose_matrix.to_3x3().col]).to_4x4() @ parent_rest_matrix @ mat_offs if rot_off else
        parent_pose_matrix.normalized() @ mat_offs if scl_off else
        parent_pose_matrix @ mat_offs
    )

    # Location matrix calculation
    mat_loc = (
        Matrix.Translation(parent_pose_matrix @ mat_offs.translation) @ parent_pose_matrix.to_3x3().to_4x4()
        if not bone.use_local_location else
        parent_pose_matrix @ mat_offs if rot_off or scl_off else
        mat_rotscale.copy()
    )

    return mat_rotscale, mat_loc

def calc_basis(pose_bone, target, parent_pose, parent_rest):
    rot, loc = get_mat_rest(pose_bone, parent_pose, parent_rest)
    basis = (target.inverted() @ rot).transposed().to_4x4()
    basis.translation = loc.inverted() @ target.translation
    return basis