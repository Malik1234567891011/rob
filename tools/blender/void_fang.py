"""void_fang — VOID FANG, the shaggy black wolf-beast from Malik's character sheet
(~/Downloads/voidfang.png), as one skinned quadruped on the Heavy-family skeleton.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/void_fang.py [-- options]

      -> art/build/void_fang.fbx              one armature + 5 meshes + Rig__Sockets   (~12 s total)
      -> art/previews/void_fang_sheet.jpg     front / side / back / 3/4 + details, 5-stud capsule
      -> art/previews/void_fang_rigtest.jpg   jaw +25 deg, tail curl 20 deg/bone, stress, blink, wag

Options (after `--`):
    --no-export        skip the FBX
    --no-sheet         skip the sheet render
    --no-rigtest       skip the rig test render
    --overlay DIR      ortho renders blended over the sheet's own front/side/back drawings (iteration aid)
    --fast             half-resolution renders, fewer samples
    --verify           re-import the exported FBX and print meshes, tris, bones, weights
    --density F        fur clump Poisson density multiplier (the Fur tri budget still caps it)

Meshes (one MeshPart each in Roblox, all skinned to the same 33 Heavy-family bones):
    VoidFang__Fur    body, head, ears, lids, legs, tail + ~950 fur clumps. The VERTEX COLOUR is
                     the fur (near-black roots, dark-gray tips), so Part.Color must be WHITE:
                     vertex colour multiplies Part.Color. Clump normals lean to the body normal.
    VoidFang__Glow   flame streaks + glowing tail strands/tip. Vertex white: Neon #2F7BFF.
    VoidFang__Eyes   the two eyes. Vertex white: Neon #FF2A2A.
    VoidFang__Gold   sabre fangs + claw tips. Vertex white: tint aged gold, Foil/Metal.
    VoidFang__Dark   nose, mouth bag, tongue, ivory teeth, claw roots. Vertex coloured: WHITE.
    Rig__Sockets     one tetrahedron per bone so the importer keeps every bone (see DECISIONS.md).

Scale: 1 unit = 1 stud, Z up, facing -Y. Head top ~5.07 studs with fur (ear tips 5.43). Proportions
are MEASURED off the sheet's SIDE VIEW (0.01272 studs per sheet pixel, head top pinned at 5.0): the
sheet's wolf is about as long nose-to-rump (~5.5) as it is tall, so it is not 8-9 studs long.

How it is built:
  1. Body: SDF sculpt (sdf.py) of the coat mass: torso, mane hump, chest ruff, neck, wolf head with
     a snarl gap, thick legs, big toed paws, tail core. Eyes are seated on the skull by marching it.
  2. Fur: area-weighted Poisson samples on the body; each becomes a leaf-like spike (triangular
     section, 9-15 tris) combed by a per-region direction field (mane back/up, chest ruff down,
     leg feathering back/down, tail along the tail), tips painted dark gray.
  3. Glow: every marking is traced from the sheet in the view it was drawn in (side / front / top),
     smoothed into a flame, ray-cast onto the body, floated on the local fur (cast onto the clumps)
     and built as a raised tapered ribbon; clumps rooted under or lying over a streak are trimmed.
     The tail's flames and brush tip are glowing clumps inside the tail fur.
  4. Skin: capsule-distance weights with region masks, Laplacian-smoothed over the body surface
     (no candy-wrapper at shoulders/hips), jaw region blended onto Jaw, tail weights parametric
     along Tail1-4. Every clump / streak takes the smoothed weights of the body under it.
"""

import sys

sys.path.insert(0, "/Users/malik/rob/tools/blender")

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import time

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

import creatures
import famkit as fk
import sdf

T0 = time.time()
ROOT = fk.ROOT
FBX_NAME = "void_fang.fbx"
SHEET = os.path.join(ROOT, "art", "previews", "void_fang_sheet.jpg")
RIGTEST = os.path.join(ROOT, "art", "previews", "void_fang_rigtest.jpg")
REF = "/Users/malik/Downloads/voidfang.png"
NAME = "VoidFang"

BUDGET = {"Fur": 18000, "Glow": 6000}
BODY_TRIS = 4400


def log(*a):
    print("[void_fang %6.1fs]" % (time.time() - T0), *a, flush=True)


def V(*a):
    return Vector(a)


def T(v):
    return (float(v[0]), float(v[1]), float(v[2]))


def H(h):
    return ((h >> 16 & 255) / 255.0, (h >> 8 & 255) / 255.0, (h & 255) / 255.0)


def to_lin(c):
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def smooth01(a, b, x):
    """smoothstep that also works for a > b (falling ramp); scalar or numpy."""
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)
    r = t * t * (3 - 2 * t)
    return float(r) if np.ndim(r) == 0 else r


# ═══ PALETTE (sRGB, from the sheet's COLOR PALETTE panel) ══════════════════════

GLOW_HEX, EYE_HEX, GOLD_HEX = 0x2F7BFF, 0xFF2A2A, 0xB8923A
FUR_SKIN = H(0x0E0E11)       # pitch black body under the clumps
FUR_ROOT = H(0x0B0B0D)
FUR_TIP = H(0x282A31)        # dark gray at the tips
TAIL_TIP = H(0x383A42)       # the tail reads grayer on the sheet
MUZZLE = H(0x1C1C21)
INNER_EAR = H(0x4A4A53)
NOSE = H(0x0A0A0C)
MOUTH = H(0x3A1418)
TONGUE = H(0x5A2A30)
TOOTH = H(0xD9CFB0)
CLAW = H(0x1A1A1D)
WHITE = (1.0, 1.0, 1.0)


# ═══ SKELETON: the Heavy-family bone set, placed on the wolf ════════════════════
# Sockets measured off the sheet (see module doc). creatures.Family.skeleton() builds the
# bones, so names, parenting, roll and the tiny up/forward bone tails are identical.

TAIL_PTS = [V(0, 2.56, 3.46), V(0, 2.9, 2.82), V(0, 3.1, 2.08), V(0, 3.2, 1.36), V(0, 3.24, 0.76)]
TAIL_R = [0.36, 0.34, 0.3, 0.24, 0.14]

LEGS = {
    #       hip / shoulder       knee / elbow         foot
    "FL": (V(0.52, -0.95, 2.72), V(0.6, -0.62, 1.8), V(0.67, -1.05, 0.12)),
    "FR": (V(-0.52, -0.95, 2.72), V(-0.6, -0.62, 1.8), V(-0.67, -1.05, 0.12)),
    "BL": (V(0.52, 2.12, 2.98), V(0.62, 1.64, 1.86), V(0.7, 2.1, 0.12)),
    "BR": (V(-0.52, 2.12, 2.98), V(-0.62, 1.64, 1.86), V(-0.7, 2.1, 0.12)),
}
HOCK = {"BL": V(0.68, 2.32, 0.98), "BR": V(-0.68, 2.32, 0.98)}
PAW = {"FL": V(0.68, -1.15, 0.16), "FR": V(-0.68, -1.15, 0.16), "BL": V(0.7, 2.02, 0.16), "BR": V(-0.7, 2.02, 0.16)}

EYE_GUIDE = {"L": V(0.272, -2.075, 4.35), "R": V(-0.272, -2.075, 4.35)}
EYE = {k: v.copy() for k, v in EYE_GUIDE.items()}   # re-seated on the skull by place_eyes()
EAR_BASE = {"L": V(0.42, -1.7, 4.72), "R": V(-0.42, -1.7, 4.72)}

SOCK = dict(
    root=V(0, 0.55, 2.85), belly=V(0, 0.35, 2.35), spine=V(0, 0.55, 3.2), neck=V(0, -1.0, 3.55),
    head=V(0, -1.68, 4.28),
    jaw=V(0, -1.82, 3.9), tongue=V(0, -2.02, 3.84),
    eyeL=EYE["L"], eyeR=EYE["R"],
    cheekL=V(0.36, -1.9, 4.05), cheekR=V(-0.36, -1.9, 4.05),
    earL=EAR_BASE["L"], earR=EAR_BASE["R"],
    hornC=V(0, -1.98, 4.8), hornL=V(0.26, -1.92, 4.76), hornR=V(-0.26, -1.92, 4.76),
    back=V(0, 0.2, 3.95), wingL=V(0.5, 0.2, 3.85), wingR=V(-0.5, 0.2, 3.85),
    tail=TAIL_PTS, legs=LEGS,
)


class VoidFangRig(creatures.Family):
    name = NAME

    def base_sockets(self, head):
        return SOCK


def build_armature():
    arm = fk.armature("Rig_VoidFang", VoidFangRig().skeleton("Round"))
    return arm


# ═══ BODY SDF ════════════════════════════════════════════════════════════════

def stretch(shape, center, factors):
    c = np.array(T(center), dtype=np.float32)
    f = np.array(factors, dtype=np.float32)
    return sdf.warp(shape, lambda P: (P - c) * f + c)


def place_eyes():
    """March the undished head SDF along each eye's facing ray and seat the eye on the skin."""
    shape = head_shape(dishes=False)
    for side in "LR":
        e0 = EYE_GUIDE[side]
        f = eye_facing(e0)
        origin = e0 + f * 0.6
        ts = np.linspace(0.0, 1.0, 1000)
        P = np.array([T(origin - f * t) for t in ts], dtype=np.float32)
        inside = np.where(shape[0](P) < 0)[0]
        hit = origin - f * float(ts[inside[0]]) if len(inside) else e0
        EYE[side][:] = hit - f * 0.022


def head_shape(dishes=True):
    E, RC, su, M = sdf.ellipsoid, sdf.round_cone, sdf.smooth_union, sdf.mirror_x
    cranium = E((0, -1.76, 4.44), (0.45, 0.52, 0.42))
    occiput = E((0, -1.5, 4.38), (0.42, 0.4, 0.42))
    zyg = M(E((0.3, -1.95, 4.2), (0.2, 0.34, 0.18)))
    brow = M(E((0.21, -2.13, 4.47), (0.17, 0.17, 0.085), rot=(0, 18, -16)))
    muzzle = stretch(RC((0, -2.06, 4.14), (0, -2.66, 4.0), 0.25, 0.135), (0, -2.36, 4.07), (1 / 1.1, 1, 1.0))
    bridge = RC((0, -2.12, 4.34), (0, -2.64, 4.08), 0.09, 0.07)
    flews = M(E((0.15, -2.3, 3.93), (0.1, 0.33, 0.09)))
    jaw = stretch(RC((0, -1.84, 3.82), (0, -2.47, 3.74), 0.19, 0.085), (0, -2.15, 3.78), (1 / 1.12, 1, 1.0))
    head = su(cranium, occiput, k=0.2)
    head = su(head, zyg, brow, k=0.12)
    head = su(head, muzzle, bridge, flews, k=0.14)
    head = su(head, jaw, k=0.1)
    gap = E((0, -2.44, 3.848), (0.36, 0.52, 0.034), rot=(4, 0, 0))
    head = sdf.smooth_subtract(head, gap, k=0.02)
    for e in (EYE.values() if dishes else ()):
        f = eye_facing(e)
        dish = sdf.sphere(T(e + f * 0.025), 0.068)
        head = sdf.smooth_subtract(head, dish, k=0.03)
    return head


def leg_shapes():
    E, RC, su, M, sph = sdf.ellipsoid, sdf.round_cone, sdf.smooth_union, sdf.mirror_x, sdf.sphere
    hip, knee, foot = LEGS["FL"]
    up = RC(T(hip + V(0, 0, -0.1)), T(knee), 0.4, 0.3)
    fore = RC(T(knee), (0.66, -0.95, 0.5), 0.29, 0.19)
    past = RC((0.66, -0.95, 0.5), (0.68, -1.08, 0.22), 0.19, 0.19)
    paw = PAW["FL"]
    pad = E(T(paw), (0.37, 0.41, 0.17))
    toes = [sph(T(t), 0.125) for t in toe_centers("FL")]
    heel = sph((0.68, -0.88, 0.14), 0.12)
    front = M(su(su(su(up, fore, k=0.14), past, k=0.1), su(su(pad, heel, k=0.07), *toes, k=0.035), k=0.12))

    hip, knee, foot = LEGS["BL"]
    hock = HOCK["BL"]
    thigh = RC(T(hip + V(0, 0, -0.08)), T(knee), 0.5, 0.3)
    shin = RC(T(knee), T(hock + V(0, -0.02, 0)), 0.34, 0.19)
    point = sph(T(hock + V(0, 0.08, 0.02)), 0.14)
    meta = RC(T(hock), (0.7, 2.13, 0.26), 0.19, 0.18)
    paw = PAW["BL"]
    pad = E(T(paw), (0.34, 0.38, 0.17))
    toes = [sph(T(t), 0.115) for t in toe_centers("BL")]
    heel = sph((0.7, 2.26, 0.14), 0.12)
    hind = M(su(su(su(thigh, shin, k=0.14), point, meta, k=0.08), su(su(pad, heel, k=0.07), *toes, k=0.035), k=0.12))
    return front, hind


def toe_centers(leg):
    p = PAW[leg]
    front = leg[0] == "F"
    ty = -0.34 if front else -0.3
    spread = 0.255 if front else 0.235
    out = []
    for i, dx in enumerate((-spread, -spread / 2.9, spread / 2.9, spread)):
        back = 0.08 if i in (0, 3) else 0.0
        out.append(p + V(dx, ty + back, -0.03))
    return out


def body_shape():
    """The coat mass, not the skeleton: the sheet's wolf is mostly fur, so the SDF already carries
    the mane hump, chest ruff and heavy thighs; the clumps only add the ragged outer layer."""
    E, RC, su, M = sdf.ellipsoid, sdf.round_cone, sdf.smooth_union, sdf.mirror_x
    chest = E((0, -0.72, 2.86), (0.86, 1.02, 0.86))
    withers = E((0, -0.45, 3.4), (0.78, 0.9, 0.52))
    waist = E((0, 0.78, 3.08), (0.76, 0.95, 0.52))
    hips = E((0, 1.98, 3.02), (0.8, 0.8, 0.64))
    torso = su(chest, withers, waist, hips, k=0.45)
    scap = M(E((0.5, -0.8, 2.8), (0.36, 0.55, 0.76), rot=(-14, 0, 0)))
    thigh = M(E((0.48, 2.0, 2.56), (0.42, 0.72, 0.82), rot=(-24, 0, 0)))
    torso = su(torso, scap, thigh, k=0.3)
    neck = RC((0, -0.78, 3.32), (0, -1.55, 4.2), 0.66, 0.46)
    mane = E((0, -0.85, 3.98), (0.84, 0.86, 0.84), rot=(-35, 0, 0))
    throat = E((0, -1.5, 3.25), (0.56, 0.42, 0.66), rot=(-15, 0, 0))
    brisket = E((0, -1.25, 2.42), (0.64, 0.52, 0.52))
    body = su(torso, neck, mane, k=0.4)
    body = su(body, throat, brisket, k=0.35)
    body = su(body, head_shape(), k=0.26)
    front, hind = leg_shapes()
    body = su(body, front, k=0.22)
    body = su(body, hind, k=0.22)
    tail = creatures.chain_shape(TAIL_PTS, TAIL_R, k=0.1)
    return su(body, tail, k=0.22)


def eye_facing(e):
    side = 1.0 if e.x > 0 else -1.0
    return V(0.26 * side, -1.0, 0.06).normalized()


# ═══ MESH ACCUMULATOR ══════════════════════════════════════════════════════════

class Acc:
    """Collects verts/faces/per-vertex sRGB colour/per-vertex bone weights for one output mesh."""

    def __init__(self, bones):
        self.bones = bones
        self.bi = {b: i for i, b in enumerate(bones)}
        self.V, self.F, self.C, self.W = [], [], [], []
        self.N = {}

    def add(self, verts, faces, cols, weights, normals=None):
        o = len(self.V)
        if normals is not None:
            self.N.update({o + i: Vector(nv).normalized() for i, nv in enumerate(normals)})
        self.V.extend([T(v) for v in verts])
        self.F.extend([tuple(i + o for i in f) for f in faces])
        if isinstance(cols, tuple) and len(cols) == 3 and not isinstance(cols[0], (tuple, list)):
            cols = [cols] * len(verts)
        self.C.extend(cols)
        if isinstance(weights, str):
            row = np.zeros(len(self.bones), dtype=np.float32)
            row[self.bi[weights]] = 1.0
            self.W.append(np.repeat(row[None, :], len(verts), axis=0))
        else:
            self.W.append(np.asarray(weights, dtype=np.float32).reshape(len(verts), len(self.bones)))

    def tris(self):
        return sum(len(f) - 2 for f in self.F)

    def build(self, name, arm):
        self.V = [(x, y, max(z, 0.0)) for x, y, z in self.V]
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.V, [], self.F)
        me.update()
        me.shade_smooth()
        if self.N:
            vn = [v.normal.copy() for v in me.vertices]
            for i, nv in self.N.items():
                vn[i] = nv
            me.normals_split_custom_set_from_vertices(vn)
        obj = bpy.data.objects.new(name, me)
        fk.link(obj)
        ca = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        me.color_attributes.active_color = ca
        try:
            me.color_attributes.render_color_index = me.color_attributes.find("Col")
        except Exception:
            pass
        vi = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", vi)
        C = np.asarray(self.C, dtype=np.float32)
        rgba = np.concatenate([C[vi], np.ones((len(vi), 1), dtype=np.float32)], axis=1)
        ca.data.foreach_set("color_srgb", rgba.ravel())
        W = np.concatenate(self.W, axis=0) if self.W else np.zeros((0, len(self.bones)))
        write_weights(obj, W, self.bones)
        obj.parent = arm
        obj.matrix_parent_inverse = arm.matrix_world.inverted()
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        return obj


def write_weights(obj, W, bones, max_inf=4):
    W = prune(W, max_inf)
    used = np.where(W.max(axis=0) > 0.0)[0]
    for j in used:
        g = obj.vertex_groups.new(name=bones[j])
        col = W[:, j]
        idx = np.where(col > 0.0)[0]
        # group identical weights to cut add() calls
        q = np.round(col[idx] * 1000).astype(np.int32)
        for val in np.unique(q):
            sel = idx[q == val]
            g.add(sel.tolist(), float(val) / 1000.0, "REPLACE")


def prune(W, k=4, floor=0.02):
    W = np.array(W, dtype=np.float64)
    if len(W) == 0:
        return W
    if W.shape[1] > k:
        cut = np.sort(W, axis=1)[:, -k][:, None]
        W = np.where(W >= cut, W, 0.0)
    W = np.where(W >= floor, W, 0.0)
    s = W.sum(axis=1, keepdims=True)
    s[s == 0] = 1.0
    return W / s


# ═══ GEOMETRY BUILDERS ═══════════════════════════════════════════════════════

def tube(points, radii, sides=8, ref_side=(1, 0, 0), sx=1.0, sy=1.0, cap_start=False):
    """Tube through points; radii[-1] == 0 closes it to a point. Returns verts, faces, ring_index."""
    pts = [Vector(p) for p in points]
    n = len(pts)
    tans = [(pts[min(n - 1, i + 1)] - pts[max(0, i - 1)]).normalized() for i in range(n)]
    side = Vector(ref_side)
    verts, faces, rings, ring_of = [], [], [], []
    for i in range(n):
        t = tans[i]
        s = side - t * side.dot(t)
        if s.length < 1e-6:
            s = t.orthogonal()
        side = s.normalized()
        up = t.cross(side)
        r = radii[i]
        if r <= 1e-6 and i == n - 1:
            rings.append([len(verts)])
            verts.append(pts[i])
            ring_of.append(i)
            continue
        ring = []
        for k in range(sides):
            a = 2 * math.pi * k / sides
            ring.append(len(verts))
            verts.append(pts[i] + side * (math.cos(a) * r * sx) + up * (math.sin(a) * r * sy))
            ring_of.append(i)
        rings.append(ring)
    for i in range(n - 1):
        A, B = rings[i], rings[i + 1]
        if len(B) == 1:
            for k in range(sides):
                faces.append((A[k], A[(k + 1) % sides], B[0]))
        else:
            for k in range(sides):
                faces.append((A[k], A[(k + 1) % sides], B[(k + 1) % sides], B[k]))
    if cap_start:
        faces.append(tuple(reversed(rings[0])))
    return verts, faces, ring_of


def curve(points, n):
    """Catmull-Rom resample through control points to n points."""
    P = [Vector(p) for p in points]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    segs = len(P) - 3
    out = []
    for j in range(n):
        u = j / (n - 1) * segs
        i = min(int(u), segs - 1)
        t = u - i
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out


def ellipsoid_mesh(center, radii, basis=None, seg=16, rings=10):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    verts = [v.co.copy() for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    B = basis or Matrix.Identity(3)
    out = [Vector(center) + B @ Vector((v.x * radii[0], v.y * radii[1], v.z * radii[2])) for v in verts]
    return out, faces


def sdf_geometry(name, shape, voxel, tris):
    obj = sdf.to_mesh(name, shape, voxel=voxel)
    obj = fk.decimate_to(obj, tris)
    me = obj.data
    verts = [v.co.copy() for v in me.vertices]
    faces = [tuple(p.vertices) for p in me.polygons]
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(me)
    return verts, faces


# ═══ BODY SURFACE (weights live here; everything else borrows them) ════════════

class Body:
    def __init__(self, verts, faces):
        self.P = np.array([T(v) for v in verts], dtype=np.float64)
        tri = []
        for f in faces:
            for i in range(1, len(f) - 1):
                tri.append((f[0], f[i], f[i + 1]))
        self.tri = np.array(tri, dtype=np.int64)
        self.faces = [tuple(t) for t in self.tri]
        a, b, c = (self.P[self.tri[:, i]] for i in range(3))
        fn = np.cross(b - a, c - a)
        self.area = 0.5 * np.linalg.norm(fn, axis=1)
        vn = np.zeros_like(self.P)
        for i in range(3):
            np.add.at(vn, self.tri[:, i], fn)
        self.N = vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-9)
        self.bvh = BVHTree.FromPolygons([T(p) for p in self.P], self.faces)
        e = np.concatenate([self.tri[:, [0, 1]], self.tri[:, [1, 2]], self.tri[:, [2, 0]]])
        e = np.sort(e, axis=1)
        self.edges = np.unique(e, axis=0)
        self.W = None

    def nearest(self, p):
        """(location, smooth normal, weights row) of the closest surface point."""
        loc, _, idx, _ = self.bvh.find_nearest(Vector(p))
        if loc is None:
            return None
        ia, ib, ic = self.tri[idx]
        a, b, c = self.P[ia], self.P[ib], self.P[ic]
        bc = barycentric(np.array(T(loc)), a, b, c)
        n = bc[0] * self.N[ia] + bc[1] * self.N[ib] + bc[2] * self.N[ic]
        n = Vector(n).normalized()
        w = None
        if self.W is not None:
            w = bc[0] * self.W[ia] + bc[1] * self.W[ib] + bc[2] * self.W[ic]
        return loc, n, w

    def raycast(self, origin, direction):
        loc, _, idx, _ = self.bvh.ray_cast(Vector(origin), Vector(direction).normalized(), 50.0)
        if loc is None:
            return None
        ia, ib, ic = self.tri[idx]
        bc = barycentric(np.array(T(loc)), self.P[ia], self.P[ib], self.P[ic])
        n = Vector(bc[0] * self.N[ia] + bc[1] * self.N[ib] + bc[2] * self.N[ic]).normalized()
        return loc, n


def barycentric(p, a, b, c):
    v0, v1, v2 = b - a, c - a, p - a
    d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
    d20, d21 = v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-14:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    bc = np.clip(np.array([1 - v - w, v, w]), 0, 1)
    return bc / max(bc.sum(), 1e-9)


# ═══ SKIN WEIGHTS ════════════════════════════════════════════════════════════

def seg_dist_np(P, a, b):
    a = np.asarray(T(a))
    b = np.asarray(T(b))
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1), t


def poly_param_np(P, pts):
    """distance to polyline + global parameter 0..1 along it."""
    best = np.full(len(P), 1e9)
    par = np.zeros(len(P))
    n = len(pts) - 1
    for i in range(n):
        d, t = seg_dist_np(P, pts[i], pts[i + 1])
        m = d < best
        best[m] = d[m]
        par[m] = (i + t[m]) / n
    return best, par


def tail_weights_np(par, bones):
    """Parametric Tail1-4 weights (hat functions), Root near the base."""
    bi = {b: i for i, b in enumerate(bones)}
    W = np.zeros((len(par), len(bones)))
    u = np.clip(par, 0, 1) * 4.0
    for i in range(4):
        c = i + 0.5
        w = np.clip(1.0 - np.abs(u - c), 0, 1)
        if i == 0:
            w = np.where(u < c, 1.0, w)
        if i == 3:
            w = np.where(u > c, 1.0, w)
        W[:, bi[f"Tail{i + 1}"]] = w
    root = smooth01(0.3, 0.0, u) * 0.9
    W *= (1 - root)[:, None]
    W[:, bi["Root"]] += root
    return W / np.maximum(W.sum(axis=1, keepdims=True), 1e-9)


def body_weights(body, bones):
    P = body.P
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    bi = {b: i for i, b in enumerate(bones)}
    W = np.zeros((len(P), len(bones)))

    def put(name, d, r, mask):
        de = np.maximum(d - r, 0.0) + 0.25 * d
        W[:, bi[name]] += mask / (1e-3 + (de / 0.3) ** 4)

    put("Root", seg_dist_np(P, (0, 0.3, 2.95), (0, 2.35, 3.0))[0], 0.5, smooth01(-0.9, -0.2, y))
    put("Spine", seg_dist_np(P, (0, 0.3, 3.05), (0, -1.0, 3.3))[0], 0.55, smooth01(2.3, 1.5, y))
    put("Neck", seg_dist_np(P, (0, -0.95, 3.5), (0, -1.55, 4.15))[0], 0.38, smooth01(0.3, -0.5, y))
    put("Head", seg_dist_np(P, (0, -1.62, 4.38), (0, -2.55, 4.08))[0], 0.3, smooth01(-1.2, -1.55, y))
    for leg, (hip, knee, foot) in LEGS.items():
        sgn = 1.0 if hip.x > 0 else -1.0
        side = smooth01(0.06, 0.3, x * sgn)
        if leg[0] == "F":
            put(f"Leg{leg}1", seg_dist_np(P, hip, knee)[0], 0.2, side * smooth01(3.1, 2.55, z))
            put(f"Leg{leg}2", seg_dist_np(P, knee, foot)[0], 0.14, side * smooth01(2.2, 1.85, z))
        else:
            put(f"Leg{leg}1", seg_dist_np(P, hip, knee)[0], 0.26, side * smooth01(3.3, 2.8, z))
            d2 = np.minimum(seg_dist_np(P, knee, HOCK[leg])[0], seg_dist_np(P, HOCK[leg], foot)[0])
            put(f"Leg{leg}2", d2, 0.12, side * smooth01(2.0, 1.7, z))
    W /= np.maximum(W.sum(axis=1, keepdims=True), 1e-12)

    # tail: parametric along the chain, faded in past the rump
    dt, par = poly_param_np(P, TAIL_PTS)
    m_tail = smooth01(2.5, 2.8, y) * smooth01(0.55, 0.35, dt)
    W = W * (1 - m_tail)[:, None] + tail_weights_np(par, bones) * m_tail[:, None]

    # Laplacian smoothing over the surface: soft shoulders/hips, clean neck bend
    E = body.edges
    deg = np.bincount(E.ravel(), minlength=len(P)).astype(np.float64)
    for _ in range(14):
        acc = np.zeros_like(W)
        np.add.at(acc, E[:, 0], W[E[:, 1]])
        np.add.at(acc, E[:, 1], W[E[:, 0]])
        W = 0.5 * W + 0.5 * acc / np.maximum(deg, 1)[:, None]

    # jaw: everything under the snarl line, ahead of the hinge
    mz = 3.85 - (-(y) - 1.9) * 0.02
    w_jaw = smooth01(mz + 0.012, mz - 0.03, z) * smooth01(-1.74, -1.96, y) * smooth01(0.34, 0.24, ax) * smooth01(3.5, 3.62, z)
    W *= (1 - w_jaw)[:, None]
    W[:, bi["Jaw"]] += w_jaw
    # cheeks puff with the chew; belly breathes a little
    for s, name in ((1, "CheekL"), (-1, "CheekR")):
        c = np.array(T(SOCK["cheek" + name[-1]]))
        w = 0.45 * np.exp(-np.sum((P - c) ** 2, axis=1) / (0.2 ** 2)) * smooth01(0.05, 0.2, x * s)
        W *= (1 - w)[:, None]
        W[:, bi[name]] += w
    wb = 0.3 * smooth01(2.55, 2.2, z) * smooth01(-0.7, -0.3, y) * smooth01(1.5, 1.1, y) * smooth01(0.5, 0.2, ax)
    W *= (1 - wb)[:, None]
    W[:, bi["Belly"]] += wb
    body.W = prune(W, 4)
    return body.W


# ═══ FUR CLUMPS ══════════════════════════════════════════════════════════════

def dist_seg(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared == 0 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (p - (a + ab * t)).length, t


def dist_poly(p, pts):
    best, par = 1e9, 0.0
    n = len(pts) - 1
    for i in range(n):
        d, t = dist_seg(p, pts[i], pts[i + 1])
        if d < best:
            best, par = d, (i + t) / n
    return best, par


def tail_frame(par):
    n = len(TAIL_PTS) - 1
    u = min(max(par, 0.0), 1.0) * n
    i = min(int(u), n - 1)
    t = u - i
    c = TAIL_PTS[i].lerp(TAIL_PTS[i + 1], t)
    tan = (TAIL_PTS[i + 1] - TAIL_PTS[i]).normalized()
    r = TAIL_R[i] * (1 - t) + TAIL_R[i + 1] * t
    back = V(0, 1, 0.35)
    back = (back - tan * back.dot(tan)).normalized()
    side = tan.cross(back).normalized()
    return c, tan, back, side, r


def fur_params(p, n):
    """Region -> clump parameters, or None where the sheet shows smooth fur/skin.
    Locks lie low (the sheet's fur is layered, not bristling) and flick out at the tips."""
    x, y, z = p
    ax = abs(x)
    sd = 1.0 if x >= 0 else -1.0
    ss = smooth01

    # ── tail ──────────────────────────────────────────────────────────────
    dt, tt = dist_poly(p, TAIL_PTS)
    if y > 2.55 and dt < 0.6 and (tt > 0.1 or y > 2.85):
        c, tan, back, side, r = tail_frame(tt)
        radial = (p - c)
        radial = (radial - tan * radial.dot(tan)).normalized()
        g = tan + radial * 0.1
        root = ss(0.22, 0.02, tt)   # lie flat over the rump where the tail leaves it: no ledge
        return dict(kind="tail", g=g, lift=(13 + 11 * math.sin(math.pi * min(tt, 1.0))) * (1 - 0.7 * root),
                    L=(0.66 + 0.3 * math.sin(math.pi * (0.15 + 0.75 * tt))) * (1 - 0.25 * root),
                    W=0.44, space=0.15, tip=TAIL_TIP, bend=0.14, droop=0.0, prio=4, tt=tt)

    # ── head ──────────────────────────────────────────────────────────────
    if y < -1.42 and z > 3.5:
        for e in EYE.values():
            if (p - e).length < 0.24:
                return None
        for b in EAR_BASE.values():
            if (p - b).length < 0.15:
                return None
        if y < -2.02 and z > 3.7:
            return None  # muzzle and face stay smooth
        if z > 4.46 and ax < 0.3 and y < -1.75:
            return dict(kind="brow", g=V(sd * 0.15, 1, 0.2), lift=6, L=0.2, W=0.13, space=0.085, tip=FUR_TIP, bend=0.08, droop=0, prio=4)
        if z > 4.56 and ax < 0.42:
            k = ss(-2.0, -1.5, y)
            return dict(kind="crown", g=V(sd * 0.25, 1, 0.45), lift=18, L=0.22 + 0.2 * k, W=0.18 + 0.08 * k, space=0.1, tip=FUR_TIP, bend=0.12,
                        droop=0, prio=4)
        if ax > 0.2 and y > -2.0 and 3.62 < z < 4.5:
            k = ss(-2.05, -1.58, y)
            return dict(kind="cheek", g=V(sd * 1.0, 0.5, -0.3), lift=30, L=0.42 + 0.4 * k, W=0.22 + 0.08 * k, space=0.09, tip=FUR_TIP,
                        bend=0.14, droop=0.04, prio=5)
        if z >= 4.4 and y > -2.0:
            return dict(kind="headside", g=V(sd * 0.45, 1, 0.1), lift=14, L=0.3, W=0.18, space=0.1, tip=FUR_TIP, bend=0.1, droop=0, prio=4)
        if z < 3.82:
            k = ss(-2.3, -1.6, y)
            return dict(kind="beard", g=V(0, 0.3, -1), lift=18, L=0.32 + 0.3 * k, W=0.2, space=0.1, tip=FUR_TIP, bend=0.08, droop=0.08, prio=4)
        return None

    # ── legs below the torso ──────────────────────────────────────────────
    for leg, (hip, knee, foot) in LEGS.items():
        if (x > 0) != (hip.x > 0):
            continue
        front = leg[0] == "F"
        zc = 2.0 if front else 1.9
        if z > zc:
            continue
        chain = [knee, foot] if front else [knee, HOCK[leg], foot]
        d, _ = dist_poly(p, chain)
        if d > 0.55:
            continue
        if z < 0.55:
            return None
        if n.y > 0.1 and z > (0.75 if front else 0.62):
            k = ss(0.8, 1.9, z) if front else ss(0.6, 1.7, z)
            return dict(kind="feather", g=V(sd * 0.15, 0.6, -1), lift=24, L=0.28 + 0.2 * k, W=0.24, space=0.11, tip=FUR_TIP,
                        bend=0.14, droop=0.05, prio=3)
        low = ss(1.05, 0.55, z)
        return dict(kind="legside", g=V(sd * 0.08, 0.12, -1), lift=17 - 9 * low, L=0.24 + 0.1 * ss(0.4, 1.6, z) - 0.06 * low, W=0.22 - 0.05 * low,
                    space=0.13, tip=FUR_TIP,
                    bend=0.1, droop=0, prio=2)

    # ── neck + mane + chest ruff ──────────────────────────────────────────
    front_facing = n.y < -0.2 or n.z < -0.3
    if y < -0.5 and 1.62 < z < 3.95 and front_facing and ax < 1.0:
        k = ss(3.6, 2.1, z)
        return dict(kind="ruff", g=V(sd * 0.2, 0.35, -1), lift=14 + 8 * k, L=0.5 + 0.22 * k, W=0.4, space=0.15, tip=FUR_TIP,
                    bend=0.14, droop=0.05, prio=5)
    if -1.85 < y < 0.7 and z > 2.95:
        crest_peak = math.exp(-((y + 0.7) / 0.8) ** 2)
        fade = ss(0.7, 0.0, y)
        near_head = 0.42 + 0.58 * ss(-1.75, -0.95, y)
        if n.z > 0.35 and z > 3.5:
            return dict(kind="crest", g=V(sd * 0.1, 1, 0.18), lift=(16 + 8 * max(0.0, n.z - 0.5)) * (0.55 + 0.45 * ss(-1.6, -1.0, y)),
                        L=(0.66 + 0.42 * crest_peak) * (0.7 + 0.3 * fade) * near_head, W=0.42, space=0.15, tip=FUR_TIP, bend=0.2, droop=0.0, prio=6)
        return dict(kind="mane", g=V(sd * 0.2, 1, -0.55 - 0.35 * ss(3.8, 4.4, z)), lift=8 + 5 * ss(3.2, 3.8, z) - 5 * ss(3.8, 4.4, z), L=(0.64 + 0.3 * crest_peak) * (0.78 + 0.22 * fade) * near_head, W=0.42,
                    space=0.15, tip=FUR_TIP, bend=0.16, droop=0.06, prio=6)

    # ── shoulders / upper forelegs ────────────────────────────────────────
    if -1.4 < y < 0.2 and 1.7 < z <= 2.95 and ax > 0.45:
        return dict(kind="shoulder", g=V(sd * 0.3, 0.45, -1), lift=12, L=0.52 + 0.14 * ss(2.9, 2.0, z), W=0.38, space=0.16, tip=FUR_TIP,
                    bend=0.14, droop=0.05, prio=4)

    # ── belly ─────────────────────────────────────────────────────────────
    if -0.7 < y < 1.5 and n.z < -0.35 and z < 2.8:
        return dict(kind="belly", g=V(sd * 0.15, 0.6, -1), lift=16, L=0.34 + 0.1 * ss(1.3, 0.0, y), W=0.32, space=0.15, tip=FUR_TIP,
                    bend=0.12, droop=0.08, prio=3)

    # ── rump + thighs ─────────────────────────────────────────────────────
    if y >= 1.3 and z > 1.6:
        if n.y > 0.45:
            return dict(kind="haunch", g=V(sd * 0.3, 0.6, -1), lift=18, L=0.58, W=0.38, space=0.16, tip=FUR_TIP, bend=0.14, droop=0.05, prio=4)
        if n.z > 0.55:
            return dict(kind="back", g=V(sd * 0.15, 1, -0.35 * ss(2.0, 2.6, y)), lift=11 - 6 * ss(2.0, 2.6, y), L=0.58 + 0.2 * ss(2.0, 2.6, y), W=0.4, space=0.16, tip=FUR_TIP, bend=0.12, droop=0, prio=5)
        return dict(kind="thigh", g=V(sd * 0.12, 0.55, -1), lift=10, L=0.5, W=0.36, space=0.17, tip=FUR_TIP, bend=0.12, droop=0.03, prio=3)

    # ── back + flank ──────────────────────────────────────────────────────
    if n.z > 0.5:
        return dict(kind="back", g=V(sd * 0.15, 1, -0.05), lift=10 + 5 * ss(1.4, 0.4, y), L=0.62 - 0.06 * ss(0.6, 1.4, y), W=0.4, space=0.16,
                    tip=FUR_TIP, bend=0.12, droop=0.02, prio=5)
    return dict(kind="flank", g=V(sd * 0.1, 1, -0.5), lift=10, L=0.56, W=0.4, space=0.16, tip=FUR_TIP, bend=0.12, droop=0.03, prio=4)


def sample_clumps(body, rng, density=1.0, n_candidates=26000):
    prob = body.area / body.area.sum()
    idx = rng.choice(len(body.tri), n_candidates, p=prob)
    r1, r2 = rng.random(n_candidates), rng.random(n_candidates)
    s = np.sqrt(r1)
    bary = np.stack([1 - s, s * (1 - r2), s * r2], axis=1)
    tri = body.tri[idx]
    P = np.einsum("ij,ijk->ik", bary, body.P[tri])
    N = np.einsum("ij,ijk->ik", bary, body.N[tri])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    grid = {}
    cell = 0.2
    specs = []
    for i in range(n_candidates):
        p = Vector(P[i])
        n = Vector(N[i])
        fp = fur_params(p, n)
        if fp is None:
            continue
        space = fp["space"] / density
        key = (int(math.floor(p.x / cell)), int(math.floor(p.y / cell)), int(math.floor(p.z / cell)))
        reach = int(math.ceil(space / cell))
        ok = True
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for dz in range(-reach, reach + 1):
                    for q in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if (q - p).length < space:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                break
        if not ok:
            continue
        grid.setdefault(key, []).append(p)
        fp["p"], fp["n"] = p, n
        specs.append(fp)
    return specs


def finalize_clump(sp, rng):
    """Turn region params into a concrete bent spike: centreline fn, frame, sizes (jittered)."""
    p, n = sp["p"], sp["n"]
    g = sp["g"]
    t = g - n * g.dot(n)
    if t.length < 1e-3:
        t = V(0, 1, 0) - n * n.y
    t.normalize()
    yaw = math.radians(rng.uniform(-17, 17))
    t = Quaternion(n, yaw) @ t
    lift = math.radians(sp["lift"] + rng.uniform(-5, 5))
    d = (t * math.cos(lift) + n * math.sin(lift)).normalized()
    sv = n.cross(d)
    if sv.length < 1e-4:
        sv = d.orthogonal()
    sv.normalize()
    sv = Quaternion(d, math.radians(rng.uniform(-25, 25))) @ sv
    L = sp["L"] * rng.uniform(0.8, 1.2)
    W = sp["W"] * rng.uniform(0.85, 1.15)
    sp.update(d=d, sv=sv, up=d.cross(sv).normalized(), L=L, W=W, Th=W * rng.uniform(0.2, 0.28),
              base=p - n * min(0.05, 0.15 * W), tipk=rng.uniform(0.7, 1.3), curl=sp["bend"] * rng.uniform(0.5, 1.5))
    return sp


def clump_center(sp, s):
    L = sp["L"]
    return sp["base"] + sp["d"] * (L * s) + sp["up"] * (sp["curl"] * L * s * s) + V(0, 0, -sp["droop"] * L * s * s)


def clump_geometry(sp):
    """A leaf-like spike with a triangular section (ridge on top, flat belly): 9 or 15 tris."""
    L = sp["L"]
    ss = [0.0, 0.34, 0.68] if L > 0.42 else [0.0, 0.5]
    prof = {0.0: 0.8, 0.34: 1.0, 0.68: 0.62, 0.5: 0.82}
    pts = [clump_center(sp, s) for s in ss] + [clump_center(sp, 1.0)]
    verts, faces, cols, rings, nrm = [], [], [], [], []
    tipc = tuple(min(1.0, c * sp["tipk"]) for c in sp["tip"])
    for i, s in enumerate(ss):
        c = pts[i]
        tan = (pts[i + 1] - c).normalized()
        side = sp["sv"] - tan * sp["sv"].dot(tan)
        side.normalize()
        up = tan.cross(side)
        w = sp["W"] * prof[s] * 0.5
        h = sp["Th"] * (1 - 0.5 * s) * 0.5
        k2 = s ** 1.1
        col = tuple(FUR_ROOT[j] * (1 - k2) + tipc[j] * k2 for j in range(3))
        ring = []
        for k, off in enumerate((side * w - up * h * 0.35, up * h, -side * w - up * h * 0.35)):
            ring.append(len(verts))
            verts.append(c + off)
            cols.append(col if k == 1 else tuple(v * 0.72 for v in col))
            nrm.append((sp["n"] * 0.72 + off.normalized() * 0.28).normalized())
        rings.append(ring)
    tip = len(verts)
    verts.append(pts[-1])
    cols.append(tipc)
    nrm.append((sp["n"] * 0.8 + sp["d"] * 0.2).normalized())
    sp["_normals"] = nrm
    for A, B in zip(rings[:-1], rings[1:]):
        for k in range(3):
            faces.append((A[k], A[(k + 1) % 3], B[(k + 1) % 3], B[k]))
    A = rings[-1]
    for k in range(3):
        faces.append((A[k], A[(k + 1) % 3], tip))
    return verts, faces, cols


def keep_above_ground(sp, floor=0.03):
    """Shorten a clump until its whole geometry clears the ground; drop it if that leaves a stub."""
    L0 = sp["L"]
    for _ in range(8):
        v, _, _ = clump_geometry(sp)
        if min(q.z for q in v) >= floor:
            return True
        sp["L"] *= 0.8
    sp["L"] = L0
    return False


def clump_tris(sp):
    return 15 if sp["L"] > 0.42 else 9


# ═══ GLOW MARKINGS (traced from the sheet, per view) ═════════════════════════════
# view: "side" (y, z) cast from +X (mirror casts from -X) · "front" (x, z) from -Y ·
# "top" (x, y) from above · "back" (x, z) from +Y. Branch = (index on the main line, points).

MARKS = [
    # neck: two flames from under the ear down the side of the neck toward the chest
    ("side", True, 0.12, [(-1.12, 4.36), (-1.28, 4.02), (-1.36, 3.62)], []),
    ("side", True, 0.14, [(-1.26, 3.56), (-1.42, 3.18), (-1.48, 2.78)], [(1, [(-1.24, 3.04)])]),
    # cheek flick from the eye back
    ("side", True, 0.065, [(-1.98, 4.4), (-1.78, 4.34), (-1.52, 4.3)], []),
    # shoulder: three parallel slashes, withers down toward the elbow
    ("side", True, 0.17, [(0.0, 3.78), (-0.24, 3.3), (-0.5, 2.66)], [(1, [(-0.02, 3.02)])]),
    ("side", True, 0.12, [(-0.34, 3.82), (-0.52, 3.44), (-0.72, 3.02)], []),
    ("side", True, 0.1, [(0.3, 3.5), (0.12, 3.18), (-0.06, 2.9)], []),
    # foreleg
    ("side", True, 0.12, [(-0.5, 1.92), (-0.62, 1.4), (-0.78, 0.84)], [(1, [(-0.46, 1.2)])]),
    # ribs
    ("side", True, 0.09, [(0.14, 2.72), (0.4, 2.9), (0.62, 3.12)], []),
    # back of the thigh, down the gaskin toward the hock
    ("side", True, 0.13, [(2.36, 2.74), (2.46, 2.2), (2.28, 1.64), (2.22, 1.2)], []),
    # forehead flame between the eyes
    ("front", False, 0.095, [(0.0, 4.38), (0.0, 4.58), (0.0, 4.84)], [(1, [(0.1, 4.68)]), (1, [(-0.1, 4.68)])]),
    # chest flames (front view)
    ("front", True, 0.15, [(0.66, 3.58), (0.54, 3.3), (0.44, 3.04)], []),
    ("front", True, 0.2, [(0.72, 2.98), (0.58, 2.62), (0.38, 2.22)], [(1, [(0.74, 2.5)])]),
    # forearms (front view)
    ("front", True, 0.15, [(0.6, 1.6), (0.66, 1.3), (0.72, 1.0)], []),
    # spine (top view), in three flames
    ("top", False, 0.09, [(0, -1.85), (0, -1.15), (0, -0.4)], []),
    ("top", False, 0.09, [(0, -0.5), (0, 0.3), (0, 1.05)], []),
    ("top", False, 0.085, [(0, 0.95), (0, 1.75), (0, 2.6)], []),
]
# fishbone chevrons off the spine (top view): (y, length), small at the neck, longer mid-back
CHEVRONS = [(-1.45, 0.12), (-1.15, 0.15), (-0.85, 0.18), (-0.45, 0.22), (-0.05, 0.24), (0.4, 0.25), (0.85, 0.24), (1.3, 0.22), (1.75, 0.19), (2.15, 0.15)]


def cast_2d(body, view, u, v, sgn):
    if view == "side":
        return body.raycast((6.0 * sgn, u, v), (-sgn, 0, 0))
    if view == "front":
        return body.raycast((u * sgn, -8.0, v), (0, 1, 0))
    if view == "top":
        return body.raycast((u * sgn, v, 9.0), (0, 0, -1))
    if view == "back":
        return body.raycast((u * sgn, 8.0, v), (0, -1, 0))
    raise ValueError(view)


def resample2d(pts, step):
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(L / step)))
        for i in range(1, n + 1):
            t = i / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def stroke_paths():
    """All marking strokes as 2D polylines per view (branches become their own strokes)."""
    paths = []
    for view, mirror, width, pts, branches in MARKS:
        sides = (1.0, -1.0) if mirror else (1.0,)
        items = [(pts, width, "flame")]
        for idx, bpts in branches:
            items.append(([pts[idx]] + list(bpts), width * 0.72, "branch"))
        for sgn in sides:
            for p2, w, kind in items:
                paths.append((view, sgn, p2, w, kind))
    for y0, length in CHEVRONS:
        for sgn in (1.0, -1.0):
            pts = [(0.02, y0), (0.4 * length, y0 + 0.32 * length), (length, y0 + 0.9 * length)]
            paths.append(("top", sgn, pts, 0.07, "branch"))
    return paths


def project_strokes(body):
    strokes = []
    for view, sgn, pts, width, kind in stroke_paths():
        if len(pts) >= 3:
            pts = [(c.x, c.y) for c in curve([V(u, v, 0) for u, v in pts], 8 * len(pts))]
        dense = resample2d(pts, 0.04)
        run = []
        for u, v in dense:
            hit = cast_2d(body, view, u, v, sgn)
            if hit is None:
                if len(run) > 2:
                    strokes.append((run, width, kind))
                run = []
                continue
            run.append(hit)
        if len(run) > 2:
            strokes.append((run, width, kind))
    out = []
    for run, width, kind in strokes:
        # resample in 3D at ~0.06 and smooth the normals
        P = [Vector(h[0]) for h in run]
        N = [Vector(h[1]) for h in run]
        acc = [0.0]
        for a, b in zip(P[:-1], P[1:]):
            acc.append(acc[-1] + (b - a).length)
        total = acc[-1]
        if total < 0.08:
            continue
        m = max(3, int(total / 0.06) + 1)
        pts, nrm = [], []
        j = 0
        for i in range(m):
            s = total * i / (m - 1)
            while j < len(acc) - 2 and acc[j + 1] < s:
                j += 1
            t = (s - acc[j]) / max(acc[j + 1] - acc[j], 1e-9)
            pts.append(P[j].lerp(P[j + 1], t))
            nrm.append(N[j].lerp(N[j + 1], t).normalized())
        sm = []
        for i in range(m):
            a = nrm[max(0, i - 2): i + 3]
            sm.append(sum(a, Vector()).normalized())
        out.append(dict(pts=pts, nrm=sm, width=width, kind=kind, length=total))
    return out


def stroke_width(u, width, kind):
    """Flame profile: a soft start, fattest around a third of the way, a needle tip."""
    if kind == "branch":
        return width * (min(1.0, u / 0.15) ** 0.6) * ((1 - u) ** 1.1) * 1.35
    if u < 0.32:
        return width * (0.2 + 0.8 * math.sin(u / 0.32 * math.pi / 2))
    return width * ((1 - u) / 0.68) ** 1.15


def stroke_geometry(st):
    pts, nrm = st["pts"], st["nrm"]
    lifts = st.get("lift") or [0.05] * len(pts)
    m = len(pts)
    verts, faces = [], []
    rows = []
    for i in range(m):
        u = i / (m - 1)
        tan = (pts[min(m - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
        n = nrm[i]
        side = n.cross(tan).normalized()
        w = stroke_width(u, st["width"], st["kind"]) * 0.5
        c = pts[i] + n * lifts[i]
        if w < 0.004 and (i == 0 or i == m - 1):
            rows.append([len(verts)])
            verts.append(c + n * 0.01)
            continue
        rows.append([len(verts), len(verts) + 1, len(verts) + 2])
        verts += [c + side * w - n * 0.02, c + n * (0.012 + 0.3 * w), c - side * w - n * 0.02]
    for i in range(m - 1):
        A, B = rows[i], rows[i + 1]
        if len(A) == 3 and len(B) == 3:
            faces += [(A[0], A[1], B[1], B[0]), (A[1], A[2], B[2], B[1])]
        elif len(A) == 1 and len(B) == 3:
            faces += [(A[0], B[1], B[0]), (A[0], B[2], B[1])]
        elif len(A) == 3 and len(B) == 1:
            faces += [(A[0], A[1], B[0]), (A[1], A[2], B[0])]
    return verts, faces


def stroke_samples(strokes):
    out = []
    for st in strokes:
        m = len(st["pts"])
        for i, (p, n) in enumerate(zip(st["pts"], st["nrm"])):
            out.append((p, n, stroke_width(i / (m - 1), st["width"], st["kind"]) * 0.5))
    return out


def drop_rooted_in_strokes(specs, strokes):
    """A clump growing out of the skin right under a streak would stab through it: drop those."""
    from mathutils.kdtree import KDTree
    samples = stroke_samples(strokes)
    kd = KDTree(len(samples))
    for i, smp in enumerate(samples):
        kd.insert(smp[0], i)
    kd.balance()
    kept = []
    for sp in specs:
        hit = False
        for s in (0.0, 0.2):
            c = clump_center(sp, s)
            for (_, qi, _) in kd.find_range(c, 0.3):
                qp, qn, qw = samples[qi]
                rel = c - qp
                lat = (rel - qn * rel.dot(qn)).length
                if lat < qw + 0.035:
                    hit = True
                    break
            if hit:
                break
        if not hit:
            kept.append(sp)
    log(f"streak partings: dropped {len(specs) - len(kept)} clumps")
    return kept


def lift_strokes(strokes, clump_bvh, ceiling=0.26):
    """Float each streak on top of the local fur: cast down onto the clumps, max-filter, smooth, clamp."""
    for st in strokes:
        m = len(st["pts"])
        raw = []
        for i, (p, n) in enumerate(zip(st["pts"], st["nrm"])):
            tan = (st["pts"][min(m - 1, i + 1)] - st["pts"][max(0, i - 1)]).normalized()
            side = n.cross(tan).normalized()
            w = stroke_width(i / (m - 1), st["width"], st["kind"]) * 0.5
            h = 0.0
            loc, _, _, dist = clump_bvh.ray_cast(p + n * 0.8, -n, 0.8)
            if loc is not None:
                h = 0.8 - dist
            raw.append(min(max(h, 0.03), ceiling))
        sm = [sum(raw[max(0, i - 2): i + 3]) / len(raw[max(0, i - 2): i + 3]) for i in range(m)]
        st["lift"] = [h + 0.03 for h in sm]


def trim_over_strokes(specs, strokes):
    """Clumps whose locks pass OVER a lifted streak get cut short just before it."""
    from mathutils.kdtree import KDTree
    samples = []
    for st in strokes:
        m = len(st["pts"])
        for i, (p, n) in enumerate(zip(st["pts"], st["nrm"])):
            samples.append((p, n, stroke_width(i / (m - 1), st["width"], st["kind"]) * 0.5, st["lift"][i]))
    kd = KDTree(len(samples))
    for i, smp in enumerate(samples):
        kd.insert(smp[0], i)
    kd.balance()
    cut_n = drop_n = 0
    kept = []
    for sp in specs:
        cut = None
        for s in (0.3, 0.45, 0.6, 0.75, 0.9, 1.0):
            c = clump_center(sp, s)
            for (_, qi, _) in kd.find_range(c, 0.7):
                qp, qn, qw, ql = samples[qi]
                rel = c - qp
                h = rel.dot(qn)
                lat = (rel - qn * h).length
                if lat < qw + 0.02 + sp["W"] * 0.42 and h > ql - 0.05:
                    cut = s
                    break
            if cut is not None:
                break
        if cut is None:
            kept.append(sp)
            continue
        keep = cut - 0.12
        if keep < 0.35:
            drop_n += 1
            continue
        sp["L"] *= keep
        cut_n += 1
        kept.append(sp)
    log(f"streaks: {cut_n} clumps trimmed, {drop_n} dropped")
    return kept


def tail_glow_clumps(rng):
    """Glowing strands in the tail fur (two side flames + the spine line) and the brush tip."""
    out = []

    def add(tt, phi, lift, L, W, off):
        c, tan, back, side, r = tail_frame(tt)
        radial = back * math.cos(phi) + side * math.sin(phi)
        p = c + radial * (r + off)
        sp = dict(g=tan, lift=lift, L=L, W=W, bend=0.1, droop=0.0, tip=WHITE, p=p, n=radial, kind="tailglow", tt=tt)
        finalize_clump(sp, rng)
        sp["base"] = p
        out.append(sp)

    # two flames down the back of the tail that converge into the glowing tip (the sheet's BACK view)
    for i in range(8):
        tt = 0.08 + i * 0.09
        spread = 46 - 30 * (tt / 0.72)
        for sgn in (1, -1):
            add(tt + rng.uniform(-0.015, 0.015), math.radians(sgn * (spread + rng.uniform(-5, 5))), 13, 0.78, 0.2, 0.26)
    for i in range(4):
        add(0.1 + i * 0.16, rng.uniform(-0.08, 0.08), 12, 0.5, 0.11, 0.24)
    for i in range(18):
        phi = i / 18 * math.tau
        tt = rng.uniform(0.78, 0.93)
        add(tt, phi, 12 + rng.uniform(0, 10), 0.62 + rng.uniform(0, 0.25), 0.17, 0.04)
    return out


# ═══ PARTS: ears, lids, eyes, nose, mouth, fangs, claws ═════════════════════════════

def ear_geometry(side):
    """Tall pointed wolf ear: a cone with a concave opening facing forward-out. Returns
    verts, faces, colours and the ear's rotation (for the tufts)."""
    sd = 1.0 if side == "L" else -1.0
    base = EAR_BASE[side]
    height, width, depth = 0.72, 0.66, 0.5
    ctrl = [(-1, 0.05), (-0.72, -0.55), (-0.3, -0.35), (0.0, -0.1), (0.3, -0.35), (0.72, -0.55), (1, 0.05), (0.66, 0.62), (0, 0.85), (-0.66, 0.62)]
    outline = []
    for i in range(len(ctrl)):   # doubled outline, midpoints pushed out a little
        a, b = ctrl[i], ctrl[(i + 1) % len(ctrl)]
        outline.append(a)
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        r = math.hypot(mx, my) or 1.0
        bulge = 1.06 if my >= -0.2 else 1.0
        outline.append((mx * bulge, my * bulge))
    levels = [(0.0, 1.0), (0.18, 0.97), (0.38, 0.84), (0.58, 0.64), (0.76, 0.42), (0.9, 0.22)]
    R = Euler((math.radians(-8), math.radians(8 * sd), math.radians(26 * sd))).to_matrix()
    verts, faces, cols, rings = [], [], [], []
    for h, k in levels:
        ring = []
        for ox, oy in outline:
            local = V(ox * width * 0.5 * k + sd * 0.03 * h, oy * depth * 0.5 * (0.55 + 0.45 * k), h * height)
            ring.append(len(verts))
            verts.append(base + R @ local)
            inner = oy < -0.12 and abs(ox) < 0.62
            cols.append(INNER_EAR if inner and 0.08 < h < 0.8 else FUR_SKIN)
        rings.append(ring)
    tip = len(verts)
    verts.append(base + R @ V(sd * 0.05, 0.02, height * 1.02))
    cols.append(FUR_TIP)
    m = len(outline)
    for a, b in zip(rings[:-1], rings[1:]):
        for j in range(m):
            faces.append((a[j], a[(j + 1) % m], b[(j + 1) % m], b[j]))
    for j in range(m):
        faces.append((rings[-1][j], rings[-1][(j + 1) % m], tip))
    c = sum(verts, Vector()) / len(verts)
    f = faces[0]
    nrm = (verts[f[1]] - verts[f[0]]).cross(verts[f[2]] - verts[f[0]])
    if nrm.dot(verts[f[0]] - c) < 0:
        faces = [tuple(reversed(f)) for f in faces]
    return verts, faces, cols, R


def ear_tufts(side, R, rng):
    """Light fur inside the ear opening + dark tufts hiding the ear/skull seam (rigid to the ear)."""
    sd = 1.0 if side == "L" else -1.0
    base = EAR_BASE[side]
    out = []
    specs = [((-0.09, -0.06, 0.1), (0, -1, 0.1), (0.1, 0.1, 1), 22, 0.3, 0.12, H(0x55555E)),
             ((0.09, -0.06, 0.1), (0, -1, 0.1), (-0.1, 0.1, 1), 22, 0.3, 0.12, H(0x55555E)),
             ((0.0, -0.05, 0.24), (0, -1, 0.15), (0, 0.1, 1), 18, 0.26, 0.1, H(0x5C5C66))]
    for dx in (-0.22, -0.08, 0.08, 0.22):
        specs.append(((dx, 0.16, 0.06), (0, 1, 0.3), (dx * 1.5, 0.35, 1), 14, 0.28, 0.17, FUR_TIP))
    for dx in (-0.27, 0.27):
        specs.append(((dx, -0.02, 0.05), (math.copysign(1, dx), 0, 0.2), (dx * 2, 0.2, 1), 16, 0.26, 0.15, FUR_TIP))
    for loc, n, g, lift, L, W, tip in specs:
        n = (R @ V(*n)).normalized()
        sp = dict(p=base + R @ V(loc[0] * sd, loc[1], loc[2]), n=n, g=R @ V(g[0] * sd, g[1], g[2]), lift=lift, L=L, W=W, bend=0.1, droop=0.0,
                  tip=tip, kind="ear", prio=9)
        finalize_clump(sp, rng)
        out.append(sp)
    return out


def lid_geometry(side):
    """Upper-lid shell, rest pose OPEN (tucked up/back), exactly the creatures.py convention:
    the animator rotates LidX by -165 deg to close it."""
    e = EYE[side]
    r = 0.128
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -r * 0.12], context="VERTS")
    m = Matrix.Translation(e) @ Euler((math.radians(-78), 0, 0)).to_matrix().to_4x4() @ Matrix.Diagonal(V(1.0, 0.62, 0.66, 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.016)
    verts = [v.co.copy() for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return verts, faces


def eye_geometry(side):
    e = EYE[side]
    f = eye_facing(e)
    sd = 1.0 if side == "L" else -1.0
    ex = V(-f.y, f.x, 0).normalized()   # horizontal, along the face, toward the outer corner
    if ex.x * sd < 0:
        ex = -ex
    ez = f.cross(ex).normalized()
    if ez.z < 0:
        ez = -ez
    roll = Quaternion(f, math.radians(15 * sd))   # outer corner up: the angry slant
    ex, ez = roll @ ex, roll @ ez
    B = Matrix((ex, f, ez)).transposed()
    return ellipsoid_mesh(e, (0.122, 0.036, 0.04), B, seg=16, rings=8)


def fang_geometry(side):
    sd = 1.0 if side == "L" else -1.0
    root = V(0.232 * sd, -2.29, 4.03)
    ctrl = [root, root + V(-0.004 * sd, -0.04, -0.17), root + V(-0.02 * sd, -0.035, -0.36), root + V(-0.04 * sd, 0.0, -0.52),
            root + V(-0.05 * sd, 0.05, -0.62)]
    pts = curve(ctrl, 10)
    radii = [0.064 * (1 - (i / 9) ** 1.6) for i in range(10)]
    radii[-1] = 0.0
    return tube(pts, radii, sides=10, ref_side=(1, 0, 0), sx=0.72, sy=1.0, cap_start=True)


def claw_geometry(leg, toe):
    front = leg[0] == "F"
    base = toe + V(0, -0.05, 0.04)
    k = 1.22 if front else 1.1
    ctrl = [base, base + V(0, -0.1, 0.006) * k, base + V(0, -0.19, -0.04) * k, base + V(0, -0.235, -0.12) * k, base + V(0, -0.24, -0.165) * k]
    pts = curve(ctrl, 8)
    tip_z = pts[-1].z
    if tip_z < 0.004:
        pts = [q + V(0, 0, 0.004 - tip_z) for q in pts]
    radii = [r * k for r in (0.052, 0.049, 0.043, 0.035, 0.026, 0.017, 0.008, 0.0)]
    dark_v, dark_f, _ = tube(pts[:4], radii[:4], sides=7, ref_side=(1, 0, 0), sx=0.85, cap_start=False)
    gold_v, gold_f, _ = tube(pts[2:], radii[2:], sides=7, ref_side=(1, 0, 0), sx=0.85, cap_start=True)
    dark_v = [pts_near(v, pts) for v in dark_v]
    return (dark_v, dark_f), (gold_v, gold_f)


def pts_near(v, pts):
    best = min(pts[:4], key=lambda q: (q - v).length)
    return best + (v - best) * 1.06


def nose_shape():
    E = sdf.ellipsoid
    nose = sdf.smooth_union(E((0, -2.69, 4.02), (0.13, 0.1, 0.085)), E((0, -2.63, 4.07), (0.1, 0.1, 0.06)), k=0.04)
    nostrils = sdf.mirror_x(E((0.055, -2.785, 3.995), (0.03, 0.03, 0.022), rot=(0, 0, 25)))
    return sdf.smooth_subtract(nose, nostrils, k=0.015)


def mouth_parts():
    """(verts, faces, colour, weights-spec) tuples for the Dark mesh."""
    parts = []
    # mouth bag inside the snarl gap: upper half on Head, lower half on Jaw
    v, f = ellipsoid_mesh((0, -2.18, 3.845), (0.15, 0.4, 0.05), seg=14, rings=8)
    parts.append((v, f, MOUTH, "bag"))
    v, f = ellipsoid_mesh((0, -2.18, 3.8), (0.1, 0.27, 0.03), seg=12, rings=6)
    parts.append((v, f, TONGUE, "Tongue"))
    # incisors (upper on Head, lower on Jaw) + small lower canines
    for i, x in enumerate((-0.12, -0.075, -0.026, 0.026, 0.075, 0.12)):
        y = -2.595 + 0.9 * x * x * 6
        tv, tf, _ = tube([(x, y, 3.905), (x, y - 0.005, 3.85), (x, y - 0.006, 3.81)], [0.018, 0.015, 0.0], sides=5)
        parts.append((tv, tf, TOOTH, "Head"))
    for x in (-0.09, -0.03, 0.03, 0.09):
        y = -2.45 + 0.9 * x * x * 6
        tv, tf, _ = tube([(x, y, 3.765), (x, y - 0.004, 3.81), (x, y - 0.005, 3.84)], [0.015, 0.013, 0.0], sides=5)
        parts.append((tv, tf, TOOTH, "Jaw"))
    for sd in (1, -1):
        tv, tf, _ = tube([(0.125 * sd, -2.4, 3.76), (0.13 * sd, -2.41, 3.83), (0.132 * sd, -2.42, 3.885)], [0.03, 0.022, 0.0], sides=6)
        parts.append((tv, tf, TOOTH, "Jaw"))
    return parts


# ═══ BUILD ═══════════════════════════════════════════════════════════════════

def build(args):
    rng = np.random.default_rng(1337)
    prng = random.Random(1337)
    fk.reset_scene()
    place_eyes()
    log("eyes", {k: tuple(round(c, 3) for c in v) for k, v in EYE.items()})
    arm = build_armature()
    bones = [b.name for b in arm.data.bones]
    log("bones", len(bones))

    log("sculpting body SDF")
    bverts, bfaces = sdf_geometry("VF_Body", body_shape(), voxel=0.032, tris=BODY_TRIS)
    body = Body(bverts, bfaces)
    body_weights(body, bones)
    log("body", len(body.P), "verts", len(body.tri), "tris")

    strokes = project_strokes(body)
    log("glow strokes", len(strokes))

    specs = sample_clumps(body, rng, density=args.density)
    for sp in specs:
        finalize_clump(sp, prng)
    specs = [sp for sp in specs if not (sp["kind"] == "tail" and sp.get("tt", 0) > 0.88)]
    specs = [sp for sp in specs if keep_above_ground(sp)]
    specs = drop_rooted_in_strokes(specs, strokes)

    # ears / lids
    ears = {s: ear_geometry(s) for s in "LR"}
    lids = {s: lid_geometry(s) for s in "LR"}
    fixed_tris = sum(sum(len(x) - 2 for x in f) for _, f, _, _ in ears.values()) + sum(sum(len(x) - 2 for x in f) for _, f in lids.values())

    budget = BUDGET["Fur"] - len(body.tri) - fixed_tris
    total = sum(clump_tris(sp) for sp in specs)
    log(f"clump tris {total} vs budget {budget}")
    if total > budget:
        # thin out evenly, low-priority regions (flank, belly, leg sides) a bit faster
        order = sorted(range(len(specs)), key=lambda i: prng.random() * specs[i]["prio"])
        drop = set()
        for i in order:
            if total <= budget:
                break
            drop.add(i)
            total -= clump_tris(specs[i])
        specs = [sp for i, sp in enumerate(specs) if i not in drop]
        log(f"budget: dropped {len(drop)} clumps")
    kinds = {}
    for sp in specs:
        kinds[sp["kind"]] = kinds.get(sp["kind"], 0) + 1
    log("clumps", len(specs), kinds)

    cv, cf = [], []
    for sp in specs:
        v, f, _ = clump_geometry(sp)
        o = len(cv)
        cv += [T(x) for x in v]
        cf += [tuple(i + o for i in t) for t in f]
    lift_strokes(strokes, BVHTree.FromPolygons(cv, cf))
    specs = trim_over_strokes(specs, strokes)

    # ── Fur ──
    fur = Acc(bones)
    fur.add(body.P, body.faces, [skin_color(p) for p in body.P], body.W)
    for sp in specs:
        v, f, c = clump_geometry(sp)
        if sp["kind"] == "tail":
            _, par = poly_param_np(np.array([T(x) for x in v]), TAIL_PTS)
            w = tail_weights_np(np.clip(par, 0, 1), bones)
            wb = body.nearest(sp["p"])[2]
            wt = np.where(w.sum(axis=1, keepdims=True) > 0, w, wb[None, :])
            # the root of a tail clump on the rump follows the body
            k = smooth01(2.55, 2.85, np.array([x.y for x in v]))[:, None]
            w = wt * k + wb[None, :] * (1 - k)
        else:
            w = np.repeat(body.nearest(sp["p"])[2][None, :], len(v), axis=0)
        fur.add(v, f, c, w, normals=sp["_normals"])
    for s in "LR":
        v, f, c, R = ears[s]
        fur.add(v, f, c, "Ear" + s)
        for sp in ear_tufts(s, R, prng):
            tv, tf, tc = clump_geometry(sp)
            fur.add(tv, tf, tc, "Ear" + s, normals=sp["_normals"])
        v, f = lids[s]
        fur.add(v, f, FUR_SKIN, "Lid" + s)
    fur_obj = fur.build(f"{NAME}__Fur", arm)

    # ── Glow ──
    glow = Acc(bones)
    for st in strokes:
        v, f = stroke_geometry(st)
        w = np.array([body.nearest(x)[2] for x in v])
        glow.add(v, f, WHITE, w)
    for sp in tail_glow_clumps(prng):
        v, f, _ = clump_geometry(sp)
        _, par = poly_param_np(np.array([T(x) for x in v]), TAIL_PTS)
        glow.add(v, f, WHITE, tail_weights_np(np.clip(par, 0, 1), bones))
    glow_obj = glow.build(f"{NAME}__Glow", arm)

    # ── Eyes ──
    eyes = Acc(bones)
    for s in "LR":
        v, f = eye_geometry(s)
        eyes.add(v, f, WHITE, "Head")
    eyes_obj = eyes.build(f"{NAME}__Eyes", arm)

    # ── Gold + Dark ──
    gold = Acc(bones)
    dark = Acc(bones)
    for s in "LR":
        v, f, _ = fang_geometry(s)
        gold.add(v, f, WHITE, "Head")
    for leg in LEGS:
        for toe in toe_centers(leg):
            (dv, df), (gv, gf) = claw_geometry(leg, toe)
            dark.add(dv, df, CLAW, f"Leg{leg}2")
            gold.add(gv, gf, WHITE, f"Leg{leg}2")
    gold_obj = gold.build(f"{NAME}__Gold", arm)

    nv, nf = sdf_geometry("VF_Nose", nose_shape(), voxel=0.008, tris=420)
    dark.add(nv, nf, NOSE, "Head")
    for v, f, col, wspec in mouth_parts():
        if wspec == "bag":
            zc = 3.845
            w = np.zeros((len(v), len(bones)))
            k = smooth01(zc - 0.02, zc + 0.02, np.array([x.z for x in v]))
            w[:, bones.index("Head")] = k
            w[:, bones.index("Jaw")] = 1 - k
            dark.add(v, f, col, w)
        else:
            dark.add(v, f, col, wspec)
    dark_obj = dark.build(f"{NAME}__Dark", arm)

    meshes = [fur_obj, glow_obj, eyes_obj, gold_obj, dark_obj]
    fk.bake_ao(fur_obj, samples=10, distance=0.5, strength=0.35, floor_z=0.0)
    carrier = fk.socket_carrier(arm)
    stats = {o.name: fk.triangle_count(o) for o in meshes}
    log("tris", stats)
    return arm, meshes, carrier, stats, body


def skin_color(p):
    x, y, z = p
    if y < -2.0 and z > 3.7:
        return MUZZLE
    return FUR_SKIN


# ═══ EXPORT + VERIFY ═════════════════════════════════════════════════════════

def export(arm, meshes, carrier):
    for o in meshes:
        o.data.materials.clear()
    path = fk.export_fbx([arm] + meshes + [carrier], FBX_NAME)
    log("exported", path, "%.2f MB" % (os.path.getsize(path) / 1e6))
    return path


def verify(path):
    fk.reset_scene()
    bpy.ops.import_scene.fbx(filepath=path)
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    print("VERIFY armatures:", [a.name for a in arms])
    for a in arms:
        print("VERIFY bones (%d):" % len(a.data.bones), " ".join(b.name for b in a.data.bones))
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in meshes:
        me = o.data
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        groups = [g.name for g in o.vertex_groups]
        unweighted = sum(1 for v in me.vertices if not v.groups)
        maxinf = max((len(v.groups) for v in me.vertices), default=0)
        print(f"VERIFY {o.name}: {tris} tris, {len(me.vertices)} verts, groups={len(groups)}, unweighted={unweighted}, max_influences={maxinf}, "
              f"colors={[c.name for c in me.color_attributes]}")
        if o.name.startswith(NAME):
            for v in me.vertices:
                w = o.matrix_world @ v.co
                lo = Vector(map(min, lo, w))
                hi = Vector(map(max, hi, w))
    print("VERIFY bounds", tuple(round(c, 3) for c in lo), tuple(round(c, 3) for c in hi), "size", tuple(round(c, 3) for c in hi - lo))


# ═══ PREVIEW RENDERING ═══════════════════════════════════════════════════════

BG_HEX = 0xE3E3E1


def preview_materials(meshes):
    def principled(name):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        return m, m.node_tree, next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")

    mats = {}
    m, nt, b = principled("PV_Fur")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    nt.links.new(attr.outputs[0], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.62
    b.inputs["Specular IOR Level"].default_value = 0.2
    b.inputs["Sheen Weight"].default_value = 0.15
    b.inputs["Sheen Roughness"].default_value = 0.35
    b.inputs["Sheen Tint"].default_value = (0.55, 0.6, 0.75, 1)
    mats["Fur"] = m
    m, nt, b = principled("PV_Dark")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    nt.links.new(attr.outputs[0], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.28
    mats["Dark"] = m
    for key, hexv, strength in (("Glow", GLOW_HEX, 0.9), ("Eyes", EYE_HEX, 2.2)):
        m, nt, b = principled("PV_" + key)
        c = (*to_lin(H(hexv)), 1)
        b.inputs["Base Color"].default_value = c
        b.inputs["Emission Color"].default_value = c
        b.inputs["Emission Strength"].default_value = strength
        mats[key] = m
    m, nt, b = principled("PV_Gold")
    b.inputs["Base Color"].default_value = (*to_lin(H(0xC9A24A)), 1)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.3
    mats["Gold"] = m
    for o in meshes:
        key = o.name.split("__")[-1]
        o.data.materials.clear()
        o.data.materials.append(mats[key])
    return mats


def studio(res_scale=1.0, samples=48):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = samples
        sc.eevee.use_shadows = True
    except Exception:
        pass
    try:
        sc.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    sc.render.film_transparent = False
    bg = (*to_lin(H(BG_HEX)), 1)
    world = sc.world or bpy.data.worlds.new("VF_World")
    sc.world = world
    world.use_nodes = True
    node = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    node.inputs[0].default_value = bg
    node.inputs[1].default_value = 1.0
    for name, energy, rot, ang in (("VF_Key", 2.6, (52, 0, -38), 4), ("VF_Rim", 2.3, (58, 0, 150), 3), ("VF_Fill", 0.5, (70, 0, 60), 20)):
        if name in bpy.data.objects:
            continue
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy = energy
        ld.angle = math.radians(ang)
        lo = bpy.data.objects.new(name, ld)
        fk.link(lo)
        lo.rotation_euler = [math.radians(a) for a in rot]
    if "VF_Floor" not in bpy.data.objects:
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60)
        floor = fk.mesh_object("VF_Floor", bm)
        m = bpy.data.materials.new("VF_FloorMat")
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
        s2r = nt.nodes.new("ShaderNodeShaderToRGB")
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 1.1
        mr.inputs["From Max"].default_value = 2.6
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs[6].default_value = tuple(c * 0.62 for c in bg[:3]) + (1,)
        mix.inputs[7].default_value = bg
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(diff.outputs[0], s2r.inputs[0])
        nt.links.new(s2r.outputs[0], bw.inputs[0])
        nt.links.new(bw.outputs[0], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], mix.inputs[0])
        nt.links.new(mix.outputs[2], em.inputs[0])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        floor.data.materials.append(m)
    # bloom on emissive glow only (background stays under the threshold)
    try:
        ng = bpy.data.node_groups.get("VF_Comp") or bpy.data.node_groups.new("VF_Comp", "CompositorNodeTree")
        for n in list(ng.nodes):
            ng.nodes.remove(n)
        if not ng.interface.items_tree:
            ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = 0.95
        gl.inputs["Strength"].default_value = 0.45
        gl.inputs["Size"].default_value = 0.35
        out = ng.nodes.new("NodeGroupOutput")
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs["Image"], out.inputs[0])
        sc.compositing_node_group = ng
        sc.render.use_compositing = True
    except Exception as e:
        log("bloom compositor unavailable:", e)
    return sc


def camera():
    sc = bpy.context.scene
    cam = sc.camera
    if not cam:
        cam = bpy.data.objects.new("VF_Cam", bpy.data.cameras.new("VF_Cam"))
        fk.link(cam)
        sc.camera = cam
    cam.data.clip_end = 500
    return cam


def aim(target, yaw, pitch, dist, ortho=None, lens=50, shift=(0, 0)):
    cam = camera()
    t = Vector(target)
    yr, pr = math.radians(yaw), math.radians(pitch)
    off = Vector((math.sin(yr) * math.cos(pr), -math.cos(yr) * math.cos(pr), math.sin(pr))) * dist
    cam.location = t + off
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = "PERSP"
        cam.data.lens = lens
    cam.data.shift_x, cam.data.shift_y = shift
    return cam


def render(path, w, h):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def capsule(loc):
    o = bpy.data.objects.get("VF_Capsule")
    if not o:
        v, f = sdf_geometry("VF_Capsule", sdf.capsule((0, 0, 0.75), (0, 0, 4.25), 0.75), voxel=0.06, tris=900)
        me = bpy.data.meshes.new("VF_Capsule")
        me.from_pydata([T(x) for x in v], [], f)
        me.shade_smooth()
        o = bpy.data.objects.new("VF_Capsule", me)
        fk.link(o)
        m = bpy.data.materials.new("VF_CapsuleMat")
        m.use_nodes = True
        b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        b.inputs["Base Color"].default_value = (*to_lin(H(0x8E8E94)), 1)
        b.inputs["Roughness"].default_value = 0.8
        me.materials.append(m)
    o.location = loc
    o.hide_render = False
    return o


COMPOSE = r'''
import json, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
spec = json.load(open(sys.argv[1]))
def font(sz, title=False):
    names = (["/System/Library/Fonts/Supplemental/Didot.ttc"] if title else []) + ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"]
    for f in names:
        try:
            return ImageFont.truetype(f, sz)
        except Exception:
            pass
    return ImageFont.load_default()
W, Hh = spec["size"]
bg = tuple(spec["bg"])
sheet = Image.new("RGB", (W, Hh), bg)
d = ImageDraw.Draw(sheet)
ink = (38, 38, 42)
d.text((40, 24), spec["title"], fill=ink, font=font(64, True))
d.text((44, 98), spec["subtitle"], fill=(90, 90, 96), font=font(22))
for t in spec["tiles"]:
    im = Image.open(t["path"]).convert("RGB")
    if t.get("size"):
        im = im.resize(tuple(t["size"]), Image.LANCZOS)
    if t.get("shadows") is not None:
        rbg = im.getpixel((1, 1))
        canvas = Image.new("RGB", im.size, bg)
        sh = Image.new("L", im.size, 0)
        ds = ImageDraw.Draw(sh)
        for (x0, y0, x1, y1, a) in t["shadows"]:
            ds.ellipse([x0, y0, x1, y1], fill=int(a))
        sh = sh.filter(ImageFilter.GaussianBlur(max(3, im.width / 90)))
        canvas = Image.composite(Image.new("RGB", im.size, tuple(int(c * 0.62) for c in bg)), canvas, sh)
        diff = ImageChops.difference(im, Image.new("RGB", im.size, rbg)).convert("L")
        mask = diff.point(lambda v: 0 if v < 2 else min(255, v * 60))
        canvas.paste(im, (0, 0), mask)
        im = canvas
    sheet.paste(im, tuple(t["at"]))
    if t.get("label"):
        f = font(t.get("fs", 24))
        tw = d.textlength(t["label"], font=f)
        x = t["at"][0] + im.width / 2 - tw / 2
        d.text((x, t["at"][1] + im.height + 6), t["label"], fill=ink, font=f)
    if t.get("frame"):
        d.rectangle([t["at"][0] - 1, t["at"][1] - 1, t["at"][0] + im.width, t["at"][1] + im.height], outline=(150, 150, 150))
for (x, y, text, sz) in spec.get("texts", []):
    d.text((x, y), text, fill=(70, 70, 76), font=font(sz))
for (x0, y0, x1, y1) in spec.get("rules", []):
    d.line([(x0, y0), (x1, y1)], fill=(150, 150, 150), width=2)
sheet.save(spec["out"], quality=spec.get("quality", 90), optimize=True)
print("composed", spec["out"], sheet.size)
'''


def compose(spec):
    tmp = tempfile.mkdtemp(prefix="vf_compose_")
    sp = os.path.join(tmp, "spec.json")
    json.dump(spec, open(sp, "w"))
    script = os.path.join(tmp, "compose.py")
    open(script, "w").write(COMPOSE)
    py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else (shutil.which("python3") or "python3")
    r = subprocess.run([py, script, sp], capture_output=True, text=True)
    log((r.stdout + r.stderr).strip()[-400:])
    shutil.rmtree(tmp, ignore_errors=True)


def ground_shadows(w, h, cap=None):
    """Screen-space ellipses (px) under the paws, tail tip and capsule for the PIL compositor."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    cam = sc.camera

    def box(points, alpha):
        xs, ys = [], []
        for q in points:
            c = world_to_camera_view(sc, cam, Vector(q))
            xs.append(c.x * w)
            ys.append((1 - c.y) * h)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        ry = max((y1 - y0) / 2, h * 0.012)
        cy = (y0 + y1) / 2
        return [x0, cy - ry, x1, cy + ry, alpha]

    pts = []
    for p in PAW.values():
        for dx, dy in ((-0.45, -0.65), (0.45, -0.65), (-0.45, 0.55), (0.45, 0.55)):
            pts.append((p.x + dx, p.y + dy, 0.0))
    out = [box(pts, 120)]
    if cap is not None and not cap.hide_render:
        c = cap.location
        out.append(box([(c.x + dx, c.y + dy, 0.0) for dx, dy in ((-0.85, -0.85), (0.85, -0.85), (-0.85, 0.85), (0.85, 0.85))], 90))
    return out


def render_sheet(meshes, stats, dims, fast=False):
    studio(samples=16 if fast else 48)
    floor = bpy.data.objects.get("VF_Floor")
    if floor:
        floor.hide_render = True
    k = 0.5 if fast else 1.0
    tmp = tempfile.mkdtemp(prefix="vf_sheet_")
    H_ = int(1000 * k)
    span = 6.9                          # studs covered vertically by every ortho view
    spp = span / H_
    tiles = []
    cap = capsule((0, 0, 0))
    zc = 2.85
    # label, target, yaw, width in studs, capsule position
    views = [
        ("FRONT VIEW", (-0.95, 0, zc), 0, 5.4, (-2.75, 1.5, 0)),
        ("SIDE VIEW", (0, -0.75, zc), 90, 9.9, (-1.5, -4.55, 0)),
        ("BACK VIEW", (0.95, 0, zc), 180, 5.4, (2.75, -1.5, 0)),
    ]
    x, y0 = 40, 150
    for label, tgt, yaw, width_studs, cap_at in views:
        cap.location = cap_at
        cap.hide_render = False
        w = int(round(width_studs / spp))
        aim(tgt, yaw, 0, 40, ortho=max(w, H_) * spp)
        p = render(os.path.join(tmp, label.split()[0] + ".png"), w, H_)
        tiles.append(dict(path=p, at=[x, y0], label=label, shadows=ground_shadows(w, H_, cap)))
        x += w + 40
    cap.hide_render = True
    aim((0.35, 0.0, 2.45), -40, 10, 13.5, lens=50)
    w34 = int(1150 * k)
    p = render(os.path.join(tmp, "Q34.png"), w34, H_)
    tiles.append(dict(path=p, at=[x, y0], label="3/4 VIEW", shadows=ground_shadows(w34, H_, cap)))
    W = x + w34 + 40
    cap.hide_render = True

    dy = y0 + H_ + 90
    dsz = int(430 * k)
    details = [
        ("HEAD CLOSE-UP", (0, -2.2, 4.3), -14, 3, 3.6),
        ("GOLD FANGS + SNARL", (0.1, -2.3, 3.95), -72, 2, 2.6),
        ("PAW DETAIL", (0.68, -1.3, 0.3), -28, 12, 2.6),
        ("MARKINGS FROM ABOVE", (0, 0.5, 3.0), 180, 58, 11.5),
        ("TAIL TIP GLOW", (0, 3.35, 1.3), 150, 8, 6.2),
    ]
    dx = 40
    for label, tgt, yaw, pitch, dist in details:
        aim(tgt, yaw, pitch, dist, lens=50)
        p = render(os.path.join(tmp, "d_" + label.split()[0] + ".png"), dsz, dsz)
        tiles.append(dict(path=p, at=[dx, dy], label=label, fs=20, frame=True))
        dx += dsz + 24
    info_x = dx + 20
    texts = [
        (info_x, dy + 6, "BUILD", 26),
        (info_x, dy + 46, "Head top %.2f studs (with fur), ear tips %.2f" % (dims["head_top"], dims["ear_top"]), 19),
        (info_x, dy + 72, "Nose to rump %.2f studs" % dims["nose_rump"], 19),
        (info_x, dy + 98, "Overall %.2f L x %.2f W x %.2f H" % (dims["length"], dims["width"], dims["height"]), 19),
    ]
    yy = dy + 138
    for name, tris in stats.items():
        texts.append((info_x, yy, "%s  %d tris" % (name, tris), 19))
        yy += 26
    texts.append((info_x, yy + 12, "Grey capsule = 5-stud player", 19))
    Hh = dy + dsz + 60
    W = max(W, info_x + 440)
    spec = dict(size=[W, Hh], bg=[int(c * 255) for c in H(BG_HEX)], title="VOID FANG",
                subtitle="WILD THINGS REMEMBER  ·  Blender build, Neon-style preview (glow, eyes emissive; gold metallic)",
                tiles=tiles, texts=texts, rules=[[40, dy - 34, W - 40, dy - 34]], out=SHEET)
    os.makedirs(os.path.dirname(SHEET), exist_ok=True)
    compose(spec)
    shutil.rmtree(tmp, ignore_errors=True)


def pose_bones(arm, rotations):
    """rotations: bone -> (axis, degrees) in ROOT/world space, converted per bone exactly like
    CreatureAnimator:set (basis:Inverse() * q * basis)."""
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = Quaternion()
    for name, rots in rotations.items():
        pb = arm.pose.bones.get(name)
        if not pb:
            continue
        q = Quaternion()
        for axis, deg in rots:
            q = Quaternion(Vector(axis), math.radians(deg)) @ q
        B = pb.bone.matrix_local.to_quaternion()
        pb.rotation_quaternion = B.inverted() @ q @ B
    bpy.context.view_layer.update()


def render_rigtest(arm, fast=False):
    studio(samples=16 if fast else 40)
    for name in ("VF_Floor", "VF_Capsule"):
        o = bpy.data.objects.get(name)
        if o:
            o.hide_render = True
    k = 0.5 if fast else 1.0
    tmp = tempfile.mkdtemp(prefix="vf_rig_")
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    tail = {f"Tail{i}": [(X, 20)] for i in range(1, 5)}
    jaw = {"Jaw": [(X, 25)]}
    stress = {"Neck": [(X, -25)], "Head": [(Z, 30)], "LegFL1": [(X, 30)], "LegFL2": [(X, -40)], "LegBR1": [(X, -30)], "LegBR2": [(X, 40)],
              "LegFR1": [(X, -20)], "LegBL1": [(X, 22)], "Spine": [(Y, 0), (Z, 10)], **{f"Tail{i}": [(Z, 18)] for i in range(1, 5)}}
    sz = int(600 * k)
    panels = [
        ("REST POSE", {}, ("side", 9.8, None)),
        ("JAW +25°, TAIL CURL +20°/BONE", {**jaw, **tail}, ("side", 9.8, None)),
        ("JAW +25° CLOSE-UP", jaw, ((0, -2.2, 4.1), -60, 6, 5.2)),
        ("TAIL +20°/BONE FROM BEHIND", tail, ((0, 2.4, 2.2), 125, 12, 12.5)),
        ("STRESS: NECK -25°, HEAD YAW 30°, LEGS ±30°", stress, ((0.2, 0.2, 2.4), -38, 14, 13.0)),
        ("SHOULDER + HIP UNDER THE STRESS POSE", stress, ((0.6, 0.6, 1.9), -90, 4, 8.0)),
        ("LIDS -165° (BLINK), EARS ±20°", {"LidL": [(X, -165)], "LidR": [(X, -165)], "EarL": [(Z, -20)], "EarR": [(Z, 20)]},
         ((0, -2.2, 4.4), -22, 6, 4.2)),
        ("TAIL WAG: YAW 25°/BONE (ANIMATOR AXIS)", {f"Tail{i}": [(Z, 25)] for i in range(1, 5)}, ((0, 1.2, 1.6), 160, 55, 13.0)),
    ]
    tiles = []
    for i, (label, rot, cam) in enumerate(panels):
        pose_bones(arm, rot)
        if cam[0] == "side":
            aim((0, 1.25, 2.75), 90, 0, 40, ortho=cam[1])
        else:
            aim(cam[0], cam[1], cam[2], cam[3], lens=50)
        p = render(os.path.join(tmp, "%02d.png" % i), sz, sz)
        tiles.append(dict(path=p, at=[40 + (i % 4) * (sz + 20), 150 + (i // 4) * (sz + 56)], label=label, fs=18, frame=True, shadows=[]))
    pose_bones(arm, {})
    W = 40 + 4 * (sz + 20) + 20
    Hh = 150 + 2 * (sz + 56) + 10
    spec = dict(size=[W, Hh], bg=[int(c * 255) for c in H(BG_HEX)], title="VOID FANG · RIG TEST",
                subtitle="Rotations are applied in root space and converted per bone exactly like CreatureAnimator:set (basis⁻¹·q·basis). +X opens the jaw.",
                tiles=tiles, out=RIGTEST)
    compose(spec)
    shutil.rmtree(tmp, ignore_errors=True)


def render_overlay(out_dir):
    """Ortho renders at the sheet's own scale, blended over its FRONT/SIDE/BACK drawings."""
    os.makedirs(out_dir, exist_ok=True)
    studio(samples=12)
    sc = bpy.context.scene
    for name in ("VF_Floor", "VF_Capsule"):
        o = bpy.data.objects.get(name)
        if o:
            o.hide_render = True
    s = 0.01272
    views = {
        # name: (crop box in sheet px, yaw, centre mapping)
        "side": ((295, 90, 820, 540), 90, lambda cx, cy: (0, (cx - 520) * s, (527 - cy) * s), s),
        "front": ((40, 95, 340, 540), 0, lambda cx, cy: ((cx - 182.5) * s, 0, (530 - cy) * s), s),
        "back": ((820, 180, 1010, 545), 180, lambda cx, cy: (-(cx - 914) * s / 0.81, 0, (532 - cy) * s / 0.81), s / 0.81),
    }
    items = []
    for name, (box, yaw, mapc, scale) in views.items():
        w, h = box[2] - box[0], box[3] - box[1]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        tgt = mapc(cx, cy)
        aim(tgt, yaw, 0, 40, ortho=max(w, h) * scale)
        p = os.path.join(out_dir, f"_{name}_render.png")
        render(p, w * 2, h * 2)
        items.append((name, box, p))
    script = r'''
import sys, json
from PIL import Image, ImageChops, ImageOps, ImageFilter
items = json.loads(sys.argv[1]); out = sys.argv[2]
ref = Image.open(sys.argv[3]).convert("RGB")
tiles = []
for name, box, p in items:
    r = ref.crop(tuple(box)).resize(((box[2]-box[0])*2, (box[3]-box[1])*2), Image.LANCZOS)
    m = Image.open(p).convert("RGB")
    bg = m.getpixel((2, 2))
    diff = ImageChops.difference(m, Image.new("RGB", m.size, bg)).convert("L").point(lambda v: 255 if v > 18 else 0)
    edge = diff.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    blend = Image.blend(r, m, 0.5)
    red = Image.new("RGB", m.size, (255, 30, 30))
    blend.paste(red, (0, 0), edge)
    sbs = Image.new("RGB", (m.width * 2, m.height), (255, 255, 255))
    sbs.paste(r, (0, 0)); sbs.paste(m, (m.width, 0))
    tiles.append(blend); tiles.append(sbs)
W = max(t.width for t in tiles); H = sum(t.height for t in tiles)
sheet = Image.new("RGB", (W, H), (255, 255, 255)); y = 0
for t in tiles:
    sheet.paste(t, (0, y)); y += t.height
sheet.save(out, quality=85)
'''
    py = "/usr/bin/python3"
    for name, box, p in items:
        subprocess.run([py, "-c", script, json.dumps([[name, list(box), p]]), os.path.join(out_dir, f"overlay_{name}.jpg"), REF])
        os.remove(p)
    log("overlays in", out_dir)


def measure(meshes, body):
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    for o in meshes:
        for v in o.data.vertices:
            lo = Vector(map(min, lo, v.co))
            hi = Vector(map(max, hi, v.co))
    fur = next(o for o in meshes if o.name.endswith("__Fur"))
    head_top = max(v.co.z for v in fur.data.vertices if abs(v.co.x) < 0.12 and -2.1 < v.co.y < -1.45)
    ear_top = max(v.co.z for v in fur.data.vertices if v.co.y < -1.3)
    nose = min(v.co.y for o in meshes for v in o.data.vertices)
    dt, _ = poly_param_np(body.P, TAIL_PTS)
    rump = float(body.P[(dt > 0.45) & (body.P[:, 2] > 1.8), 1].max())
    return dict(head_top=head_top, ear_top=ear_top, nose_rump=rump - nose, length=hi.y - lo.y, width=hi.x - lo.x, height=hi.z - lo.z,
                lo=tuple(round(c, 3) for c in lo), hi=tuple(round(c, 3) for c in hi))


# ═══ MAIN ════════════════════════════════════════════════════════════════════

def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--no-rigtest", action="store_true")
    ap.add_argument("--overlay", default="")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--density", type=float, default=1.0)
    return ap.parse_args(argv)


def main():
    args = parse_args()
    if args.verify:
        verify(os.path.join(fk.BUILD, FBX_NAME))
        return
    arm, meshes, carrier, stats, body = build(args)
    dims = measure(meshes, body)
    log("dims", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in dims.items()})
    if not args.no_export:
        export(arm, meshes, carrier)
    carrier.hide_render = True
    preview_materials(meshes)
    if args.overlay:
        render_overlay(args.overlay)
    if not args.no_sheet:
        render_sheet(meshes, stats, dims, fast=args.fast)
    if not args.no_rigtest:
        render_rigtest(arm, fast=args.fast)
    log("done")


if __name__ == "__main__":
    main()
