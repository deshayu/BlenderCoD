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
import bmesh
import array
from mathutils import *
from math import *
from bpy_extras.image_utils import load_image
from mathutils import Vector

from . import shared as shared
from .PyCoD import xmodel as XModel


def get_armature_for_object(ob):
    '''
    Get the armature for a given object.
    If the object *is* an armature, the object itself is returned.
    '''
    if ob is None:
        return None

    if ob.type == 'ARMATURE':
        return ob

    return ob.find_armature()

def get_armature_modifier_for_object(ob):
    for mod in ob.modifiers:
        if mod.type == 'ARMATURE':
            return mod
    return None

def reassign_children(ebs, bone1, bone2):
    for child in bone2.children:
        kid = ebs[child.name]
        kid.parent = bone1

    ebs.remove(bone2)

def load(self, context,
         filepath,
         global_scale=1.0,
         apply_unit_scale=False,
         use_single_mesh=True,
         use_dup_tris=True,
         use_custom_normals=True,
         use_vertex_colors=True,
         use_armature=True,
         use_parents=True,
         use_image_search=True):

    # Apply unit conversion factor to the scale
    if apply_unit_scale:
        global_scale *= shared.calculate_unit_scale_factor(context.scene)

    target_scale = global_scale

    split_meshes = not use_single_mesh
    load_images = True

    scene = bpy.context.scene
    view_layer = bpy.context.view_layer
        
    # Load the model
    model_name = os.path.splitext(os.path.basename(filepath))[0]
    model = XModel.Model(model_name)

    ext = os.path.splitext(filepath)[1].upper()
    LoadModelFile = model.LoadFile_Bin if ext == '.XMODEL_BIN' else model.LoadFile_Raw
    LoadModelFile(filepath, split_meshes=split_meshes)

    # Materials
    materials = []

    for material in model.materials:
        mat = bpy.data.materials.get(material.name) or bpy.data.materials.new(name=material.name)
        materials.append(mat)

    # Meshes
    mesh_objs = []

    for sub_mesh in model.meshes:
        sub_mesh.name = f"{model.name}_mesh" if not split_meshes else sub_mesh.name
        mesh = bpy.data.meshes.new(sub_mesh.name)
        bm = bmesh.new()

        # Create layers
        uv_layer = bm.loops.layers.uv.new("UVMap")
        vert_color_layer = bm.loops.layers.color.new("Color") if use_vertex_colors else None

        # Add Verts
        for vert in sub_mesh.verts:
            bm.verts.new(Vector(vert.offset) * target_scale)
        bm.verts.ensure_lookup_table()

        # Lists
        dup_faces, dup_verts, used_faces, loop_normals = [], [], [], []
        dup_verts_mapping = [None] * len(sub_mesh.verts)
        material_usage_counts = [0] * len(materials)
        
        # Inner function used set up a bmesh tri's: normals, UVs, material, vertex colors
        def setup_tri(f):
            material_index = face.material_id
            f.material_index = material_index
            material_usage_counts[material_index] += 1

            for i, loop in enumerate(f.loops):
                v = face.indices[i]
                loop_normals.append(v.normal)

                # Flip UV Y-coordinate
                loop[uv_layer].uv = Vector((v.uv[0], 1.0 - v.uv[1]))

                if use_vertex_colors:
                    loop[vert_color_layer] = v.color

            used_faces.append(face)

        unused_faces = []

        vert_count = len(sub_mesh.verts)

        for face_index, face in enumerate(sub_mesh.faces):
            # Fix winding order by swapping indices 1 and 2
            face.indices[1], face.indices[2] = face.indices[2], face.indices[1]

            indices = [bm.verts[index.vertex] for index in face.indices]

            try:
                f = bm.faces.new(indices)
            except ValueError:
                unused_faces.append(face)

                if not face.isValid():
                    print(f"TRI {face_index} is invalid! {[index.vertex for index in face.indices]}")
                    continue

                for index in face.indices:
                    vert = index.vertex
                    if dup_verts_mapping[vert] is None:
                        dup_verts_mapping[vert] = len(dup_verts) + vert_count
                        dup_verts.append(sub_mesh.verts[vert])
                    index.vertex = dup_verts_mapping[vert]

                dup_faces.append(face)
            else:
                setup_tri(f)

        # Remove the unused tris so they aren't accidentally used later
        for face in unused_faces:
            sub_mesh.faces.remove(face)

        if use_dup_tris:
            # Add duplicate verts
            for vert in dup_verts:
                bm.verts.new(Vector(vert.offset) * target_scale)
            bm.verts.ensure_lookup_table()

            # Add duplicate faces
            for face in dup_faces:
                indices = [bm.verts[index.vertex] for index in face.indices]
                try:
                    f = bm.faces.new(indices)
                except ValueError:
                    pass  # skip duplicates of duplicates
                else:
                    setup_tri(f)

        # Vertex Weights
        deform_layer = bm.verts.layers.deform.new()
        for vert_index, vert in enumerate(sub_mesh.verts):
            for bone, weight in vert.weights:
                bm.verts[vert_index][deform_layer][bone] = weight

        if use_dup_tris:
            offset = len(sub_mesh.verts)
            for vert_index, vert in enumerate(dup_verts):
                for bone, weight in vert.weights:
                    bm.verts[vert_index + offset][deform_layer][bone] = weight

        # Assign Materials
        for mat in materials:
            mesh.materials.append(mat)

        bm.to_mesh(mesh)

        # For this mesh remove all materials that aren't used by its faces
        # material_index, material_usage_index must be tracked manually because
        # enumerate() doesn't compensate for the removed materials properly
        material_index = 0
        material_usage_index = 0
        for material in mesh.materials:
            if material_usage_counts[material_usage_index] == 0:
                # Note: update_data must be True, otherwise - after the first
                #  material is removed, the indices are invalidated
                mesh.materials.pop(index=material_index)
            else:
                material_index += 1
            material_usage_index += 1

        if use_custom_normals:
            if bpy.app.version >= (4, 1, 0): #~ Use old method on versions older than 4.1+
                mesh.normals_split_custom_set(loop_normals)
            else:
                mesh.create_normals_split()

            mesh.validate(clean_customdata=False)

            clnors = array.array('f', [0.0] * (len(mesh.loops) * 3))
            mesh.loops.foreach_get("normal", clnors)

            polygon_count = len(mesh.polygons)
            mesh.polygons.foreach_set("use_smooth", [True] * polygon_count)

            mesh.normals_split_custom_set(tuple(zip(*(iter(clnors),) * 3)))

            if bpy.app.version < (4, 1, 0):
                mesh.use_auto_smooth = True

        else:
            mesh.validate()

            polygon_count = len(mesh.polygons)
            mesh.polygons.foreach_set("use_smooth", [True] * polygon_count)
            if bpy.app.version >= (4, 1, 0):
                mesh.update() 
            else:
                mesh.calc_normals() 

        # Determine object name
        obj_name = f"{model.name}_{mesh.name}" if split_meshes else model.name

        # Create the model object and link it to the scene
        obj = bpy.data.objects.new(obj_name, mesh)
        mesh_objs.append(obj)

        scene.collection.objects.link(obj)
        view_layer.objects.active = obj

        # Create Vertex Groups
        # These automatically weight the verts based on the deform groups
        for bone in model.bones:
            obj.vertex_groups.new(name=bone.name.lower())

        # Assign the texture images to the current mesh (for Texture view)
        if load_images:
            # Build a material_id to Blender image map
            material_image_map = [None] * len(model.materials)
            for index, material in enumerate(model.materials):
                if 'color' in material.images:
                    color_map = material.images['color']
                    if color_map in bpy.data.images:
                        material_image_map[index] = bpy.data.images[color_map]

    if use_armature:
        armature = bpy.data.armatures.new(f"{model.name}_amt")
        armature.display_type = "STICK"

        skel_obj = bpy.data.objects.new(f"{model.name}_skel", armature)
        skel_obj.show_in_front = True

        # Link to scene and set active
        scene.collection.objects.link(skel_obj)
        view_layer.objects.active = skel_obj
        bpy.ops.object.mode_set(mode='EDIT')

        # Create bones
        for bone in model.bones:
            edit_bone = armature.edit_bones.new(bone.name.lower())
            edit_bone.use_local_location = False

            offset = Vector(bone.offset) * target_scale
            axis = Vector(bone.matrix[1]) * target_scale
            roll = Vector(bone.matrix[2])

            edit_bone.head = offset
            edit_bone.tail = offset + axis
            edit_bone.align_roll(roll)

            if bone.parent != -1 and self.use_parents:
                edit_bone.parent = armature.edit_bones[bone.parent]

        # HACK: Force the pose bone list for the armature to be rebuilt
        bpy.ops.object.mode_set(mode='OBJECT')

        # Add armature modifier to meshes
        for mesh_obj in mesh_objs:
            mesh_obj.parent = skel_obj
            mod = mesh_obj.modifiers.new('Armature Rig', 'ARMATURE')
            mod.object = skel_obj
            mod.use_bone_envelopes = False
            mod.use_vertex_groups = True