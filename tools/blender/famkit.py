"""famkit — shared Blender helpers for Feed a Monster! assets.

Load inside Blender (MCP or `blender -b -P`):

    import sys, importlib
    sys.path.insert(0, "/Users/malik/rob/tools/blender")
    import famkit; importlib.reload(famkit)

Conventions (verified against Roblox, see docs/DECISIONS.md):
  * 1 Blender unit = 1 stud. Z up. Creatures FACE -Y (arrives in Roblox facing -Z).
  * Vertex colours multiply Part.Color in Roblox, so paint GREYSCALE shading/detail and
    let the genome tint it. Fixed-colour parts (eye whites, pupils) paint real colour and
    are tinted white.
  * Skinned parts bind to bones BY NAME inside their assembly, so every family skeleton
    uses the same socket names and a part authored on one rig binds to any rig.
"""

import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = "/Users/malik/rob"
BUILD = os.path.join(ROOT, "art", "build")


# ═══ SCENE ════════════════════════════════════════════════════════════════════

def reset_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.metaballs, bpy.data.curves, bpy.data.materials):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def collection(name):
    c = bpy.data.collections.get(name)
    if not c:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
    return c


def mesh_object(name, bm_or_mesh, collection_=None):
    if isinstance(bm_or_mesh, bmesh.types.BMesh):
        me = bpy.data.meshes.new(name)
        bm_or_mesh.to_mesh(me)
        bm_or_mesh.free()
    else:
        me = bm_or_mesh
        me.name = name
    obj = bpy.data.objects.new(name, me)
    link(obj, collection_)
    return obj


def evaluated_copy(obj, name=None):
    """Bake every modifier into a fresh mesh without bpy.ops (works headless)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    me.transform(obj.matrix_world)
    out = bpy.data.objects.new(name or obj.name, me)
    link(out)
    return out


def apply_modifiers(obj):
    new = evaluated_copy(obj, obj.name + "_tmp")
    old_name = obj.name
    bpy.data.objects.remove(obj, do_unlink=True)
    new.name = old_name
    new.data.name = old_name
    return new


# ═══ ORGANIC SHAPES ═══════════════════════════════════════════════════════════

def metaball_mesh(name, elements, resolution=0.06, threshold=0.6, voxel=None, smooth_iters=4, target_tris=None):
    """Blobby union of ellipsoids/capsules/boxes -> clean mesh.

    elements: dicts {type: BALL|ELLIPSOID|CAPSULE|CUBE, co, radius, size(x,y,z), rot(euler deg),
              stiffness, negative}
    """
    mb = bpy.data.metaballs.new(name + "_mb")
    mb.resolution = resolution
    mb.render_resolution = resolution
    mb.threshold = threshold
    for e in elements:
        el = mb.elements.new(type=e.get("type", "ELLIPSOID"))
        el.co = Vector(e["co"])
        el.radius = e.get("radius", 1.0)
        sx, sy, sz = e.get("size", (1.0, 1.0, 1.0))
        el.size_x, el.size_y, el.size_z = sx, sy, sz
        el.stiffness = e.get("stiffness", 2.0)
        el.use_negative = e.get("negative", False)
        if "rot" in e:
            from mathutils import Euler
            el.rotation = Euler([math.radians(a) for a in e["rot"]]).to_quaternion()
    mbo = bpy.data.objects.new(name + "_mbo", mb)
    link(mbo)
    bpy.context.view_layer.update()
    obj = evaluated_copy(mbo, name)
    bpy.data.objects.remove(mbo, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    if voxel:
        obj = remesh(obj, voxel)
    if smooth_iters:
        obj = smooth(obj, smooth_iters)
    if target_tris:
        obj = decimate_to(obj, target_tris)
    shade_smooth(obj)
    return obj


def remesh(obj, voxel):
    m = obj.modifiers.new("Remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel
    m.adaptivity = 0.0
    return apply_modifiers(obj)


def smooth(obj, iterations=4, factor=0.5):
    m = obj.modifiers.new("Smooth", "SMOOTH")
    m.iterations = iterations
    m.factor = factor
    return apply_modifiers(obj)


def subdivide(obj, levels=1):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return apply_modifiers(obj)


def decimate_to(obj, target_tris):
    tris = triangle_count(obj)
    if tris <= target_tris:
        return obj
    m = obj.modifiers.new("Decimate", "DECIMATE")
    m.ratio = max(0.02, target_tris / tris)
    m.use_collapse_triangulate = True
    return apply_modifiers(obj)


def triangle_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def shade_smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True


def shade_flat(obj):
    for p in obj.data.polygons:
        p.use_smooth = False


def tube(name, points, radii, subsurf=2, sides_hint=None, voxel=None, target_tris=None):
    """Organic tube through `points` with per-point `radii` (Skin modifier + subsurf).

    Good for tails, legs, antennae, horns: continuous topology, no seams."""
    me = bpy.data.meshes.new(name)
    verts = [Vector(p) for p in points]
    edges = [(i, i + 1) for i in range(len(verts) - 1)]
    me.from_pydata(verts, edges, [])
    obj = bpy.data.objects.new(name, me)
    link(obj)
    skin = obj.modifiers.new("Skin", "SKIN")
    skin.use_smooth_shade = True
    for i, sv in enumerate(me.skin_vertices[0].data):
        r = radii[i]
        if isinstance(r, (int, float)):
            sv.radius = (r, r)
        else:
            sv.radius = tuple(r)
    me.skin_vertices[0].data[0].use_root = True
    if subsurf:
        ss = obj.modifiers.new("Subsurf", "SUBSURF")
        ss.levels = subsurf
        ss.render_levels = subsurf
    obj = apply_modifiers(obj)
    if voxel:
        obj = remesh(obj, voxel)
        obj = smooth(obj, 2)
    if target_tris:
        obj = decimate_to(obj, target_tris)
    shade_smooth(obj)
    return obj


def uv_sphere(name, center, radius, segments=24, rings=14, scale=(1, 1, 1), rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    from mathutils import Euler
    mat = Matrix.Translation(Vector(center)) @ Euler([math.radians(a) for a in rot]).to_matrix().to_4x4() \
        @ Matrix.Diagonal(Vector((*scale, 1.0)))
    bmesh.ops.transform(bm, matrix=mat, verts=bm.verts)
    obj = mesh_object(name, bm)
    shade_smooth(obj)
    return obj


def join(objs, name):
    """Join meshes into one object (keeps vertex colours / groups)."""
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    obj = mesh_object(name, bm)
    shade_smooth(obj)
    return obj


def transform(obj, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    from mathutils import Euler
    mat = Matrix.Translation(Vector(loc)) @ Euler([math.radians(a) for a in rot]).to_matrix().to_4x4() \
        @ Matrix.Diagonal(Vector((*scale, 1.0)))
    obj.data.transform(mat)
    obj.data.update()
    return obj


def mirror_x(obj, name):
    me = obj.data.copy()
    me.transform(Matrix.Diagonal(Vector((-1, 1, 1, 1))))
    me.flip_normals()
    out = bpy.data.objects.new(name, me)
    link(out)
    return out


def deform(obj, fn):
    """fn(Vector co) -> Vector co, applied to every vertex."""
    for v in obj.data.vertices:
        v.co = fn(v.co.copy())
    obj.data.update()
    return obj


# ═══ VERTEX COLOUR ════════════════════════════════════════════════════════════

def ensure_color_layer(obj, name="Col"):
    me = obj.data
    layer = me.color_attributes.get(name)
    if not layer:
        layer = me.color_attributes.new(name, "BYTE_COLOR", "CORNER")
    me.color_attributes.active_color = layer
    try:
        me.color_attributes.render_color_index = me.color_attributes.find(name)
    except Exception:
        pass
    return layer


def paint(obj, fn):
    """fn(co: Vector, normal: Vector) -> (r, g, b). Per-corner, uses vertex position/normal."""
    layer = ensure_color_layer(obj)
    me = obj.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            v = me.vertices[vi]
            r, g, b = fn(v.co, v.normal)
            layer.data[li].color = (r, g, b, 1.0)
    return obj


def solid_color(obj, rgb):
    return paint(obj, lambda co, n: rgb)


def bake_ao(obj, occluders=None, samples=24, distance=0.9, strength=0.55, floor_z=None, seed=7):
    """Cheap, good-looking ambient occlusion straight into vertex colours by raycasting.

    Multiplies into the existing colour. `occluders` are other objects that shadow this one
    (eg. the head shadows the body under the chin)."""
    rng = random.Random(seed)
    dirs = []
    while len(dirs) < samples:
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.05 < d.length <= 1.0:
            dirs.append(d.normalized())

    bm = bmesh.new()
    for o in [obj] + list(occluders or []):
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    if floor_z is not None:
        s = 40
        vs = [bm.verts.new((x, y, floor_z)) for x, y in ((-s, -s), (s, -s), (s, s), (-s, s))]
        bm.faces.new(vs)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()

    mw = obj.matrix_world
    nmat = mw.to_3x3().inverted().transposed()
    occl = []
    for v in obj.data.vertices:
        p = mw @ v.co
        n = (nmat @ v.normal).normalized()
        hits, total = 0.0, 0.0
        for d in dirs:
            if d.dot(n) < 0:
                d = -d
            w = d.dot(n)
            total += w
            loc, _, _, dist = bvh.ray_cast(p + n * 0.012, d, distance)
            if loc is not None:
                hits += w * (1.0 - dist / distance) ** 0.7
        occl.append(hits / total if total else 0.0)

    layer = ensure_color_layer(obj)
    me = obj.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            k = 1.0 - strength * occl[vi]
            c = layer.data[li].color
            layer.data[li].color = (c[0] * k, c[1] * k, c[2] * k, 1.0)
    return obj


# ═══ UVs (box projection, uniform texel density so tiling materials match) ════

def box_uv(obj, studs_per_tile=2.0):
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    s = 1.0 / studs_per_tile
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            uv[li].uv = (u * s, v * s)
    return obj


# ═══ ARMATURE + SKINNING ══════════════════════════════════════════════════════

def armature(name, bones):
    """bones: list of (name, head, tail, parent_or_None). Built without bpy.ops edit mode
    toggling where possible; edit mode is required by Blender for edit_bones."""
    ad = bpy.data.armatures.new(name)
    ao = bpy.data.objects.new(name, ad)
    link(ao)
    prev_active = bpy.context.view_layer.objects.active
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = ao
    ao.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for bname, head, tail, parent in bones:
        b = ad.edit_bones.new(bname)
        b.head = Vector(head)
        b.tail = Vector(tail)
        b.roll = 0.0
        if parent:
            b.parent = made[parent]
        made[bname] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = prev_active
    return ao


def bone_segments(arm):
    segs = {}
    for b in arm.data.bones:
        segs[b.name] = (arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)
    return segs


def _seg_dist(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared == 0 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length, t


def skin(obj, arm, bones, falloff=0.35, rigid=None, max_influences=4, custom=None):
    """Distance-based skin weights restricted to `bones`.

    rigid: bone name -> every vertex fully weighted to that bone (eyes, horns...).
    custom: fn(co) -> {bone: weight} overrides the distance model for that vertex when it
            returns a non-empty dict (used for jaw/cheek regions on bodies)."""
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    groups = {b: obj.vertex_groups.new(name=b) for b in (bones if not rigid else [rigid])}
    segs = bone_segments(arm)
    mw = obj.matrix_world
    for v in obj.data.vertices:
        if rigid:
            groups[rigid].add([v.index], 1.0, "REPLACE")
            continue
        p = mw @ v.co
        weights = custom(p) if custom else None
        if not weights:
            weights = {}
            for bname in bones:
                a, b = segs[bname]
                d, _ = _seg_dist(p, a, b)
                weights[bname] = 1.0 / (1e-4 + (d / falloff) ** 4)
        top = sorted(weights.items(), key=lambda kv: -kv[1])[:max_influences]
        total = sum(w for _, w in top) or 1.0
        for bname, w in top:
            if bname not in groups:
                groups[bname] = obj.vertex_groups.new(name=bname)
            if w / total > 0.01:
                groups[bname].add([v.index], w / total, "REPLACE")
    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = obj.modifiers.get("Armature") or obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return obj


# ═══ EXPORT ═══════════════════════════════════════════════════════════════════

def export_fbx(objs, filename):
    os.makedirs(BUILD, exist_ok=True)
    path = filename if os.path.isabs(filename) else os.path.join(BUILD, filename)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        add_leaf_bones=False,
        bake_anim=False,
        apply_scale_options="FBX_SCALE_ALL",
        mesh_smooth_type="FACE",
        colors_type="SRGB",
        use_armature_deform_only=False,
    )
    return path


# ═══ LOOKING AT THINGS ════════════════════════════════════════════════════════

def vcol_material():
    """Viewport/preview material that shows vertex colours × a tint."""
    mat = bpy.data.materials.get("FAM_VCol")
    if mat:
        return mat
    mat = bpy.data.materials.new("FAM_VCol")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    nt.links.new(attr.outputs[0], mix.inputs[6])
    obj_info = nt.nodes.new("ShaderNodeObjectInfo")
    nt.links.new(obj_info.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    return mat


def preview_tint(obj, rgb):
    """Set object colour (drives the preview material's tint, like Part.Color in Roblox)."""
    obj.color = (rgb[0], rgb[1], rgb[2], 1.0)
    mat = vcol_material()
    if not obj.data.materials:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat
    return obj


def look_setup(target=(0, 0, 1), distance=7.0, yaw=-35, pitch=12, lens=50):
    """Point the active 3D viewport + scene camera at the creature for screenshots."""
    scene = bpy.context.scene
    cam = scene.camera
    if not cam:
        cam_data = bpy.data.cameras.new("PreviewCam")
        cam = bpy.data.objects.new("PreviewCam", cam_data)
        link(cam)
        scene.camera = cam
    cam.data.lens = lens
    t = Vector(target)
    yr, pr = math.radians(yaw), math.radians(pitch)
    offset = Vector((math.sin(yr) * math.cos(pr), -math.cos(yr) * math.cos(pr), math.sin(pr))) * distance
    cam.location = t + offset
    direction = t - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"
                    r3d = space.region_3d
                    r3d.view_perspective = "CAMERA"
    return cam


def render_png(path, res=(900, 900), engine=None):
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    scene.render.film_transparent = False
    if engine:
        try:
            scene.render.engine = engine
        except TypeError:
            pass
    bpy.ops.render.render(write_still=True)
    return path


# ═══ PREVIEW STUDIO (renders I can actually look at) ══════════════════════════

def preview_studio(floor_color=(0.93, 0.95, 0.9)):
    scene = bpy.context.scene
    if "PreviewFloor" not in bpy.data.objects:
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
        floor = mesh_object("PreviewFloor", bm)
        mat = bpy.data.materials.new("PreviewFloorMat")
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (*floor_color, 1)
        bsdf.inputs["Roughness"].default_value = 0.9
        floor.data.materials.append(mat)
    for name, energy, rot, size in (
        ("KeyLight", 4.0, (math.radians(50), 0, math.radians(-35)), 0.08),
        ("FillLight", 1.2, (math.radians(65), 0, math.radians(140)), 0.3),
    ):
        if name not in bpy.data.objects:
            ld = bpy.data.lights.new(name, "SUN")
            ld.energy = energy
            ld.angle = size
            lo = bpy.data.objects.new(name, ld)
            link(lo)
            lo.rotation_euler = rot
    world = scene.world or bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.62, 0.74, 0.86, 1)
    bg.inputs[1].default_value = 0.9
    engines = [i.identifier for i in scene.render.bl_rna.properties["engine"].enum_items]
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    return scene.render.engine


def render_views(path, target=(0, 0, 1), distance=7.0, views=((-35, 12), (35, 8), (180, 15)), res=520, lens=50):
    """Render several camera angles and tile them into one PNG. Returns the path."""
    import numpy as np
    preview_studio()
    tiles = []
    tmp = os.path.join(BUILD, "_tile.png")
    for yaw, pitch in views:
        look_setup(target=target, distance=distance, yaw=yaw, pitch=pitch, lens=lens)
        render_png(tmp, res=(res, res))
        img = bpy.data.images.load(tmp, check_existing=False)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
        tiles.append(px)
        bpy.data.images.remove(img)
    sheet = np.concatenate(tiles, axis=1)
    h, w = sheet.shape[0], sheet.shape[1]
    out = bpy.data.images.new("_sheet", width=w, height=h, alpha=True)
    out.pixels = sheet.ravel()
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    return path


def socket_carrier(arm, name="Rig__Sockets", size=0.004):
    """Roblox's importer DROPS bones that no vertex is weighted to. A creature body only
    influences ~9 bones, so eyes/ears/legs would find nothing to bind to. This invisible
    mesh puts one tiny tetrahedron on every bone, fully weighted to it, so the whole
    skeleton survives import. The builder hides/destroys the MeshPart; bones stay."""
    bm = bmesh.new()
    owners = []
    for b in arm.data.bones:
        c = arm.matrix_world @ b.head_local
        vs = [bm.verts.new(c + Vector(o) * size) for o in ((1, 1, 1), (-1, -1, 1), (-1, 1, -1), (1, -1, -1))]
        for tri in ((0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)):
            bm.faces.new([vs[i] for i in tri])
        owners.append((b.name, vs))
    bm.verts.index_update()
    index_owner = []
    for bname, vs in owners:
        index_owner.append((bname, [v.index for v in vs]))
    obj = mesh_object(name, bm)
    for bname, idxs in index_owner:
        g = obj.vertex_groups.new(name=bname)
        g.add(idxs, 1.0, "REPLACE")
    obj.parent = arm
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return obj
