"""kit_events — WORLD-EVENT props: UFO, tractor beam, giant picnic, meteor, earthquake rock seal.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/kit_events.py
      -> art/build/kit_events.fbx      one mesh per asset, base at z=0, centred XY, vertex colours
      -> art/previews/kit_events.jpg   labelled contact sheet (5-stud capsule in every tile)
                                       + a real-scale lineup seen from game distance

Iterate on a few assets without exporting:
    ... -P tools/blender/kit_events.py -- --only UFO_Saucer,Meteor_Big --sheet /path/sheet.jpg
Check the exported FBX (re-imports it into an empty scene and checks every kit rule):
    ... -P tools/blender/kit_events.py -- --verify

Same structure as kit_props.py: an asset is a list of Pieces (SDF sculpts or small hand-built
meshes), each meshed separately so colour edges stay crisp, decimated to a share of the asset's
budget, painted in sRGB (converted to the linear values Blender's byte colour attribute expects,
so the FBX carries the exact hex), joined, snapped to base z=0 / centred XY, then AO is baked.
Glowing pieces skip most of the AO.

Scale: these are big set pieces (the saucer is 26 studs wide), so voxel sizes are ~0.1-0.2 studs
and most crisp detail (gingham checks, wicker weave, saucer panels) is painted per FACE on
hand-built grids that line up with the pattern.
"""

import sys; sys.path.insert(0, "/Users/malik/rob/tools/blender")
import bpy, bmesh, math, numpy as np
from mathutils import Vector
import famkit as fk, sdf
fk.reset_scene()

import json
import os
import random
import shutil
import subprocess
import tempfile
import time

from mathutils import Euler, Matrix

ROOT = "/Users/malik/rob"
KIT = "kit_events"
FBX_NAME = KIT + ".fbx"
PREVIEW = os.path.join(ROOT, "art", "previews", KIT + ".jpg")


# ═══ COLOUR (as kit_props) ═══════════════════════════════════════════════════════

def H(h):
    """0xRRGGBB -> sRGB floats."""
    return ((h >> 16 & 255) / 255.0, (h >> 8 & 255) / 255.0, (h & 255) / 255.0)


def to_lin(c):
    # Byte colour attributes are read/written in linear; the FBX exporter writes sRGB.
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def mixc(a, b, t):
    t = clamp01(t)
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def lighter(c, t):
    return mixc(c, (1.0, 0.99, 0.94), t)


def richer(c, t):
    """Darker AND a touch more saturated (shadows in this game are colourful, not grey)."""
    t = clamp01(t)
    return tuple((x ** (1.0 + 0.9 * t)) * (1.0 - 0.18 * t) for x in c)


def tone(c, n, hi=0.2, lo=0.35):
    z = n.z
    if z >= 0:
        return lighter(c, hi * z * z)
    return richer(c, lo * -z)


ss = fk.smoothstep


def wave(co, f=6.0, seed=0.0):
    """Cheap smooth 3D noise in [-1, 1] for paint jobs."""
    x, y, z = co.x * f, co.y * f, co.z * f
    s = seed
    return 0.6 * math.sin(x + s * 1.7) * math.sin(y * 1.31 + s * 2.3) * math.sin(z * 0.87 + s * 0.9) + \
        0.4 * math.sin(x * 2.1 + z * 1.3 + s) * math.sin(y * 1.9 - x * 0.7 + s * 3.1)


# ═══ SDF EXTRAS (kit-local: sdf.py is shared and frozen) ═══════════════════════════

F32 = np.float32


def T(v):
    return (float(v[0]), float(v[1]), float(v[2]))


def U(*shapes, k=0.05):
    return sdf.smooth_union(*shapes, k=k) if len(shapes) > 1 else shapes[0]


def half_space(point, normal):
    """Everything on the +normal side of the plane is 'inside' (use as a cutter)."""
    n = np.asarray(normal, dtype=F32)
    n = n / np.linalg.norm(n)
    p = np.asarray(point, dtype=F32)
    return (lambda P: -((P - p) @ n), (p - 0.1, p + 0.1))


def surface(shape, p, iters=12, eps=1e-3):
    """Project a point onto the SDF surface. Returns (point, normal) as Vectors."""
    p = np.asarray(T(p), dtype=np.float64)
    g = np.array([0, 0, 1.0])
    for _ in range(iters):
        P = np.array([p, p + (eps, 0, 0), p - (eps, 0, 0), p + (0, eps, 0), p - (0, eps, 0),
                      p + (0, 0, eps), p - (0, 0, eps)], dtype=F32)
        D = shape[0](P).astype(np.float64)
        g = np.array([D[1] - D[2], D[3] - D[4], D[5] - D[6]]) / (2 * eps)
        ln = np.linalg.norm(g)
        if ln < 1e-8:
            break
        g /= ln
        p = p - D[0] * g
    return Vector(p), Vector(g)


def sdf_at(shape, co):
    return float(shape[0](np.array([[co.x, co.y, co.z]], dtype=F32))[0])


def ray_extent(shape, origin, direction, tmax=30.0, step=0.05):
    """Distance from origin (inside) along direction to the surface."""
    o, d = Vector(origin), Vector(direction).normalized()
    t = 0.0
    while t < tmax:
        if sdf_at(shape, o + d * t) > 0:
            return t
        t += step
    return tmax


# ═══ LITTLE HAND-BUILT MESHES ════════════════════════════════════════════════════

_uid = [0]


def _name(tag):
    _uid[0] += 1
    return f"_{tag}_{_uid[0]}"


def _frame(n):
    n = Vector(n).normalized()
    t = n.orthogonal().normalized()
    return n, t, n.cross(t)


def dots_mesh(spots, sides=6, sink=0.4):
    """spots: [(point, normal, radius, height)] -> one object of little lens-shaped studs."""
    bm = bmesh.new()
    for p, n, r, h in spots:
        n, t, b = _frame(n)
        base = Vector(p) - n * (h * sink)
        top = bm.verts.new(base + n * h)
        bot = bm.verts.new(base - n * h * 0.5)
        ring = [bm.verts.new(base + (t * math.cos(a) + b * math.sin(a)) * r)
                for a in (2 * math.pi * i / sides for i in range(sides))]
        for i in range(sides):
            j = (i + 1) % sides
            bm.faces.new((top, ring[i], ring[j]))
            bm.faces.new((bot, ring[j], ring[i]))
    return fk.mesh_object(_name("dots"), bm)


def crystal_mesh(specs):
    """specs: [(base, direction, radius, length, sides, tip_frac, twist_deg)] -> faceted prisms."""
    bm = bmesh.new()
    for base, d, r, length, sides, tipf, twist in specs:
        n, t, b = _frame(d)
        base = Vector(base)
        tw = math.radians(twist)
        ring0 = [bm.verts.new(base - n * 0.05 * length + (t * math.cos(a + tw) + b * math.sin(a + tw)) * r * 0.9)
                 for a in (2 * math.pi * i / sides for i in range(sides))]
        ring1 = [bm.verts.new(base + n * length * (1 - tipf) + (t * math.cos(a + tw) + b * math.sin(a + tw)) * r)
                 for a in (2 * math.pi * i / sides for i in range(sides))]
        apex = bm.verts.new(base + n * length)
        bot = bm.verts.new(base - n * 0.08 * length)
        for i in range(sides):
            j = (i + 1) % sides
            bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i]))
            bm.faces.new((ring1[i], ring1[j], apex))
            bm.faces.new((ring0[j], ring0[i], bot))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return fk.mesh_object(_name("crys"), bm)


def loft(rings, bottom=None, top=None, closed=False, tag="loft"):
    """Bridge equal-length vertex loops into quads.

    Winding: loops run CCW seen from +Z (or, for tubes, CCW around the travel direction) and
    are ordered along the surface so the solid is on the left of travel in the (r, z) half
    plane; faces then point outward. Face order: bottom fan, then band k column i, then top
    fan, so painters can recover (k, i) from poly.index."""
    bm = bmesh.new()
    R = [[bm.verts.new(Vector(p)) for p in ring] for ring in rings]
    n = len(rings[0])
    if bottom is not None:
        c = bm.verts.new(Vector(bottom))
        for i in range(n):
            bm.faces.new((c, R[0][(i + 1) % n], R[0][i]))
    pairs = list(zip(R[:-1], R[1:])) + ([(R[-1], R[0])] if closed else [])
    for A, B in pairs:
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((A[i], A[j], B[j], B[i]))
    if top is not None:
        c = bm.verts.new(Vector(top))
        for i in range(n):
            bm.faces.new((R[-1][i], R[-1][(i + 1) % n], c))
    return fk.mesh_object(_name(tag), bm)


def circle(r, z, n, phase=0.0):
    return [(r * math.cos(phase + 2 * math.pi * i / n), r * math.sin(phase + 2 * math.pi * i / n), z) for i in range(n)]


def lathe(profile, n, phase=0.0, tag="lathe"):
    """profile [(r, z)] traversed with the solid on its left (bottom pole -> out -> up -> in).
    r == 0 at either end closes a pole."""
    pb = profile[0][0] <= 1e-6
    pt = profile[-1][0] <= 1e-6
    body = profile[(1 if pb else 0):(len(profile) - 1 if pt else len(profile))]
    rings = [circle(r, z, n, phase) for r, z in body]
    return loft(rings, bottom=(0, 0, profile[0][1]) if pb else None, top=(0, 0, profile[-1][1]) if pt else None, tag=tag)


def superellipse(a, b, e, n, dense=1440):
    """n points spaced by ARC LENGTH on |x/a|^e + |y/b|^e = 1, CCW from the front middle (0, -b).
    Returns [(point, outward normal)] as 3D Vectors on z=0."""
    pts = []
    for k in range(dense):
        t = -math.pi / 2 + 2 * math.pi * k / dense
        c, s = math.cos(t), math.sin(t)
        pts.append((a * math.copysign(abs(c) ** (2 / e), c), b * math.copysign(abs(s) ** (2 / e), s)))
    L = [0.0]
    for k in range(1, dense + 1):
        p0, p1 = pts[k - 1], pts[k % dense]
        L.append(L[-1] + math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    out, kk = [], 0
    for i in range(n):
        target = L[-1] * i / n
        while L[kk + 1] < target:
            kk += 1
        f = (target - L[kk]) / max(1e-9, L[kk + 1] - L[kk])
        p0, p1 = pts[kk], pts[(kk + 1) % dense]
        out.append((p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f))
    res = []
    for i in range(n):
        pa, pb = out[i - 1], out[(i + 1) % n]
        tx, ty = pb[0] - pa[0], pb[1] - pa[1]
        ln = math.hypot(tx, ty)
        res.append((Vector((out[i][0], out[i][1], 0.0)), Vector((ty / ln, -tx / ln, 0.0))))
    return res


def se_ring(base, z, s=1.0, d=0.0):
    return [T(p * s + nrm * d + Vector((0, 0, z))) for p, nrm in base]


def tube_xz(path, r, sides=6):
    """Tube along a path that lives in the XZ plane (handles). Rings CCW around travel."""
    rings = []
    Y = Vector((0, 1, 0))
    for k, p in enumerate(path):
        a = Vector(path[max(0, k - 1)])
        b = Vector(path[min(len(path) - 1, k + 1)])
        t = (b - a).normalized()
        u = Y
        v = t.cross(u)
        rings.append([T(Vector(p) + (u * math.cos(al) + v * math.sin(al)) * r)
                      for al in (2 * math.pi * i / sides for i in range(sides))])
    return loft(rings, tag="tube")


def orient_faces(obj, ref_fn):
    """Flip faces whose normal points toward ref_fn(face_center) (open sheets have no inside)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    for f in bm.faces:
        c = f.calc_center_median()
        if f.normal.dot(c - Vector(ref_fn(c))) < 0:
            f.normal_flip()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj


# ═══ PIECES → ONE ASSET ══════════════════════════════════════════════════════════

class Piece:
    """color: sRGB tuple, fn(co, n) -> sRGB, or with face="idx" fn(co, n, poly) -> sRGB
    (poly.index follows construction order, so hand-built grids paint crisp per-face patterns
    while co/n still give a smooth per-vertex gradient).

    shape/obj: an SDF or a ready mesh object.  tris: fixed allowance (else share by area).
    post: Matrix applied after meshing.  glow: keep full brightness (little AO, gentle tone).
    flat: faceted shading.  face=True: one colour per face from its centre."""

    def __init__(self, color, shape=None, obj=None, voxel=None, tris=None, weight=1.0, post=None,
                 glow=False, flat=False, face=False, hi=0.2, lo=0.35, lit=True):
        self.color, self.shape, self.obj, self.voxel, self.tris = color, shape, obj, voxel, tris
        self.weight, self.post, self.glow, self.flat, self.face = weight, post, glow, flat, face
        self.hi, self.lo, self.lit = hi, lo, lit


def M(loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    return Matrix.Translation(Vector(loc)) @ Euler([math.radians(a) for a in rot]).to_matrix().to_4x4() \
        @ Matrix.Diagonal(Vector((scale, scale, scale, 1.0)))


def _decimate(o, target):
    for _ in range(8):
        if fk.triangle_count(o) <= target:
            break
        o = fk.decimate_to(o, target)
    return o


def _paint(o, pc, M_inv):
    hi, lo = (pc.hi * 0.5, pc.lo * 0.3) if pc.glow else (pc.hi, pc.lo)

    def shade(c, n):
        return to_lin(tone(c, n, hi, lo) if pc.lit else c)

    layer = fk.ensure_color_layer(o)
    me = o.data
    if pc.face == "idx":
        for poly in me.polygons:
            for li in poly.loop_indices:
                v = me.vertices[me.loops[li].vertex_index]
                co = M_inv @ v.co if M_inv is not None else v.co
                c = shade(pc.color(co, v.normal, poly), v.normal)
                layer.data[li].color = (c[0], c[1], c[2], 1.0)
        return
    fn = pc.color if callable(pc.color) else (lambda co, n, c=pc.color: c)
    if not pc.face:
        fk.paint(o, lambda co, n: shade(fn(M_inv @ co if M_inv is not None else co, n), n))
        return
    for poly in me.polygons:
        ctr = M_inv @ poly.center if M_inv is not None else poly.center
        c = shade(fn(ctr, poly.normal), poly.normal)
        for li in poly.loop_indices:
            layer.data[li].color = (c[0], c[1], c[2], 1.0)


def build(name, pieces, cap, ao=0.5, ao_dist=1.0, floor=True, samples=24):
    target_total = cap - max(20, cap // 40)
    meshed = []  # (obj, piece, voxel)
    for pc in pieces:
        if pc.obj is not None:
            o, vox = pc.obj, None
            if pc.tris is None:
                pc.tris = fk.triangle_count(o)
        else:
            lo, hi = pc.shape[1]
            ext = float(np.max(np.asarray(hi) - np.asarray(lo)))
            vox = pc.voxel or max(0.02, ext / 90.0)
            o = sdf.to_mesh(_name("sdf"), pc.shape, voxel=vox)
        meshed.append((o, pc, vox))

    fixed = sum(min(pc.tris, fk.triangle_count(o)) for o, pc, _ in meshed if pc.tris is not None)
    free = [(i, fk.triangle_count(o) * vox * vox * pc.weight) for i, (o, pc, vox) in enumerate(meshed) if pc.tris is None]
    remaining = max(60, target_total - fixed)
    area = sum(a for _, a in free) or 1.0
    alloc = {i: max(28, remaining * a / area) for i, a in free}

    decimated = []
    for i, (o, pc, vox) in enumerate(meshed):
        target = pc.tris if pc.tris is not None else int(alloc[i])
        raw = fk.triangle_count(o)
        if pc.obj is None:
            o = _decimate(o, max(12, target))
        if os.environ.get("KIT_DEBUG"):
            print(f"   piece {i}: raw {raw} target {target} -> {fk.triangle_count(o)}")
        decimated.append([o, pc])
    # hard budget guard: take any overflow back from the biggest SDF piece
    for _ in range(4):
        total = sum(fk.triangle_count(o) for o, _ in decimated)
        if total <= cap:
            break
        sdf_idx = [j for j in range(len(decimated)) if decimated[j][1].obj is None]
        if not sdf_idx:
            raise SystemExit(f"{name}: hand-built pieces alone are {total} tris > cap {cap}")
        k = max(sdf_idx, key=lambda j: fk.triangle_count(decimated[j][0]))
        o = decimated[k][0]
        decimated[k][0] = _decimate(o, fk.triangle_count(o) - (total - target_total))

    objs, spans = [], []
    for o, pc in decimated:
        M_inv = None
        if pc.post is not None:
            o.data.transform(pc.post)
            M_inv = pc.post.inverted()
        o.data.update()
        _paint(o, pc, M_inv)
        spans.append((len(o.data.polygons), pc))
        objs.append(o)

    obj = fk.join(objs, name)
    xs = [v.co for v in obj.data.vertices]
    lo = Vector((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
    hi = Vector((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
    obj.data.transform(Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))))
    obj.data.update()

    start = 0
    glow_loops, flat_polys = [], []
    for count, pc in spans:
        rng = range(start, start + count)
        if pc.flat:
            flat_polys.extend(rng)
        if pc.glow:
            for pi in rng:
                glow_loops.extend(obj.data.polygons[pi].loop_indices)
        start += count
    for pi in flat_polys:
        obj.data.polygons[pi].use_smooth = False

    layer = fk.ensure_color_layer(obj)
    if ao:
        keep = {li: tuple(layer.data[li].color) for li in glow_loops}
        fk.bake_ao(obj, floor_z=0.0 if floor else None, samples=samples, distance=ao_dist, strength=ao)
        for li, c in keep.items():
            a = layer.data[li].color
            layer.data[li].color = tuple(a[i] * 0.15 + c[i] * 0.85 for i in range(3)) + (1.0,)
    fk.box_uv(obj, 2.0)
    obj.data.materials.clear()
    return obj


# ═══ ASSETS ══════════════════════════════════════════════════════════════════════
# Every function returns build(...). Coordinates are studs, Z up, front faces -Y.

ASSETS = {}
BUDGET = {}


def asset(cap):
    def deco(fn):
        ASSETS[fn.__name__] = fn
        BUDGET[fn.__name__] = cap
        return fn
    return deco


# gingham, shared by the blanket and the basket's cloth
G_RED = H(0xD8343A)
G_PINK = H(0xF19A9C)
G_WHITE = H(0xFFF4E6)


def gingham(ix, iy):
    a, b = ix % 2 == 0, iy % 2 == 0
    return G_RED if (a and b) else G_PINK if (a or b) else G_WHITE


# ── UFO ─────────────────────────────────────────────────────────────────────────

HULL = H(0xA9A2D0)
HULL_HI = H(0xDCD8F0)
BELLY = H(0x7C74AC)
RIM_BAND = H(0x6A55B0)
RING_METAL = H(0x5E5889)
EMIT_EDGE = H(0x9DF58A)
EMIT_HOT = H(0xF1FFE8)
DOME = H(0xBDF5CF)
DOME_DEEP = H(0x5CC898)
LIGHTS = [H(0xB6FF3A), H(0x3AF0FF), H(0xFF5EC8)]
UFO_SEG = 40
N_LIGHTS = 12
LIGHT_R = 13.1
DOME_C, DOME_RX, DOME_RZ = 4.0, 5.6, 3.0


def dome_point(th_deg, ph_deg, lift=0.0):
    th, ph = math.radians(th_deg), math.radians(ph_deg)
    p = Vector((DOME_RX * math.cos(ph) * math.cos(th), DOME_RX * math.cos(ph) * math.sin(th), DOME_C + DOME_RZ * math.sin(ph)))
    n = Vector((math.cos(ph) * math.cos(th) / DOME_RX, math.cos(ph) * math.sin(th) / DOME_RX, math.sin(ph) / DOME_RZ)).normalized()
    return p + n * lift, n


def dome_glint(th0, th1, phi_fn, nu=6, lift=0.035):
    """A curved crescent decal hugging the glass dome."""
    bm = bmesh.new()
    rows = []
    for a in range(nu + 1):
        u = a / nu
        lo, hi = phi_fn(u)
        th = th0 + (th1 - th0) * u
        rows.append([bm.verts.new(dome_point(th, ph, lift)[0]) for ph in (lo, (lo + hi) / 2, hi)])
    for a in range(nu):
        for b in range(2):
            bm.faces.new((rows[a][b], rows[a + 1][b], rows[a + 1][b + 1], rows[a][b + 1]))
    obj = fk.mesh_object(_name("glint"), bm)
    return orient_faces(obj, lambda c: (0, 0, DOME_C))


@asset(2500)
def UFO_Saucer():
    S = UFO_SEG
    emitter = lathe([(0, 0.30), (1.6, 0.38), (2.72, 0.64)], S)
    belly = lathe([(2.66, 0.66), (2.86, 0.2), (3.5, 0.0), (4.14, 0.2), (4.3, 0.64), (5.0, 0.86), (7.2, 1.08),
                   (9.7, 1.45), (11.6, 1.85), (12.45, 2.1)], S)
    rim = lathe([(12.45, 2.1), (12.95, 2.25), (LIGHT_R, 2.5), (LIGHT_R, 3.5), (12.95, 3.75), (12.45, 3.9)], S)
    top = lathe([(12.45, 3.9), (10.8, 4.08), (8.6, 4.22), (6.6, 4.3), (6.0, 4.45), (5.45, 4.56)], S)
    dome = lathe([(DOME_RX * math.cos(math.radians(p)), DOME_C + DOME_RZ * math.sin(math.radians(p)))
                  for p in (-8, 12, 30, 48, 66)] + [(0, DOME_C + DOME_RZ)], S)

    def emitter_col(co, n):
        return mixc(EMIT_HOT, EMIT_EDGE, ss(0.3, 2.6, math.hypot(co.x, co.y)))

    def belly_col(co, n, poly):
        r = math.hypot(co.x, co.y)
        _, i = divmod(poly.index, S)
        if poly.center.to_2d().length < 4.45:
            return mixc(RING_METAL, lighter(RING_METAL, 0.25), ss(0.5, 0.0, co.z))
        c = mixc(HULL, BELLY, ss(12.0, 5.5, r))
        return richer(c, 0.18) if (i // 5) % 2 else c

    def rim_col(co, n):
        return mixc(RIM_BAND, lighter(RIM_BAND, 0.3), ss(2.9, 3.9, co.z))

    def top_col(co, n, poly):
        r = math.hypot(co.x, co.y)
        _, i = divmod(poly.index, S)
        if poly.center.to_2d().length < 6.7:  # collar lip
            return mixc(RIM_BAND, lighter(RIM_BAND, 0.35), ss(4.25, 4.56, co.z))
        c = mixc(HULL, HULL_HI, ss(12.2, 6.6, r) * 0.6)
        return richer(c, 0.22) if (i // 5) % 2 else c

    def dome_col(co, n):
        t = (co.z - DOME_C) / DOME_RZ
        c = mixc(DOME_DEEP, DOME, ss(-0.1, 0.55, t))
        # soft sky reflection band on the back-right, a touch whiter near the top
        c = mixc(c, H(0xE9FFF4), ss(0.55, 1.0, t) * 0.35)
        return mixc(c, H(0xE4FFF1), ss(0.2, 0.9, n.x * 0.6 + n.y * 0.8) * 0.3 * ss(0.0, 0.35, t))

    spots = []
    for m in range(N_LIGHTS):
        a = 2 * math.pi * (m + 0.5) / N_LIGHTS
        nrm = Vector((math.cos(a), math.sin(a), 0))
        spots.append((Vector((LIGHT_R * math.cos(a), LIGHT_R * math.sin(a), 3.0)), nrm, 0.7, 0.44))
    lights = dots_mesh(spots, sides=10, sink=0.45)

    def light_col(co, n):
        a = math.atan2(co.y, co.x) % (2 * math.pi)
        m = int(round(a / (2 * math.pi) * N_LIGHTS - 0.5)) % N_LIGHTS
        c = LIGHTS[m % 3]
        ac = 2 * math.pi * (m + 0.5) / N_LIGHTS
        centre = Vector((LIGHT_R * math.cos(ac), LIGHT_R * math.sin(ac), 3.0))
        q = co - centre
        nn = Vector((math.cos(ac), math.sin(ac), 0))
        radial = (q - nn * q.dot(nn)).length
        return mixc(lighter(c, 0.55), c, ss(0.05, 0.4, radial))

    glint = dome_glint(196, 246, lambda u: (36 + 7 * math.sin(math.pi * u) - (0.6 + 5.5 * math.sin(math.pi * u)),
                                            38 + 7 * math.sin(math.pi * u) + (0.6 + 5.5 * math.sin(math.pi * u))))
    gp, gn = dome_point(256, 20)
    glint_dot = dots_mesh([(gp, gn, 0.4, 0.05)], sides=8, sink=0.0)

    return build("UFO_Saucer", [
        Piece(emitter_col, obj=emitter, glow=True, lit=False),
        Piece(belly_col, obj=belly, face="idx", hi=0.15, lo=0.25),
        Piece(rim_col, obj=rim, hi=0.2, lo=0.3),
        Piece(top_col, obj=top, face="idx", hi=0.25, lo=0.3),
        Piece(dome_col, obj=dome, hi=0.1, lo=0.2),
        Piece(light_col, obj=lights, glow=True, lit=False),
        Piece(H(0xFBFFFD), obj=glint, glow=True, lit=False),
        Piece(H(0xFBFFFD), obj=glint_dot, glow=True, lit=False),
    ], BUDGET["UFO_Saucer"], ao=0.45, ao_dist=1.6, floor=False)


@asset(300)
def UFO_Beam():
    seg, zs, H_ = 18, (0.0, 15.0, 30.0, 45.0, 60.0), 60.0

    def radius(z):
        t = z / H_
        return 2.0 + 7.0 * (0.8 * t + 0.2 * t * t)

    outer = loft([circle(radius(z), z, seg) for z in zs], tag="beam_out")
    inner = loft([circle(radius(z) - 0.08, z, seg) for z in reversed(zs)], tag="beam_in")
    return build("UFO_Beam", [
        Piece(lambda co, n: mixc(H(0xD6FFC8), H(0xA2F096), (co.z / H_) ** 0.8), obj=outer, glow=True, lit=False),
        Piece(lambda co, n: mixc(H(0xBDF7AE), H(0x88E27C), co.z / H_), obj=inner, glow=True, lit=False),
    ], BUDGET["UFO_Beam"], ao=None)


# ── PICNIC ──────────────────────────────────────────────────────────────────────

@asset(2500)
def Picnic_Blanket():
    NX, NY, HX, HY, TH = 26, 18, 12.6, 8.6, 0.3   # wobble + soft hem bring the footprint to 26 x 18

    def lift(x, y):
        d = min(HX - abs(x), HY - abs(y))
        e = ss(2.8, 0.0, d)
        w = 0.5 + 0.5 * (0.6 * math.sin(0.95 * x + 0.4) * math.sin(0.8 * y + 1.1) + 0.4 * math.sin(0.55 * x - 0.7 * y + 2.0))
        z = e ** 1.6 * (0.1 + 0.75 * w)
        z += 0.95 * ss(4.5, 0.0, math.hypot(x - HX, y + HY)) ** 2      # front-right corner flips up
        z += 0.45 * ss(3.5, 0.0, math.hypot(x + HX, y - HY)) ** 2      # a smaller back-left curl
        return z

    def wobble(x, y):
        dx = (0.3 * math.sin(1.15 * y + 0.3) * ss(1.0, 0.0, HX - abs(x))) * (1 if x > 0 else -1)
        dy = (0.3 * math.sin(1.05 * x + 1.7) * ss(1.0, 0.0, HY - abs(y))) * (1 if y > 0 else -1)
        return x + dx, y + dy

    bm = bmesh.new()
    top, bot = {}, {}
    for i in range(NX + 1):
        for j in range(NY + 1):
            x, y = -HX + i * (2 * HX / NX), -HY + j * (2 * HY / NY)
            z = lift(x, y)
            wx, wy = wobble(x, y)
            top[i, j] = bm.verts.new((wx, wy, z + TH))
            bot[i, j] = bm.verts.new((wx, wy, z))
    faces_meta = []  # (ix, iy) gingham cell for every face, in creation order
    for i in range(NX):
        for j in range(NY):
            cell = (i // 2, j // 2)   # 2 grid cells per gingham stripe
            bm.faces.new((top[i, j], top[i + 1, j], top[i + 1, j + 1], top[i, j + 1]))
            faces_meta.append(cell)
            bm.faces.new((bot[i, j], bot[i, j + 1], bot[i + 1, j + 1], bot[i + 1, j]))
            faces_meta.append(cell)
    loop = [(i, 0) for i in range(NX)] + [(NX, j) for j in range(NY)] + \
           [(i, NY) for i in range(NX, 0, -1)] + [(0, j) for j in range(NY, 0, -1)]
    mid = []
    for (i, j) in loop:
        t, b = top[i, j].co, bot[i, j].co
        out = Vector((t.x, t.y, 0)).normalized()
        if i in (0, NX) and 0 < j < NY:
            out = Vector((1 if i else -1, 0, 0))
        elif j in (0, NY) and 0 < i < NX:
            out = Vector((0, 1 if j else -1, 0))
        mid.append(bm.verts.new((t + b) * 0.5 + out * 0.1))
    n = len(loop)
    for k in range(n):
        a, b2 = loop[k], loop[(k + 1) % n]
        cx, cy = min(a[0], b2[0], NX - 1), min(a[1], b2[1], NY - 1)   # the grid cell this edge borders
        cell = (cx // 2, cy // 2)
        bm.faces.new((bot[a], bot[b2], mid[(k + 1) % n], mid[k]))
        faces_meta.append(cell)
        bm.faces.new((mid[k], mid[(k + 1) % n], top[b2], top[a]))
        faces_meta.append(cell)
    obj = fk.mesh_object(_name("blanket"), bm)

    def col(co, n, poly):
        ix, iy = faces_meta[poly.index]
        return gingham(ix, iy)

    return build("Picnic_Blanket", [Piece(col, obj=obj, face="idx", hi=0.1, lo=0.3)],
                 BUDGET["Picnic_Blanket"], ao=0.45, ao_dist=1.2, samples=20)


WICKER = H(0xDFA95E)
WICKER_DK = H(0xC48B47)
WICKER_BASE = H(0x8A5A2C)
RIM_A = H(0x94602E)
RIM_B = H(0xB47A3E)
HANDLE_A = H(0x7C4C23)
HANDLE_B = H(0xA86F39)


@asset(1500)
def Picnic_Basket():
    COLS = 24
    A, B, E = 1.45, 1.08, 3.0
    base = superellipse(A, B, E, COLS)

    # body: rounded foot, gentle taper, rows line up with the weave
    rows = [(0.0, 0.84, 0.0), (0.06, 0.92, 0.0), (0.18, 0.96, 0.0)]
    rows += [(0.18 + 1.72 * k / 9, 0.96 + 0.04 * k / 9 + 0.035 * math.sin(math.pi * k / 9), 0.012 * (1 if k % 2 else -1) if k < 9 else 0.0) for k in range(1, 10)]
    body = loft([se_ring(base, z, s, d) for z, s, d in rows], bottom=(0, 0, 0))

    def body_col(co, n, poly):
        if poly.index < COLS:
            return WICKER_BASE
        k, i = divmod(poly.index - COLS, COLS)
        if k < 2:
            return WICKER_BASE
        return WICKER if (i // 1 + k) % 2 else WICKER_DK

    # rolled rim
    RZ, RD, RR = 1.92, 0.05, 0.13
    rim_rings = [se_ring(base, RZ + RR * math.sin(al), 1.0, RD + RR * math.cos(al))
                 for al in (math.radians(-90 + 60 * q) for q in range(6))]
    rim = loft(rim_rings, closed=True)

    def rim_col(co, n, poly):
        k, i = divmod(poly.index, COLS)
        return RIM_A if (i + k) % 2 else RIM_B

    # lid, tilted up at the front so the cloth can peek out
    lid_rows = [(2.0, 1.0, 0.10), (2.1, 1.0, 0.13), (2.2, 1.0, 0.12), (2.3, 1.0, 0.04), (2.37, 0.8, 0.0), (2.42, 0.45, 0.0)]
    lid = loft([se_ring(base, z, s, d) for z, s, d in lid_rows], top=(0, 0, 2.45))
    lid.data.transform(Matrix.Translation(Vector((0, 1.2, 2.0))) @ Matrix.Rotation(math.radians(-3.0), 4, "X")
                       @ Matrix.Translation(Vector((0, -1.2, -2.0))))

    def lid_col(co, n, poly):
        k, i = divmod(poly.index, COLS)
        if k >= 5:
            return RIM_A
        if k < 3:
            return RIM_B if (i + k) % 2 else RIM_A
        return WICKER if (i + k) % 2 else WICKER_DK

    # handle: legs on the short ends, arching over the lid
    HX_, Z0, ZT = 1.66, 1.3, 2.87
    path = [(-HX_, 0, Z0), (-HX_, 0, 1.75), (-HX_, 0, 2.15)]
    for q in range(1, 10):
        t = math.pi - math.pi * q / 10
        path.append((HX_ * math.cos(t), 0, 2.15 + (ZT - 2.15) * math.sin(t)))
    path += [(HX_, 0, 2.15), (HX_, 0, 1.75), (HX_, 0, Z0)]
    handle = tube_xz(path, 0.12, sides=6)

    def handle_col(co, n, poly):
        k, s_ = divmod(poly.index, 6)
        return HANDLE_B if (k + s_) % 3 == 0 else HANDLE_A

    bosses = dots_mesh([((sx * 1.44, 0, Z0 + 0.02), (sx, 0, 0), 0.19, 0.3) for sx in (-1, 1)], sides=8, sink=0.3)

    # checked napkin corner poking out under the lid, draped over the front
    x0, NU = 0.42, 5
    drape = [(-0.9, 2.08), (-1.18, 2.1), (-1.36, 1.98), (-1.32, 1.76), (-1.2, 1.5), (-1.11, 1.22), (-1.09, 0.98)]
    bm = bmesh.new()
    grid = []
    for v, (y, z) in enumerate(drape):
        f = v / (len(drape) - 1)
        hw = 0.56 * (1 - f) ** 0.85 + 0.03
        grid.append([bm.verts.new((x0 - hw + 2 * hw * u / NU + 0.05 * math.sin(v * 1.3), y, z)) for u in range(NU + 1)])
    for v in range(len(drape) - 1):
        for u in range(NU):
            bm.faces.new((grid[v][u], grid[v][u + 1], grid[v + 1][u + 1], grid[v + 1][u]))
    cloth = orient_faces(fk.mesh_object(_name("cloth"), bm), lambda c: (c.x, 0.0, 1.2))

    def cloth_col(co, n, poly):
        v, u = divmod(poly.index, NU)
        return gingham(u, v)

    return build("Picnic_Basket", [
        Piece(body_col, obj=body, face="idx", hi=0.2, lo=0.3),
        Piece(rim_col, obj=rim, face="idx", hi=0.25, lo=0.3),
        Piece(lid_col, obj=lid, face="idx", hi=0.25, lo=0.3),
        Piece(handle_col, obj=handle, face="idx", hi=0.25, lo=0.3),
        Piece(H(0x5E3A1C), obj=bosses, hi=0.2),
        Piece(cloth_col, obj=cloth, face="idx", hi=0.1, lo=0.2),
    ], BUDGET["Picnic_Basket"], ao=0.5, ao_dist=0.45)


# ── METEOR ──────────────────────────────────────────────────────────────────────

BASALT = H(0x3A3642)
BASALT_HI = H(0x676178)
BASALT_DK = H(0x221F29)
VEIN_BLEED = H(0x8A3AD6)


def chain(points, radii, k=0.05):
    if isinstance(radii, (int, float)):
        radii = [radii] * len(points)
    parts = [sdf.round_cone(T(points[i]), T(points[i + 1]), radii[i], radii[i + 1]) for i in range(len(points) - 1)]
    return sdf.smooth_union(*parts, k=k) if len(parts) > 1 else parts[0]


def polyline_t(points, co):
    """(distance, arc-length parameter 0..1) of the closest point on a polyline."""
    best, bt, acc = 1e9, 0.0, 0.0
    lens = [(points[i + 1] - points[i]).length for i in range(len(points) - 1)]
    total = sum(lens) or 1.0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        ab = b - a
        t = 0.0 if ab.length_squared == 0 else max(0.0, min(1.0, (co - a).dot(ab) / ab.length_squared))
        d = (co - (a + ab * t)).length
        if d < best:
            best, bt = d, (acc + t * lens[i]) / total
        acc += lens[i]
    return best, bt


def crack_path(shape, c, d, heading, n=7, step=1.15, jitter=0.55, seed=0):
    """A jagged crack walked across the SDF surface. Returns [(point, normal)]."""
    rng = random.Random(seed)
    dv = Vector(d).normalized()
    p, nrm = surface(shape, c + dv * ray_extent(shape, c, dv))
    h = Vector(heading)
    out = [(p, nrm)]
    for _ in range(n - 1):
        h = (h - nrm * h.dot(nrm)).normalized()
        side = nrm.cross(h)
        q = p + h * step + side * rng.uniform(-jitter, jitter)
        p, nrm = surface(shape, q)
        out.append((p, nrm))
    return out


@asset(3000)
def Meteor_Big():
    c = Vector((0.0, 0.0, 3.3))
    blob = U(sdf.ellipsoid(T(c), (5.2, 4.4, 3.7)),
             sdf.ellipsoid((1.8, -0.7, 4.4), (3.0, 2.7, 2.5)),
             sdf.ellipsoid((-2.6, 1.0, 2.5), (2.8, 2.6, 2.3)), k=1.2)
    rock = blob
    for d, keep in (((0.6, -0.5, 0.65), 0.85), ((-0.65, -0.5, 0.55), 0.86), ((0.1, 0.6, 0.8), 0.87), ((0.95, 0.3, 0.15), 0.87),
                    ((-0.9, 0.35, -0.05), 0.88), ((-0.1, -1.0, 0.1), 0.88), ((0.2, 0.1, 1.0), 0.88), ((0.5, 0.8, 0.1), 0.88),
                    ((-0.5, 0.85, 0.2), 0.88), ((0.8, -0.6, -0.1), 0.88), ((-0.35, -0.2, 1.0), 0.9), ((-0.2, -0.75, 0.6), 0.9)):
        dv = Vector(d).normalized()
        ext = ray_extent(blob, c, dv)
        rock = sdf.smooth_intersect(rock, half_space(T(c + dv * ext * keep), T(-dv)), k=0.3)
    rock = sdf.noise_bumps(rock, amplitude=0.16, frequency=0.9, seed=4)
    rock = sdf.noise_bumps(rock, amplitude=0.06, frequency=2.4, seed=5)
    rock = sdf.smooth_subtract(rock, half_space((0, 0, 0.5), (0, 0, -1)), k=0.3)

    paths = [
        crack_path(rock, c, (-0.2, -1.0, 0.2), (1.0, 0.0, 0.35), n=8, seed=1),
        crack_path(rock, c, (0.3, -0.7, 0.8), (-0.6, 0.2, 0.2), n=7, seed=2),
        crack_path(rock, c, (-0.9, -0.3, 0.3), (0.1, 0.3, 1.0), n=7, seed=3),
        crack_path(rock, c, (0.9, -0.2, 0.2), (0.0, 1.0, 0.3), n=7, seed=4),
        crack_path(rock, c, (-0.3, 0.9, 0.3), (-0.7, 0.0, -0.3), n=6, seed=5),
        crack_path(rock, c, (0.2, 0.5, 0.9), (1.0, 0.4, -0.2), n=6, seed=6),
        crack_path(rock, c, (-0.6, -0.8, -0.1), (-0.3, 0.2, -1.0), n=4, step=0.9, seed=7),
    ]
    taper = lambda n: [0.12 + 0.17 * math.sin(math.pi * (i + 0.5) / n) for i in range(n)]
    grooves, glows, polys = [], [], []
    for pth in paths:
        rr = taper(len(pth))
        grooves.append(chain([p for p, _ in pth], [r + 0.2 for r in rr], k=0.1))
        glows.append(chain([p - nr * 0.34 for p, nr in pth], rr, k=0.1))
        polys.append([p for p, _ in pth])
    rock = sdf.smooth_subtract(rock, sdf.union(*grooves), k=0.1)
    veins = sdf.union(*glows)

    def nearest_vein(co):
        best = (1e9, 0.0)
        for pl in polys:
            d, t = polyline_t(pl, co)
            if d < best[0]:
                best = (d, t)
        return best

    def rock_col(co, n):
        cc = mixc(BASALT, BASALT_DK, 0.5 + 0.5 * wave(co, 0.55, 3))
        cc = mixc(cc, BASALT_HI, ss(0.3, 0.95, n.z) * 0.7)
        d, _ = nearest_vein(co)
        return mixc(cc, VEIN_BLEED, ss(1.0, 0.35, d) * 0.7)

    def vein_col(co, n):
        _, t = nearest_vein(co)
        hot = math.sin(math.pi * t)
        cc = mixc(H(0xA646FF), H(0xFF45CF), ss(0.1, 0.6, hot))
        return mixc(cc, H(0xFFC6F2), ss(0.65, 1.0, hot) * 0.7)

    shard_dirs = (((0.42, -0.3, 0.86), 0.95, 2.9, 0, 0), ((0.8, 0.05, 0.6), 0.6, 1.9, 1, 25), ((0.1, -0.62, 0.78), 0.45, 1.3, 2, 10),
                  ((-0.6, 0.35, 0.72), 0.72, 2.2, 1, 5), ((-0.9, -0.4, 0.2), 0.5, 1.4, 0, 30))
    specs, owner = [], []
    for d, r, out, kind, tw in shard_dirs:
        dv = Vector(d).normalized()
        base = c + dv * 2.0
        specs.append((base, dv, r, ray_extent(rock, base, dv) + out, 6, 0.32, tw))
        owner.append(kind)
    shards = crystal_mesh(specs)
    SHARD = [(H(0x8A3CF0), H(0xE7B4FF)), (H(0xD2309C), H(0xFFB0E6)), (H(0x6848E6), H(0xC8B8FF))]

    def shard_col(co, n):
        best, kind, tt = 1e9, 0, 0.0
        for (base, dv, r, L, *_), kd in zip(specs, owner):
            q = co - base
            t = max(0.0, min(L, q.dot(dv)))
            dd = (q - dv * t).length
            if dd < best:
                best, kind, tt = dd, kd, t / L
        lo_, hi_ = SHARD[kind]
        cc = mixc(lo_, hi_, ss(0.45, 1.0, tt))
        return mixc(cc, H(0xFFF2FF), ss(0.3, 0.9, n.z * 0.6 - n.x * 0.4) * 0.4)

    return build("Meteor_Big", [
        Piece(rock_col, rock, voxel=0.1, tris=2200, hi=0.22, lo=0.3),
        Piece(vein_col, veins, voxel=0.06, tris=640, glow=True, lit=False),
        Piece(shard_col, obj=shards, flat=True, face=True, glow=True, lit=False),
    ], BUDGET["Meteor_Big"], ao=0.5, ao_dist=1.6)


# ── EARTHQUAKE ROCK SEAL ────────────────────────────────────────────────────────

SLATE = H(0x5C6883)
SLATE_HI = H(0x8B99B5)
SLATE_DK = H(0x363D50)
MOSS = H(0x2E9A86)
MOSS_HI = H(0x7ADDC0)
CYAN = (H(0x137FA6), H(0x2CC6E0), H(0xD2FBFF))


def stone(c, half, rot, rounding):
    """A chunky river-stone: rounded box softened by an ellipsoid (flat-ish faces, no cube corners)."""
    return sdf.smooth_intersect(sdf.round_box(c, half, rounding, rot=rot),
                                sdf.ellipsoid(c, tuple(h * 1.3 for h in half), rot=rot), k=0.25)


@asset(2500)
def Rock_Seal():
    S = [  # centre, half extents, rot (x, y, z deg), rounding, tint
        ((-6.9, 0.1, 2.7), (3.3, 1.8, 2.8), (0, 12, 4), 1.3, 1.0),
        ((-1.3, -0.3, 2.3), (2.6, 1.85, 2.4), (0, -18, -5), 1.2, 0.92),
        ((3.3, 0.15, 3.0), (2.4, 1.75, 3.1), (0, 8, 6), 1.1, 1.07),
        ((7.7, -0.1, 2.25), (2.4, 1.75, 2.35), (0, -20, -4), 1.1, 0.96),
        ((-8.1, 0.2, 7.6), (2.1, 1.65, 2.3), (0, 25, 3), 1.0, 1.05),
        ((-4.1, -0.4, 7.1), (2.3, 1.85, 2.5), (0, -8, -6), 1.1, 0.9),
        ((0.6, 0.1, 6.9), (2.7, 1.75, 2.2), (0, 15, 5), 1.1, 1.03),
        ((5.6, -0.25, 7.5), (3.0, 1.8, 2.4), (0, -6, -3), 1.2, 0.95),
        ((8.9, 0.2, 6.2), (1.3, 1.5, 1.8), (0, 30, 8), 0.8, 1.08),
        ((-6.0, 0.1, 11.6), (2.4, 1.7, 2.2), (0, -15, 5), 1.1, 0.97),
        ((-1.8, -0.3, 11.7), (2.3, 1.75, 2.5), (0, 20, -4), 1.1, 1.06),
        ((2.8, 0.2, 11.2), (2.7, 1.75, 2.1), (0, -10, 3), 1.1, 0.92),
        ((7.0, 0.0, 10.7), (1.7, 1.55, 1.9), (0, 18, -6), 0.9, 1.02),
        ((-3.6, 0.0, 14.6), (1.8, 1.55, 1.4), (0, -12, 4), 0.9, 1.04),
        ((0.9, -0.2, 14.8), (2.2, 1.65, 1.3), (0, 8, -3), 0.9, 0.96),
        ((4.6, 0.1, 13.8), (1.5, 1.45, 1.3), (0, -25, 5), 0.8, 1.08),
    ]
    W = [  # small wedge stones jammed into crevices (front and back)
        ((-3.9, -1.4, 4.9), (0.9, 0.8, 0.85)), ((1.2, -1.35, 4.8), (0.85, 0.8, 0.8)), ((5.6, -1.3, 4.6), (0.8, 0.75, 0.7)),
        ((-6.4, -1.2, 9.6), (0.8, 0.7, 0.7)), ((0.6, -1.3, 9.2), (0.9, 0.8, 0.75)), ((-1.5, -1.2, 13.4), (0.7, 0.65, 0.6)),
        ((2.3, 1.3, 9.0), (0.9, 0.8, 0.8)), ((-3.0, 1.3, 5.0), (0.9, 0.8, 0.9)),
    ]
    S = [((c[0] * 0.95, c[1], c[2]), h, rot, r * 0.75, 1.0 + (t - 1.0) * 1.6) for c, h, rot, r, t in S]
    W = [((c[0] * 0.95, c[1], c[2]), r) for c, r in W]
    S = [(c, (h[0], h[1] * 0.85, h[2]), rot, r, t) for c, h, rot, r, t in S]
    W = [((c[0], c[1] * 0.85, c[2]), (r[0], r[1] * 0.85, r[2])) for c, r in W]
    stones = [stone(c, h, rot, r) for c, h, rot, r, _ in S]
    wedges = [sdf.ellipsoid(c, r, rot=(15 * i, 40 * i, 20 * i)) for i, (c, r) in enumerate(W)]
    plug = sdf.ellipsoid((0, 0, 6.8), (8.6, 0.8, 7.6))
    wall = sdf.smooth_union(*stones, *wedges, plug, k=0.28)
    wall = sdf.noise_bumps(wall, amplitude=0.12, frequency=0.8, seed=21)
    wall = sdf.noise_bumps(wall, amplitude=0.05, frequency=2.0, seed=22)
    wall = sdf.smooth_subtract(wall, half_space((0, 0, 0.25), (0, 0, -1)), k=0.2)

    parts = stones + wedges
    tints = [s[4] for s in S] + [0.84] * len(W)

    def col(co, n):
        P = np.array([[co.x, co.y, co.z]], dtype=F32)
        i = int(np.argmin([p[0](P)[0] for p in parts]))
        base = tuple(min(1.0, x * tints[i]) for x in SLATE)
        cc = mixc(base, SLATE_DK, (0.5 + 0.5 * wave(co, 0.6, i)) * 0.3)
        cc = mixc(cc, SLATE_HI, ss(0.2, 0.9, n.z) * 0.55)
        clump = wave(co, 0.38, 7) + 0.35 * wave(co, 1.1, 9) + 0.25
        moss = ss(0.3, 0.62, n.z) * ss(0.0, 0.22, clump)
        cc = mixc(cc, mixc(MOSS, MOSS_HI, ss(0.55, 1.0, n.z) * ss(0.2, 0.6, clump)), moss)
        return cc

    rock_only = sdf.smooth_union(*stones, *wedges, plug, k=0.28)
    specs = []
    for x, z, d, r, L, tw in ((-2.5, 4.6, (-0.3, -1.0, 0.45), 0.42, 1.7, 0), (-2.1, 4.9, (0.4, -1.0, 0.2), 0.3, 1.2, 20),
                              (3.2, 9.3, (0.35, -1.0, 0.5), 0.38, 1.5, 10), (-4.6, 10.0, (-0.4, -1.0, 0.3), 0.3, 1.1, 30)):
        hit = Vector((x, -4.0, z))
        while sdf_at(rock_only, hit) > 0 and hit.y < 3:
            hit.y += 0.05
        dv = Vector(d).normalized()
        specs.append((hit - dv * 0.5, dv, r, L + 0.5, 5, 0.35, tw))
    glints = crystal_mesh(specs)

    def glint_col(co, n):
        return mixc(CYAN[1], CYAN[2], ss(0.2, 0.9, -n.y * 0.6 + n.z * 0.4))

    return build("Rock_Seal", [
        Piece(col, wall, voxel=0.14, tris=2380, hi=0.25, lo=0.35),
        Piece(glint_col, obj=glints, flat=True, face=True, glow=True, lit=False),
    ], BUDGET["Rock_Seal"], ao=0.6, ao_dist=2.2)


# ═══ ORDER (these ARE the FBX object names) ═══════════════════════════════════════

ORDER = ["UFO_Saucer", "UFO_Beam", "Picnic_Blanket", "Picnic_Basket", "Meteor_Big", "Rock_Seal"]


# ═══ PREVIEW ═══════════════════════════════════════════════════════════════════

COMPOSE = r'''
import json, sys
from PIL import Image, ImageDraw, ImageFont
spec = json.load(open(sys.argv[1]))
tile, cols = spec["tile"], spec["cols"]
rows = (len(spec["tiles"]) + cols - 1) // cols
W = tile * cols
strip = Image.open(spec["strip"]).convert("RGB") if spec.get("strip") else None
sh = strip.height * W // strip.width if strip else 0
sheet = Image.new("RGB", (W, tile * rows + sh), (40, 44, 52))
def font(sz):
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(f, sz)
        except Exception:
            pass
    return ImageFont.load_default()
F = font(max(12, tile // 26))
d = ImageDraw.Draw(sheet, "RGBA")
for i, (path, label) in enumerate(spec["tiles"]):
    im = Image.open(path).convert("RGB").resize((tile, tile))
    x, y = (i % cols) * tile, (i // cols) * tile
    sheet.paste(im, (x, y))
    h = max(18, tile // 17)
    d.rectangle([x, y, x + tile - 1, y + h], fill=(20, 22, 28, 175))
    d.text((x + 6, y + 2), label, fill=(255, 255, 255, 255), font=F)
    d.rectangle([x, y, x + tile - 1, y + tile - 1], outline=(20, 22, 28, 255))
if strip:
    y = tile * rows
    sheet.paste(strip.resize((W, sh)), (0, y))
    h = max(18, tile // 17)
    d.rectangle([0, y, W - 1, y + h], fill=(20, 22, 28, 175))
    d.text((6, y + 2), spec.get("strip_label", ""), fill=(255, 255, 255, 255), font=F)
sheet.save(spec["out"], quality=88, optimize=True)
'''

# yaw, pitch, preview-only lift (the saucer hovers)
VIEW = {
    "UFO_Saucer": (-30, 16, 4.0),
    "UFO_Beam": (-30, 8, 0.0),
    "Picnic_Blanket": (-26, 36, 0.0),
    "Picnic_Basket": (-34, 22, 0.0),
    "Meteor_Big": (-30, 18, 0.0),
    "Rock_Seal": (-24, 12, 0.0),
}


def setup_preview():
    fk.preview_studio(floor_color=(0.55, 0.62, 0.5))
    sc = bpy.context.scene
    try:
        sc.eevee.taa_render_samples = 24
    except Exception:
        pass
    sc.view_settings.exposure = -0.35
    floor = bpy.data.objects.get("PreviewFloor")
    if floor:
        floor.scale = (8, 8, 1)
    mat = bpy.data.materials.get("PreviewFloorMat")
    if mat:
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (0.2, 0.26, 0.17, 1)
    return fk.vcol_material()


def bounds(obj):
    xs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = Vector((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
    hi = Vector((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
    return lo, hi


def ref_capsule():
    o = sdf.to_mesh("_RefCapsule", sdf.capsule((0, 0, 0.75), (0, 0, 4.25), 0.75), voxel=0.08)
    o = fk.decimate_to(o, 500)
    fk.solid_color(o, to_lin(H(0xE58FB5)))
    fk.preview_tint(o, (1, 1, 1))
    return o


def render_sheet(objs, out, cols=3, tile=440, strip=True):
    setup_preview()
    scene = bpy.context.scene
    tmp = tempfile.mkdtemp(prefix="kit_events_tiles_")
    for o in objs:
        fk.preview_tint(o, (1, 1, 1))
    cap = ref_capsule()
    fk.look_setup(target=(0, 0, 1), distance=10)
    scene.camera.data.clip_end = 2000
    half_fov = math.atan(18.0 / 50.0)
    tiles = []
    for o in objs:
        for p in objs:
            p.hide_render = p is not o
        yaw, pitch, lift = VIEW.get(o.name, (-30, 20, 0.0))
        floor = bpy.data.objects.get("PreviewFloor")
        if floor:
            floor.hide_render = pitch < 0  # looking up at the underside
        o.location = (0, 0, lift)
        bpy.context.view_layer.update()
        lo0, hi0 = bounds(o)
        dims = hi0 - lo0
        # capsule stands just in front of the right half of the asset's footprint (low verts only)
        low = [o.matrix_world @ v.co for v in o.data.vertices]
        low = [c for c in low if c.z < min(hi0.z, lo0.z + 4.0)] or low
        fx0, fx1 = min(c.x for c in low), max(c.x for c in low)
        fy0 = min(c.y for c in low)
        cap.location = ((fx0 + fx1) / 2 + max(1.6, (fx1 - fx0) * 0.3), fy0 - 1.6, 0)
        cl = cap.location
        lo2 = Vector((min(lo0.x, cl.x - 0.8), min(lo0.y, cl.y - 0.8), 0.0))
        hi2 = Vector((max(hi0.x, cl.x + 0.8), max(hi0.y, cl.y + 0.8), max(hi0.z, 5.0)))
        centre = (lo2 + hi2) / 2
        radius = (hi2 - lo2).length / 2
        dist = radius / math.sin(half_fov) * 0.9
        fk.look_setup(target=T(centre), distance=dist, yaw=yaw, pitch=pitch, lens=50)
        path = os.path.join(tmp, f"{len(tiles):02d}_{o.name}.png")
        fk.render_png(path, res=(tile, tile))
        o.location = (0, 0, 0)
        tiles.append((path, f"{len(tiles) + 1}. {o.name}   {fk.triangle_count(o)} tris   "
                            f"{dims.x:.1f} x {dims.y:.1f} x {dims.z:.1f}"))
    for p in objs:
        p.hide_render = False
    strip_path = None
    if strip:
        strip_path = os.path.join(tmp, "strip.png")
        render_lineup(objs, cap, strip_path, width=cols * tile)
    spec = os.path.join(tmp, "spec.json")
    json.dump({"tile": tile, "cols": cols, "tiles": tiles, "out": out, "strip": strip_path,
               "strip_label": "real scale from ~150 studs: rock seal, meteor, capsule, picnic, saucer hovering (beam is 60 tall, tile 2)"},
              open(spec, "w"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    script = os.path.join(tmp, "compose.py")
    open(script, "w").write(COMPOSE)
    py = shutil.which("python3") or "/usr/bin/python3"
    r = subprocess.run([py, script, spec], capture_output=True, text=True)
    if r.returncode != 0:
        print("[kit_events] PIL compose failed:", r.stderr[-600:])
    shutil.rmtree(tmp, ignore_errors=True)
    bpy.data.objects.remove(cap, do_unlink=True)
    return out


def render_lineup(objs, cap, path, width=1320):
    by = {o.name: o for o in objs}
    place = {"Rock_Seal": (-48, 0, 0), "Meteor_Big": (-29, 0, 0), "Picnic_Blanket": (0, 0, 0),
             "Picnic_Basket": (-5, -2.5, 0.3), "UFO_Saucer": (31, 0, 9.0)}
    for o in objs:
        o.hide_render = o.name not in place
        if o.name in place:
            o.location = place[o.name]
    cap.location = (-19, -1, 0)
    cap2 = cap.copy()
    cap2.data = cap.data
    fk.link(cap2)
    cap2.location = (31, -1, 0)
    fk.look_setup(target=(-7.5, 0, 6.0), distance=150, yaw=-10, pitch=12, lens=50)
    fk.render_png(path, res=(width, int(width / 3.2)))
    for o in objs:
        o.location = (0, 0, 0)
        o.hide_render = False
    bpy.data.objects.remove(cap2, do_unlink=True)


# ═══ VERIFY (re-import the FBX) ══════════════════════════════════════════════════

def verify():
    path = os.path.join(fk.BUILD, FBX_NAME)
    fk.reset_scene()
    bpy.ops.import_scene.fbx(filepath=path)
    ok = True
    names = sorted(o.name for o in bpy.data.objects)
    print(f"[verify] {path}")
    print(f"[verify] objects: {names}")
    extra = [n for n in names if n not in ORDER]
    if extra:
        ok = False
        print(f"[verify] UNEXPECTED objects {extra}")
    for n in ORDER:
        o = bpy.data.objects.get(n)
        if o is None or o.type != "MESH":
            ok = False
            print(f"[verify] MISSING {n}")
            continue
        me = o.data
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        lo, hi = bounds(o)
        dims = hi - lo
        cols = [a.name for a in me.color_attributes]
        mats = len(me.materials)
        xform = (tuple(round(x, 4) for x in o.location), tuple(round(math.degrees(x), 2) for x in o.rotation_euler),
                 tuple(round(x, 4) for x in o.scale))
        problems = []
        if tris > BUDGET[n]:
            problems.append(f"tris {tris} > {BUDGET[n]}")
        if abs(lo.z) > 1e-3:
            problems.append(f"base z {lo.z:.4f}")
        if abs(lo.x + hi.x) > 1e-2 or abs(lo.y + hi.y) > 1e-2:
            problems.append(f"not centred ({(lo.x + hi.x) / 2:.3f}, {(lo.y + hi.y) / 2:.3f})")
        if not cols:
            problems.append("no vertex colours")
        if mats:
            problems.append(f"{mats} materials")
        sample = ""
        if cols:
            attr = me.color_attributes[cols[0]]
            srgb = [tuple(attr.data[i].color_srgb[:3]) for i in range(len(attr.data))]
            lum = sorted(sum(c) / 3 for c in srgb)
            sample = f"sRGB lum min {lum[0]:.2f} med {lum[len(lum) // 2]:.2f} max {lum[-1]:.2f}"
            if n == "UFO_Beam":
                # the narrow-end ring is painted exactly #D6FFC8 with no AO: the round trip must keep it
                wm = o.matrix_world
                zs = [(wm @ me.vertices[me.loops[li].vertex_index].co).z for li in range(len(me.loops))] \
                    if attr.domain == "CORNER" else [(wm @ v.co).z for v in me.vertices]
                idx = [i for i, z in enumerate(zs) if z < 0.01]
                got = tuple(round(x * 255) for x in srgb[idx[0]])
                sample += f"  narrow-end colour {'#%02X%02X%02X' % got} (painted #D6FFC8)"
                if max(abs(a - b) for a, b in zip(got, (0xD6, 0xFF, 0xC8))) > 2:
                    problems.append("beam colour drifted")
        ok = ok and not problems
        print(f"[verify] {n:15s} {tris:5d}/{BUDGET[n]:<5d} tris  {dims.x:6.2f} x {dims.y:6.2f} x {dims.z:6.2f}  "
              f"min z {lo.z:+.4f}  colours {cols} ({me.color_attributes[cols[0]].domain if cols else '-'})  "
              f"xform {xform}  {sample}  {'OK' if not problems else 'PROBLEM: ' + '; '.join(problems)}")
    print(f"[verify] {'ALL OK' if ok else 'FAILED'}")
    return ok


# ═══ MAIN ═══════════════════════════════════════════════════════════════════════

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"only": None, "sheet": None, "tile": "440", "cols": "3", "view": None}
    flags = set()
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in opts and i + 1 < len(argv):
            opts[k] = argv[i + 1]
            i += 2
        else:
            flags.add(k)
            i += 1
    if "verify" in flags:
        if not verify():
            raise SystemExit(1)
        return
    if opts["view"]:  # --view UFO_Saucer=-30,-25,8;Rock_Seal=160,15,0   (preview camera overrides)
        for item in opts["view"].split(";"):
            k, v = item.split("=")
            VIEW[k] = tuple(float(x) for x in v.split(","))
    names = opts["only"].split(",") if opts["only"] else ORDER
    missing = [n for n in names if n not in ASSETS]
    if missing:
        raise SystemExit(f"unknown assets: {missing}")
    t0 = time.time()
    objs = []
    for n in names:
        t = time.time()
        o = ASSETS[n]()
        tris = fk.triangle_count(o)
        lo, hi = bounds(o)
        dims = hi - lo
        flag = "" if tris <= BUDGET[n] and o.name == n and abs(lo.z) < 1e-4 else "  <-- PROBLEM"
        print(f"[{KIT}] {n:15s} {tris:5d}/{BUDGET[n]:<5d} tris  size {dims.x:6.2f} x {dims.y:6.2f} x {dims.z:6.2f}  "
              f"({time.time() - t:.1f}s){flag}", flush=True)
        objs.append(o)
    print(f"[{KIT}] built {len(objs)} assets in {time.time() - t0:.0f}s")

    if not opts["only"]:
        for o in objs:
            assert o.data.materials is not None and len(o.data.materials) == 0
            assert tuple(o.location) == (0, 0, 0) and tuple(o.rotation_euler) == (0, 0, 0) and tuple(o.scale) == (1, 1, 1)
        path = fk.export_fbx(objs, FBX_NAME)
        print(f"[{KIT}] exported {path}")
    out = opts["sheet"] or (PREVIEW if not opts["only"] else None)
    if out:
        render_sheet(objs, out, cols=int(opts["cols"]), tile=int(opts["tile"]), strip="nostrip" not in flags)
        print(f"[{KIT}] sheet {out}")


main()
