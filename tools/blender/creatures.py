"""creatures — the three body families and every anatomy part, as code.

Naming contract with the Roblox builder (src/shared/CreatureBuilder.luau):

    MeshPart name  = "<Slot>__<Variant>__<Piece>"     e.g. Eyes__Big__PupilL
    body pieces    = "Body__<HeadVariant>__Main" / "__Belly"

Colour is resolved in Roblox from the PIECE name (Config/Anatomy.pieceColor), because
FBX cannot carry attributes. Vertex colours are greyscale shading that multiplies the tint.

One FBX per (family, head variant) body, one FBX per family for all parts. Every rig uses
the same bone names, so any part binds to any body of its family (bind-by-name, see
docs/DECISIONS.md).
"""

import math
import os

import bpy
import numpy as np
from mathutils import Vector

import famkit as fk
import sdf

WHITE = (1.0, 1.0, 1.0)


# ═══ FAMILY GEOMETRY ══════════════════════════════════════════════════════════
# All numbers are studs at the GROWN stage (scale 1). Creatures face -Y.

class Family:
    name = "?"
    head_variants = ("Round",)

    def sockets(self, head):
        raise NotImplementedError

    def body_shape(self, head):
        raise NotImplementedError

    def belly_shape(self, head):
        return None

    def skeleton(self, head):
        s = self.sockets(head)
        up = Vector((0, 0, 0.18))
        fwd = Vector((0, -0.18, 0))
        bones = [
            ("Root", s["root"], s["root"] + up, None),
            ("Spine", s["spine"], s["neck"], "Root"),
            ("Belly", s["belly"], s["belly"] + up, "Root"),
            ("Neck", s["neck"], s["head"], "Spine"),
            ("Head", s["head"], s["head"] + Vector((0, 0, 0.45)), "Neck"),
            ("Jaw", s["jaw"], s["jaw"] + fwd, "Head"),
            ("Tongue", s["tongue"], s["tongue"] + fwd, "Jaw"),
            ("EyeL", s["eyeL"], s["eyeL"] + fwd, "Head"),
            ("EyeR", s["eyeR"], s["eyeR"] + fwd, "Head"),
            ("LidL", s["eyeL"] + Vector((0, 0.001, 0)), s["eyeL"] + fwd + Vector((0, 0.001, 0)), "Head"),
            ("LidR", s["eyeR"] + Vector((0, 0.001, 0)), s["eyeR"] + fwd + Vector((0, 0.001, 0)), "Head"),
            ("CheekL", s["cheekL"], s["cheekL"] + up, "Head"),
            ("CheekR", s["cheekR"], s["cheekR"] + up, "Head"),
            ("EarL", s["earL"], s["earL"] + up, "Head"),
            ("EarR", s["earR"], s["earR"] + up, "Head"),
            ("HornC", s["hornC"], s["hornC"] + up, "Head"),
            ("HornL", s["hornL"], s["hornL"] + up, "Head"),
            ("HornR", s["hornR"], s["hornR"] + up, "Head"),
            ("Back", s["back"], s["back"] + up, "Spine"),
            ("WingL", s["wingL"], s["wingL"] + Vector((0.18, 0, 0)), "Back"),
            ("WingR", s["wingR"], s["wingR"] + Vector((-0.18, 0, 0)), "Back"),
        ]
        # tail chain
        t = s["tail"]
        prev = "Root"
        for i in range(4):
            a, b = t[i], t[i + 1]
            bones.append((f"Tail{i + 1}", a, b, prev))
            prev = f"Tail{i + 1}"
        # legs: two bones each
        for leg, (hip, knee, foot) in s["legs"].items():
            bones.append((f"Leg{leg}1", hip, knee, "Root"))
            bones.append((f"Leg{leg}2", knee, foot, f"Leg{leg}1"))
        return bones


def V(*a):
    return Vector(a)


class Cute(Family):
    """Chubby hamster-blob. The head is most of the creature; the body is a soft pear
    it sits on. Reads as 'baby' at any size, which is the point (SPEC §8 egg -> blob)."""

    name = "Cute"
    head_variants = ("Round", "Blocky", "Snouted", "Bulb")

    def head_params(self, head):
        # centre, radii of the head mass; face_y is the front surface at eye height
        if head == "Blocky":
            return V(0, -0.42, 1.68), (1.02, 0.9, 0.86)
        if head == "Snouted":
            return V(0, -0.38, 1.7), (0.98, 0.9, 0.9)
        if head == "Bulb":
            return V(0, -0.4, 1.74), (0.96, 0.88, 0.98)
        return V(0, -0.36, 1.7), (1.04, 0.98, 0.92)

    def sockets(self, head):
        hc, hr = self.head_params(head)
        face_y = hc.y - hr[1]
        eye_z = hc.z + 0.12
        eye_x = 0.43
        snout = 0.28 if head == "Snouted" else 0.0
        top = hc.z + hr[2]
        if head == "Bulb":
            top += 0.42
        s = dict(
            root=V(0, 0.25, 0.55),
            belly=V(0, -0.1, 0.72),
            spine=V(0, 0.25, 0.9),
            neck=V(0, -0.12, 1.28),
            head=V(0, hc.y + 0.1, hc.z - 0.25),
            jaw=V(0, face_y + 0.42, hc.z - 0.38),
            tongue=V(0, face_y + 0.3, hc.z - 0.4),
            eyeL=V(eye_x, face_y + 0.2 - snout * 0.2, eye_z),
            eyeR=V(-eye_x, face_y + 0.2 - snout * 0.2, eye_z),
            cheekL=V(0.56, face_y + 0.38, hc.z - 0.3),
            cheekR=V(-0.56, face_y + 0.38, hc.z - 0.3),
            earL=V(0.58, hc.y + 0.05, top - 0.22),
            earR=V(-0.58, hc.y + 0.05, top - 0.22),
            hornC=V(0, hc.y - 0.2, top - 0.06),
            hornL=V(0.34, hc.y - 0.25, top - 0.12),
            hornR=V(-0.34, hc.y - 0.25, top - 0.12),
            back=V(0, 0.5, 1.62),
            wingL=V(0.42, 0.55, 1.5),
            wingR=V(-0.42, 0.55, 1.5),
            tail=[V(0, 0.98, 0.8), V(0, 1.28, 0.88), V(0, 1.58, 1.02), V(0, 1.84, 1.22), V(0, 2.06, 1.46)],
            legs={
                "FL": (V(0.5, -0.5, 0.55), V(0.52, -0.56, 0.28), V(0.53, -0.6, 0.0)),
                "FR": (V(-0.5, -0.5, 0.55), V(-0.52, -0.56, 0.28), V(-0.53, -0.6, 0.0)),
                "BL": (V(0.56, 0.56, 0.55), V(0.58, 0.6, 0.28), V(0.59, 0.62, 0.0)),
                "BR": (V(-0.56, 0.56, 0.55), V(-0.58, 0.6, 0.28), V(-0.59, 0.62, 0.0)),
            },
        )
        s["face_y"] = face_y
        s["head_c"] = hc
        s["head_r"] = hr
        return s

    def body_shape(self, head):
        s = self.sockets(head)
        hc, hr = s["head_c"], s["head_r"]
        body = sdf.ellipsoid((0, 0.2, 0.9), (0.9, 0.84, 0.72))
        rump = sdf.ellipsoid((0, 0.62, 0.82), (0.74, 0.46, 0.54))
        belly = sdf.ellipsoid((0, -0.12, 0.76), (0.74, 0.66, 0.5))
        torso = sdf.smooth_union(body, rump, belly, k=0.3)
        if head == "Blocky":
            headshape = sdf.round_box(tuple(hc), (hr[0], hr[1], hr[2]), 0.42)
        else:
            headshape = sdf.ellipsoid(tuple(hc), hr)
        if head == "Bulb":
            bulb = sdf.ellipsoid((hc.x, hc.y + 0.05, hc.z + 0.78), (0.5, 0.48, 0.46))
            headshape = sdf.smooth_union(headshape, bulb, k=0.35)
        if head == "Snouted":
            snout = sdf.ellipsoid((0, s["face_y"] - 0.1, hc.z - 0.22), (0.5, 0.42, 0.34))
            nose = sdf.ellipsoid((0, s["face_y"] - 0.45, hc.z - 0.1), (0.16, 0.1, 0.1))
            headshape = sdf.smooth_union(headshape, snout, k=0.3)
            headshape = sdf.smooth_union(headshape, nose, k=0.08)
        cheeks = sdf.mirror_x(sdf.ellipsoid((0.54, s["face_y"] + 0.36, hc.z - 0.32), (0.4, 0.32, 0.32)))
        shape = sdf.smooth_union(torso, headshape, k=0.42)
        shape = sdf.smooth_union(shape, cheeks, k=0.22)
        # mouth slit so the jaw can actually open (upper lip on Head, lower lip on Jaw)
        slit_y = s["face_y"] + 0.02 - (0.3 if head == "Snouted" else 0.0)
        slit = sdf.ellipsoid((0, slit_y, s["jaw"].z + 0.02), (0.26, 0.3, 0.035))
        shape = sdf.smooth_subtract(shape, slit, k=0.02)
        # eye sockets: shallow dishes so eyes sit IN the face, not stuck on it
        for x in (s["eyeL"].x, s["eyeR"].x):
            dish = sdf.sphere((x, s["eyeL"].y + 0.06, s["eyeL"].z), 0.26)
            shape = sdf.smooth_subtract(shape, dish, k=0.08)
        return shape

    def belly_region(self, head):
        """Faces whose centre is inside this shape become the Belly piece (secondary tint)."""
        s = self.sockets(head)
        return sdf.ellipsoid((0, -0.55, 0.9), (0.62, 0.55, 0.62))


FAMILIES = {"Cute": Cute()}


# ═══ BODY BUILD ═══════════════════════════════════════════════════════════════

def _split_by_region(obj, region_fn, name_in, name_out):
    """Cut the mesh exactly along region_fn == 0 and split it into two objects.

    Crossing edges are split at the interpolated zero, faces are cut between the new
    vertices, so the seam is a smooth contour instead of a triangle sawtooth. Both halves
    share identical boundary positions (identical skin weights -> no cracks when bones
    move) and keep the unsplit smooth normals as custom normals (no lighting seam)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    bm.verts.ensure_lookup_table()

    pos = np.array([v.co[:] for v in bm.verts], dtype=np.float32)
    vals = {v: float(d) for v, d in zip(bm.verts, region_fn(pos))}
    normals = {v: v.normal.copy() for v in bm.verts}

    crossing = [e for e in bm.edges if (vals[e.verts[0]] < 0) != (vals[e.verts[1]] < 0)]
    new_verts = set()
    for e in crossing:
        a, b = e.verts
        da, db = vals[a], vals[b]
        t = da / (da - db)
        na, nb = normals[a], normals[b]
        ne, nv = bmesh.utils.edge_split(e, a, t)
        vals[nv] = 0.0
        normals[nv] = (na.lerp(nb, t)).normalized()
        new_verts.add(nv)

    for f in list(bm.faces):
        on = [v for v in f.verts if v in new_verts]
        if len(on) == 2 and not bm.edges.get(on):
            try:
                bmesh.ops.connect_verts(bm, verts=on)
            except Exception:
                pass
    bmesh.ops.triangulate(bm, faces=bm.faces[:])

    def face_inside(f):
        return sum(vals[v] for v in f.verts) / len(f.verts) < 0

    halves = []
    for want_inside, name in ((True, name_in), (False, name_out)):
        part = bm.copy()
        part.verts.ensure_lookup_table()
        # map values by index (copy preserves order)
        idx_vals = [vals[v] for v in bm.verts]
        idx_norm = [normals[v] for v in bm.verts]
        doomed = [f for f in part.faces if (sum(idx_vals[v.index] for v in f.verts) / len(f.verts) < 0) != want_inside]
        keep_norm = {}
        bmesh.ops.delete(part, geom=doomed, context="FACES")
        loose = [v for v in part.verts if not v.link_faces]
        bmesh.ops.delete(part, geom=loose, context="VERTS")
        me = bpy.data.meshes.new(name)
        # remember normals through the index remap
        part.verts.index_update()
        norms = []
        for v in part.verts:
            norms.append(v.normal.copy())
        part.to_mesh(me)
        halves.append((me, part))
    # custom normals: nearest original vertex normal by position
    from mathutils.kdtree import KDTree
    kd = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert(v.co, i)
    kd.balance()
    all_norms = [normals[v] for v in bm.verts]
    out = []
    for me, part in halves:
        vn = []
        for v in me.vertices:
            _, i, _ = kd.find(v.co)
            vn.append(all_norms[i])
        try:
            me.normals_split_custom_set_from_vertices(vn)
        except Exception:
            pass
        part.free()
        o = bpy.data.objects.new(me.name, me)
        fk.link(o)
        fk.shade_smooth(o)
        out.append(o)
    bm.free()
    bpy.data.objects.remove(obj, do_unlink=True)
    return out[0], out[1]


def body_weights(fam, head):
    s = fam.sockets(head)
    hc = s["head_c"]
    jaw_z = s["jaw"].z + 0.02

    def custom(p):
        # lower face in front of the jaw pivot follows the jaw
        if p.y < s["face_y"] + 0.55 and p.z < jaw_z and p.z > jaw_z - 0.55 and abs(p.x) < 0.5:
            t = min(1.0, (jaw_z - p.z) / 0.08)
            return {"Jaw": t, "Head": 1.0 - t} if t < 1 else {"Jaw": 1.0}
        return None

    return custom


def build_body(fam, head, collection=None):
    shape = fam.body_shape(head)
    obj = sdf.to_mesh(f"Body__{head}", shape, voxel=0.03)
    obj = fk.decimate_to(obj, 5200)
    fk.solid_color(obj, WHITE)
    fk.bake_ao(obj, floor_z=0.0, samples=24, distance=0.7, strength=0.5)
    fk.box_uv(obj, studs_per_tile=2.0)
    arm = fk.armature(f"Rig_{fam.name}_{head}", fam.skeleton(head))
    bones = ["Root", "Spine", "Belly", "Neck", "Head", "Jaw", "CheekL", "CheekR", "Tail1"]
    region = fam.belly_region(head)
    belly, main = _split_by_region(obj, region[0], f"Body__{head}__Belly", f"Body__{head}__Main")
    for piece in (main, belly):
        fk.skin(piece, arm, bones, falloff=0.45, custom=body_weights(fam, head))
    return arm, main, belly


# ═══ PARTS ════════════════════════════════════════════════════════════════════
# Each generator returns a list of (object, bones_or_rigid) where bones_or_rigid is a bone
# name (rigid) or a list of bone names (distance skinned). Objects are named
# Slot__Variant__Piece.

def _eye_pieces(variant, side, s, radius=0.27, squash=(1.0, 0.62, 1.08), pupil_scale=0.78, glow=False):
    e = s["eye" + side]
    sign = 1 if side == "L" else -1
    bone_eye, bone_lid = "Eye" + side, "Lid" + side
    out = []
    white = fk.uv_sphere(f"Eyes__{variant}__White{side}", e, radius, 20, 12, scale=squash)
    fk.solid_color(white, (0.97, 0.97, 0.95))
    out.append((white, bone_eye))
    pr = radius * pupil_scale
    pupil = fk.uv_sphere(f"Eyes__{variant}__Pupil{side}", e + V(0, -radius * squash[1] * 0.42, 0.0), pr, 18, 10,
                         scale=(0.92, 0.55, 1.0))
    if glow:
        fk.solid_color(pupil, WHITE)
    else:
        fk.paint(pupil, lambda co, n: (0.07, 0.06, 0.09) if (co - e).length > pr * 0.35 else (0.02, 0.02, 0.03))
    out.append((pupil, bone_eye))
    shine = fk.uv_sphere(f"Eyes__{variant}__Shine{side}",
                         e + V(0.1, -radius * squash[1] - 0.02, radius * 0.36), radius * 0.2, 10, 6,
                         scale=(1.0, 0.5, 1.0))
    fk.solid_color(shine, WHITE)
    out.append((shine, bone_eye))
    small = fk.uv_sphere(f"Eyes__{variant}__Shine2{side}",
                         e + V(-0.08, -radius * squash[1] - 0.01, -radius * 0.24), radius * 0.09, 8, 5,
                         scale=(1.0, 0.5, 1.0))
    fk.solid_color(small, WHITE)
    out.append((small, bone_eye))
    return out


def _lid(variant, side, s, radius, squash, closed_fraction=0.0):
    """Upper eyelid shell. Rest pose is OPEN (rotated up and back behind the brow); the
    animator rotates LidX down to blink. closed_fraction bakes a sleepy droop."""
    import bmesh
    e = s["eye" + side]
    r = radius * 1.08
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=r)
    # keep the upper-front cap only
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -r * 0.05], context="VERTS")
    from mathutils import Matrix, Euler
    open_angle = math.radians(-78 + 95 * closed_fraction)
    m = Matrix.Translation(e) @ Euler((open_angle, 0, 0)).to_matrix().to_4x4() @ Matrix.Diagonal(V(*squash, 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.025)
    obj = fk.mesh_object(f"Eyes__{variant}__Lid{side}", bm)
    fk.shade_smooth(obj)
    fk.solid_color(obj, (0.92, 0.92, 0.92))
    return (obj, "Lid" + side)


def part_eyes(fam, variant):
    s = fam.sockets("Round")
    out = []
    if variant == "Big":
        for side in "LR":
            out += _eye_pieces(variant, side, s, 0.29)
            out.append(_lid(variant, side, s, 0.29, (1.0, 0.62, 1.08)))
    elif variant == "Dot":
        for side in "LR":
            e = s["eye" + side]
            bead = fk.uv_sphere(f"Eyes__Dot__Pupil{side}", e + V(0, -0.1, 0), 0.15, 16, 10, scale=(0.85, 0.6, 1.0))
            fk.solid_color(bead, (0.05, 0.05, 0.07))
            shine = fk.uv_sphere(f"Eyes__Dot__Shine{side}", e + V(0.04, -0.2, 0.06), 0.035, 8, 5)
            fk.solid_color(shine, WHITE)
            out += [(bead, "Eye" + side), (shine, "Eye" + side)]
            out.append(_lid("Dot", side, s, 0.16, (0.85, 0.6, 1.0)))
    elif variant == "Sleepy":
        for side in "LR":
            out += _eye_pieces(variant, side, s, 0.25, pupil_scale=0.7)
            out.append(_lid(variant, side, s, 0.25, (1.0, 0.62, 1.08), closed_fraction=0.55))
    elif variant == "Glow":
        for side in "LR":
            out += _eye_pieces(variant, side, s, 0.28, pupil_scale=0.82, glow=True)
            out.append(_lid(variant, side, s, 0.28, (1.0, 0.62, 1.08)))
    return out


def part_mouth(fam, variant):
    s = fam.sockets("Round")
    j = s["jaw"]
    fy = s["face_y"]
    out = []
    inner = fk.uv_sphere(f"Mouth__{variant}__Inner", V(0, fy + 0.46, j.z + 0.0), 0.28, 16, 10, scale=(0.95, 0.8, 0.6))
    fk.paint(inner, lambda co, n: (0.36, 0.1, 0.14))
    out.append((inner, "Head"))
    tongue = fk.uv_sphere(f"Mouth__{variant}__Tongue", V(0, fy + 0.46, j.z - 0.08), 0.18, 14, 8, scale=(1.0, 1.3, 0.42))
    fk.paint(tongue, lambda co, n: (0.95, 0.45, 0.55))
    out.append((tongue, "Tongue"))
    if variant == "Fangs":
        for x in (0.12, -0.12):
            fang = fk.tube(f"Mouth__Fangs__Fang{'L' if x > 0 else 'R'}",
                           [(x, fy + 0.06, j.z + 0.02), (x, fy + 0.02, j.z - 0.1)], [0.05, 0.012], subsurf=2)
            fk.solid_color(fang, WHITE)
            out.append((fang, "Head"))
    return out


def part_ears(fam, variant):
    s = fam.sockets("Round")
    out = []
    for side, sign in (("L", 1), ("R", -1)):
        e = s["ear" + side]
        if variant == "Round":
            outer = sdf.ellipsoid(tuple(e + V(0.08 * sign, 0, 0.18)), (0.3, 0.13, 0.3), rot=(0, 25 * sign, 0))
            dent = sdf.ellipsoid(tuple(e + V(0.08 * sign, -0.12, 0.2)), (0.2, 0.08, 0.2), rot=(0, 25 * sign, 0))
            ear = sdf.to_mesh(f"Ears__Round__Ear{side}", sdf.smooth_subtract(outer, dent, k=0.04), voxel=0.02)
            fk.paint(ear, lambda co, n, e=e: (1, 1, 1) if n.y > -0.4 else (0.86, 0.86, 0.86))
            out.append((fk.decimate_to(ear, 700), "Ear" + side))
        elif variant == "Pointy":
            ear = fk.tube(f"Ears__Pointy__Ear{side}", [tuple(e), tuple(e + V(0.16 * sign, 0.02, 0.42)), tuple(e + V(0.3 * sign, 0.05, 0.72))],
                          [(0.2, 0.07), (0.14, 0.05), (0.01, 0.01)], subsurf=2)
            fk.solid_color(ear, WHITE)
            out.append((fk.decimate_to(ear, 700), "Ear" + side))
    return out


def part_tail(fam, variant):
    s = fam.sockets("Round")
    t = s["tail"]
    out = []
    if variant == "Stub":
        ball = fk.uv_sphere("Tail__Stub__Tail", t[0] + V(0, 0.2, 0.1), 0.28, 16, 10)
        fk.solid_color(ball, WHITE)
        out.append((ball, "Tail1"))
    elif variant == "Long":
        pts = [tuple(p) for p in t]
        tube = fk.tube("Tail__Long__Tail", pts, [0.2, 0.16, 0.12, 0.09, 0.05], subsurf=2)
        fk.solid_color(tube, WHITE)
        out.append((fk.decimate_to(tube, 1400), ["Tail1", "Tail2", "Tail3", "Tail4"]))
    return out


def part_legs(fam, variant):
    s = fam.sockets("Round")
    out = []
    for leg, (hip, knee, foot) in s["legs"].items():
        if variant == "Stubby":
            limb = sdf.round_cone(tuple(hip + V(0, 0, 0.05)), tuple(foot + V(0, -0.02, 0.17)), 0.25, 0.22)
            paw = sdf.ellipsoid(tuple(foot + V(0, -0.06, 0.1)), (0.24, 0.28, 0.13))
            shape = sdf.smooth_union(limb, paw, k=0.12)
            m = sdf.to_mesh(f"Legs__Stubby__{leg}", shape, voxel=0.025)
            fk.solid_color(m, WHITE)
            fk.bake_ao(m, floor_z=0.0, samples=12, distance=0.3, strength=0.35)
            out.append((fk.decimate_to(m, 700), [f"Leg{leg}1", f"Leg{leg}2"]))
    return out


PART_BUILDERS = {
    "Eyes": part_eyes,
    "Mouth": part_mouth,
    "Ears": part_ears,
    "Tail": part_tail,
    "Legs": part_legs,
}


def build_part(fam, arm, slot, variant):
    pieces = PART_BUILDERS[slot](fam, variant)
    objs = []
    for obj, bones in pieces:
        if isinstance(bones, str):
            fk.skin(obj, arm, [bones], rigid=bones)
        else:
            fk.skin(obj, arm, bones, falloff=0.3)
        objs.append(obj)
    return objs


def preview_tints(objs, primary=(1.0, 0.72, 0.8), secondary=(1.0, 0.92, 0.86)):
    for o in objs:
        n = o.name
        if "__Belly" in n:
            fk.preview_tint(o, secondary)
        elif any(k in n for k in ("__White", "__Pupil", "__Shine", "__Inner", "__Tongue", "__Fang")):
            fk.preview_tint(o, WHITE)
        elif "__Pupil" in n:
            fk.preview_tint(o, WHITE)
        else:
            fk.preview_tint(o, primary)


# ═══ EXPORT ═══════════════════════════════════════════════════════════════════

def clear_scene_keep_preview():
    keep = ("PreviewFloor", "KeyLight", "FillLight", "PreviewCam")
    for o in list(bpy.data.objects):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
    # purge orphans so re-built objects get their exact names (no ".003" suffixes,
    # which the Roblox builder would not recognise)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)


def _strip_materials(objs):
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear()


def export_body(fam, head):
    clear_scene_keep_preview()
    arm, main, belly = build_body(fam, head)
    carrier = fk.socket_carrier(arm)
    _strip_materials([main, belly])
    path = fk.export_fbx([arm, main, belly, carrier], f"{fam.name.lower()}_body_{head}.fbx")
    return path


def export_parts(fam, selection):
    """selection: list of (slot, variant)."""
    clear_scene_keep_preview()
    arm = fk.armature(f"Rig_{fam.name}_Parts", fam.skeleton("Round"))
    objs = []
    for slot, variant in selection:
        objs += build_part(fam, arm, slot, variant)
    _strip_materials(objs)
    carrier = fk.socket_carrier(arm)
    path = fk.export_fbx([arm] + objs + [carrier], f"{fam.name.lower()}_parts.fbx")
    return path, [o.name for o in objs]
