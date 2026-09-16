"""creatures — the three body families and every anatomy part, as code.

Naming contract with the Roblox builder (src/shared/CreatureBuilder.luau):

    MeshPart name  = "<Slot>__<Variant>__<Piece>"     e.g. Eyes__Big__PupilL
    body pieces    = "Body__<HeadVariant>__Main" / "__Belly"

Colour is resolved in Roblox from the PIECE name prefix (Config/Anatomy.pieceStyle and each
variant's `style`), because FBX cannot carry attributes. Vertex colours are greyscale
shading that multiplies the tint — except fixed-colour pieces (pupils, mouth) which paint
their real colour and are tinted white.

One FBX per (family, head) body and one per family for all parts. Every rig uses the same
bone names, so any part binds to any body of its family (bind-by-name, DECISIONS.md).
Parts are authored on the family's Round-head skeleton; on other heads the socket bones
sit elsewhere and the parts follow them.
"""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

import famkit as fk
import sdf

WHITE = (1.0, 1.0, 1.0)


def V(*a):
    return Vector(a)


def T(v):
    return (float(v[0]), float(v[1]), float(v[2]))


# ═══ FAMILIES ═════════════════════════════════════════════════════════════════
# Studs at the GROWN stage (scale 1). Creatures face -Y, Z up.

class Family:
    name = "?"
    head_variants = ("Round", "Blocky", "Snouted", "Bulb")
    ps = 1.0            # part scale: eyes/ears/horns size multiplier
    eye_r = 0.29
    leg_r = 0.25
    legs = ("FL", "FR", "BL", "BR")
    neck_blend = 0.4

    def head_params(self, head):
        raise NotImplementedError

    def torso_shape(self):
        raise NotImplementedError

    def base_sockets(self, head):
        raise NotImplementedError

    def sockets(self, head):
        return self.base_sockets(head)

    def skeleton(self, head):
        s = self.sockets(head)
        up = V(0, 0, 0.18)
        fwd = V(0, -0.18, 0)
        bones = [
            ("Root", s["root"], s["root"] + up, None),
            ("Spine", s["spine"], s["neck"], "Root"),
            ("Belly", s["belly"], s["belly"] + up, "Root"),
            ("Neck", s["neck"], s["head"], "Spine"),
            ("Head", s["head"], s["head"] + V(0, 0, 0.45), "Neck"),
            ("Jaw", s["jaw"], s["jaw"] + fwd, "Head"),
            ("Tongue", s["tongue"], s["tongue"] + fwd, "Jaw"),
            ("EyeL", s["eyeL"], s["eyeL"] + fwd, "Head"),
            ("EyeR", s["eyeR"], s["eyeR"] + fwd, "Head"),
            ("LidL", s["eyeL"] + V(0, 0.001, 0), s["eyeL"] + fwd + V(0, 0.001, 0), "Head"),
            ("LidR", s["eyeR"] + V(0, 0.001, 0), s["eyeR"] + fwd + V(0, 0.001, 0), "Head"),
            ("CheekL", s["cheekL"], s["cheekL"] + up, "Head"),
            ("CheekR", s["cheekR"], s["cheekR"] + up, "Head"),
            ("EarL", s["earL"], s["earL"] + up, "Head"),
            ("EarR", s["earR"], s["earR"] + up, "Head"),
            ("HornC", s["hornC"], s["hornC"] + up, "Head"),
            ("HornL", s["hornL"], s["hornL"] + up, "Head"),
            ("HornR", s["hornR"], s["hornR"] + up, "Head"),
            ("Back", s["back"], s["back"] + up, "Spine"),
            ("WingL", s["wingL"], s["wingL"] + V(0.18, 0, 0), "Back"),
            ("WingR", s["wingR"], s["wingR"] + V(-0.18, 0, 0), "Back"),
        ]
        t = s["tail"]
        prev = "Root"
        for i in range(4):
            bones.append((f"Tail{i + 1}", t[i], t[i + 1], prev))
            prev = f"Tail{i + 1}"
        for leg in ("FL", "FR", "BL", "BR"):
            hip, knee, foot = s["legs"][leg]
            bones.append((f"Leg{leg}1", hip, knee, "Root"))
            bones.append((f"Leg{leg}2", knee, foot, f"Leg{leg}1"))
        return bones

    # --- body -----------------------------------------------------------------
    def head_shape(self, head, s):
        hc, hr = s["head_c"], s["head_r"]
        ps = self.ps
        if head == "Blocky":
            shape = sdf.round_box(T(hc), (hr[0] * 0.92, hr[1] * 0.88, hr[2] * 0.9), 0.3 * ps)
        else:
            shape = sdf.ellipsoid(T(hc), hr)
        if head == "Bulb":
            bulb = sdf.ellipsoid((hc.x, hc.y + 0.06 * ps, hc.z + hr[2] * 0.82), (hr[0] * 0.5, hr[1] * 0.5, hr[2] * 0.5))
            shape = sdf.smooth_union(shape, bulb, k=0.32 * ps)
        if head == "Snouted":
            snout = sdf.ellipsoid((0, s["face_y"] - 0.12 * ps, s["jaw"].z + 0.1 * ps), (hr[0] * 0.5, hr[1] * 0.46, hr[2] * 0.36))
            nose = sdf.ellipsoid((0, s["face_y"] - 0.5 * ps, s["jaw"].z + 0.24 * ps), (0.17 * ps, 0.1 * ps, 0.11 * ps))
            shape = sdf.smooth_union(shape, snout, k=0.3 * ps)
            shape = sdf.smooth_union(shape, nose, k=0.08 * ps)
        return shape

    def body_shape(self, head):
        s = self.sockets(head)
        ps = self.ps
        shape = sdf.smooth_union(self.torso_shape(), self.head_shape(head, s), k=self.neck_blend)
        cheeks = sdf.mirror_x(sdf.ellipsoid(T(s["cheekL"] + V(-0.02, 0.0, -0.02) * ps), (0.4 * ps, 0.32 * ps, 0.32 * ps)))
        shape = sdf.smooth_union(shape, cheeks, k=0.22 * ps)
        # mouth slit: the lower lip rides the Jaw bone, so the mouth can really open
        slit = sdf.ellipsoid(T(s["slit"]), (0.26 * ps, 0.34 * ps, 0.034 * ps))
        shape = sdf.smooth_subtract(shape, slit, k=0.02)
        for key in ("eyeL", "eyeR"):
            dish = sdf.sphere(T(s[key] + V(0, 0.07, 0) * ps), self.eye_r * 0.9)
            shape = sdf.smooth_subtract(shape, dish, k=0.08 * ps)
        return shape

    def belly_region(self, head):
        raise NotImplementedError

    def jaw_custom(self, head):
        s = self.sockets(head)
        slit = s["slit"]
        ps = self.ps
        fy = s["face_y"]

        def custom(p, weights):
            wx = 1.0 - fk.smoothstep(0.22 * ps, 0.46 * ps, abs(p.x))
            dz = slit.z - p.z
            wz = fk.smoothstep(-0.005, 0.05 * ps, dz) * (1.0 - fk.smoothstep(0.3 * ps, 0.55 * ps, dz))
            wy = 1.0 - fk.smoothstep(fy + 0.3 * ps, fy + 0.62 * ps, p.y)
            w = wx * wz * wy
            if w <= 0.001:
                return weights
            out = {k: v * (1 - w) for k, v in weights.items()}
            out["Jaw"] = out.get("Jaw", 0) + w
            return out

        return custom


class Cute(Family):
    """Chubby hamster-blob. The head is most of the creature; the body is a soft pear it
    sits on. Reads as 'baby' at any size (SPEC §8)."""

    name = "Cute"
    ps = 1.0
    eye_r = 0.29
    neck_blend = 0.42

    def head_params(self, head):
        if head == "Blocky":
            return V(0, -0.36, 1.68), (1.06, 0.96, 0.9)
        if head == "Snouted":
            return V(0, -0.3, 1.72), (1.0, 0.92, 0.9)
        if head == "Bulb":
            return V(0, -0.34, 1.7), (1.0, 0.94, 0.9)
        return V(0, -0.36, 1.7), (1.04, 0.98, 0.92)

    def torso_shape(self):
        body = sdf.ellipsoid((0, 0.2, 0.9), (0.9, 0.84, 0.72))
        rump = sdf.ellipsoid((0, 0.62, 0.82), (0.74, 0.46, 0.54))
        belly = sdf.ellipsoid((0, -0.12, 0.76), (0.74, 0.66, 0.5))
        return sdf.smooth_union(body, rump, belly, k=0.3)

    def base_sockets(self, head):
        hc, hr = self.head_params(head)
        face_y = hc.y - hr[1]
        eye_z = hc.z + 0.12
        top = hc.z + hr[2] + (0.4 if head == "Bulb" else 0.0)
        snout = head == "Snouted"
        jaw = V(0, face_y + 0.42 - (0.34 if snout else 0), hc.z - (0.42 if snout else 0.38))
        return dict(
            root=V(0, 0.25, 0.55), belly=V(0, -0.1, 0.72), spine=V(0, 0.25, 0.9), neck=V(0, -0.12, 1.28),
            head=V(0, hc.y + 0.1, hc.z - 0.25),
            jaw=jaw, tongue=jaw + V(0, -0.1, -0.03),
            slit=V(0, jaw.y - 0.4, jaw.z + 0.02),
            eyeL=V(0.43, face_y + 0.2 + (0.06 if snout else 0), eye_z + (0.05 if snout else 0)),
            eyeR=V(-0.43, face_y + 0.2 + (0.06 if snout else 0), eye_z + (0.05 if snout else 0)),
            cheekL=V(0.56, face_y + 0.38, hc.z - 0.32), cheekR=V(-0.56, face_y + 0.38, hc.z - 0.32),
            earL=V(0.58, hc.y + 0.05, top - 0.22), earR=V(-0.58, hc.y + 0.05, top - 0.22),
            hornC=V(0, hc.y - 0.2, top - 0.06), hornL=V(0.34, hc.y - 0.25, top - 0.12), hornR=V(-0.34, hc.y - 0.25, top - 0.12),
            back=V(0, 0.5, 1.58), wingL=V(0.42, 0.55, 1.48), wingR=V(-0.42, 0.55, 1.48),
            tail=[V(0, 0.98, 0.8), V(0, 1.28, 0.88), V(0, 1.58, 1.02), V(0, 1.84, 1.22), V(0, 2.06, 1.46)],
            legs={
                "FL": (V(0.5, -0.5, 0.55), V(0.52, -0.56, 0.28), V(0.53, -0.6, 0.0)),
                "FR": (V(-0.5, -0.5, 0.55), V(-0.52, -0.56, 0.28), V(-0.53, -0.6, 0.0)),
                "BL": (V(0.56, 0.56, 0.55), V(0.58, 0.6, 0.28), V(0.59, 0.62, 0.0)),
                "BR": (V(-0.56, 0.56, 0.55), V(-0.58, 0.6, 0.28), V(-0.59, 0.62, 0.0)),
            },
            face_y=face_y, head_c=hc, head_r=hr, top=top,
            back_surface=[V(0, -0.1, 1.62), V(0, 0.25, 1.62), V(0, 0.6, 1.48), V(0, 0.92, 1.2)],
            belly_front=V(0, -0.72, 0.9),
        )

    def belly_region(self, head):
        return sdf.ellipsoid((0, -0.55, 0.9), (0.62, 0.55, 0.62))


class Heavy(Family):
    """Wide, low, chunky quadruped — bulldog / baby rhino / hippo. A barrel torso with the
    head slung low and forward, small eyes in a big face, pillar legs. Brave and lazy."""

    name = "Heavy"
    ps = 1.25
    eye_r = 0.25
    leg_r = 0.34
    neck_blend = 0.5

    def head_params(self, head):
        if head == "Blocky":
            return V(0, -1.32, 1.28), (1.02, 0.86, 0.8)
        if head == "Snouted":
            return V(0, -1.3, 1.3), (0.98, 0.84, 0.8)
        if head == "Bulb":
            return V(0, -1.3, 1.3), (0.98, 0.84, 0.82)
        return V(0, -1.35, 1.28), (1.02, 0.86, 0.82)

    def torso_shape(self):
        barrel = sdf.ellipsoid((0, 0.3, 1.12), (1.22, 1.3, 0.92))
        shoulders = sdf.ellipsoid((0, -0.4, 1.32), (1.12, 0.78, 0.86))
        rump = sdf.ellipsoid((0, 1.02, 1.08), (1.0, 0.66, 0.8))
        belly = sdf.ellipsoid((0, 0.2, 0.78), (1.02, 1.1, 0.55))
        return sdf.smooth_union(barrel, shoulders, rump, belly, k=0.4)

    def base_sockets(self, head):
        hc, hr = self.head_params(head)
        face_y = hc.y - hr[1]
        eye_z = hc.z + 0.24
        top = hc.z + hr[2] + (0.42 if head == "Bulb" else 0.0)
        snout = head == "Snouted"
        jaw = V(0, face_y + 0.52 - (0.4 if snout else 0), hc.z - (0.36 if snout else 0.3))
        return dict(
            root=V(0, 0.3, 0.8), belly=V(0, 0.2, 0.75), spine=V(0, 0.3, 1.2), neck=V(0, -0.8, 1.32),
            head=V(0, hc.y + 0.25, hc.z - 0.2),
            jaw=jaw, tongue=jaw + V(0, -0.12, -0.03),
            slit=V(0, jaw.y - 0.46, jaw.z + 0.02),
            eyeL=V(0.52, face_y + 0.24 + (0.05 if snout else 0), eye_z),
            eyeR=V(-0.52, face_y + 0.24 + (0.05 if snout else 0), eye_z),
            cheekL=V(0.66, face_y + 0.45, hc.z - 0.26), cheekR=V(-0.66, face_y + 0.45, hc.z - 0.26),
            earL=V(0.74, hc.y + 0.12, top - 0.18), earR=V(-0.74, hc.y + 0.12, top - 0.18),
            hornC=V(0, hc.y - 0.28, top - 0.05), hornL=V(0.44, hc.y - 0.32, top - 0.12), hornR=V(-0.44, hc.y - 0.32, top - 0.12),
            back=V(0, 0.3, 1.98), wingL=V(0.6, 0.4, 1.86), wingR=V(-0.6, 0.4, 1.86),
            tail=[V(0, 1.6, 1.12), V(0, 1.92, 1.2), V(0, 2.22, 1.32), V(0, 2.5, 1.5), V(0, 2.74, 1.74)],
            legs={
                "FL": (V(0.74, -0.58, 0.82), V(0.77, -0.62, 0.42), V(0.78, -0.66, 0.0)),
                "FR": (V(-0.74, -0.58, 0.82), V(-0.77, -0.62, 0.42), V(-0.78, -0.66, 0.0)),
                "BL": (V(0.76, 1.02, 0.82), V(0.79, 1.06, 0.42), V(0.8, 1.1, 0.0)),
                "BR": (V(-0.76, 1.02, 0.82), V(-0.79, 1.06, 0.42), V(-0.8, 1.1, 0.0)),
            },
            face_y=face_y, head_c=hc, head_r=hr, top=top,
            back_surface=[V(0, -0.6, 2.12), V(0, 0.1, 2.06), V(0, 0.8, 1.96), V(0, 1.36, 1.72)],
            belly_front=V(0, -1.0, 0.72),
        )

    def belly_region(self, head):
        return sdf.ellipsoid((0, -0.2, 0.62), (0.95, 1.35, 0.5))


class Weird(Family):
    """Tall upright alien biped: a bean body, a long neck, the head on top, little arms.
    Mischievous and nervous. The silhouette is nothing like the other two, on purpose."""

    name = "Weird"
    ps = 0.95
    eye_r = 0.3
    leg_r = 0.2
    neck_blend = 0.28
    arms = ("FL", "FR")

    def head_params(self, head):
        if head == "Blocky":
            return V(0, -0.42, 3.64), (0.84, 0.74, 0.7)
        if head == "Snouted":
            return V(0, -0.36, 3.66), (0.8, 0.72, 0.7)
        if head == "Bulb":
            return V(0, -0.38, 3.62), (0.8, 0.72, 0.7)
        return V(0, -0.42, 3.64), (0.86, 0.76, 0.72)

    def torso_shape(self):
        bean = sdf.ellipsoid((0, 0.12, 1.5), (0.7, 0.6, 1.02))
        hips = sdf.ellipsoid((0, 0.18, 1.02), (0.68, 0.58, 0.52))
        neck = sdf.round_cone((0, 0.02, 2.2), (0, -0.32, 3.3), 0.3, 0.17)
        return sdf.smooth_union(sdf.smooth_union(bean, hips, k=0.3), neck, k=0.3)

    def base_sockets(self, head):
        hc, hr = self.head_params(head)
        face_y = hc.y - hr[1]
        eye_z = hc.z + 0.12
        top = hc.z + hr[2] + (0.38 if head == "Bulb" else 0.0)
        snout = head == "Snouted"
        jaw = V(0, face_y + 0.4 - (0.32 if snout else 0), hc.z - (0.36 if snout else 0.32))
        return dict(
            root=V(0, 0.15, 0.9), belly=V(0, -0.2, 1.3), spine=V(0, 0.12, 1.45), neck=V(0, -0.08, 2.5),
            head=V(0, hc.y + 0.08, hc.z - 0.3),
            jaw=jaw, tongue=jaw + V(0, -0.1, -0.03),
            slit=V(0, jaw.y - 0.38, jaw.z + 0.02),
            eyeL=V(0.38, face_y + 0.2 + (0.05 if snout else 0), eye_z),
            eyeR=V(-0.38, face_y + 0.2 + (0.05 if snout else 0), eye_z),
            cheekL=V(0.48, face_y + 0.34, hc.z - 0.28), cheekR=V(-0.48, face_y + 0.34, hc.z - 0.28),
            earL=V(0.52, hc.y + 0.04, top - 0.2), earR=V(-0.52, hc.y + 0.04, top - 0.2),
            hornC=V(0, hc.y - 0.18, top - 0.05), hornL=V(0.3, hc.y - 0.22, top - 0.1), hornR=V(-0.3, hc.y - 0.22, top - 0.1),
            back=V(0, 0.66, 2.02), wingL=V(0.4, 0.66, 2.2), wingR=V(-0.4, 0.66, 2.2),
            tail=[V(0, 0.66, 1.02), V(0, 0.98, 0.9), V(0, 1.28, 0.86), V(0, 1.56, 0.92), V(0, 1.8, 1.08)],
            legs={
                # front "legs" are little arms hanging from the chest
                "FL": (V(0.62, -0.26, 2.02), V(0.8, -0.42, 1.68), V(0.84, -0.56, 1.36)),
                "FR": (V(-0.62, -0.26, 2.02), V(-0.8, -0.42, 1.68), V(-0.84, -0.56, 1.36)),
                "BL": (V(0.38, 0.2, 0.78), V(0.4, 0.1, 0.4), V(0.42, 0.02, 0.0)),
                "BR": (V(-0.38, 0.2, 0.78), V(-0.4, 0.1, 0.4), V(-0.42, 0.02, 0.0)),
            },
            face_y=face_y, head_c=hc, head_r=hr, top=top,
            back_surface=[V(0, 0.62, 2.3), V(0, 0.74, 1.92), V(0, 0.76, 1.5), V(0, 0.66, 1.1)],
            belly_front=V(0, -0.5, 1.42),
        )

    def belly_region(self, head):
        return sdf.ellipsoid((0, -0.45, 1.42), (0.52, 0.4, 0.82))


FAMILIES = {"Cute": Cute(), "Heavy": Heavy(), "Weird": Weird()}


# ═══ BODY BUILD ═══════════════════════════════════════════════════════════════

def _split_by_region(obj, region_fn, name_in, name_out):
    """Cut the mesh exactly along region_fn == 0 into two objects: smooth seam, identical
    boundary positions (so identical skin weights -> no cracks) and the unsplit normals kept
    as custom normals (no lighting seam)."""
    from mathutils.kdtree import KDTree
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
        _, nv = bmesh.utils.edge_split(e, a, t)
        vals[nv] = 0.0
        normals[nv] = na.lerp(nb, t).normalized()
        new_verts.add(nv)
    for f in list(bm.faces):
        on = [v for v in f.verts if v in new_verts]
        if len(on) == 2 and not bm.edges.get(on):
            try:
                bmesh.ops.connect_verts(bm, verts=on)
            except Exception:
                pass
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.verts.index_update()
    idx_vals = [vals[v] for v in bm.verts]
    all_norms = [normals[v] for v in bm.verts]
    kd = KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert(v.co, i)
    kd.balance()
    out = []
    for want_inside, name in ((True, name_in), (False, name_out)):
        part = bm.copy()
        part.verts.ensure_lookup_table()
        doomed = [f for f in part.faces if (sum(idx_vals[v.index] for v in f.verts) / len(f.verts) < 0) != want_inside]
        bmesh.ops.delete(part, geom=doomed, context="FACES")
        bmesh.ops.delete(part, geom=[v for v in part.verts if not v.link_faces], context="VERTS")
        me = bpy.data.meshes.new(name)
        part.to_mesh(me)
        part.free()
        vn = [all_norms[kd.find(v.co)[1]] for v in me.vertices]
        try:
            me.normals_split_custom_set_from_vertices(vn)
        except Exception:
            pass
        o = bpy.data.objects.new(name, me)
        fk.link(o)
        fk.shade_smooth(o)
        out.append(o)
    bm.free()
    bpy.data.objects.remove(obj, do_unlink=True)
    return out[0], out[1]


BODY_BONES = ["Root", "Spine", "Belly", "Neck", "Head", "Jaw", "CheekL", "CheekR", "Tail1"]


def build_body(fam, head):
    obj = sdf.to_mesh(f"Body__{head}", fam.body_shape(head), voxel=0.03 * max(1.0, fam.ps))
    obj = fk.decimate_to(obj, 5600)
    fk.solid_color(obj, WHITE)
    fk.bake_ao(obj, floor_z=0.0, samples=24, distance=0.7 * fam.ps, strength=0.5)
    fk.box_uv(obj, studs_per_tile=2.0)
    arm = fk.armature(f"Rig_{fam.name}_{head}", fam.skeleton(head))
    region = fam.belly_region(head)
    belly, main = _split_by_region(obj, region[0], f"Body__{head}__Belly", f"Body__{head}__Main")
    for piece in (main, belly):
        fk.skin(piece, arm, BODY_BONES, falloff=0.45 * fam.ps, custom=fam.jaw_custom(head))
    return arm, main, belly


# ═══ PART HELPERS ═════════════════════════════════════════════════════════════

def sdf_part(name, shape, voxel=0.02, tris=900, paint=None, ao=0.0, flat=False):
    obj = sdf.to_mesh(name, shape, voxel=voxel)
    obj = fk.decimate_to(obj, tris)
    if flat:
        fk.shade_flat(obj)
    if paint:
        fk.paint(obj, paint)
    else:
        fk.solid_color(obj, WHITE)
    if ao:
        fk.bake_ao(obj, samples=12, distance=0.25, strength=ao)
    fk.box_uv(obj, 2.0)
    return obj


def grey(k):
    return (k, k, k)


def curve_points(a, b, bend, n=6):
    """Quadratic arc from a to b bulging by vector `bend` at the middle."""
    a, b, bend = Vector(a), Vector(b), Vector(bend)
    mid = (a + b) * 0.5 + bend
    return [a * (1 - t) ** 2 + mid * 2 * t * (1 - t) + b * t * t for t in (i / (n - 1) for i in range(n))]


def chain_shape(points, radii, k=0.06):
    """Smooth union of round cones along a polyline."""
    shapes = [sdf.round_cone(T(points[i]), T(points[i + 1]), radii[i], radii[i + 1]) for i in range(len(points) - 1)]
    return sdf.smooth_union(*shapes, k=k)


def _stretch(shape, center, factors):
    c = np.array(T(center), dtype=np.float32)
    f = np.array(factors, dtype=np.float32)
    return sdf.warp(shape, lambda P: (P - c) * f + c)


# ═══ EYES ═════════════════════════════════════════════════════════════════════

def _eye_set(variant, e, radius, tag, bone, pupil_scale=0.78, glow=False):
    squash = (1.0, 0.62, 1.08)
    out = []
    white = fk.uv_sphere(f"Eyes__{variant}__White{tag}", e, radius, 20, 12, scale=squash)
    fk.solid_color(white, (0.98, 0.98, 0.96))
    out.append((white, bone))
    pr = radius * pupil_scale
    pupil = fk.uv_sphere(f"Eyes__{variant}__Pupil{tag}", e + V(0, -radius * squash[1] * 0.42, 0), pr, 18, 10, scale=(0.92, 0.55, 1.0))
    if glow:
        fk.paint(pupil, lambda co, n, e=e, pr=pr: grey(1.0) if (co - e).length > pr * 0.2 else grey(0.75))
    else:
        fk.paint(pupil, lambda co, n, e=e, pr=pr: (0.09, 0.07, 0.13) if (co - e).length > pr * 0.35 else (0.02, 0.02, 0.03))
    out.append((pupil, bone))
    k = radius / 0.29
    shine = fk.uv_sphere(f"Eyes__{variant}__Shine{tag}", e + V(0.1 * k, -radius * squash[1] - 0.02 * k, radius * 0.36), radius * 0.2, 10, 6, scale=(1.0, 0.5, 1.0))
    fk.solid_color(shine, WHITE)
    small = fk.uv_sphere(f"Eyes__{variant}__Shine2{tag}", e + V(-0.08 * k, -radius * squash[1] - 0.01 * k, -radius * 0.24), radius * 0.09, 8, 5, scale=(1.0, 0.5, 1.0))
    fk.solid_color(small, WHITE)
    out += [(shine, bone), (small, bone)]
    return out


def _lid(variant, tag, e, radius, bone, squash=(1.0, 0.62, 1.08), droop=0.0):
    """Upper-eyelid shell, rest pose OPEN (tucked up and back into the brow). The animator
    rotates LidX by up to -165 degrees to close it. `droop` bakes a sleepy lid."""
    r = radius * 1.09
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=22, v_segments=12, radius=r)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -r * 0.04], context="VERTS")
    angle = math.radians(-78 + 110 * droop)
    m = Matrix.Translation(e) @ Euler((angle, 0, 0)).to_matrix().to_4x4() @ Matrix.Diagonal(V(*squash, 1.0))
    bmesh.ops.transform(bm, matrix=m, verts=bm.verts)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.022)
    obj = fk.mesh_object(f"Eyes__{variant}__Lid{tag}", bm)
    fk.shade_smooth(obj)
    fk.solid_color(obj, grey(0.94))
    return (obj, bone)


def part_eyes(fam, variant):
    s = fam.sockets("Round")
    r = fam.eye_r
    ps = fam.ps
    out = []
    if variant in ("Big", "Glow", "Sleepy"):
        rr = {"Big": r, "Glow": r * 0.97, "Sleepy": r * 0.88}[variant]
        pscale = {"Big": 0.8, "Glow": 0.84, "Sleepy": 0.72}[variant]
        for side in "LR":
            e = s["eye" + side]
            out += _eye_set(variant, e, rr, side, "Eye" + side, pupil_scale=pscale, glow=variant == "Glow")
            out.append(_lid(variant, side, e, rr, "Lid" + side, droop=0.62 if variant == "Sleepy" else 0.0))
    elif variant == "Dot":
        for side in "LR":
            e = s["eye" + side]
            bead = fk.uv_sphere(f"Eyes__Dot__Pupil{side}", e + V(0, -0.1, 0) * ps, 0.16 * ps, 16, 10, scale=(0.85, 0.62, 1.0))
            fk.solid_color(bead, (0.06, 0.05, 0.08))
            shine = fk.uv_sphere(f"Eyes__Dot__Shine{side}", e + V(0.045, -0.2, 0.065) * ps, 0.04 * ps, 8, 5)
            fk.solid_color(shine, WHITE)
            out += [(bead, "Eye" + side), (shine, "Eye" + side)]
            out.append(_lid("Dot", side, e + V(0, -0.1, 0) * ps, 0.16 * ps, "Lid" + side, squash=(0.85, 0.62, 1.0)))
    elif variant == "Many":
        for side in "LR":
            e = s["eye" + side]
            out += _eye_set(variant, e, r * 0.82, side, "Eye" + side)
            out.append(_lid(variant, side, e, r * 0.82, "Lid" + side))
        fy, ez = s["face_y"], s["eyeL"].z
        for tag, c, rad in (("C", V(0, fy + 0.16, ez + 0.4), 0.17), ("D", V(0.72, fy + 0.46, ez - 0.18), 0.12),
                            ("E", V(-0.72, fy + 0.46, ez - 0.18), 0.12), ("F", V(0.28, fy + 0.3, ez + 0.52), 0.09)):
            cc = V(c.x * ps, fy + (c.y - fy) * ps, ez + (c.z - ez) * ps)
            out += _eye_set(variant, cc, rad * ps, tag, "Head")
    elif variant == "Screen":
        fy = s["face_y"]
        ez = s["eyeL"].z - 0.08 * ps
        bezel = sdf.round_box((0, fy + 0.02 * ps, ez), (0.66 * ps, 0.16 * ps, 0.44 * ps), 0.12 * ps)
        cut = sdf.round_box((0, fy - 0.16 * ps, ez), (0.54 * ps, 0.08 * ps, 0.33 * ps), 0.06 * ps)
        out.append((sdf_part("Eyes__Screen__Bezel", sdf.smooth_subtract(bezel, cut, k=0.01), voxel=0.018, tris=900, ao=0.3), "Head"))

        def pixels(co, n, ez=ez, ps=ps):
            for ex in (-0.22 * ps, 0.22 * ps):
                if abs(co.x - ex) < 0.09 * ps and abs(co.z - (ez + 0.06 * ps)) < 0.11 * ps:
                    return grey(0.12)
            if abs(co.x) < 0.14 * ps and abs(co.z - (ez - 0.17 * ps)) < 0.03 * ps:
                return grey(0.2)
            return grey(0.92 + 0.08 * math.sin(co.z * 60))

        screen = sdf_part("Eyes__Screen__Screen", sdf.round_box((0, fy - 0.1 * ps, ez), (0.55 * ps, 0.03 * ps, 0.34 * ps), 0.05 * ps),
                          voxel=0.012, tris=1600, paint=pixels)
        out.append((screen, "Head"))
    return out


# ═══ MOUTH ════════════════════════════════════════════════════════════════════

def part_mouth(fam, variant):
    s = fam.sockets("Round")
    ps = fam.ps
    slit = s["slit"]
    out = []
    size = 1.35 if variant == "Gaping" else 1.0
    inner = fk.uv_sphere(f"Mouth__{variant}__Inner", V(0, slit.y + 0.3 * ps, slit.z - 0.04 * ps), 0.3 * ps * size, 18, 10, scale=(1.0, 0.85, 0.72))
    fk.paint(inner, lambda co, n: (0.3, 0.07, 0.11))
    out.append((inner, "Head"))
    tongue = fk.uv_sphere(f"Mouth__{variant}__Tongue", V(0, slit.y + 0.28 * ps, slit.z - 0.12 * ps), 0.19 * ps * size, 16, 8, scale=(1.0, 1.35, 0.42))
    fk.paint(tongue, lambda co, n: (0.96, 0.46, 0.56))
    out.append((tongue, "Tongue"))
    if variant == "Fangs":
        for x, tag in ((0.13 * ps, "L"), (-0.13 * ps, "R")):
            fang = sdf_part(f"Mouth__Fangs__Fang{tag}",
                            sdf.round_cone((x, slit.y + 0.05 * ps, slit.z + 0.03 * ps), (x, slit.y + 0.02 * ps, slit.z - 0.13 * ps), 0.05 * ps, 0.008 * ps),
                            voxel=0.008, tris=300)
            out.append((fang, "Head"))
    elif variant == "Gaping":
        for i in range(5):
            a = (i - 2) / 2.0
            x = a * 0.24 * ps
            y = slit.y + 0.06 * ps + abs(a) * 0.1 * ps
            up = sdf_part(f"Mouth__Gaping__ToothU{i}", sdf.round_cone((x, y, slit.z + 0.03 * ps), (x, y, slit.z - 0.08 * ps), 0.04 * ps, 0.006 * ps), voxel=0.008, tris=160)
            out.append((up, "Head"))
            if i % 2 == 0:
                lo = sdf_part(f"Mouth__Gaping__ToothL{i}", sdf.round_cone((x, y + 0.02 * ps, slit.z - 0.2 * ps), (x, y + 0.02 * ps, slit.z - 0.09 * ps), 0.035 * ps, 0.006 * ps), voxel=0.008, tris=160)
                out.append((lo, "Jaw"))
    elif variant == "Beak":
        upper = sdf.ellipsoid((0, slit.y - 0.2 * ps, slit.z + 0.07 * ps), (0.36 * ps, 0.36 * ps, 0.11 * ps))
        upper = sdf.smooth_subtract(upper, sdf.ellipsoid((0, slit.y - 0.2 * ps, slit.z - 0.02 * ps), (0.5 * ps, 0.6 * ps, 0.05 * ps)), k=0.02)
        nostril = sdf.mirror_x(sdf.sphere((0.1 * ps, slit.y - 0.38 * ps, slit.z + 0.16 * ps), 0.025 * ps))
        upper = sdf.smooth_subtract(upper, nostril, k=0.01)
        out.append((sdf_part("Mouth__Beak__BeakUpper", upper, voxel=0.012, tris=900, paint=lambda co, n: grey(1.0 if n.z > -0.2 else 0.85)), "Head"))
        lower = sdf.ellipsoid((0, slit.y - 0.14 * ps, slit.z - 0.06 * ps), (0.3 * ps, 0.3 * ps, 0.08 * ps))
        lower = sdf.smooth_subtract(lower, sdf.ellipsoid((0, slit.y - 0.14 * ps, slit.z + 0.03 * ps), (0.45 * ps, 0.5 * ps, 0.05 * ps)), k=0.02)
        out.append((sdf_part("Mouth__Beak__BeakLower", lower, voxel=0.012, tris=700, paint=lambda co, n: grey(0.9)), "Jaw"))
    return out


# ═══ EARS ═════════════════════════════════════════════════════════════════════

def part_ears(fam, variant):
    s = fam.sockets("Round")
    ps = fam.ps
    out = []
    for side, sign in (("L", 1), ("R", -1)):
        e = s["ear" + side]
        bone = "Ear" + side
        if variant == "Round":
            outer = sdf.ellipsoid(T(e + V(0.08 * sign, 0, 0.18) * ps), (0.3 * ps, 0.13 * ps, 0.3 * ps), rot=(0, 25 * sign, 0))
            dent = sdf.ellipsoid(T(e + V(0.08 * sign, -0.12, 0.2) * ps), (0.2 * ps, 0.08 * ps, 0.2 * ps), rot=(0, 25 * sign, 0))
            out.append((sdf_part(f"Ears__Round__Ear{side}", sdf.smooth_subtract(outer, dent, k=0.04 * ps), tris=700,
                                 paint=lambda co, n: grey(1.0) if n.y > -0.4 else grey(0.84)), bone))
        elif variant == "Pointy":
            tip = e + V(0.34 * sign, 0.06, 0.78) * ps
            cone = sdf.round_cone(T(e + V(0, 0, 0.05) * ps), T(tip), 0.2 * ps, 0.02 * ps)
            out.append((sdf_part(f"Ears__Pointy__Ear{side}", _stretch(cone, e, (1, 2.1, 1)), tris=700,
                                 paint=lambda co, n: grey(1.0) if n.y > -0.3 else grey(0.8)), bone))
        elif variant == "Floppy":
            pts = [e + V(0.02 * sign, 0, 0.02) * ps, e + V(0.3 * sign, 0.02, 0.1) * ps, e + V(0.55 * sign, 0.04, -0.12) * ps,
                   e + V(0.66 * sign, 0.02, -0.52) * ps, e + V(0.62 * sign, 0.0, -0.82) * ps]
            radii = [0.13 * ps, 0.19 * ps, 0.21 * ps, 0.18 * ps, 0.08 * ps]
            ear = _stretch(chain_shape(pts, radii, k=0.1 * ps), e, (1, 2.4, 1))
            out.append((sdf_part(f"Ears__Floppy__Ear{side}", ear, tris=900, paint=lambda co, n: grey(1.0) if n.y > -0.3 else grey(0.82)), bone))
        elif variant == "Antenna":
            base = s["horn" + side] + V(-0.06 * sign, 0.05, -0.05) * ps
            pts = curve_points(base, base + V(0.28 * sign, -0.1, 0.72) * ps, V(0.18 * sign, 0.12, 0.05) * ps, n=6)
            stalk = sdf_part(f"Ears__Antenna__Stalk{side}", chain_shape(pts, [0.055 * ps] * 3 + [0.04 * ps] * 3, k=0.02), voxel=0.012, tris=500)
            bulb = fk.uv_sphere(f"Ears__Antenna__Bulb{side}", pts[-1] + V(0.02 * sign, -0.02, 0.08) * ps, 0.13 * ps, 16, 10)
            fk.paint(bulb, lambda co, n: grey(1.0) if n.z > -0.3 else grey(0.8))
            out += [(stalk, bone), (bulb, bone)]
    return out


# ═══ HORNS ════════════════════════════════════════════════════════════════════

def part_horn(fam, variant):
    s = fam.sockets("Round")
    ps = fam.ps
    out = []
    if variant == "Nub":
        c = s["hornC"]
        stem_pts = curve_points(c + V(0, 0, -0.05) * ps, c + V(0, 0.04, 0.3) * ps, V(0.03, 0, 0) * ps, n=5)
        out.append((sdf_part("Horn__Nub__Stem", chain_shape(stem_pts, [0.05 * ps, 0.045 * ps, 0.04 * ps, 0.035 * ps, 0.03 * ps], k=0.02),
                             voxel=0.01, tris=300), "HornC"))
        top = stem_pts[-1]
        for tag, sign, lift in (("A", 1, 0.0), ("B", -1, 0.05)):
            leaf = sdf.ellipsoid(T(top + V(0.2 * sign, -0.02, 0.1 + lift) * ps), (0.22 * ps, 0.1 * ps, 0.035 * ps), rot=(10, 0, -30 * sign))
            vein = sdf.ellipsoid(T(top + V(0.2 * sign, -0.02, 0.135 + lift) * ps), (0.2 * ps, 0.008 * ps, 0.02 * ps), rot=(10, 0, -30 * sign))
            out.append((sdf_part(f"Horn__Nub__Leaf{tag}", sdf.smooth_subtract(leaf, vein, k=0.01), voxel=0.008, tris=500,
                                 paint=lambda co, n: grey(1.0) if n.z > 0 else grey(0.78)), "HornC"))
    elif variant == "Curved":
        for side, sign in (("L", 1), ("R", -1)):
            h = s["horn" + side]
            pts = []
            for i in range(9):
                t = i / 8
                ang = t * 3.4
                rad = 0.36 * (1 - 0.35 * t) * ps
                pts.append(h + V(sign * (0.08 * ps + rad * math.sin(ang) * 0.9), 0.12 * t * ps + rad * (1 - math.cos(ang)) * 0.9,
                                 rad * math.sin(ang * 0.9) * 0.6 + 0.1 * t * ps))
            radii = [(0.14 - 0.11 * i / 8) * ps for i in range(9)]
            out.append((sdf_part(f"Horn__Curved__Horn{side}", chain_shape(pts, radii, k=0.03 * ps), voxel=0.012, tris=1200,
                                 paint=lambda co, n, h=h: grey(0.85 + 0.15 * (0.5 + 0.5 * math.sin((co - h).length * 60)))), "Horn" + side))
    elif variant == "Crystal":
        for side, sign in (("L", 1), ("R", -1)):
            h = s["horn" + side]
            shards = []
            for (dx, dy, tilt_x, tilt_y, length, rad) in ((0, 0, -8, 12, 0.62, 0.1), (0.1, 0.1, 18, 30, 0.42, 0.07), (-0.08, -0.06, -20, -8, 0.36, 0.065)):
                base = h + V(dx * sign, dy, 0) * ps
                direction = Euler((math.radians(tilt_x), math.radians(tilt_y * sign), 0)).to_matrix() @ V(0, 0, 1)
                tip = base + direction * length * ps
                mid = base + direction * length * 0.7 * ps
                shards.append(sdf.union(sdf.round_cone(T(base), T(mid), rad * ps, rad * 0.95 * ps), sdf.round_cone(T(mid), T(tip), rad * 0.95 * ps, 0.005)))
            out.append((sdf_part(f"Horn__Crystal__Crystal{side}", sdf.union(*shards), voxel=0.014, tris=500, flat=True,
                                 paint=lambda co, n: grey(0.8 + 0.2 * abs(n.x))), "Horn" + side))
    elif variant == "Single":
        c = s["hornC"] + V(0, -0.12, -0.04) * ps
        tip = c + V(0, -0.36, 0.86) * ps
        cone = sdf.round_cone(T(c), T(tip), 0.15 * ps, 0.01 * ps)
        axis = np.array(T((tip - c).normalized()), dtype=np.float32)
        c0 = np.array(T(c), dtype=np.float32)
        spiral = sdf.warp(cone, lambda P: P + np.outer(np.sin(((P - c0) @ axis) * 34.0) * 0.012 * ps, np.array([1, 0, 0], dtype=np.float32)))
        out.append((sdf_part("Horn__Single__Horn", spiral, voxel=0.01, tris=900,
                             paint=lambda co, n, c=c: grey(0.88 + 0.12 * math.sin((co - c).length * 70))), "HornC"))
    elif variant == "Crown":
        c = s["hornC"] + V(0, 0.02, -0.02) * ps
        ring = sdf.smooth_subtract(sdf.cylinder(T(c + V(0, 0, 0.08) * ps), 0.3 * ps, 0.09 * ps, rounding=0.02 * ps),
                                   sdf.cylinder(T(c + V(0, 0, 0.08) * ps), 0.24 * ps, 0.2 * ps), k=0.01)
        spikes = []
        for i in range(5):
            a = i / 5 * math.tau + math.pi / 2
            base = c + V(math.cos(a) * 0.27, math.sin(a) * 0.27, 0.14) * ps
            spikes.append(sdf.round_cone(T(base), T(base + V(0, 0, 0.2) * ps), 0.065 * ps, 0.012 * ps))
            spikes.append(sdf.sphere(T(base + V(0, 0, 0.22) * ps), 0.035 * ps))
        out.append((sdf_part("Horn__Crown__Crown", sdf.union(ring, *spikes), voxel=0.01, tris=1400,
                             paint=lambda co, n: grey(0.8 + 0.2 * max(0, n.z))), "HornC"))
        gem = fk.uv_sphere("Horn__Crown__Gem", c + V(0, -0.29, 0.1) * ps, 0.07 * ps, 8, 6, scale=(1, 0.6, 1.2))
        fk.shade_flat(gem)
        fk.solid_color(gem, WHITE)
        out.append((gem, "HornC"))
    return out


# ═══ BACK ═════════════════════════════════════════════════════════════════════

def part_back(fam, variant):
    s = fam.sockets("Round")
    ps = fam.ps
    out = []
    path = s["back_surface"]
    if variant == "Spikes":
        spikes = []
        for i, t in enumerate((0.08, 0.34, 0.6, 0.86)):
            seg = t * (len(path) - 1)
            j = min(int(seg), len(path) - 2)
            p = path[j].lerp(path[j + 1], seg - j)
            size = (0.24 - 0.04 * abs(i - 1.2)) * ps
            tip = p + V(0, 0.18, 0.42) * size / 0.24
            spikes.append(sdf.round_cone(T(p - V(0, 0, 0.05) * ps), T(tip), size * 0.55, 0.015 * ps))
        out.append((sdf_part("Back__Spikes__Spike", sdf.smooth_union(*spikes, k=0.04), voxel=0.014, tris=1000,
                             paint=lambda co, n: grey(0.85 + 0.15 * max(0, n.z))), "Back"))
    elif variant == "Shell":
        c = s["back"] + V(0, 0.08, 0.16) * ps
        blobs = []
        for i in range(14):
            t = i / 13
            ang = t * 2.6 * math.pi
            rad = 0.62 * math.exp(-t * 1.3) * ps
            pos = c + V(0, math.sin(ang) * rad * 0.95, math.cos(ang) * rad * 0.95 + 0.1 * ps)
            blobs.append(sdf.sphere(T(pos), (0.5 * math.exp(-t * 1.25) + 0.05) * ps))
        shell = _stretch(sdf.smooth_union(*blobs, k=0.16 * ps), c, (1 / 1.35, 1, 1))

        def spiral_paint(co, n, c=c):
            rel = co - c
            return grey(0.72 + 0.28 * (0.5 + 0.5 * math.sin(math.atan2(rel.y, rel.z) * 2 + math.hypot(rel.y, rel.z) * 26 / ps)))

        out.append((sdf_part("Back__Shell__Shell", shell, voxel=0.02 * ps, tris=2200, paint=spiral_paint, ao=0.3), "Back"))
    elif variant == "Wings":
        for side, sign in (("L", 1), ("R", -1)):
            w = s["wing" + side]
            upper = sdf.ellipsoid(T(w + V(0.95 * sign, 0.22, 0.78) * ps), (1.05 * ps, 0.045 * ps, 0.82 * ps), rot=(-8, -40 * sign, 0))
            lower = sdf.ellipsoid(T(w + V(0.72 * sign, 0.42, -0.05) * ps), (0.62 * ps, 0.04 * ps, 0.5 * ps), rot=(-6, 34 * sign, 0))
            root = sdf.sphere(T(w + V(0.06 * sign, 0.05, 0.1) * ps), 0.1 * ps)
            wx = w.x
            shape = sdf.warp(sdf.smooth_union(upper, lower, root, k=0.14 * ps),
                             lambda P, wx=wx, sign=sign: P + np.outer(((P[:, 0] - wx) * sign) ** 2 * 0.18 / ps, np.array([0, 1, 0], dtype=np.float32)))
            spots = [w + V(0.95 * sign, 0.22, 0.95) * ps, w + V(0.72 * sign, 0.42, -0.1) * ps]

            def wing_paint(co, n, w=w, spots=spots):
                for sp in spots:
                    d = (co - sp).length / ps
                    if d < 0.2:
                        return grey(0.5)
                    if d < 0.27:
                        return grey(1.0)
                return grey(1.0 - 0.4 * fk.smoothstep(0.9, 1.6, (co - w).length / ps))

            out.append((sdf_part(f"Back__Wings__Wing{side}", shape, voxel=0.016, tris=1100, paint=wing_paint), "Wing" + side))
    elif variant == "Fins":
        fin = sdf.ellipsoid(T(s["back"] + V(0, 0.16, 0.34) * ps), (0.035 * ps, 0.62 * ps, 0.42 * ps), rot=(-22, 0, 0))
        fin = sdf.smooth_subtract(fin, sdf.ellipsoid(T(s["back"] + V(0, 0.2, -0.08) * ps), (0.3 * ps, 0.9 * ps, 0.3 * ps)), k=0.05 * ps)
        out.append((sdf_part("Back__Fins__Fin", fin, voxel=0.012, tris=900,
                             paint=lambda co, n: grey(0.78 + 0.22 * (0.5 + 0.5 * math.sin(co.y * 22 / ps)))), "Back"))
    elif variant == "Mushroom":
        for i, (off, cap_r, stem_h) in enumerate(((V(0.36, 0.3, 0.12), 0.34, 0.36), (V(-0.28, 0.6, 0.02), 0.26, 0.26), (V(0.02, 0.0, 0.08), 0.2, 0.22))):
            base = s["back"] + off * ps + V(0, 0, -0.08) * ps
            top = base + V(0, 0, stem_h) * ps
            out.append((sdf_part(f"Back__Mushroom__Stem{i}", sdf.round_cone(T(base), T(top), 0.08 * ps, 0.06 * ps), voxel=0.012, tris=300,
                                 paint=lambda co, n: grey(0.95)), "Back"))
            dome = sdf.ellipsoid(T(top + V(0, 0, 0.02) * ps), (cap_r * ps, cap_r * ps, cap_r * 0.62 * ps))
            dome = sdf.smooth_subtract(dome, sdf.ellipsoid(T(top - V(0, 0, 0.1) * ps), (cap_r * 1.2 * ps, cap_r * 1.2 * ps, cap_r * 0.35 * ps)), k=0.03 * ps)
            out.append((sdf_part(f"Back__Mushroom__Cap{i}", dome, voxel=0.012, tris=700,
                                 paint=lambda co, n: grey(1.0) if n.z > -0.2 else grey(0.7)), "Back"))
            dots = []
            for j in range(5):
                a = j / 5 * math.tau + i
                el = 0.55 if j % 2 else 0.3
                p = top + V(math.cos(a) * cap_r * el, math.sin(a) * cap_r * el, cap_r * 0.62 * math.sqrt(max(0.0, 1 - el * el)) + 0.02) * ps
                dots.append(sdf.ellipsoid(T(p), (0.05 * ps, 0.05 * ps, 0.02 * ps)))
            out.append((sdf_part(f"Back__Mushroom__Dots{i}", sdf.union(*dots), voxel=0.008, tris=300), "Back"))
    elif variant == "Screen":
        bf = s["belly_front"]
        bezel = sdf.round_box(T(bf + V(0, 0.02, 0) * ps), (0.44 * ps, 0.1 * ps, 0.34 * ps), 0.08 * ps, rot=(12, 0, 0))
        out.append((sdf_part("Back__Screen__Bezel", bezel, voxel=0.016, tris=600, ao=0.2), "Belly"))
        scr = sdf.round_box(T(bf + V(0, -0.07, 0) * ps), (0.36 * ps, 0.03 * ps, 0.26 * ps), 0.04 * ps, rot=(12, 0, 0))
        out.append((sdf_part("Back__Screen__Screen", scr, voxel=0.01, tris=900,
                             paint=lambda co, n: grey(0.85 + 0.15 * math.sin(co.x * 90) * math.sin(co.z * 70))), "Belly"))
    return out


# ═══ TAILS ════════════════════════════════════════════════════════════════════

TAIL_BONES = ["Tail1", "Tail2", "Tail3", "Tail4"]


def part_tail(fam, variant):
    s = fam.sockets("Round")
    ps = fam.ps
    t = s["tail"]
    out = []
    if variant == "Stub":
        ball = fk.uv_sphere("Tail__Stub__Tail", t[0] + V(0, 0.2, 0.1) * ps, 0.28 * ps, 16, 10)
        fk.solid_color(ball, WHITE)
        fk.bake_ao(ball, samples=8, distance=0.2, strength=0.2)
        out.append((ball, "Tail1"))
    elif variant == "Long":
        out.append((sdf_part("Tail__Long__Tail", chain_shape(t, [0.2 * ps, 0.16 * ps, 0.12 * ps, 0.085 * ps, 0.045 * ps], k=0.04 * ps),
                             voxel=0.016, tris=1200), TAIL_BONES))
    elif variant == "Fluffy":
        pts = curve_points(t[0], t[0] + V(0, 0.55, 1.35) * ps, V(0, 0.55, 0.1) * ps, n=7)
        shape = chain_shape(pts, [r * ps for r in (0.18, 0.3, 0.4, 0.44, 0.4, 0.3, 0.12)], k=0.12 * ps)
        shape = sdf.noise_bumps(shape, amplitude=0.035 * ps, frequency=11.0 / ps, seed=3)
        out.append((sdf_part("Tail__Fluffy__Tail", shape, voxel=0.02, tris=1600,
                             paint=lambda co, n, tip=pts[-2]: grey(1.0 if (co - tip).length > 0.3 * ps else 0.92)), TAIL_BONES))
    elif variant == "Bolt":
        zig = [V(0, 0, 0), V(0, 0.32, 0.4), V(0, 0.2, 0.62), V(0, 0.62, 1.08), V(0, 0.46, 1.24), V(0, 0.95, 1.72)]
        zig = [t[0] + p * ps for p in zig]
        shape = _stretch(chain_shape(zig, [r * ps for r in (0.13, 0.12, 0.12, 0.1, 0.1, 0.02)], k=0.01), t[0], (2.4, 1, 1))
        out.append((sdf_part("Tail__Bolt__Tail", shape, voxel=0.012, tris=900, flat=True), TAIL_BONES))
    elif variant == "FishTail":
        out.append((sdf_part("Tail__FishTail__Tail", chain_shape(t[:4], [0.22 * ps, 0.17 * ps, 0.12 * ps, 0.08 * ps], k=0.05 * ps),
                             voxel=0.016, tris=1000), TAIL_BONES))
        tip = t[3]
        lobes = [sdf.ellipsoid(T(tip + V(0, 0.34, 0.3 * sign) * ps), (0.045 * ps, 0.42 * ps, 0.2 * ps), rot=(40 * sign, 0, 0)) for sign in (1, -1)]
        out.append((sdf_part("Tail__FishTail__Fin", sdf.smooth_union(*lobes, k=0.08 * ps), voxel=0.012, tris=800,
                             paint=lambda co, n, tip=tip: grey(0.75 + 0.25 * (0.5 + 0.5 * math.sin((co - tip).length * 30 / ps)))), ["Tail3", "Tail4"]))
    return out


# ═══ LEGS ═════════════════════════════════════════════════════════════════════

def part_legs(fam, variant):
    s = fam.sockets("Round")
    ps = fam.ps
    lr = fam.leg_r
    out = []
    for leg in fam.legs:
        hip, knee, foot = s["legs"][leg]
        bones = [f"Leg{leg}1", f"Leg{leg}2"]
        if leg in getattr(fam, "arms", ()):
            # arms: same variant language, but they hang from the chest and never reach
            # the ground, so no drop and a small hand instead of a paw
            k = {"Stubby": (0.62, 0.9), "Chunky": (0.95, 0.85), "Long": (0.5, 1.25), "Noodle": (0.32, 1.45)}[variant]
            r = lr * k[0]
            elbow = hip + (knee - hip) * k[1]
            hand = hip + (foot - hip) * k[1]
            shape = sdf.smooth_union(chain_shape([hip, elbow, hand], [r, r * 0.85, r * 0.8], k=0.05 * ps),
                                     sdf.sphere(T(hand + (hand - elbow).normalized() * r * 0.6), r * 1.25), k=0.06 * ps)
            m = sdf_part(f"Legs__{variant}__{leg}", shape, voxel=0.018 * ps, tris=600)
            out.append((m, bones))
            continue
        if variant == "Stubby":
            shape = sdf.smooth_union(sdf.round_cone(T(hip + V(0, 0, 0.05)), T(foot + V(0, -0.02, 0.17) * ps), lr, lr * 0.88),
                                     sdf.ellipsoid(T(foot + V(0, -0.06, 0.1) * ps), (lr * 0.96, lr * 1.12, 0.13 * ps)), k=0.12 * ps)
        elif variant == "Chunky":
            shape = sdf.smooth_union(sdf.round_cone(T(hip + V(0, 0, 0.05)), T(foot + V(0, 0, 0.2) * ps), lr * 1.35, lr * 1.25),
                                     sdf.ellipsoid(T(foot + V(0, -0.08, 0.12) * ps), (lr * 1.4, lr * 1.55, 0.16 * ps)), k=0.12 * ps)
            shape = sdf.smooth_union(shape, *[sdf.sphere(T(foot + V(dx, -0.3, 0.09) * ps), 0.07 * ps) for dx in (-0.12, 0.0, 0.12)], k=0.05 * ps)
        elif variant == "Long":
            drop = 0.75 * ps
            k2 = knee + V(0, 0.1 if leg[0] == "F" else -0.1, -drop * 0.45)
            f2 = foot + V(0, 0, -drop)
            shape = sdf.smooth_union(chain_shape([hip + V(0, 0, 0.05), k2, f2 + V(0, 0, 0.12) * ps], [lr * 0.85, lr * 0.6, lr * 0.55], k=0.08 * ps),
                                     sdf.ellipsoid(T(f2 + V(0, -0.07, 0.08) * ps), (lr * 0.8, lr * 1.05, 0.1 * ps)), k=0.08 * ps)
        elif variant == "Noodle":
            f2 = foot + V(0, 0, -1.15 * ps)
            bend = V(0.1 if leg[1] == "L" else -0.1, 0, 0) * ps
            shape = sdf.smooth_union(chain_shape(curve_points(hip + V(0, 0, 0.05), f2 + V(0, 0, 0.08) * ps, bend, n=6), [lr * 0.42] * 6, k=0.03),
                                     sdf.ellipsoid(T(f2 + V(0, -0.08, 0.06) * ps), (lr * 0.62, lr * 0.95, 0.07 * ps)), k=0.06 * ps)
        else:
            continue
        m = sdf_part(f"Legs__{variant}__{leg}", shape, voxel=0.022 * ps, tris=800)
        fk.bake_ao(m, floor_z=min(v.co.z for v in m.data.vertices), samples=12, distance=0.3 * ps, strength=0.35)
        out.append((m, bones))
    return out


PART_BUILDERS = {
    "Eyes": part_eyes, "Mouth": part_mouth, "Ears": part_ears, "Horn": part_horn,
    "Back": part_back, "Tail": part_tail, "Legs": part_legs,
}

ALL_PARTS = {
    "Eyes": ["Dot", "Big", "Sleepy", "Glow", "Many", "Screen"],
    "Mouth": ["Smile", "Fangs", "Beak", "Gaping"],
    "Ears": ["Round", "Floppy", "Pointy", "Antenna"],
    "Horn": ["Nub", "Curved", "Crystal", "Single", "Crown"],
    "Back": ["Spikes", "Shell", "Wings", "Fins", "Mushroom", "Screen"],
    "Tail": ["Stub", "Long", "Fluffy", "Bolt", "FishTail"],
    "Legs": ["Stubby", "Long", "Chunky", "Noodle"],
}


def build_part(fam, arm, slot, variant):
    objs = []
    for obj, bones in PART_BUILDERS[slot](fam, variant):
        if isinstance(bones, str):
            fk.skin(obj, arm, [bones], rigid=bones)
        else:
            fk.skin(obj, arm, bones, falloff=0.3 * fam.ps)
        objs.append(obj)
    return objs


FIXED = ("__White", "__Pupil", "__Shine", "__Inner", "__Tongue", "__Fang", "__Tooth", "__Bezel", "__Dots", "__Stem")


def preview_tints(objs, primary=(1.0, 0.62, 0.72), secondary=(0.62, 0.78, 1.0), trait=(0.55, 0.9, 1.0)):
    belly = tuple(primary[i] + (1 - primary[i]) * 0.6 for i in range(3))
    for o in objs:
        n = o.name
        if "__Belly" in n:
            fk.preview_tint(o, belly)
        elif any(k in n for k in FIXED):
            fk.preview_tint(o, WHITE)
        elif any(k in n for k in ("__Crystal", "__Screen", "__Bulb", "__Wing", "__Fin", "__Cap", "Horn__Single")):
            fk.preview_tint(o, trait)
        elif "__Leaf" in n:
            fk.preview_tint(o, (0.42, 0.76, 0.29))
        elif any(k in n for k in ("__Crown", "__Gem", "__Beak")):
            fk.preview_tint(o, (1.0, 0.8, 0.25))
        elif "Horn__Curved" in n:
            fk.preview_tint(o, (0.94, 0.89, 0.8))
        elif any(k in n for k in ("__Spike", "__Shell")):
            fk.preview_tint(o, secondary)
        else:
            fk.preview_tint(o, primary)


# ═══ EXPORT ═══════════════════════════════════════════════════════════════════

def clear_scene_keep_preview():
    keep = ("PreviewFloor", "KeyLight", "FillLight", "PreviewCam")
    for o in list(bpy.data.objects):
        if o.name not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
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
    return fk.export_fbx([arm, main, belly, carrier], f"{fam.name.lower()}_body_{head}.fbx")


def export_parts(fam, selection=None):
    clear_scene_keep_preview()
    arm = fk.armature(f"Rig_{fam.name}_Parts", fam.skeleton("Round"))
    objs = []
    selection = selection or [(slot, v) for slot, vs in ALL_PARTS.items() for v in vs]
    for slot, variant in selection:
        objs += build_part(fam, arm, slot, variant)
    _strip_materials(objs)
    carrier = fk.socket_carrier(arm)
    return fk.export_fbx([arm] + objs + [carrier], f"{fam.name.lower()}_parts.fbx"), [o.name for o in objs]


# ═══ PREVIEW (Blender-side look before any upload) ═════════════════════════════

def preview_creature(fam, head, selection, offset=(0, 0, 0), primary=(1.0, 0.62, 0.72)):
    """Build body + selected parts in place, shifted by `offset`. Returns objects."""
    arm, main, belly = build_body(fam, head)
    objs = [main, belly]
    parts_arm = fk.armature(f"Rig_{fam.name}_PartsPrev", fam.skeleton("Round"))
    for slot, variant in selection:
        objs += build_part(fam, parts_arm, slot, variant)
    preview_tints(objs, primary=primary)
    off = Vector(offset)
    for o in objs + [arm, parts_arm]:
        if o.parent is None:  # children follow their armature; moving both doubles the offset
            o.location = o.location + off
    return objs
