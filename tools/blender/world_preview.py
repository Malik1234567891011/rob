"""world_preview.py: rebuild the Roblox world offline in Blender and render review shots.

Studio's viewport can't always be captured, so this rebuilds the placed world from the export
(art/build/world_export/parts.txt + terrain.txt) with the real kit meshes, renders a fixed set
of review cameras, and tiles them into a labelled contact sheet.

Run (from anywhere):

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
        -P ~/rob/tools/blender/world_preview.py -- [--views hub_overview,meadow] [--fast]
        [--samples 16] [--res 1280x720] [--no-refs] [--no-sheet] [--list]
        [--cam "name=px,py,pz:lx,ly,lz[:fov]"]   # ad-hoc camera in Roblox coords, repeatable

All views take ~40 s at 1280x720 (Eevee). Outputs: art/previews/world/<view>.jpg, _sheet.jpg
(labelled contact sheet, needs system python3 + PIL) and _checks.txt (numeric placement
checks: floating / buried / under terrain / on roads / on plot lawns, with coordinates).
The pink capsules are 5-stud character stand-ins for judging scale (--no-refs hides them).

Limits: terrain is a HEIGHTFIELD from a top-down raycast, so overhangs don't exist here: cave
interiors, the tunnel mouth under the Cave_Arch, and anything under the mountain are hidden.
Floating terrain (Strange Zone) gets a guessed tapered underside. Materials/lighting are
approximations; layout, scale, density and colour blocking are what this is for.

Coordinates. 1 stud = 1 Blender unit. The kit FBX export maps Blender (x, y, z) to Roblox
(-x, z, y), so Roblox (X, Y, Z) -> Blender (-X, Z, Y) and a CFrame rotation R converts to
C @ R @ C with C = [[-1,0,0],[0,0,1],[0,1,0]] (C is symmetric and orthogonal, det +1, so no
mirroring). The exported position is the part's BOUNDING-BOX centre and the size is its local
bbox, so each instance is: translate(pos) @ rot @ scale(size / mesh dims) @ translate(-mesh centre),
with Roblox size (sx, sy, sz) matching Blender mesh dims (dx, dz, dy). The script re-checks that
permutation against every kit part at startup and prints the result.
"""

import argparse
import math
import os
import re
import subprocess
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.path.expanduser("~/rob")
BUILD = os.path.join(ROOT, "art", "build")
EXPORT = os.path.join(BUILD, "world_export")
OUT = os.path.join(ROOT, "art", "previews", "world")
KITS = (("Hub", "kit_hub.fbx"), ("Meadow", "kit_meadow.fbx"), ("Junk", "kit_junk.fbx"), ("Props", "kit_props.fbx"))

TERRAIN_HEX = {
    "Grass": "68B048", "LeafyGrass": "60A446", "Ground": "B08E64", "Sand": "ECD6A0", "Rock": "8A8A8A",
    "Slate": "6E7078", "Cobblestone": "A09A90", "Mud": "7A5A40", "Basalt": "3A3A40",
}
UNKNOWN_TERRAIN_HEX = "C0C0C0"
WATER_HEX = "3FA7E0"
SKY_HEX = "A8D4F5"
HORIZON_HEX = "CFE3F2"
SUN_HEX = "FFF0D8"
REF_HEX = "FF3B6B"

SEA_LEVEL = 0.0           # Roblox sea surface (WorldTerrain: sea level 0)
SEA_FLOOR = -30.0
SEA_EXTENT = (-3000, 3000, -3000, 3000)  # x0, x1, z0, z1 of the Roblox sea fill
CUT = 60.0                # a grid quad spanning more height than this is a discontinuity (floating island edge)
SKIRT_MAX = 60.0          # skirt depth down a cliff that the 6-stud grid can't connect
SKIRT_VOID = 8.0          # skirt depth where terrain ends at void
UNDER_EDGE = 2.5          # floating terrain: thickness at its rim
UNDER_SLOPE = 1.1         # ...growing by this many studs per stud inward
UNDER_MAX = 70.0

S15, C15 = math.sin(math.radians(15)), math.cos(math.radians(15))
# plot k=0 per WorldBuilder.plots(): angle 15 deg, pos = (cos a * 205, 0, sin a * 205)
PLOT0 = (205 * C15, 205 * S15)

# name: (camera pos, look-at, vertical FOV deg), all in ROBLOX coordinates
VIEWS = {
    "hub_overview": ((0, 140, 300), (0, 0, 0), 70),
    "hub_close": ((60, 30, 90), (0, 5, 0), 70),
    "plots_ring": ((0, 460, 60), (0, 0, 0), 70),
    "plot_close": ((PLOT0[0] + 40, 40, PLOT0[1] + 60), (PLOT0[0], 0, PLOT0[1]), 70),
    "meadow": ((300, 120, 60), (470, 0, 20), 70),
    "junkyard": ((-280, 110, 70), (-470, 0, 0), 70),
    "caves_outside": ((60, 140, -180), (0, 60, -470), 70),
    "ocean": ((0, 80, 330), (0, -10, 520), 70),
    "strange": ((-400, 290, -560), (-560, 230, -640), 70),
    "trials_race": ((5950, 80, -80), (6000, 0, 100), 70),
    "world_top": ((0, 1700, -150), (0, 0, -160), 78),
    # extra close-ups: the places a player actually stands
    "hub_ground": ((22, 9, 34), (0, 5, -50), 70),
    "meadow_road": ((180, 26, 26), (300, 6, -6), 70),
    "caves_entrance": ((16, 24, -250), (0, 10, -330), 70),
    "junk_towers": ((-430, 34, 90), (-470, 12, 138), 70),
    "trials_obstacle": ((6062, 50, 1470), (6000, 6, 1640), 70),
    "farm": ((180, 60, 160), (290, 0, 270), 70),
    "woods": ((260, 70, -180), (370, 10, -300), 70),
    "orchard": ((-230, 50, -180), (-330, 0, -300), 70),
    "pond": ((380, 30, 40), (440, 0, 100), 70),
    "from_plot": ((150, 12, 150), (0, 20, -400), 70),
}

# 5-stud character stand-ins (Roblox x, z) so scale reads at a glance
REFS = [
    (0, 36), (36, 20), (-8, -60), (PLOT0[0], PLOT0[1]), (PLOT0[0] - 20, PLOT0[1] - 6), (420, 40), (300, 4),
    (-290, 4), (-450, 0), (0, -330), (0, 380), (5882, -34), (6000, -70),
]

C3 = Matrix(((-1, 0, 0), (0, 0, 1), (0, 1, 0)))


def rb(x, y, z):
    """Roblox point -> Blender point."""
    return Vector((-x, z, y))


def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_lin(h):
    return tuple(srgb_to_lin(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def log(*a):
    print("[world_preview]", *a, flush=True)


# ═══ ARGS ═════════════════════════════════════════════════════════════════════

def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="world_preview.py")
    ap.add_argument("--views", default="", help="comma list of view names (default: all)")
    ap.add_argument("--samples", type=int, default=16, help="Eevee render samples")
    ap.add_argument("--fast", action="store_true", help="half resolution, 4 samples")
    ap.add_argument("--res", default="1280x720")
    ap.add_argument("--export", default=EXPORT)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--quality", type=int, default=88, help="JPEG quality")
    ap.add_argument("--no-refs", action="store_true", help="skip the 5-stud reference figures")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--engine", default="", help="force BLENDER_EEVEE or BLENDER_WORKBENCH")
    ap.add_argument("--save-blend", default="", help="optional .blend path to save the rebuilt scene")
    ap.add_argument("--cam", action="append", default=[],
                    help='ad-hoc view in Roblox coords: name=px,py,pz:lx,ly,lz[:fov] (repeatable)')
    ap.add_argument("--list", action="store_true", help="print view names and exit")
    a = ap.parse_args(argv)
    if a.list:
        print("\n".join(VIEWS))
        sys.exit(0)
    for spec in a.cam:
        name, _, rest = spec.partition("=")
        bits = rest.split(":")
        VIEWS[name] = (tuple(float(v) for v in bits[0].split(",")), tuple(float(v) for v in bits[1].split(",")),
                       float(bits[2]) if len(bits) > 2 else 70)
    a.view_list = [v.strip() for v in a.views.split(",") if v.strip()] or list(VIEWS)
    bad = [v for v in a.view_list if v not in VIEWS]
    if bad:
        ap.error("unknown views %s; known: %s" % (bad, ", ".join(VIEWS)))
    w, h = (int(v) for v in a.res.lower().split("x"))
    if a.fast:
        w, h, a.samples = w // 2, h // 2, min(a.samples, 4)
    a.w, a.h = w, h
    return a


# ═══ SCENE / MATERIALS ════════════════════════════════════════════════════════

def reset_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for b in list(coll):
            coll.remove(b)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def new_collection(name, exclude=False):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    if exclude:
        bpy.context.view_layer.layer_collection.children[name].exclude = True
    return c


def _math(nt, op, a=None, b=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def fog_group():
    """Distance fog as a shader group so one set of values drives every material."""
    g = bpy.data.node_groups.new("WP_Fog", "ShaderNodeTree")
    g.interface.new_socket("Fac", in_out="OUTPUT", socket_type="NodeSocketFloat")
    g.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    out = g.nodes.new("NodeGroupOutput")
    cam = g.nodes.new("ShaderNodeCameraData")
    vals = {}
    for name, v in (("start", 200.0), ("falloff", 2000.0), ("max", 0.6)):
        n = g.nodes.new("ShaderNodeValue")
        n.name = name
        n.outputs[0].default_value = v
        vals[name] = n.outputs[0]
    col = g.nodes.new("ShaderNodeRGB")
    col.name = "color"
    col.outputs[0].default_value = (*hex_lin(HORIZON_HEX), 1)
    d = _math(g, "SUBTRACT", cam.outputs["View Distance"], vals["start"])
    d = _math(g, "MAXIMUM", d, 0.0)
    d = _math(g, "DIVIDE", d, vals["falloff"])
    d = _math(g, "MULTIPLY", d, -1.0)
    d = _math(g, "EXPONENT", d)
    d = _math(g, "SUBTRACT", 1.0, d)
    d = _math(g, "MULTIPLY", d, vals["max"])
    g.links.new(d, out.inputs["Fac"])
    g.links.new(col.outputs[0], out.inputs["Color"])
    return g


def set_fog(start, falloff, maximum):
    g = bpy.data.node_groups["WP_Fog"]
    g.nodes["start"].outputs[0].default_value = start
    g.nodes["falloff"].outputs[0].default_value = falloff
    g.nodes["max"].outputs[0].default_value = maximum


def new_material(name):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    return mat, nt


def finish(mat, surface):
    nt = mat.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    fg = nt.nodes.new("ShaderNodeGroup")
    fg.node_tree = bpy.data.node_groups["WP_Fog"]
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(fg.outputs["Color"], em.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fg.outputs["Fac"], mix.inputs[0])
    nt.links.new(surface, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


def vcol_times_object(nt):
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    info = nt.nodes.new("ShaderNodeObjectInfo")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    nt.links.new(attr.outputs[0], mix.inputs[6])
    nt.links.new(info.outputs["Color"], mix.inputs[7])
    return mix.outputs[2], info


def principled(nt, rough=0.7, spec=0.25):
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Roughness"].default_value = rough
    for key in ("Specular IOR Level", "Specular"):
        if key in b.inputs:
            b.inputs[key].default_value = spec
            break
    return b


def make_materials():
    fog_group()
    mats = {}

    # kit meshes and plain parts: vertex colour x Part.Color (object colour), alpha = 1 - transparency
    mat, nt = new_material("WP_Kit")
    col, info = vcol_times_object(nt)
    b = principled(nt, 0.72, 0.2)
    nt.links.new(col, b.inputs["Base Color"])
    nt.links.new(info.outputs["Alpha"], b.inputs["Alpha"])
    mats["kit"] = finish(mat, b.outputs[0])

    # Neon: emissive
    mat, nt = new_material("WP_Neon")
    col, info = vcol_times_object(nt)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 2.2
    nt.links.new(col, em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(info.outputs["Alpha"], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    mats["neon"] = finish(mat, mix.outputs[0])

    # ForceField: translucent tinted shimmer
    mat, nt = new_material("WP_ForceField")
    col, info = vcol_times_object(nt)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.2
    nt.links.new(col, em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    fac = _math(nt, "MULTIPLY", info.outputs["Alpha"], 0.55)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fac, mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    mats["forcefield"] = finish(mat, mix.outputs[0])

    # terrain: vertex colour only
    mat, nt = new_material("WP_Terrain")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    b = principled(nt, 0.95, 0.1)
    nt.links.new(attr.outputs[0], b.inputs["Base Color"])
    mats["terrain"] = finish(mat, b.outputs[0])

    # water
    mat, nt = new_material("WP_Water")
    b = principled(nt, 0.32, 0.3)
    b.inputs["Base Color"].default_value = (*hex_lin(WATER_HEX), 1)
    b.inputs["Alpha"].default_value = 0.7
    mats["water"] = finish(mat, b.outputs[0])

    # reference figures
    mat, nt = new_material("WP_Ref")
    b = principled(nt, 0.5, 0.3)
    b.inputs["Base Color"].default_value = (*hex_lin(REF_HEX), 1)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*hex_lin(REF_HEX), 1)
    em.inputs["Strength"].default_value = 0.35
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(b.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    mats["ref"] = finish(mat, add.outputs[0])

    for key, m in mats.items():
        method = "BLENDED" if key == "water" else "DITHERED"   # blended: no dither grain on the sea
        for attr_name, val in (("surface_render_method", method), ("use_backface_culling", False)):
            try:
                setattr(m, attr_name, val)
            except Exception:
                pass
    return mats


def setup_render(args):
    scene = bpy.context.scene
    engines = [args.engine] if args.engine else ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH"]
    for eng in engines:
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    ee = scene.eevee
    for k, v in (("taa_render_samples", args.samples), ("use_shadows", True), ("shadow_ray_count", 1),
                 ("shadow_step_count", 6), ("use_raytracing", False), ("use_fast_gi", False),
                 ("use_gtao", True), ("gtao_distance", 6.0), ("use_volumetric_shadows", False),
                 ("shadow_resolution_scale", 1.0), ("shadow_pool_size", "2048")):
        try:
            setattr(ee, k, v)
        except Exception:
            pass
    scene.render.resolution_x, scene.render.resolution_y = args.w, args.h
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
    except TypeError:
        pass
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    ims = scene.render.image_settings
    try:
        ims.media_type = "IMAGE"
    except Exception:
        pass
    ims.file_format = "JPEG"
    ims.color_mode = "RGB"
    ims.quality = args.quality

    # world: light blue sky for camera rays, a softer ambient for lighting
    world = bpy.data.worlds.new("WP_World")
    scene.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    nt = world.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_WORLD":
            nt.nodes.remove(n)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    sky = nt.nodes.new("ShaderNodeBackground")
    amb = nt.nodes.new("ShaderNodeBackground")
    lp = nt.nodes.new("ShaderNodeLightPath")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeMix")
    ramp.data_type = "RGBA"
    grad = _math(nt, "MAXIMUM", sep.outputs[2], 0.0)
    grad = _math(nt, "POWER", grad, 0.6)
    nt.links.new(grad, ramp.inputs[0])
    ramp.inputs[6].default_value = (*hex_lin(HORIZON_HEX), 1)
    ramp.inputs[7].default_value = (*hex_lin(SKY_HEX), 1)
    nt.links.new(ramp.outputs[2], sky.inputs["Color"])
    sky.inputs["Strength"].default_value = 1.0
    amb.inputs["Color"].default_value = (*hex_lin("B8D0EA"), 1)
    amb.inputs["Strength"].default_value = 0.55
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(amb.outputs[0], mix.inputs[1])
    nt.links.new(sky.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])

    sun_d = bpy.data.lights.new("WP_Sun", "SUN")
    sun_d.energy = 3.4
    sun_d.color = hex_lin(SUN_HEX)
    sun_d.angle = math.radians(3.5)
    try:
        sun_d.use_shadow = True
    except Exception:
        pass
    sun = bpy.data.objects.new("WP_Sun", sun_d)
    scene.collection.objects.link(sun)
    # light travels FROM the sun: sun sits up and toward Roblox (+X, -Z), so shadows fall to (-X, +Z)
    to_sun = rb(0.45, 0.78, -0.43).normalized()
    sun.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()

    cam_d = bpy.data.cameras.new("WP_Cam")
    cam_d.sensor_fit = "VERTICAL"
    cam_d.clip_start = 0.5
    cam_d.clip_end = 40000
    cam = bpy.data.objects.new("WP_Cam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    return scene.render.engine


# ═══ KIT SOURCES ══════════════════════════════════════════════════════════════

def import_kits(mats, src_coll):
    sources = {}
    for kit, fname in KITS:
        path = os.path.join(BUILD, fname)
        if not os.path.exists(path):
            log("missing kit FBX", path)
            continue
        before = set(bpy.data.objects)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            bpy.ops.import_scene.fbx(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            if o.type != "MESH":
                bpy.data.objects.remove(o, do_unlink=True)
                continue
            src_coll.objects.link(o)
            me = o.data
            mw = o.matrix_world.copy()
            if mw != Matrix.Identity(4):
                me.transform(mw)       # bake any importer axis/scale conversion into the data
                o.matrix_world = Matrix.Identity(4)
            me.materials.clear()
            me.materials.append(mats["kit"])
            if not me.color_attributes.get("Col"):
                a = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
                a.data.foreach_set("color", [1.0] * (4 * len(a.data)))
            co = np.empty(len(me.vertices) * 3, np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            lo, hi = co.min(0), co.max(0)
            base = re.sub(r"\.\d{3}$", "", o.name)
            sources[(kit, base)] = (me, Vector(((lo + hi) / 2).tolist()), Vector((hi - lo).tolist()))
        log("imported %s: %d meshes" % (fname, sum(1 for k in sources if k[0] == kit)))
    return sources


def primitive_meshes(mats):
    out = {}
    specs = {}

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    specs["#Block"] = bm

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=0.5)
    specs["#Ball"] = bm

    bm = bmesh.new()   # along Blender local X == Roblox local X
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.5, radius2=0.5, depth=1.0,
                          matrix=Matrix.Rotation(math.radians(90), 4, "Y"))
    specs["#Cylinder"] = bm

    bm = bmesh.new()   # Roblox wedge: full height at local +Z (back), slope down to -Z (front)
    vs = {}
    for sx in (-0.5, 0.5):
        for name, (y, z) in {"bf": (-0.5, -0.5), "bb": (-0.5, 0.5), "tb": (0.5, 0.5)}.items():
            vs[(sx, name)] = bm.verts.new(rb(sx, y, z))
    for f in ((("bf", -.5), ("bb", -.5), ("tb", -.5)), (("bf", .5), ("tb", .5), ("bb", .5)),
              (("bf", -.5), ("bf", .5), ("bb", .5), ("bb", -.5)), (("bb", -.5), ("bb", .5), ("tb", .5), ("tb", -.5)),
              (("bf", -.5), ("tb", -.5), ("tb", .5), ("bf", .5))):
        bm.faces.new([vs[(sx, n)] for n, sx in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    specs["#Wedge"] = bm

    for kind, bm in specs.items():
        me = bpy.data.meshes.new("WP_" + kind[1:])
        bm.to_mesh(me)
        bm.free()
        a = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        a.data.foreach_set("color", [1.0] * (4 * len(a.data)))
        me.materials.append(mats["kit"])
        out[kind] = (me, Vector((0, 0, 0)), Vector((1, 1, 1)))
    return out


# ═══ PARTS ════════════════════════════════════════════════════════════════════

def read_parts(path):
    parts = []
    with open(path) as f:
        for ln, line in enumerate(f, 1):
            p = line.split()
            if len(p) < 19:
                if p:
                    log("parts.txt:%d malformed (%d fields)" % (ln, len(p)))
                continue
            v = [float(x) for x in p[1:16]]
            parts.append({
                "kind": p[0], "pos": v[0:3], "R": v[3:12], "size": v[12:15],
                "color": p[16], "material": p[17], "transparency": float(p[18]),
            })
    return parts


def part_matrix(part, centre, dims):
    x, y, z = part["pos"]
    R = Matrix((part["R"][0:3], part["R"][3:6], part["R"][6:9]))
    RB = C3 @ R @ C3
    sx, sy, sz = part["size"]
    kind = part["kind"]
    if kind == "#Ball":
        d = min(sx, sy, sz)
        sx = sy = sz = d
    elif kind == "#Cylinder":
        d = min(sy, sz)
        sy = sz = d
    scale = Vector((sx / max(dims.x, 1e-4), sz / max(dims.y, 1e-4), sy / max(dims.z, 1e-4)))
    return Matrix.Translation(rb(x, y, z)) @ RB.to_4x4() @ Matrix.Diagonal((*scale, 1.0)) @ Matrix.Translation(-centre)


def verify_axes(parts, sources):
    """Every kit part's exported size must be its mesh dims permuted (x, z, y) times ONE uniform
    scale. A wrong axis mapping shows up as the three ratios disagreeing on non-cubic meshes."""
    ok = bad = 0
    worst = []
    for p in parts:
        if p["kind"].startswith("#"):
            continue
        kit, _, name = p["kind"].partition("/")
        src = sources.get((kit, name))
        if not src:
            continue
        d = src[2]
        sx, sy, sz = p["size"]
        r = (sx / max(d.x, 1e-4), sy / max(d.z, 1e-4), sz / max(d.y, 1e-4))
        spread = (max(r) - min(r)) / max(min(r), 1e-4)
        if spread < 0.04:
            ok += 1
        else:
            bad += 1
            worst.append((spread, p["kind"], tuple(round(v, 2) for v in r)))
    worst.sort(reverse=True)
    g = next((p for p in parts if p["kind"] == "Meadow/GrassTuft_A"), None)
    gd = sources.get(("Meadow", "GrassTuft_A"))
    msg = "axis check: %d kit parts match size == dims(x,z,y) * uniform scale, %d do not" % (ok, bad)
    if g and gd:
        msg += "; GrassTuft_A mesh dims %s, part size %s" % (tuple(round(v, 2) for v in gd[2]), tuple(g["size"]))
    return msg, worst[:10]


def build_parts(parts, sources, prims, mats, coll):
    missing = {}
    count = 0
    for p in parts:
        kind = p["kind"]
        if kind.startswith("#"):
            src = prims.get(kind) or prims["#Block"]
        else:
            kit, _, name = kind.partition("/")
            src = sources.get((kit, name))
            if not src:  # fall back to any kit with the name, else a magenta box
                src = next((v for (k, n), v in sources.items() if n == name), None)
            if not src:
                missing[kind] = missing.get(kind, 0) + 1
                src = prims["#Block"]
                p = dict(p, color="FF00FF", material="SmoothPlastic", transparency=0.0)
        me, centre, dims = src
        o = bpy.data.objects.new(kind.split("/")[-1], me)
        o.matrix_world = part_matrix(p, centre, dims)
        o.color = (*hex_lin(p["color"]), 1.0 - p["transparency"])
        coll.objects.link(o)
        mat = {"Neon": mats["neon"], "ForceField": mats["forcefield"]}.get(p["material"])
        if mat:
            o.material_slots[0].link = "OBJECT"
            o.material_slots[0].material = mat
        count += 1
    return count, missing


# ═══ TERRAIN ══════════════════════════════════════════════════════════════════

def read_terrain(path):
    with open(path) as f:
        lines = f.read().split("\n")
    names = lines[0].split()[1:]
    regions = []
    i = 1
    while i < len(lines):
        ln = lines[i]
        if not ln.startswith("R "):
            i += 1
            continue
        _, name, x0, x1, z0, z1, st = ln.split()
        x0, x1, z0, z1, st = int(x0), int(x1), int(z0), int(z1), int(st)
        nx, nz = (x1 - x0) // st + 1, (z1 - z0) // st + 1
        H = np.full((nz, nx), np.nan, np.float32)
        W = np.full((nz, nx), np.nan, np.float32)
        Mi = np.zeros((nz, nx), np.int16)
        for zi in range(nz):
            cells = lines[i + 1 + zi].split(",")
            for xi, c in enumerate(cells[:nx]):
                p = c.split()
                if not p:
                    continue
                if p[0] != "_":
                    H[zi, xi] = int(p[0]) / 2.0
                    Mi[zi, xi] = int(p[1])
                if len(p) > 2:
                    W[zi, xi] = int(p[2]) / 2.0
        regions.append({"name": name, "x0": x0, "z0": z0, "st": st, "H": H, "W": W, "M": Mi})
        i += 1 + nz
    return names, regions


def ground_at(regions, x, z):
    """Bilinear terrain height at Roblox (x, z); None where there is no terrain."""
    for r in regions:
        H = r["H"]
        fx, fz = (x - r["x0"]) / r["st"], (z - r["z0"]) / r["st"]
        if fx < 0 or fz < 0 or fx > H.shape[1] - 1 or fz > H.shape[0] - 1:
            continue
        j, i = min(int(fx), H.shape[1] - 2), min(int(fz), H.shape[0] - 2)
        tx, tz = fx - j, fz - i
        q = H[i:i + 2, j:j + 2]
        if np.isnan(q).any():
            vals = q[~np.isnan(q)]
            return float(vals.max()) if len(vals) else None
        return float((q[0, 0] * (1 - tx) + q[0, 1] * tx) * (1 - tz) + (q[1, 0] * (1 - tx) + q[1, 1] * tx) * tz)
    return None


def water_at(regions, x, z):
    for r in regions:
        W = r["W"]
        j, i = round((x - r["x0"]) / r["st"]), round((z - r["z0"]) / r["st"])
        if 0 <= i < W.shape[0] and 0 <= j < W.shape[1]:
            return None if np.isnan(W[i, j]) else float(W[i, j])
    return None


def mesh_from_arrays(name, verts, faces, colors, mat, coll, smooth=True):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    nf = len(faces)
    me.loops.add(nf * 4)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 4, 4, dtype=np.int32))
    me.update(calc_edges=True)
    if colors is not None:
        a = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        rgba = np.concatenate([colors.astype(np.float32), np.ones((len(colors), 1), np.float32)], 1)
        a.data.foreach_set("color", rgba.ravel())
    if smooth:
        try:
            me.shade_smooth()
        except AttributeError:
            me.polygons.foreach_set("use_smooth", [True] * nf)
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    return o


def label_components(mask):
    """4-connected component labels over a boolean grid (min-index propagation + pointer jumping)."""
    idx = np.arange(mask.size, dtype=np.int64).reshape(mask.shape)
    lab = np.where(mask, idx, -1)
    for _ in range(4000):
        old = lab.copy()
        for a, b, both in ((np.s_[:, :-1], np.s_[:, 1:], mask[:, :-1] & mask[:, 1:]),
                           (np.s_[:-1, :], np.s_[1:, :], mask[:-1, :] & mask[1:, :])):
            m = np.minimum(lab[a], lab[b])
            lab[a] = np.where(both, m, lab[a])
            lab[b] = np.where(both, m, lab[b])
        flat = lab.ravel()
        good = flat >= 0
        flat[good] = flat[flat[good]]
        lab = flat.reshape(mask.shape)
        if np.array_equal(lab, old):
            break
    return lab


def build_terrain_region(reg, names, mats, coll):
    H, W, Mi, st = reg["H"], reg["W"], reg["M"], reg["st"]
    nz, nx = H.shape
    X = reg["x0"] + st * np.arange(nx, dtype=np.float32)[None, :].repeat(nz, 0)
    Z = reg["z0"] + st * np.arange(nz, dtype=np.float32)[:, None].repeat(nx, 1)
    valid = ~np.isnan(H)

    palette = np.array([hex_lin(UNKNOWN_TERRAIN_HEX)] + [hex_lin(TERRAIN_HEX.get(n, UNKNOWN_TERRAIN_HEX)) for n in names],
                       np.float32)
    vcol = palette[np.clip(Mi, 0, len(names))]

    q = np.stack([H[:-1, :-1], H[:-1, 1:], H[1:, :-1], H[1:, 1:]])
    allv = ~np.isnan(q).any(0)
    qf = np.where(np.isnan(q), 0.0, q)
    qmax = np.where(allv, qf.max(0), np.nan)
    qmin = np.where(allv, qf.min(0), np.nan)
    qmean = np.where(allv, qf.mean(0), np.nan)
    drawn = allv & ((qmax - qmin) <= CUT)

    # A region with no void is one continuous heightfield (the main island + sea floor): every
    # drawn component except the biggest is terrain floating in the air (Strange Zone island,
    # orbiting rocks), which gets a tapered underside. Regions with void (trials) get slabs.
    floating = np.zeros_like(drawn)
    if valid.all() and drawn.any():
        comp = label_components(drawn)
        labels, counts = np.unique(comp[drawn], return_counts=True)
        floating = drawn & (comp != labels[counts.argmax()])

    vid = -np.ones((nz, nx), np.int64)
    vid[valid] = np.arange(valid.sum())
    verts = [np.stack([-X[valid], Z[valid], H[valid]], 1)]
    cols = [vcol[valid]]
    qi, qj = np.nonzero(drawn)
    faces = [np.stack([vid[qi, qj], vid[qi + 1, qj], vid[qi + 1, qj + 1], vid[qi, qj + 1]], 1)]
    nverts = [len(verts[0])]
    ntop = len(faces[0])

    def add(v, c, f):
        verts.append(v)
        cols.append(c)
        faces.append(f + nverts[0])
        nverts[0] += len(v)

    # tapered undersides for floating components
    nunder = 0
    if floating.any():
        D = np.full(floating.shape, np.inf)
        inner = floating.copy()
        inner[1:, :] &= floating[:-1, :]
        inner[:-1, :] &= floating[1:, :]
        inner[:, 1:] &= floating[:, :-1]
        inner[:, :-1] &= floating[:, 1:]
        inner[0, :] = inner[-1, :] = inner[:, 0] = inner[:, -1] = False
        edge = floating & ~inner
        D[edge] = 0
        for _ in range(60):
            nb = np.full_like(D, np.inf)
            nb[1:, :] = np.minimum(nb[1:, :], D[:-1, :])
            nb[:-1, :] = np.minimum(nb[:-1, :], D[1:, :])
            nb[:, 1:] = np.minimum(nb[:, 1:], D[:, :-1])
            nb[:, :-1] = np.minimum(nb[:, :-1], D[:, 1:])
            newD = np.where(floating, np.minimum(D, nb + 1), np.inf)
            if np.array_equal(newD, D):
                break
            D = newD
        Dv = np.full((nz + 1, nx + 1), np.inf)
        for di in (0, 1):
            for dj in (0, 1):
                Dv[di:nz - 1 + di, dj:nx - 1 + dj] = np.minimum(Dv[di:nz - 1 + di, dj:nx - 1 + dj], D)
        Dv = Dv[:nz, :nx]
        uv = np.isfinite(Dv) & valid
        uid = -np.ones((nz, nx), np.int64)
        uid[uv] = np.arange(uv.sum())
        depth = np.clip(UNDER_EDGE + UNDER_SLOPE * Dv[uv] * st, UNDER_EDGE, UNDER_MAX)
        ubot = np.stack([-X[uv], Z[uv], H[uv] - depth], 1)
        fi, fj = np.nonzero(floating)
        uf = np.stack([uid[fi, fj], uid[fi, fj + 1], uid[fi + 1, fj + 1], uid[fi + 1, fj]], 1)
        add(ubot, vcol[uv] * 0.4, uf)
        nunder = len(uf)

    # skirts: vertical strips under terrain edges that end at void or at a big height jump
    def pad(a, fill):
        out = np.full((nz + 1, nx + 1), fill, dtype=a.dtype)
        out[1:-1, 1:-1] = a
        return out
    Dp, Ap, Fp = pad(drawn, False), pad(allv, False), pad(floating, False)
    MINp, MEANp = pad(qmin, np.nan), pad(qmean, np.nan)
    nskirt = [0]

    def skirts(ev, A, B, p0, p1):
        A_d, B_d = Dp[A], Dp[B]
        need = ev & (A_d != B_d)
        u_all = np.where(A_d, Ap[B], Ap[A])
        u_min = np.where(A_d, MINp[B], MINp[A])
        u_mean = np.where(A_d, MEANp[B], MEANp[A])
        d_float = np.where(A_d, Fp[A], Fp[B])
        e_mean = (H[p0] + H[p1]) / 2
        with np.errstate(invalid="ignore"):
            cliff = np.clip(e_mean - u_min, 0, SKIRT_MAX)
            depth = np.where(d_float, UNDER_EDGE, np.where(u_all, cliff, SKIRT_VOID))
            keep = need & np.where(u_all, e_mean > u_mean + 1.0, True) & (depth > 0.5)
        idx = np.nonzero(keep)
        if not len(idx[0]):
            return
        a = tuple(ix[idx] for ix in p0)
        b = tuple(ix[idx] for ix in p1)
        d = depth[idx]
        n = len(d)
        va = np.stack([-X[a], Z[a], H[a]], 1)
        vb = np.stack([-X[b], Z[b], H[b]], 1)
        vbd, vad = vb.copy(), va.copy()
        vbd[:, 2] -= d
        vad[:, 2] -= d
        ca, cb = vcol[a], vcol[b]
        k = np.arange(n)
        add(np.concatenate([va, vb, vbd, vad]), np.concatenate([ca * 0.62, cb * 0.62, cb * 0.42, ca * 0.42]),
            np.stack([k, n + k, 2 * n + k, 3 * n + k], 1))
        nskirt[0] += n

    I, J = np.meshgrid(np.arange(nz), np.arange(nx - 1), indexing="ij")
    skirts(valid[:, :-1] & valid[:, 1:], np.s_[0:nz, 1:nx], np.s_[1:nz + 1, 1:nx], (I, J), (I, J + 1))
    I, J = np.meshgrid(np.arange(nz - 1), np.arange(nx), indexing="ij")
    skirts(valid[:-1, :] & valid[1:, :], np.s_[1:nz, 0:nx], np.s_[1:nz, 1:nx + 1], (I, J), (I + 1, J))

    # the raycast only saw the floating terrain's top, so the sea floor + water beneath it are
    # missing: fill them in from the surrounding ground
    Wsrc = W
    cut = allv & ~drawn
    if valid.all() and (floating.any() or cut.any()):
        fq = floating | cut
        fv = np.zeros((nz, nx), bool)
        mid = (qmax + qmin) / 2
        for k, (di, dj) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            high = cut & (np.nan_to_num(q[k]) > np.nan_to_num(mid))
            fv[di:nz - 1 + di, dj:nx - 1 + dj] |= floating | high
        Hl = np.where(fv, np.nan, H)
        Wl = np.where(fv, np.nan, W)
        Cl = np.where(fv[..., None], np.nan, vcol)
        for _ in range(80):
            holes = np.isnan(Hl)
            if not holes.any():
                break
            acc = np.zeros_like(Hl)
            wacc = np.zeros_like(Hl)
            cacc = np.zeros_like(Cl)
            n = np.zeros_like(Hl)
            wn = np.zeros_like(Hl)
            for sl_to, sl_from in ((np.s_[1:, :], np.s_[:-1, :]), (np.s_[:-1, :], np.s_[1:, :]),
                                   (np.s_[:, 1:], np.s_[:, :-1]), (np.s_[:, :-1], np.s_[:, 1:])):
                src = Hl[sl_from]
                ok = ~np.isnan(src)
                acc[sl_to] += np.where(ok, src, 0)
                cacc[sl_to] += np.where(ok[..., None], Cl[sl_from], 0)
                n[sl_to] += ok
                wsrc = Wl[sl_from]
                wok = ~np.isnan(wsrc)
                wacc[sl_to] += np.where(wok, wsrc, 0)
                wn[sl_to] += wok
            grow = holes & (n > 0)
            Hl[grow] = acc[grow] / n[grow]
            Cl[grow] = cacc[grow] / n[grow][:, None]
            wgrow = np.isnan(Wl) & (wn > 0) & fv
            Wl[wgrow] = wacc[wgrow] / wn[wgrow]
        Wsrc = np.where(fv & np.isnan(W), Wl, W)
        lv = np.zeros((nz, nx), bool)
        for di in (0, 1):
            for dj in (0, 1):
                lv[di:nz - 1 + di, dj:nx - 1 + dj] |= fq
        lv &= ~np.isnan(Hl)
        lid = -np.ones((nz, nx), np.int64)
        lid[lv] = np.arange(lv.sum())
        li, lj = np.nonzero(fq & lv[:-1, :-1] & lv[:-1, 1:] & lv[1:, :-1] & lv[1:, 1:])
        add(np.stack([-X[lv], Z[lv], Hl[lv]], 1), np.nan_to_num(Cl[lv]),
            np.stack([lid[li, lj], lid[li + 1, lj], lid[li + 1, lj + 1], lid[li, lj + 1]], 1))

    t = mesh_from_arrays("Terrain_" + reg["name"], np.concatenate(verts), np.concatenate(faces),
                         np.concatenate(cols), mats["terrain"], coll)

    # water: dilate one cell so the surface reaches under the shoreline slope
    W = Wsrc
    Wd = W.copy()
    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
        sh = np.full_like(W, np.nan)
        sh[max(di, 0):nz + min(di, 0), max(dj, 0):nx + min(dj, 0)] = W[max(-di, 0):nz - max(di, 0), max(-dj, 0):nx - max(dj, 0)]
        fill = np.isnan(Wd) & ~np.isnan(sh)
        Wd[fill] = sh[fill]
    wv = ~np.isnan(Wd)
    wq = wv[:-1, :-1] & wv[:-1, 1:] & wv[1:, :-1] & wv[1:, 1:]
    nwater = int(wq.sum())
    if nwater:
        wid = -np.ones((nz, nx), np.int64)
        wid[wv] = np.arange(wv.sum())
        wverts = np.stack([-X[wv], Z[wv], Wd[wv]], 1)
        qi, qj = np.nonzero(wq)
        wfaces = np.stack([wid[qi, qj], wid[qi + 1, qj], wid[qi + 1, qj + 1], wid[qi, qj + 1]], 1)
        mesh_from_arrays("Water_" + reg["name"], wverts, wfaces, None, mats["water"], coll, smooth=False)
    return t, ntop, nskirt[0], nunder, nwater


def build_outer_sea(regions, mats, coll):
    """The Roblox sea fill extends past the sampled main region; add it as a flat ring."""
    main = next((r for r in regions if r["name"] == "main"), None)
    if not main:
        return
    nz, nx = main["H"].shape
    ix0, iz0 = main["x0"], main["z0"]
    ix1, iz1 = ix0 + (nx - 1) * main["st"], iz0 + (nz - 1) * main["st"]
    ox0, ox1, oz0, oz1 = SEA_EXTENT
    rects = [(ox0, ox1, oz0, iz0), (ox0, ox1, iz1, oz1), (ox0, ix0, iz0, iz1), (ix1, ox1, iz0, iz1)]
    for name, y, mat, col in (("Sea_Outer", SEA_LEVEL, mats["water"], None), ("SeaFloor_Outer", SEA_FLOOR, mats["terrain"], hex_lin(TERRAIN_HEX["Sand"]))):
        verts, faces = [], []
        for x0, x1, z0, z1 in rects:
            b = len(verts)
            verts += [(-x0, z0, y), (-x0, z1, y), (-x1, z1, y), (-x1, z0, y)]
            faces.append((b, b + 1, b + 2, b + 3))
        colors = np.array([col] * len(verts), np.float32) if col else None
        mesh_from_arrays(name, np.array(verts, np.float32), np.array(faces), colors, mat, coll, smooth=False)


def build_refs(regions, parts, mats, coll):
    """5-stud-tall stand-in characters (body + head), standing on terrain or on the part below."""
    me = bpy.data.meshes.new("WP_RefMesh")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.95, radius2=0.8, depth=3.4,
                          matrix=Matrix.Translation((0, 0, 1.7)))
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=0.8, matrix=Matrix.Translation((0, 0, 4.2)))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mats["ref"])
    placed = 0
    for x, z in REFS:
        g = ground_at(regions, x, z)
        if g is None:
            continue
        o = bpy.data.objects.new("Ref5", me)
        o.location = rb(x, g, z)
        coll.objects.link(o)
        placed += 1
    return placed


# ═══ CHECKS ═══════════════════════════════════════════════════════════════════

INTENDED_WATER = ("LilyPad", "Reeds", "Bridge_Wood", "Race_Ring", "PondRim_Stone")


def on_road(x, z, r):
    d = math.hypot(x, z)
    hits = []
    if d > 50 - r and abs(z) < 8 + r and abs(x) < 340 + r:
        hits.append("E-W road")
    if d > 50 - r and abs(x) < 8 + r and -330 - r < z < 340 + r:
        hits.append("N-S road")
    if 133 - r < d < 147 + r:
        hits.append("ring road")
    return hits


def on_plot(x, z, r):
    for k in range(12):
        a = math.radians(15 + 30 * k)
        px, pz = 205 * math.cos(a), 205 * math.sin(a)
        L = (-math.cos(a), -math.sin(a))
        right = (-L[1], L[0])
        dx, dz = x - px, z - pz
        lx = dx * right[0] + dz * right[1]
        lz = -(dx * L[0] + dz * L[1])
        if abs(lx) < 33 + r and abs(lz) < 33 + r:
            return k + 1
    return None


def run_checks(parts, regions, out_path):
    lines = []
    floating, buried, under, wet, road, plot = [], [], [], [], [], []
    for p in parts:
        kind = p["kind"]
        name = kind.split("/")[-1]
        x, y, z = p["pos"]
        R = [p["R"][0:3], p["R"][3:6], p["R"][6:9]]
        sx, sy, sz = p["size"]
        corners = []
        for a in (-0.5, 0.5):
            for b in (-0.5, 0.5):
                for c in (-0.5, 0.5):
                    l = (a * sx, b * sy, c * sz)
                    corners.append(tuple((x, y, z)[i] + sum(R[i][j] * l[j] for j in range(3)) for i in range(3)))
        bottom = min(c[1] for c in corners)
        top = max(c[1] for c in corners)
        foot = [(c[0], c[2]) for c in corners] + [(x, z)]
        gs = [g for g in (ground_at(regions, fx, fz) for fx, fz in foot) if g is not None]
        rad = 0.5 * math.hypot(sx, sz)
        tag = "%s @ (%.0f, %.0f, %.0f)" % (kind, x, y, z)
        if gs:
            gmin, gmax = min(gs), max(gs)
            gc = ground_at(regions, x, z)
            if top < gmin - 1.0:
                under.append((tag, gmin - top))
            elif bottom > gmax + 1.0:
                floating.append((bottom - gmax, tag, "base %.1f, ground %.1f..%.1f" % (bottom, gmin, gmax)))
            elif gc is not None and (gc - bottom) > 0.45 * (top - bottom) and (gc - bottom) > 1.0:
                buried.append(((gc - bottom) / max(top - bottom, 0.01), tag, "base %.1f, height %.1f, ground %.1f" % (bottom, top - bottom, gc)))
            w = water_at(regions, x, z)
            if w is not None and bottom < w - 0.5 and name not in INTENDED_WATER and top > w - 30:
                wet.append((tag, "base %.1f, water %.1f" % (bottom, w)))
        else:
            floating.append((999, tag, "no terrain below (void)"))
        if abs(x) < 1000 and name not in ("Race_Ring",):
            r = 0.5 * min(sx, sz) if name in ("Bunting_Span",) else 0.35 * (sx + sz) / 2
            hits = on_road(x, z, r)
            if hits:
                road.append((tag, ",".join(hits)))
            k = on_plot(x, z, r)
            if k:
                plot.append((tag, "plot %d" % k))

    floating.sort(reverse=True)
    buried.sort(reverse=True)

    def section(title, rows, fmt):
        lines.append("")
        lines.append("== %s (%d)" % (title, len(rows)))
        for row in rows:
            lines.append("  " + fmt(row))

    lines.append("Placement checks against the sampled terrain heightfield (6-stud grid, so slopes are +-1-2 studs).")
    section("FLOATING: base above the highest ground under the footprint by >1 stud", floating, lambda r: "%-48s +%.1f  %s" % (r[1], r[0], r[2]))
    section("BURIED: >45% of height below ground at centre", buried, lambda r: "%-48s %3.0f%%  %s" % (r[1], r[0] * 100, r[2]))
    section("UNDER TERRAIN SURFACE (inside caves / under hills)", under, lambda r: "%-48s %.1f below" % r)
    section("IN WATER (base below water surface)", wet, lambda r: "%-48s %s" % r)
    section("ON ROADS (footprint overlaps the road bands WorldBuilder.onRoad keeps clear)", road, lambda r: "%-48s %s" % r)
    section("ON PLOT LAWNS (66x66 around each plot centre)", plot, lambda r: "%-48s %s" % r)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return "checks: %d floating, %d buried, %d under terrain, %d in water, %d on roads, %d on plots" % (
        len(floating), len(buried), len(under), len(wet), len(road), len(plot))


# ═══ RENDER ═══════════════════════════════════════════════════════════════════

def aim_camera(pos, look, fov):
    cam = bpy.context.scene.camera
    cam.data.angle_y = math.radians(fov)
    loc = rb(*pos)
    cam.location = loc
    cam.rotation_euler = (rb(*look) - loc).to_track_quat("-Z", "Y").to_euler()
    dist = (rb(*look) - loc).length
    set_fog(start=max(150.0, 0.9 * dist), falloff=5.0 * dist + 900.0, maximum=0.55)


SHEET_PY = r"""
import sys
from PIL import Image, ImageDraw, ImageFont
out, cols, tw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
items = [a.split("=", 1) for a in sys.argv[4:]]
th = tw * 9 // 16
bar = 34
font = None
for f in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/SFNS.ttf", "/Library/Fonts/Arial.ttf"):
    try:
        font = ImageFont.truetype(f, 22); break
    except Exception:
        pass
font = font or ImageFont.load_default()
rows = (len(items) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw, rows * (th + bar)), (24, 26, 30))
d = ImageDraw.Draw(sheet)
for i, (path, label) in enumerate(items):
    x, y = (i % cols) * tw, (i // cols) * (th + bar)
    im = Image.open(path).convert("RGB").resize((tw, th), Image.LANCZOS)
    sheet.paste(im, (x, y + bar))
    d.text((x + 10, y + 5), label, fill=(240, 240, 240), font=font)
sheet.save(out, quality=84)
print("sheet", out, sheet.size)
"""


def make_sheet(out_dir):
    items = []
    for v in VIEWS:
        p = os.path.join(out_dir, v + ".jpg")
        if os.path.exists(p):
            items.append("%s=%s" % (p, v))
    if not items:
        return
    py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else "python3"
    try:
        r = subprocess.run([py, "-c", SHEET_PY, os.path.join(out_dir, "_sheet.jpg"), "4", "640"] + items,
                           capture_output=True, text=True, timeout=120)
        log((r.stdout + r.stderr).strip() or "sheet done")
    except Exception as e:
        log("contact sheet skipped:", e)


def main():
    args = parse_args()
    t0 = time.time()
    os.makedirs(args.out, exist_ok=True)
    reset_scene()
    mats = make_materials()
    engine = setup_render(args)
    log("engine", engine, "%dx%d" % (args.w, args.h), "samples", args.samples)

    src_coll = new_collection("WP_Sources", exclude=True)
    world_coll = new_collection("WP_World")
    sources = import_kits(mats, src_coll)
    prims = primitive_meshes(mats)
    t1 = time.time()

    parts = read_parts(os.path.join(args.export, "parts.txt"))
    msg, worst = verify_axes(parts, sources)
    log(msg)
    for w in worst:
        log("  axis mismatch", w)
    n, missing = build_parts(parts, sources, prims, mats, world_coll)
    log("placed %d parts" % n + ("; MISSING meshes: %s" % missing if missing else ""))

    names, regions = read_terrain(os.path.join(args.export, "terrain.txt"))
    for reg in regions:
        _, nf, ns, nu, nw = build_terrain_region(reg, names, mats, world_coll)
        log("terrain %s: %d faces, %d skirt, %d floating-underside, %d water quads" % (reg["name"], nf, ns, nu, nw))
    build_outer_sea(regions, mats, world_coll)
    if not args.no_refs:
        log("reference figures:", build_refs(regions, parts, mats, world_coll))
    log(run_checks(parts, regions, os.path.join(args.out, "_checks.txt")))
    log("scene built in %.1fs (import %.1fs)" % (time.time() - t0, t1 - t0))

    if args.save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)

    scene = bpy.context.scene
    for v in args.view_list:
        pos, look, fov = VIEWS[v]
        aim_camera(pos, look, fov)
        scene.render.filepath = os.path.join(args.out, v + ".jpg")
        tv = time.time()
        bpy.ops.render.render(write_still=True)
        log("rendered %s in %.1fs" % (v, time.time() - tv))
    if not args.no_sheet:
        make_sheet(args.out)
    log("done in %.1fs -> %s" % (time.time() - t0, args.out))


if __name__ == "__main__":
    main()
