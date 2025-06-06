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

import re, bpy, bmesh, array

from itertools import repeat

from . import shared as shared
from .PyCoD import xmodel as XModel

def _skip_notice(ob_name, mesh_name, notice):
    vargs = (ob_name, mesh_name, notice)
    print("\nSkipped object \"%s\" (mesh \"%s\"): %s" % vargs)

def uv_layer_is_empty(uv_layer):
	return all(_lyr.uv.length_squared == 0.0 for _lyr in uv_layer.data)

def mesh_triangulate(mesh, vertex_cleanup):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)

    if vertex_cleanup:
        bmesh.ops.split(bm, use_only_faces=True)

    bm.to_mesh(mesh)
    bm.free()

    mesh.update(calc_edges=True)

def gather_exportable_objects(self, context, use_selection, use_armature, use_armature_filter=True, verbose=False):

    armature = None
    objs = []
    errored_objs = []
    secondary_objects = []

    # Use active armature if applicable
    if context.active_object and context.active_object.type == 'ARMATURE':
        armature = context.active_object

    # Disable filter if not using armature
    if not use_armature:
        use_armature_filter = False

    def test_armature_filter(obj):
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object == armature:
                return True
        return False

    # Select objects from context
    objects = context.selected_objects if use_selection else bpy.data.objects

    if verbose:
        print(f"[DEBUG] Checking {len(objects)} object(s):")

    for obj in objects:
        if verbose:
            print(f"[DEBUG] Checking '{obj.name}'...")

        if obj.type == 'ARMATURE' and use_armature and len(obj.data.bones) > 0:
            if armature is None or obj == context.active_object:
                armature = obj
            continue

        if obj.type != 'MESH':
            if verbose:
                print(f"[SKIP] '{obj.name}' is type '{obj.type}', not a MESH.")
            errored_objs.append(obj)
            continue

        # Check for materials
        if len(obj.material_slots) < 1:
            shared.add_warning(f"Object '{obj.name}' has no materials. Skipping.")
            if verbose:
                print(f"[WARN] '{obj.name}' has no materials.")
            errored_objs.append(obj)
            continue

        # Check for UVs
        uv_layer = obj.data.uv_layers.active
        if not uv_layer or uv_layer_is_empty(uv_layer):
            shared.add_warning(f"Object '{obj.name}' has no valid UVs. Skipping.")
            if verbose:
                print(f"[WARN] '{obj.name}' has no valid UVs.")
            errored_objs.append(obj)
            continue

        # Handle armature filtering
        if use_armature_filter:
            if armature is None:
                secondary_objects.append(obj)
            elif test_armature_filter(obj):
                objs.append(obj)
            continue

        objs.append(obj)

    # Handle deferred objects if filter is active and armature found
    if use_armature_filter and armature:
        for obj in secondary_objects:
            if test_armature_filter(obj):
                objs.append(obj)

    if verbose:
        print(f"[DEBUG] Found {len(objs)} exportable object(s).")

    return armature, objs

def sanitize_material_name(name):
    # Replace non-alphanumeric characters and consecutive underscores with a single underscore
    name = re.sub(r'[^a-z0-9]+', '_', name.lower())
    name = re.sub(r'_+', '_', name).strip('_')
    return name

def material_gen_image_dict(material):
    out = {'material_name': sanitize_material_name(material.name)} if material else {}
    print( material.name )
    return out

class ExportMesh(object):
    '''
    Internal class used for handling the conversion of mesh data into
    a PyCoD compatible format
    '''
    __slots__ = ('mesh', 'object', 'matrix', 'weights', 'materials')

    def __init__(self, obj, mesh, model_materials):
        self.mesh = mesh
        self.object = obj
        self.matrix = obj.matrix_world
        self.weights = [[] for i in repeat(None, len(mesh.vertices))]

        # Used to map mesh materials indices to our model material indices
        self.materials = []
        self.gen_material_indices(model_materials)

    def clear(self):
        self.mesh.user_clear()
        bpy.data.meshes.remove(self.mesh)

    # find places where we have too many weights and remove the lowest weights, then renormalize the total
    def fix_too_many_weights(self):
        b_any_bad  = False
        for v in self.weights:
            if len(v) > 15:
                b_any_bad  = True
                v.sort(key=lambda x: -x[1])
                del v[15:]
                total = sum(w for _,w in v)
                v[:] = [(b,w/total) for b,w in v] if total else v[:15]
        return b_any_bad

    def add_weights(self, bone_table, weight_min_threshold=0.0):
        if not self.object.vertex_groups:
            self.weights = [[(0, 1.0)] for _ in range(len(self.weights))]
            return

        # bone index mapping
        group_map = [bone_table.index(g.name) if g.name in bone_table else None 
                    for g in self.object.vertex_groups]

        for v_idx, vert in enumerate(self.mesh.vertices):
            self.weights[v_idx].extend(
                (group_map[g.group], g.weight)
                for g in vert.groups
                if group_map[g.group] is not None and g.weight >= weight_min_threshold
            )

        # default for empty weights
        for weights in self.weights:
            if not weights:
                weights.append((0, 1.0))

        if self.fix_too_many_weights():
            print("WARNING: Some vertices exceeded weight limit - trimmed lowest weights")

    def gen_material_indices(self, model_materials):
        self.materials = [None] * len(self.mesh.materials)
        for material_index, material in enumerate(self.mesh.materials):
            if material in model_materials:
                self.materials[material_index] = model_materials.index(material) # nopep8
            else:
                self.materials[material_index] = len(model_materials)
                model_materials.append(material)

    def to_xmodel_mesh(self, use_vtx_cols, use_alpha, use_alpha_mode, global_scale):
        mesh = XModel.Mesh(self.mesh.name)

        if self.mesh.has_custom_normals:
            if bpy.app.version < (4, 1, 0):
                self.mesh.calc_normals_split()
            else:
                clnors = array.array('f', [0.0] * (len(self.mesh.loops) * 3))
                self.mesh.loops.foreach_get('normal', clnors)
                self.mesh.normals_split_custom_set(tuple(zip(*(iter(clnors),) * 3)))
        else:
            if bpy.app.version < (4, 1, 0):
                self.mesh.calc_normals()
            else:
                self.mesh.calc_normals(mesh) # Just takes mesh instead

        uv_layer = self.mesh.uv_layers.active
        vc_layer = self.mesh.vertex_colors.active if use_vtx_cols else None

        # Get the vertex layer to use for alpha
        vca_layer = None
        if use_alpha:
            if use_alpha_mode == 'PRIMARY':
                vca_layer = vc_layer
            elif use_alpha_mode == 'SECONDARY':
                for layer in self.mesh.vertex_colors:
                    if layer is not vc_layer:
                        vca_layer = layer
                        break # Only need the first one we can find

        # Apply transformation matrix to vertices
        for vert_index, vert in enumerate(self.mesh.vertices):
            mesh_vert = XModel.Vertex()
            # Apply global scale FIRST, then matrix transform
            scaled_pos = vert.co * global_scale
            transformed_pos = self.matrix @ scaled_pos
            mesh_vert.offset = tuple(transformed_pos)
            mesh_vert.weights = self.weights[vert_index]
            mesh.verts.append(mesh_vert)

        # Extract 3x3 rotation matrix from transformation matrix (ignoring translation)
        normal_transform = self.matrix.to_3x3()
        invalid_mtl_idxs_encountered = False

        for polygon in self.mesh.polygons:
            face = XModel.Face(0, 0)

            if polygon.material_index >= self.materials.__len__():
                invalid_mtl_idxs_encountered = True
                continue

            face.material_id = self.materials[polygon.material_index]

            for i, loop_index in enumerate(polygon.loop_indices):
                loop = self.mesh.loops[loop_index]

                # Get UV coordinates
                uv = uv_layer.data[loop_index].uv

                # Get vertex colours (with optional alpha channel)
                if vca_layer is not None:
                    vert_color = vca_layer.data[loop_index].color
                    rgba = (vert_color[0], vert_color[1], vert_color[2], vert_color[3] if len(vert_color) > 3 else .0)
                elif vc_layer is not None:
                    vert_color = vc_layer.data[loop_index].color
                    rgba = (vert_color[0], vert_color[1], vert_color[2], vert_color[3] if len(vert_color) > 3 else .0)
                else:
                    rgba = (.0, .0, .0, .0)

                # Apply transformation to normal
                transformed_normal = normal_transform @ loop.normal
                transformed_normal.normalize()  # Ensure normal stays unit-length

                vert = XModel.FaceVertex(
                    loop.vertex_index,
                    transformed_normal,  # Use transformed normal
                    rgba,
                    (uv.x, 1.0 - uv.y)
                )
                face.indices[i] = vert

            # Fix winding order
            face.indices[1], face.indices[2] = face.indices[2], face.indices[1]

            mesh.faces.append(face)

        if invalid_mtl_idxs_encountered:
            shared.add_warning(f"Skipped one or more polys on '{self.mesh.name}'; material indices were invalid.")

        return mesh
    
def mark_cosmetic(bone, name):
    bone.cosmetic = name in tbl_cosmetics

tbl_cosmetics = [
    "j_teeth_lower", "j_teeth_upper", "j_tongue", "j_brow_a01", "j_brow_a01_le", "j_brow_a01_ri", "j_brow_a03_le", "j_brow_a03_ri",
    "j_brow_a05_le", "j_brow_a05_ri", "j_brow_a07_le", "j_brow_a07_ri", "j_brow_a09_le", "j_brow_a09_ri", "j_brow_b01_le",
    "j_brow_b01_ri", "j_cheek_a03_le", "j_cheek_a01_ri", "j_cheek_a01_le", "j_brow_b05_ri", "j_brow_b05_le", "j_brow_b03_ri", "j_brow_b03_le"
    , "j_cheek_b03_ri", "j_cheek_b03_le", "j_cheek_b01_ri", "j_cheek_b01_le", "j_cheek_a07_ri", "j_cheek_a07_le", "j_cheek_a05_ri", "j_cheek_a05_le", "j_cheek_a03_ri"
    , "j_cheek_c03_le", "j_cheek_c01_ri", "j_cheek_c01_le", "j_cheek_b09_ri", "j_cheek_b09_le", "j_cheek_b07_ri", "j_cheek_b07_le", "j_cheek_b05_ri", "j_cheek_b05_le"
    , "j_chin_jaw", "j_chin_a03_ri", "j_chin_a03_le", "j_chin_a01_ri", "j_chin_a01_le", "j_chin_a01", "j_cheek_c05_ri", "j_cheek_c05_le", "j_cheek_c03_ri"
    , "j_eye_a03_le", "j_eye_a01_ri", "j_eye_a01_le", "j_ear_b01_ri", "j_ear_b01_le", "j_ear_a03_ri", "j_ear_a03_le", "j_ear_a01_ri", "j_ear_a01_le"
    , "j_eye_b01_ri", "j_eye_b01_le", "j_eye_a09_ri", "j_eye_a09_le", "j_eye_a07_ri", "j_eye_a07_le", "j_eye_a05_ri", "j_eye_a05_le", "j_eye_a03_ri"
    , "j_eyelid_bot_05_le", "j_eyelid_bot_03_ri", "j_eyelid_bot_03_le", "j_eyelid_bot_01_ri", "j_eyelid_bot_01_le", "j_eye_b05_ri", "j_eye_b05_le", "j_eye_b03_ri", "j_eye_b03_le"
    , "j_forehead_a01_le", "j_forehead_a01", "j_eyelid_top_07_ri", "j_eyelid_top_07_le", "j_eyelid_top_05_ri", "j_eyelid_top_05_le", "j_eyelid_top_03_ri", "j_eyelid_top_03_le", "j_eyelid_bot_05_ri"
    , "j_forehead_b05_le", "j_forehead_b03_ri", "j_forehead_b03_le", "j_forehead_b01_ri", "j_forehead_b01_le", "j_forehead_b01", "j_forehead_a03_ri", "j_forehead_a03_le", "j_forehead_a01_ri"
    , "j_jaw_a01_ri", "j_jaw_a01_le", "j_jaw_a01", "j_jaw", "j_forehead_b09_ri", "j_forehead_b09_le", "j_forehead_b07_ri", "j_forehead_b07_le", "j_forehead_b05_ri"
    , "j_jaw_b01", "j_jaw_a09_ri", "j_jaw_a09_le", "j_jaw_a07_ri", "j_jaw_a07_le", "j_jaw_a05_ri", "j_jaw_a05_le", "j_jaw_a03_ri", "j_jaw_a03_le"
    , "j_jaw_b09_le", "j_jaw_b07_ri", "j_jaw_b07_le", "j_jaw_b05_ri", "j_jaw_b05_le", "j_jaw_b03_ri", "j_jaw_b03_le", "j_jaw_b01_ri", "j_jaw_b01_le"
    , "j_jaw_c07_le", "j_jaw_c05_ri", "j_jaw_c05_le", "j_jaw_c03_ri", "j_jaw_c03_le", "j_jaw_c01_ri", "j_jaw_c01_le", "j_jaw_c01", "j_jaw_b09_ri"
    , "j_mouth_a07_le", "j_mouth_a05_ri", "j_mouth_a05_le", "j_mouth_a03_ri", "j_mouth_a03_le", "j_mouth_a01_ri", "j_mouth_a01_le", "j_mouth_a01", "j_jaw_c07_ri"
    , "j_mouth_c01", "j_mouth_b03_ri", "j_mouth_b03_le", "j_mouth_b01_ri", "j_mouth_b01_le", "j_mouth_b01", "j_mouth_a09_ri", "j_mouth_a09_le", "j_mouth_a07_ri"
    , "j_mouth_inner_le", "j_mouth_c07_ri", "j_mouth_c07_le", "j_mouth_c05_ri", "j_mouth_c05_le", "j_mouth_c03_ri", "j_mouth_c03_le", "j_mouth_c01_ri", "j_mouth_c01_le"
    , "j_nose_a01_le", "j_nose_a01", "j_mouth_innerup_ri", "j_mouth_innerup_le", "j_mouth_innerup", "j_mouth_innerlow_ri", "j_mouth_innerlow_le", "j_mouth_innerlow", "j_mouth_inner_ri"
    , "j_nose_c03_ri", "j_nose_c03_le", "j_nose_c01_ri", "j_nose_c01_le", "j_nose_c01", "j_nose_b01_ri", "j_nose_b01_le", "j_nose_b01", "j_nose_a01_ri"
    , "j_uppercheek_a08_le", "j_uppercheek_a07_ri", "j_uppercheek_a07_le", "j_uppercheek_a05_ri", "j_uppercheek_a05_le", "j_uppercheek_a03_ri", "j_uppercheek_a03_le", "j_uppercheek_a01_ri", "j_uppercheek_a01_le"
    , "j_uppercheek_a09_ri", "j_uppercheek_a09_le", "j_uppercheek_a08_ri"
]

def save(self, context, filepath, **kwargs):
    
    # Set active object if none selected
    if not context.object or context.object.type != 'MESH':
        mesh_objects = [obj for obj in context.view_layer.objects if obj.type == 'MESH']
        if mesh_objects:
            context.view_layer.objects.active = mesh_objects[0]
        else:
            return "No mesh objects to export"

    last_mode = context.object.mode

    # Disabled parameter
    use_armature_pose = False  
    
    # Precompute
    global_scale =  kwargs.get('global_scale', 1.0)
    apply_modifiers = kwargs.get('apply_modifiers', True)
    use_vertex_cleanup = kwargs.get('use_vertex_cleanup', True)
    use_vertex_colors_alpha = kwargs.get('use_vertex_colors_alpha', False)
    use_vertex_colors_alpha_mode = kwargs.get('use_vertex_colors_alpha_mode', 'PRIMARY')

    try:
        directory, base_name, ext, filepath, filename_template = shared.process_filepath(filepath, target_format_key='target_format', default_format='XMODEL_BIN', **kwargs)
    except ValueError as e:
        return shared(e)

    # Force bone tree update
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.object.mode_set(mode='OBJECT')

    # Get exportable objects
    armature, objects = gather_exportable_objects(self, context, kwargs.get('use_selection', False), kwargs.get('use_armature', True), False)
    if not objects:
        return "There are no objects to export"
    
    # Scale
    if kwargs.get('apply_unit_scale', True):
        global_scale = shared.apply_cm_to_inch_scale(kwargs.get('global_scale', 1.0))

    use_vtx_cols = kwargs.get("format_version") < 6

    # Setup xmodel thing
    model = XModel.Model("$export")
    meshes = []
    materials = []
    obj_dupes_to_delete = []

    for obj in objects:
        mod_states = []
        for mod in obj.modifiers:
            mod_states.append(mod.show_viewport)
            if mod.type == 'ARMATURE':
                mod.show_viewport = (mod.show_viewport and use_armature_pose)
            else:
                mod.show_viewport = (mod.show_viewport and apply_modifiers)

        try:
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_obj = obj.evaluated_get( depsgraph )
            obj_dupes_to_delete.append( evaluated_obj )
            mesh = evaluated_obj.to_mesh()
        except RuntimeError as _e:
            shared.add_warning( f"RUNTIME ERROR getting object \"{ obj.name }\"'s mesh:\n{ _e }" )
            continue

        # Triangulate and clean up mesh
        mesh_triangulate(mesh, use_vertex_cleanup)

        # Normal calculations are done automatically in Blender 4.1+ -Proventus
        if bpy.app.version < (4, 1, 0):
            mesh.calc_normals_split()

        # Restore modifier states
        for i, mod in enumerate(obj.modifiers):
            mod.show_viewport = mod_states[i]

        if len(mesh.vertices) < 3:
            _skip_notice(obj.name, mesh.name, "Less than 3 vertices")
            mesh.user_clear()
            bpy.data.meshes.remove(mesh)

        meshes.append(ExportMesh(obj, mesh, materials))

    if kwargs.get('use_armature', True) and armature is not None:
        armature_matrix = armature.matrix_world
        bone_table = [b.name for b in armature.data.bones]
        for bone_index, bone in enumerate(armature.data.bones):
            if bone.parent is not None:
                bone_parent_index = bone_table.index(bone.parent.name) if bone.parent.name in bone_table else 0
            else:
                bone_parent_index = -1

            model_bone = XModel.Bone(bone.name, bone_parent_index)
            mark_cosmetic(model_bone, bone.name) # Mark cosmetic bones, might revisit

            if bone_index == 0:
                matrix = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
                offset = (0, 0, 0)
            else:
                mtx = (armature_matrix @ bone.matrix_local).to_3x3().transposed()
                matrix = [tuple(mtx[0]), tuple(mtx[1]), tuple(mtx[2])]
                offset = (armature_matrix @ bone.head_local) * global_scale

            model_bone.offset = tuple(offset)
            model_bone.matrix = matrix
            model.bones.append(model_bone)
    else:
        # create a dummy bone if no armature
        dummy_bone_name = "tag_origin"
        dummy_bone = XModel.Bone(dummy_bone_name, -1)
        dummy_bone.offset = (0, 0, 0)
        dummy_bone.matrix = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        model.bones.append(dummy_bone)
        bone_table = [dummy_bone_name]

    # Weight Threshold
    weight_threshold = 0.0 if not kwargs.get('use_weight_min', False) else kwargs.get('use_weight_min_threshold', 0.010097)

    # Generate bone weights for verts
    for mesh in meshes:
        mesh.add_weights(bone_table, weight_threshold)
        model.meshes.append(
            mesh.to_xmodel_mesh(
                use_vtx_cols=use_vtx_cols,
                use_alpha=use_vertex_colors_alpha,
                use_alpha_mode=use_vertex_colors_alpha_mode,
                global_scale=global_scale
            )
        )

    # materials
    missing_count = 0
    for material in materials:
        imgs = material_gen_image_dict(material)
        try:
            name = sanitize_material_name(material.name)
        except:
            name = f"material{missing_count}"
            missing_count += 1

        mtl = XModel.Material(name, "Lambert", imgs)
        model.materials.append(mtl)

    # output
    header_msg = shared.get_metadata_string(filepath)
    if kwargs['target_format'] == 'XMODEL_BIN':
        model.WriteFile_Bin(filepath, version=int(kwargs['version']), header_message=header_msg)
    else:
        model.WriteFile_Raw(filepath, version=int(kwargs['version']), header_message=header_msg)

    # Restore mode and update view
    bpy.ops.object.mode_set(mode=last_mode)
    context.view_layer.update()