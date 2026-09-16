"""kit_props — every ingredient pickup + the hatching eggs (docs/ART_KIT_SPEC.md).

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/kit_props.py
      -> art/build/kit_props.fbx     one mesh per ingredient id, base at z=0, vertex colours
      -> art/previews/kit_props.png  labelled contact sheet in list order

Iterate on a few items without exporting:
    ... -P tools/blender/kit_props.py -- --only Apple,Gear --sheet /path/sheet.png [--cols 5 --tile 280]
    ... -- --scale /path/lineup.png      (every item in a row next to a 5-stud avatar capsule)

How an item is made: a list of Pieces. Each piece is an SDF (soft sculpted, like the
creatures) or a tiny hand-built mesh (dots, crystal facets), meshed separately so colour
edges stay crisp, decimated to a share of the 900-triangle budget by surface area,
painted (base -> lighter top -> richer underside, colours given in sRGB), joined, snapped
to base z=0 / centred XY, then AO is baked against the floor. Glowing pieces skip the AO.
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
FBX_NAME = "kit_props.fbx"
PREVIEW = os.path.join(ROOT, "art", "previews", "kit_props.png")
TRI_CAP = 900
TRI_TARGET = 870


# ═══ COLOUR ═══════════════════════════════════════════════════════════════════

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


# ═══ SDF EXTRAS (kept here: sdf.py is shared and frozen) ═════════════════════════

F32 = np.float32


def _euler(rot):
    return np.array(Euler([math.radians(a) for a in rot]).to_matrix(), dtype=F32)


def xform(shape, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0):
    """Rotate (deg XYZ) then translate a whole composed shape."""
    R = _euler(rot)
    L = np.asarray(loc, dtype=F32)
    s = float(scale)
    f0 = shape[0]

    def fn(P):
        return f0((((P - L) @ R) / s).astype(F32)) * s

    lo, hi = shape[1]
    C = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], dtype=F32)
    W = (C * s) @ R.T + L
    return (fn, (W.min(0), W.max(0)))


def stretch(shape, center, factors):
    """Non-uniform squash about `center` (factors >1 shrink along that axis)."""
    c = np.asarray(center, dtype=F32)
    f = np.asarray(factors, dtype=F32)
    lo, hi = shape[1]
    return (lambda P: shape[0](((P - c) * f + c).astype(F32)) / float(f.max()),
            ((lo - c) / f + c, (hi - c) / f + c))


def half_space(point, normal):
    """Everything on the +normal side of the plane is 'inside' (use as a cutter)."""
    n = np.asarray(normal, dtype=F32)
    n = n / np.linalg.norm(n)
    p = np.asarray(point, dtype=F32)
    return (lambda P: -((P - p) @ n), (p - 0.1, p + 0.1))


def box_region(lo, hi):
    lo = np.asarray(lo, dtype=F32)
    hi = np.asarray(hi, dtype=F32)
    c = (lo + hi) / 2
    h = (hi - lo) / 2

    def fn(P):
        Q = np.abs(P - c) - h
        return np.linalg.norm(np.maximum(Q, 0), axis=1) + np.minimum(Q.max(1), 0)

    return (fn, (lo, hi))


def extrude2d(fn2d, bounds2d, half_h, rounding=0.0, center=(0, 0, 0), rot=None):
    """fn2d(x, y) -> 2D signed distance, extruded along local Z with rounded edges."""
    c = np.asarray(center, dtype=F32)
    R = _euler(rot) if rot else None

    def fn(P):
        Q = P - c
        if R is not None:
            Q = Q @ R
        d = fn2d(Q[:, 0], Q[:, 1]) + rounding
        w = np.abs(Q[:, 2]) - (half_h - rounding)
        out = np.sqrt(np.maximum(d, 0) ** 2 + np.maximum(w, 0) ** 2)
        return out + np.minimum(np.maximum(d, w), 0) - rounding

    x0, y0, x1, y1 = bounds2d
    m = max(abs(x0), abs(x1), abs(y0), abs(y1), half_h)
    return (fn, (c - m, c + m))


def star2d(r, rf):
    """iq's 5-point star, point along +y. r outer radius, rf inner factor."""
    k1 = np.array([0.809016994375, -0.587785252292], dtype=F32)
    k2 = np.array([-k1[0], k1[1]], dtype=F32)
    ba = np.array([rf * -k1[1], rf * k1[0]], dtype=F32) - np.array([0, 1], dtype=F32)
    bb = float(ba @ ba)

    def fn(x, y):
        p = np.stack([np.abs(x), y], axis=1)
        p = p - 2.0 * np.maximum(p @ k1, 0)[:, None] * k1
        p = p - 2.0 * np.maximum(p @ k2, 0)[:, None] * k2
        p[:, 0] = np.abs(p[:, 0])
        p[:, 1] -= r
        h = np.clip((p @ ba) / bb, 0.0, r)
        q = p - h[:, None] * ba
        return np.linalg.norm(q, axis=1) * np.sign(p[:, 1] * ba[0] - p[:, 0] * ba[1])

    return fn


def hex2d(r):
    """Hexagon with apothem r (flat sides on ±y)."""
    k = np.array([-0.866025404, 0.5], dtype=F32)
    kz = 0.577350269

    def fn(x, y):
        p = np.stack([np.abs(x), np.abs(y)], axis=1)
        p = p - 2.0 * np.minimum(p @ k, 0)[:, None] * k
        px = p[:, 0] - np.clip(p[:, 0], -kz * r, kz * r)
        py = p[:, 1] - r
        return np.sqrt(px * px + py * py) * np.sign(py)

    return fn


def circle2d(r):
    return lambda x, y: np.sqrt(x * x + y * y) - r


def curve_points(a, b, bend, n=6):
    a, b, bend = Vector(a), Vector(b), Vector(bend)
    mid = (a + b) * 0.5 + bend
    return [a * (1 - t) ** 2 + mid * 2 * t * (1 - t) + b * t * t for t in (i / (n - 1) for i in range(n))]


def T(v):
    return (float(v[0]), float(v[1]), float(v[2]))


def chain(points, radii, k=0.05):
    if isinstance(radii, (int, float)):
        radii = [radii] * len(points)
    parts = [sdf.round_cone(T(points[i]), T(points[i + 1]), radii[i], radii[i + 1]) for i in range(len(points) - 1)]
    return sdf.smooth_union(*parts, k=k) if len(parts) > 1 else parts[0]


def U(*shapes, k=0.05):
    return sdf.smooth_union(*shapes, k=k) if len(shapes) > 1 else shapes[0]


def surface(shape, p, iters=10, eps=1e-3):
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


def polyline_t(points, co):
    """Arc-length parameter (0..1) of the closest point on a polyline."""
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
    return bt


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


def decal_mesh(shape, spots, lift=0.012, sides=8):
    """Soft round spots that hug a curved SDF surface (studs read as dents on big smooth forms)."""
    bm = bmesh.new()
    for p0, r in spots:
        p, n = surface(shape, p0)
        n, t, b = _frame(n)
        c = bm.verts.new(p + n * lift * 1.8)
        rings = []
        for fr in (0.55, 1.0):
            ring = []
            for a in (2 * math.pi * i / sides for i in range(sides)):
                q, qn = surface(shape, p + (t * math.cos(a) + b * math.sin(a)) * r * fr, iters=6)
                ring.append(bm.verts.new(q + qn * lift))
            rings.append(ring)
        for i in range(sides):
            j = (i + 1) % sides
            bm.faces.new((c, rings[0][i], rings[0][j]))
            bm.faces.new((rings[0][i], rings[1][i], rings[1][j], rings[0][j]))
    return fk.mesh_object(_name("decal"), bm)


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


def hull_mesh(points):
    bm = bmesh.new()
    vs = [bm.verts.new(Vector(p)) for p in points]
    res = bmesh.ops.convex_hull(bm, input=vs)
    kill = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return fk.mesh_object(_name("hull"), bm)


def lathe_mesh(profile, segments=24, face_colors=False):
    """profile: [(radius, z)] bottom->top, revolved around Z. Radius 0 closes a pole."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        if r <= 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
        else:
            rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z))
                          for a in (2 * math.pi * i / segments for i in range(segments))])
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]
        for i in range(segments):
            j = (i + 1) % segments
            if len(A) == 1:
                bm.faces.new((A[0], B[i], B[j]))
            elif len(B) == 1:
                bm.faces.new((A[i], A[j], B[0]))
            else:
                bm.faces.new((A[i], A[j], B[j], B[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return fk.mesh_object(_name("lathe"), bm)


# ═══ PIECES → ONE ITEM ═══════════════════════════════════════════════════════════

class Piece:
    """color: sRGB tuple or fn(co, n) -> sRGB. co is in the piece's own frame (before `post`).

    shape/obj: an SDF or a ready mesh object.   tris: fixed triangle allowance (else by area).
    post: Matrix applied to the mesh after meshing.  mirror: add an X-mirrored copy.
    glow: keep full brightness (no AO, gentle top tone).  flat: faceted shading.
    face: paint per face (crisp stripes) instead of per vertex."""

    def __init__(self, color, shape=None, obj=None, voxel=None, tris=None, weight=1.0, post=None,
                 mirror=False, glow=False, flat=False, face=False, hi=0.2, lo=0.35, lit=True):
        self.color, self.shape, self.obj, self.voxel, self.tris = color, shape, obj, voxel, tris
        self.weight, self.post, self.mirror, self.glow, self.flat, self.face = weight, post, mirror, glow, flat, face
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
    fn = pc.color if callable(pc.color) else (lambda co, n, c=pc.color: c)
    hi, lo = (pc.hi * 0.5, pc.lo * 0.3) if pc.glow else (pc.hi, pc.lo)

    def f(co, n):
        c = fn(M_inv @ co if M_inv is not None else co, n)
        return to_lin(tone(c, n, hi, lo) if pc.lit else c)

    if not pc.face:
        fk.paint(o, f)
        return
    layer = fk.ensure_color_layer(o)
    me = o.data
    for poly in me.polygons:
        c = f(poly.center, poly.normal)
        for li in poly.loop_indices:
            layer.data[li].color = (c[0], c[1], c[2], 1.0)


def build(name, pieces, ao=0.5, ao_dist=None, budget=TRI_TARGET):
    meshed = []  # (obj, piece, voxel)
    for pc in pieces:
        if pc.obj is not None:
            o, vox = pc.obj, None
            if pc.tris is None:
                pc.tris = fk.triangle_count(o)
        else:
            lo, hi = pc.shape[1]
            ext = float(np.max(np.asarray(hi) - np.asarray(lo)))
            vox = pc.voxel or min(0.04, max(0.012, ext / 45.0))
            o = sdf.to_mesh(_name("sdf"), pc.shape, voxel=vox)
        meshed.append((o, pc, vox))

    fixed = sum(min(pc.tris, fk.triangle_count(o)) for o, pc, _ in meshed if pc.tris is not None)
    free = [(i, fk.triangle_count(o) * vox * vox * pc.weight) for i, (o, pc, vox) in enumerate(meshed) if pc.tris is None]
    mult = 2 if False else 1
    remaining = max(60, budget - fixed)
    area = sum(a for _, a in free) or 1.0
    alloc = {i: max(28, remaining * a / area) for i, a in free}
    over = sum(alloc.values()) / remaining
    if over > 1:
        alloc = {i: max(16, v / over) for i, v in alloc.items()}

    decimated = []
    for i, (o, pc, vox) in enumerate(meshed):
        target = pc.tris if pc.tris is not None else int(alloc[i])
        copies = 2 if pc.mirror else 1
        raw_tris = fk.triangle_count(o)
        o = _decimate(o, max(12, target // copies))
        if os.environ.get("KIT_DEBUG"):
            print(f"   piece {i}: raw {raw_tris} target {target} -> {fk.triangle_count(o)}")
        decimated.append([o, pc, copies])
    # hard budget guard: small pieces can stall above their share, so take the overflow
    # back from the biggest piece that is still decimatable
    for _ in range(4):
        total = sum(fk.triangle_count(o) * c for o, _, c in decimated)
        if total <= TRI_CAP - 20:
            break
        k = max(range(len(decimated)), key=lambda j: fk.triangle_count(decimated[j][0]) if decimated[j][1].obj is None else -1)
        o, pc, c = decimated[k]
        decimated[k][0] = _decimate(o, fk.triangle_count(o) - (total - (TRI_CAP - 30)) // c)

    objs, spans = [], []
    for o, pc, copies in decimated:
        M_inv = None
        if pc.post is not None:
            o.data.transform(pc.post)
            M_inv = pc.post.inverted()
        variants = [(o, M_inv)]
        if pc.mirror:
            me = o.data.copy()
            mir = Matrix.Diagonal(Vector((-1, 1, 1, 1)))
            me.transform(mir)
            me.flip_normals()
            m = bpy.data.objects.new(_name("mir"), me)
            fk.link(m)
            mi = (M_inv @ mir) if M_inv is not None else mir
            variants.append((m, mi))
        for ob, inv in variants:
            ob.data.update()
            _paint(ob, pc, inv)
            spans.append((len(ob.data.polygons), pc))
            objs.append(ob)

    obj = fk.join(objs, name)
    # base at z=0, centred on X/Y
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
    keep = {li: tuple(layer.data[li].color) for li in glow_loops}
    size = max(hi - lo)
    fk.bake_ao(obj, floor_z=0.0, samples=24, distance=ao_dist or max(0.18, min(0.8, size * 0.3)), strength=ao)
    for li, c in keep.items():
        a = layer.data[li].color
        layer.data[li].color = tuple(a[i] * 0.15 + c[i] * 0.85 for i in range(3)) + (1.0,)
    fk.box_uv(obj, 2.0)
    obj.data.materials.clear()
    return obj


# ═══ ITEMS ═════════════════════════════════════════════════════════════════════
# Every function returns a list of Pieces. Coordinates are studs, Z up, front faces -Y.
# The builder re-centres and drops the base to z=0, so shapes only need to be roughly placed.

ITEMS = {}


def item(fn):
    ITEMS[fn.__name__] = fn
    return fn


GREEN_LEAF = H(0x5DBB3A)
BROWN_STEM = H(0x6B4A2A)


def leaf_shape(base, tip, width, thick, lift=0.0):
    """Pointed leaf: two offset spheres intersected (a vesica), laid along base->tip."""
    base, tip = Vector(base), Vector(tip)
    L = (tip - base).length
    mid = (base + tip) / 2
    d = (tip - base).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 1e-3:
        side = Vector((1, 0, 0))
    side.normalize()
    R = (L * L / 4 + width * width) / (2 * width)
    off = R - width
    a = sdf.sphere(T(mid + side * off), R)
    b = sdf.sphere(T(mid - side * off), R)
    lens = sdf.smooth_intersect(a, b, k=0.02)
    up = side.cross(d).normalized()
    # slab with its thickness along `up`
    rot = Matrix((side, d, up)).transposed().to_euler()
    slab = sdf.round_box(T(mid + up * lift), (L * 0.6, L * 0.6, thick), thick * 0.9,
                         rot=[math.degrees(a) for a in rot])
    shape = sdf.smooth_intersect(lens, slab, k=0.01)
    return (shape[0], (np.minimum(base, tip) - width - thick, np.maximum(base, tip) + width + thick))


def leaf_paint(base_col, vein_base, vein_tip, vein_w=0.03):
    vb, vt = Vector(vein_base), Vector(vein_tip)

    def fn(co, n):
        ab = vt - vb
        t = max(0.0, min(1.0, (co - vb).dot(ab) / ab.length_squared))
        d = (co - (vb + ab * t)).length
        c = mixc(base_col, lighter(base_col, 0.25), t * 0.6)
        return mixc(lighter(c, 0.35), c, ss(vein_w * 0.6, vein_w * 1.4, d))

    return fn


@item
def Apple():
    red = H(0xE03A3A)
    body = U(sdf.sphere((0, 0, 0.82), 0.72), sdf.sphere((0, 0, 0.55), 0.58), k=0.3)
    body = sdf.smooth_subtract(body, sdf.sphere((0, 0, 1.68), 0.3), k=0.22)
    body = sdf.smooth_subtract(body, sdf.sphere((0, 0, -0.1), 0.16), k=0.12)

    def apple_col(co, n):
        ang = math.atan2(co.y, co.x)
        streak = 0.5 + 0.5 * math.sin(ang * 13 + math.sin(co.z * 5) * 1.5)
        c = mixc(red, H(0xB8202A), 0.25 * streak)
        c = mixc(c, H(0xF5B73C), 0.55 * ss(0.95, 1.45, co.z) * ss(-0.2, 0.6, co.x + co.y * 0.5))
        return c

    stem = chain(curve_points((0, 0, 1.2), (0.1, 0.04, 1.72), (0.05, 0, 0.02), 4), [0.07, 0.06, 0.055, 0.06], k=0.02)
    leaf = leaf_shape((0.08, 0.02, 1.55), (0.62, 0.12, 1.72), 0.17, 0.035)
    return [
        Piece(apple_col, body, weight=1.0),
        Piece(BROWN_STEM, stem, voxel=0.015, tris=60),
        Piece(leaf_paint(GREEN_LEAF, (0.08, 0.02, 1.55), (0.62, 0.12, 1.72)), leaf, voxel=0.012, tris=90),
    ]


@item
def Strawberry():
    red = H(0xF0283E)
    body = U(sdf.round_cone((0, 0, 0.22), (0, 0, 0.82), 0.2, 0.56), sdf.ellipsoid((0, 0, 0.9), (0.58, 0.58, 0.42)), k=0.25)
    body = sdf.smooth_subtract(body, sdf.sphere((0, 0, 1.52), 0.28), k=0.2)

    def col(co, n):
        return mixc(red, H(0xC81530), ss(0.9, 0.2, co.z) * 0.5)

    spots = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(30):
        z = 0.28 + 0.92 * (i + 0.5) / 30
        a = i * golden
        p, nn = surface(body, (math.cos(a), math.sin(a), z))
        if p.z > 1.08:
            continue
        spots.append((p, nn, 0.05, 0.03))
    seeds = dots_mesh(spots, sides=5)
    calyx = []
    for i in range(6):
        a = math.radians(i * 60 + 15)
        d = Vector((math.cos(a), math.sin(a), 0))
        base, _ = surface(body, T(d * 0.08 + Vector((0, 0, 1.6))))
        tip, tn = surface(body, T(d * 0.9 + Vector((0, 0, 1.12))))
        mid, mn = surface(body, T(d * 0.5 + Vector((0, 0, 1.45))))
        calyx.append(leaf_shape(T(base + Vector((0, 0, 0.05))), T(tip + tn * 0.04), 0.15, 0.04, lift=0.03))
    calyx.append(sdf.round_cone((0, 0, 1.25), (0.04, 0, 1.62), 0.08, 0.06))
    return [
        Piece(col, body),
        Piece(H(0xFFE38A), obj=seeds, lo=0.1),
        Piece(lambda co, n: mixc(H(0x2F8F32), H(0x6CC04A), ss(1.1, 1.4, co.z)), U(*calyx, k=0.05), voxel=0.013, tris=230),
    ]

@item
def Watermelon():
    cz = 0.95
    melon = sdf.ellipsoid((0, 0, cz), (1.25, 1.1, 0.95))
    corner = box_region((-3, -3, cz), (0.05, -0.05, 3))
    body = sdf.smooth_subtract(melon, corner, k=0.04)
    mfn = melon[0]
    dark, light = H(0x2F7D32), H(0x8ACB5E)

    def rind(co, n):
        d = float(mfn(np.array([[co.x, co.y, co.z]], dtype=F32))[0])
        if d < -0.03:
            return H(0xEAF4C9)
        ang = math.atan2(co.y, co.x)
        s_ = math.sin(ang * 9 + 0.5 * math.sin(co.z * 7.0))
        return mixc(light, dark, ss(-0.15, 0.15, s_))

    # flesh: a layer standing 0.035 proud of the cut faces, inside the white rind line
    inner = sdf.ellipsoid((0, 0, cz), (1.25 - 0.1, 1.1 - 0.1, 0.95 - 0.1))
    layer = sdf.smooth_subtract(box_region((-3, -3, cz - 0.01), (0.06, -0.04, 3)),
                                box_region((-3, -3, cz + 0.035), (0.015, -0.085, 3)), k=0.0)
    flesh = (lambda P: np.maximum(inner[0](P), layer[0](P)), inner[1])

    spots = []
    rng = random.Random(3)
    for _ in range(40):
        face = rng.choice(("x", "y", "z"))
        if face == "x":
            p0, nn = (0.015, rng.uniform(-0.9, -0.25), rng.uniform(cz + 0.2, cz + 0.65)), (-1, 0, 0)
        elif face == "y":
            p0, nn = (rng.uniform(-0.95, -0.25), -0.085, rng.uniform(cz + 0.2, cz + 0.65)), (0, -1, 0)
        else:
            p0, nn = (rng.uniform(-0.8, -0.25), rng.uniform(-0.75, -0.25), cz + 0.035), (0, 0, 1)
        if mfn(np.array([p0], dtype=F32))[0] > -0.28:
            continue
        spots.append((Vector(p0), Vector(nn), 0.06, 0.035))
        if len(spots) >= 15:
            break
    seeds = dots_mesh(spots, sides=5)
    return [
        Piece(rind, body, voxel=0.03),
        Piece(lambda co, n: mixc(H(0xFF3F55), H(0xFF6B78), ss(cz + 0.3, cz + 0.9, co.z)), flesh, voxel=0.017, tris=170),
        Piece(H(0x2A1C1C), obj=seeds, lo=0.1),
    ]


@item
def Blueberry():
    blue = H(0x3E4FA8)
    berries = [((0.0, -0.32, 0.36), 0.37, (0.0, -0.5)), ((0.34, 0.2, 0.34), 0.35, (0.45, 0.25)),
               ((-0.36, 0.18, 0.32), 0.33, (-0.45, 0.2))]
    pieces, crowns = [], []
    for c, r, lean in berries:
        s = sdf.ellipsoid(c, (r, r, r * 0.92))
        up = Vector((lean[0], lean[1], 1.0)).normalized()
        top, nn = surface(s, T(Vector(c) + up * r * 1.2))
        # star-shaped crown: a dark cup with five sepal points
        s = sdf.smooth_subtract(s, sdf.sphere(T(top + nn * 0.035), 0.1), k=0.04)
        t_, b_ = nn.orthogonal().normalized(), None
        b_ = nn.cross(t_)
        for i in range(5):
            a = 2 * math.pi * i / 5
            d = t_ * math.cos(a) + b_ * math.sin(a)
            crowns.append(sdf.round_cone(T(top - nn * 0.02 + d * 0.05), T(top + nn * 0.05 + d * 0.12), 0.035, 0.018))

        def col(co, n, c=c):
            return mixc(blue, H(0x8391D6), 0.4 * ss(-0.2, 0.9, wave(co, 8, c[0] * 10)))

        pieces.append(Piece(col, s, voxel=0.016, hi=0.35))
    pieces.append(Piece(H(0x262A5C), U(*crowns, k=0.02), voxel=0.01, tris=150, lo=0.1))
    return pieces

@item
def Carrot():
    orange = H(0xF07A1F)
    a, b = Vector((-0.75, 0, 0.32)), Vector((0.85, -0.05, 0.1))
    root = sdf.round_cone(T(a), T(b), 0.32, 0.07)

    def col(co, n):
        t = (co - a).dot((b - a).normalized())
        crease = ss(0.86, 0.98, math.sin(t * 17.0)) * ss(-0.2, 0.4, wave(co, 7, 2))
        c = mixc(orange, H(0xC9540F), crease * 0.8)
        return mixc(c, H(0xFFA24A), 0.25 * ss(-0.8, -0.45, co.x))

    stalks, leaves = [], []
    top = Vector((-0.98, 0, 0.38))
    for i, (dy, up) in enumerate(((-0.45, 0.5), (-0.2, 0.9), (0.02, 1.0), (0.24, 0.85), (0.45, 0.5))):
        tip = top + Vector((-0.3 - 0.15 * up, dy, 0.25 + 0.45 * up))
        stalks.append(chain([top, top.lerp(tip, 0.5) + Vector((0, 0, 0.04)), tip], [0.06, 0.045, 0.035], k=0.02))
        d = (tip - top).normalized()
        side = d.cross(Vector((0, 0, 1)))
        side = side.normalized() if side.length > 1e-3 else Vector((0, 1, 0))
        q = top.lerp(tip, 0.6)
        for sgn in (-1, 1):
            leaves.append(leaf_shape(T(q), T(q + side * sgn * 0.42 + d * 0.22), 0.18, 0.045))
        leaves.append(leaf_shape(T(tip - d * 0.12), T(tip + d * 0.55), 0.22, 0.045))
    small = M(scale=0.88)  # 2.4 studs long with the fronds
    return [
        Piece(col, root, voxel=0.02, post=small),
        Piece(H(0x4E9E34), U(*stalks, k=0.04), voxel=0.013, tris=110, post=small),
        Piece(lambda co, n: mixc(H(0x3F9E36), H(0x86D054), ss(0.6, 1.2, co.z)), U(*leaves, k=0.03), voxel=0.012, weight=1.6, post=small),
    ]

@item
def Pumpkin():
    orange = H(0xE8801F)
    lobes = []
    for i in range(8):
        a = math.radians(i * 45)
        lobes.append(sdf.ellipsoid((0.5 * math.cos(a), 0.5 * math.sin(a), 0.78), (0.62, 0.46, 0.76), rot=(0, 0, i * 45)))
    body = U(*lobes, k=0.14)
    body = U(body, sdf.ellipsoid((0, 0, 0.75), (0.8, 0.8, 0.72)), k=0.1)
    body = sdf.smooth_subtract(body, sdf.sphere((0, 0, 1.72), 0.36), k=0.25)

    def col(co, n):
        ang = math.atan2(co.y, co.x)
        g = math.cos(8 * ang)
        c = mixc(orange, H(0xB9520E), ss(0.2, -0.95, g) * 0.7)
        return mixc(c, H(0xF9A23C), 0.35 * ss(0.3, 1.0, g) * ss(0.4, 1.1, co.z))

    stem = chain(curve_points((0, 0, 1.2), (0.2, 0.08, 1.85), (0.0, 0.0, 0.05), 4), [0.17, 0.14, 0.12, 0.12], k=0.04)
    stem = sdf.smooth_subtract(stem, sdf.sphere((0.24, 0.1, 2.02), 0.14), k=0.05)
    leaf = leaf_shape((0.1, -0.1, 1.38), (0.35, -0.75, 1.3), 0.2, 0.035)
    return [
        Piece(col, body, voxel=0.035),
        Piece(lambda co, n: mixc(H(0x5E6B2A), H(0x8C8A45), ss(1.4, 1.9, co.z)), stem, voxel=0.018, tris=110),
        Piece(leaf_paint(H(0x4E9B35), (0.1, -0.1, 1.38), (0.35, -0.75, 1.3)), leaf, voxel=0.013, tris=90),
    ]


def flower_head(n_petals, petal_len, petal_w, petal_th, ring_r, cup_deg, center_r, center_h, layers=1):
    """Flower in local frame (faces +Z at origin). Returns (petals_shape, center_shape)."""
    petals = []
    for L in range(layers):
        for i in range(n_petals):
            a = (i + 0.5 * L) * 360.0 / n_petals
            ar = math.radians(a)
            c = (ring_r * math.cos(ar), ring_r * math.sin(ar), -0.02 * L)
            petals.append(sdf.ellipsoid(c, (petal_len, petal_w, petal_th), rot=(0, -cup_deg, a)))
    center = sdf.ellipsoid((0, 0, center_h * 0.3), (center_r, center_r, center_h))
    return U(*petals, k=0.02), center


@item
def Daisy():
    tilt, hloc = 42, (0, -0.1, 0.72)
    petals, center = flower_head(13, 0.25, 0.085, 0.04, 0.3, 12, 0.17, 0.11)
    stem = chain(curve_points((0, 0.25, 0.02), hloc, (0, 0.08, 0), 4), [0.08, 0.07, 0.065, 0.06], k=0.03)
    leaves = U(leaf_shape((0, 0.2, 0.05), (0.5, 0.0, 0.12), 0.15, 0.035),
               leaf_shape((0, 0.25, 0.05), (-0.45, 0.45, 0.14), 0.14, 0.035), k=0.02)
    post = M(hloc, (tilt, 0, 0))
    return [
        Piece(lambda co, n: mixc(H(0xFFFFFF), H(0xF3C6DA), ss(0.35, 0.56, math.hypot(co.x, co.y))),
              petals, voxel=0.012, post=post, weight=1.2, hi=0.1),
        Piece(lambda co, n: mixc(H(0xFFC21E), H(0xFFE36A), ss(0.05, 0.14, co.z)), center, voxel=0.012, post=post, tris=120),
        Piece(H(0x4FA83A), U(stem, leaves, k=0.04), voxel=0.014, tris=160),
    ]


@item
def Sunflower():
    tilt, hloc = 40, (0, -0.15, 1.35)
    petals = []
    for L, (n_, r0, r1, w, z) in enumerate(((13, 0.34, 0.86, 0.14, -0.03), (13, 0.34, 0.8, 0.13, 0.0))):
        for i in range(n_):
            a = math.radians((i + 0.5 * L) * 360.0 / n_)
            d = Vector((math.cos(a), math.sin(a), 0))
            petals.append(leaf_shape(T(d * r0 + Vector((0, 0, z))), T(d * r1 + Vector((0, 0, z + 0.1))), w, 0.035))
    center = U(sdf.ellipsoid((0, 0, 0.04), (0.42, 0.42, 0.12)), sdf.cylinder((0, 0, -0.04), 0.44, 0.06, rounding=0.04), k=0.04)

    def center_col(co, n):
        r = math.hypot(co.x, co.y)
        spots = 0.5 + 0.5 * math.sin(r * 60) * math.sin(math.atan2(co.y, co.x) * 17)
        c = mixc(H(0x5A3418), H(0x341C0C), spots * 0.7)
        return mixc(c, H(0x8A5A22), ss(0.3, 0.42, r))

    stem = chain(curve_points((0, 0.3, 0.0), (0, -0.05, 1.3), (0, 0.15, 0), 5), [0.14, 0.12, 0.11, 0.1, 0.1], k=0.04)
    leaves = U(leaf_shape((0.05, 0.28, 0.45), (0.8, 0.15, 0.62), 0.25, 0.04),
               leaf_shape((-0.05, 0.22, 0.75), (-0.75, 0.35, 0.98), 0.23, 0.04), k=0.03)
    post = M(hloc, (tilt, 0, 0))
    return [
        Piece(lambda co, n: mixc(H(0xF59A12), H(0xFFD23A), ss(0.3, 0.7, math.hypot(co.x, co.y))),
              U(*petals, k=0.01), voxel=0.014, post=post, weight=1.1),
        Piece(center_col, center, voxel=0.018, post=post, tris=150),
        Piece(H(0x4E9E34), U(stem, leaves, k=0.05), voxel=0.02, tris=180),
    ]

@item
def Clover():
    hearts = []
    for i in range(4):
        a = math.radians(i * 90 + 45)
        d = Vector((math.cos(a), math.sin(a), 0))
        s = Vector((-d.y, d.x, 0))
        z = Vector((0, 0, 1))
        heart = U(sdf.ellipsoid(T(d * 0.34 + s * 0.12 + z * 0.06), (0.14, 0.14, 0.045)),
                  sdf.ellipsoid(T(d * 0.34 - s * 0.12 + z * 0.06), (0.14, 0.14, 0.045)),
                  sdf.ellipsoid(T(d * 0.2 + z * 0.03), (0.15, 0.1, 0.045), rot=(0, 0, math.degrees(a))), k=0.03)
        heart = sdf.smooth_subtract(heart, sdf.sphere(T(d * 0.5 + z * 0.06), 0.06), k=0.03)
        hearts.append(heart)
    leaf = U(*hearts, sdf.sphere((0, 0, 0.0), 0.05), k=0.025)

    def col(co, n):
        r = math.hypot(co.x, co.y)
        c = mixc(H(0x23883A), H(0x3FBF4C), ss(0.05, 0.35, r))
        band = ss(0.19, 0.22, r) * (1 - ss(0.27, 0.3, r))
        return mixc(c, H(0xC8F2B0), band * 0.9)

    stem = chain(curve_points((0.05, 0.42, 0.03), (0, -0.02, 0.58), (0, 0.1, -0.08), 4), [0.06, 0.05, 0.045, 0.045], k=0.03)
    return [
        Piece(col, leaf, voxel=0.012, post=M((0, -0.05, 0.6), (48, 0, 0)), hi=0.3),
        Piece(H(0x2F8F36), stem, voxel=0.013, tris=80),
    ]

def irid(co, n):
    f = 1.0 - abs(n.z)
    c = mixc(H(0x2BC25A), H(0x14A2A8), ss(-0.4, 0.6, n.x * 0.6 - n.y * 0.4))
    return mixc(c, H(0x7A4FD6), ss(0.55, 0.98, f) * 0.85)


@item
def Beetle():
    shell = sdf.ellipsoid((0, 0.12, 0.42), (0.55, 0.66, 0.38))
    shell = sdf.smooth_subtract(shell, sdf.round_box((0, 0.22, 0.8), (0.018, 0.7, 0.12), 0.015), k=0.03)
    shell = sdf.smooth_subtract(shell, half_space((0, 0, 0.16), (0, 0, -1)), k=0.05)
    pron = sdf.ellipsoid((0, -0.46, 0.38), (0.4, 0.25, 0.25))
    head = sdf.ellipsoid((0, -0.7, 0.3), (0.26, 0.19, 0.19))
    legs = []
    for y, fwd in ((-0.42, -0.14), (-0.05, 0.0), (0.32, 0.14)):
        legs.append(chain([(0.36, y, 0.24), (0.58, y + fwd, 0.2), (0.64, y + fwd * 1.4, 0.04)], [0.075, 0.065, 0.07], k=0.05))
    legs = sdf.mirror_x(U(*legs, k=0.02))
    ant = sdf.mirror_x(U(chain(curve_points((0.08, -0.82, 0.38), (0.26, -1.05, 0.62), (0, -0.04, 0.03), 4), 0.035, k=0.01),
                         sdf.sphere((0.26, -1.05, 0.62), 0.07), k=0.02))
    eyes = sdf.mirror_x(sdf.sphere((0.12, -0.82, 0.38), 0.08))
    pupils = dots_mesh([(Vector((s * 0.13, -0.9, 0.39)), Vector((s * 0.25, -1, 0.1)), 0.045, 0.02) for s in (-1, 1)], sides=6)
    dark = H(0x2A2E38)
    return [
        Piece(irid, shell, voxel=0.018, hi=0.4),
        Piece(lambda co, n: richer(irid(co, n), 0.25), pron, voxel=0.018, tris=120, hi=0.4),
        Piece(dark, U(head, legs, ant, k=0.03), voxel=0.014, weight=0.6),
        Piece(H(0xFAFAF5), eyes, voxel=0.012, tris=60, lo=0.1),
        Piece(H(0x101014), obj=pupils, lit=False),
    ]

@item
def Butterfly():
    # built head -Y like everything, then turned side-on (head -X) so the wings face the camera
    pivot = Vector((0, 0, 0.14))
    fore = sdf.ellipsoid((0.0, -0.2, 0.66), (0.045, 0.4, 0.54), rot=(-30, 0, 0))
    hind = sdf.ellipsoid((0.0, 0.26, 0.42), (0.045, 0.34, 0.36), rot=(24, 0, 0))
    wing = U(fore, hind, k=0.08)

    def wing_col(co, n):
        def e(c, ry, rz, ang):
            dy, dz = co.y - c[0], co.z - c[1]
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            u, v = dy * ca + dz * sa, -dy * sa + dz * ca
            return math.hypot(u / ry, v / rz)
        m = min(e((-0.2, 0.66), 0.4, 0.54, -30), e((0.26, 0.42), 0.34, 0.36, 24))
        inner = mixc(H(0x2E6BE0), H(0x86C8FF), ss(0.15, 0.7, m))
        c = mixc(inner, H(0x1B2150), ss(0.72, 0.8, m))
        spot = ss(0.075, 0.045, math.hypot(co.y + 0.02, co.z - 1.08)) + ss(0.065, 0.04, math.hypot(co.y + 0.36, co.z - 1.0)) \
            + ss(0.055, 0.03, math.hypot(co.y - 0.46, co.z - 0.56))
        c = mixc(c, H(0xFFFFFF), spot)
        return mixc(c, H(0xFFB23A), ss(0.1, 0.07, math.hypot(co.y - 0.24, co.z - 0.36)))

    body = U(chain([(0, 0.42, 0.1), (0, 0.0, 0.12), (0, -0.28, 0.15)], [0.07, 0.1, 0.09], k=0.04),
             sdf.sphere((0, -0.4, 0.2), 0.12), k=0.05)
    ant = sdf.mirror_x(U(chain(curve_points((0.04, -0.47, 0.28), (0.18, -0.74, 0.72), (0, -0.08, 0), 4), 0.028, k=0.01),
                         sdf.sphere((0.18, -0.74, 0.72), 0.055), k=0.02))
    turn = M(rot=(0, 0, -90))
    postR = turn @ M(pivot) @ M(rot=(0, 28, 0)) @ M(-pivot) @ M((0.06, 0, 0.02))
    postL = turn @ M(pivot) @ M(rot=(0, -28, 0)) @ M(-pivot) @ M((-0.06, 0, 0.02))
    return [
        Piece(wing_col, wing, voxel=0.013, post=postR, hi=0.1, lo=0.1),
        Piece(wing_col, wing, voxel=0.013, post=postL, hi=0.1, lo=0.1),
        Piece(H(0x2B2433), U(body, ant, k=0.03), voxel=0.012, tris=170, post=turn),
    ]

@item
def Worm():
    pink = H(0xF08FA6)
    pts = [Vector(p) for p in ((-0.6, 0.2, 0.09), (-0.4, 0.5, 0.12), (0.0, 0.62, 0.14), (0.42, 0.42, 0.15),
                               (0.55, 0.02, 0.15), (0.35, -0.32, 0.17), (0.02, -0.42, 0.3), (-0.12, -0.44, 0.5))]
    radii = [0.07, 0.11, 0.13, 0.145, 0.15, 0.15, 0.15, 0.16]
    body = chain(pts, radii, k=0.06)
    hc = Vector((-0.16, -0.46, 0.64))
    body = U(body, sdf.ellipsoid(T(hc), (0.2, 0.19, 0.19)), k=0.1)

    def col(co, n):
        t = polyline_t(pts, co)
        ring = ss(0.75, 0.97, math.sin(t * 70))
        c = mixc(pink, H(0xD8667F), ring * 0.55)
        band = ss(0.66, 0.69, t) * (1 - ss(0.76, 0.79, t))
        return mixc(c, H(0xE9738C), band * 0.8)

    face = []
    for s in (-1, 1):
        p, nn = surface(body, T(hc + Vector((s * 0.09, -0.3, 0.05))))
        face.append((p, nn, 0.04, 0.025))
    eyes = dots_mesh(face, sides=6)
    cheeks = []
    for s in (-1, 1):
        p, nn = surface(body, T(hc + Vector((s * 0.15, -0.25, -0.06))))
        cheeks.append((p, nn, 0.045, 0.015))
    return [
        Piece(col, body, voxel=0.018),
        Piece(H(0x1A1216), obj=eyes, lit=False),
        Piece(H(0xFF5F86), obj=dots_mesh(cheeks, sides=6), lo=0.1),
    ]


@item
def Stick():
    pts = [Vector(p) for p in ((-1.2, 0.0, 0.13), (-0.45, 0.1, 0.16), (0.35, -0.06, 0.15), (1.15, 0.06, 0.12))]
    main = chain(pts, [0.14, 0.13, 0.12, 0.1], k=0.08)
    br = [Vector((0.0, 0.03, 0.16)), Vector((0.45, 0.42, 0.2)), Vector((0.7, 0.72, 0.24))]
    branch = chain(br, [0.09, 0.075, 0.06], k=0.05)
    knob = sdf.sphere((-0.5, -0.09, 0.2), 0.07)
    wood = U(main, branch, knob, k=0.08)
    bark = H(0x7A5230)

    def col(co, n):
        ax = (pts[-1] - pts[0]).normalized()
        endcap = max(abs(n.dot(ax)) * ss(1.0, 1.15, abs(co.x)),
                     abs(n.dot((br[2] - br[1]).normalized())) * ss(0.62, 0.72, co.y))
        streak = 0.5 + 0.5 * math.sin(math.atan2(co.z - 0.15, co.y) * 7 + co.x * 3)
        c = mixc(bark, H(0x5A3A1F), streak * 0.5)
        return mixc(c, H(0xE8C58E), ss(0.6, 0.85, endcap))

    leaf = leaf_shape((0.72, 0.74, 0.26), (1.05, 1.05, 0.3), 0.13, 0.03)
    return [
        Piece(col, wood, voxel=0.02),
        Piece(leaf_paint(GREEN_LEAF, (0.72, 0.74, 0.26), (1.05, 1.05, 0.3)), leaf, voxel=0.012, tris=70),
    ]


@item
def Acorn():
    nut = U(sdf.round_cone((0, 0, 0.12), (0, 0, 0.55), 0.1, 0.42), sdf.ellipsoid((0, 0, 0.6), (0.44, 0.44, 0.34)),
            sdf.sphere((0, 0, 0.06), 0.06), k=0.18)
    cap = sdf.ellipsoid((0, 0, 0.84), (0.52, 0.52, 0.3))
    cap = sdf.smooth_subtract(cap, half_space((0, 0, 0.74), (0, 0, -1)), k=0.03)
    stem = sdf.round_cone((0, 0, 1.05), (0.05, 0.0, 1.26), 0.06, 0.045)

    def nut_col(co, n):
        streak = 0.5 + 0.5 * math.sin(math.atan2(co.y, co.x) * 9)
        c = mixc(H(0xA8703A), H(0x8A552A), streak * 0.4)
        return mixc(c, H(0xD9A868), ss(0.25, 0.05, co.z))

    def cap_col(co, n):
        ang = math.atan2(co.y, co.x)
        scale = (0.5 + 0.5 * math.sin(ang * 16 + co.z * 30)) * (0.5 + 0.5 * math.sin(ang * 16 - co.z * 30))
        return mixc(H(0x7A5A3A), H(0x4E3824), scale * 0.8)

    return [
        Piece(nut_col, nut, voxel=0.016, hi=0.35),
        Piece(cap_col, U(cap, stem, k=0.04), voxel=0.016),
    ]


@item
def MudClump():
    splat = U(sdf.ellipsoid((0, 0, 0.05), (0.85, 0.7, 0.08)), sdf.ellipsoid((0.7, 0.35, 0.04), (0.28, 0.2, 0.05)),
              sdf.ellipsoid((-0.62, -0.45, 0.04), (0.26, 0.24, 0.05)), sdf.ellipsoid((-0.2, 0.7, 0.04), (0.22, 0.16, 0.05)), k=0.15)
    lumps = U(sdf.ellipsoid((0.0, 0.05, 0.22), (0.62, 0.52, 0.26)), sdf.ellipsoid((0.3, -0.12, 0.3), (0.3, 0.28, 0.2)),
              sdf.ellipsoid((-0.3, 0.15, 0.28), (0.28, 0.26, 0.18)), k=0.2)
    mud = U(splat, lumps, k=0.25)
    mud = sdf.noise_bumps(mud, amplitude=0.025, frequency=10.0, seed=4)
    mud = sdf.smooth_subtract(mud, half_space((0, 0, 0.0), (0, 0, -1)), k=0.02)
    mud = U(mud, sdf.ellipsoid((0.75, -0.55, 0.05), (0.09, 0.08, 0.06)), sdf.ellipsoid((-0.85, 0.3, 0.04), (0.07, 0.06, 0.05)), k=0.0)

    def col(co, n):
        c = mixc(H(0x6B4A2E), H(0x4A3220), ss(-0.3, 0.5, wave(co, 5, 1)))
        c = mixc(c, H(0x3A2616), ss(0.12, 0.0, co.z) * 0.5)
        wet = ss(0.25, 0.65, wave(co, 11, 3)) * ss(0.5, 0.95, n.z)
        return mixc(c, H(0xB08A62), wet * 0.8)

    grass = U(*[leaf_shape((x, y, 0.4), (x + dx, y + dy, 0.85), 0.06, 0.025) for x, y, dx, dy in
                ((-0.02, 0.0, 0.05, -0.08), (0.04, 0.03, 0.2, 0.06), (-0.04, 0.05, -0.14, 0.1))], k=0.02)
    return [
        Piece(col, mud, voxel=0.022, hi=0.35),
        Piece(lambda co, n: mixc(H(0x4E9E34), H(0x9ED45A), ss(0.5, 0.85, co.z)), grass, voxel=0.011, tris=90),
    ]

@item
def Pebble():
    body = sdf.ellipsoid((0, 0, 0.2), (0.48, 0.38, 0.2), rot=(0, 0, 20))
    body = U(body, sdf.ellipsoid((0.1, 0.04, 0.26), (0.3, 0.26, 0.14)), k=0.15)
    body = sdf.smooth_subtract(body, half_space((0, 0, 0.03), (0, 0, -1)), k=0.06)
    small = sdf.ellipsoid((0.5, -0.3, 0.1), (0.2, 0.16, 0.1), rot=(0, 0, -30))
    vein = Vector((0.85, 0.2, 0.5)).normalized()

    def col(co, n):
        c = mixc(H(0x9C9488), H(0x81796E), ss(-0.4, 0.6, wave(co, 12, 5)))
        d = abs(co.dot(vein) - 0.1)
        return mixc(c, H(0xE6E0D4), ss(0.03, 0.018, d) * ss(0.1, 0.2, co.z))

    return [
        Piece(col, body, voxel=0.012, hi=0.25),
        Piece(lambda co, n: mixc(H(0x8A93A0), H(0x6E7784), ss(-0.4, 0.6, wave(co, 14, 2))), small, voxel=0.012, tris=140, hi=0.4),
    ]

@item
def RubberDuck():
    yellow = H(0xFFD02A)
    body = U(sdf.ellipsoid((0, 0.1, 0.4), (0.56, 0.72, 0.4)), sdf.ellipsoid((0, 0.66, 0.62), (0.26, 0.22, 0.24), rot=(-30, 0, 0)), k=0.22)
    body = sdf.smooth_subtract(body, half_space((0, 0, 0.03), (0, 0, -1)), k=0.08)
    head = sdf.sphere((0, -0.32, 1.02), 0.37)
    duck = U(body, head, k=0.18)
    wings = sdf.mirror_x(sdf.ellipsoid((0.5, 0.18, 0.5), (0.1, 0.34, 0.2), rot=(-15, 0, -8)))
    beak = U(sdf.ellipsoid((0, -0.7, 0.96), (0.2, 0.2, 0.075)), sdf.ellipsoid((0, -0.64, 0.88), (0.15, 0.14, 0.05)), k=0.03)
    eyes = []
    for s in (-1, 1):
        p, nn = surface(head, (s * 0.2, -0.75, 1.14))
        eyes.append((p, nn, 0.06, 0.03))
    shine = []
    for s in (-1, 1):
        p, nn = surface(head, (s * 0.2 - 0.02, -0.75, 1.17))
        shine.append((p + nn * 0.028, nn, 0.02, 0.01))
    return [
        Piece(lambda co, n: mixc(yellow, H(0xFFE680), ss(0.9, 1.35, co.z) * 0.6), duck, voxel=0.02, hi=0.3),
        Piece(H(0xF5B81A), wings, voxel=0.014, tris=90),
        Piece(H(0xFF8A1E), beak, voxel=0.012, tris=90),
        Piece(H(0x15151A), obj=dots_mesh(eyes), lit=False),
        Piece(H(0xFFFFFF), obj=dots_mesh(shine, sides=4), lit=False, glow=True),
    ]


@item
def BouncyBall():
    ball = sdf.sphere((0, 0, 0.62), 0.62)

    def seam(P):
        return (P[:, 2] - 0.62 - 0.16 * np.sin(3 * np.arctan2(P[:, 1], P[:, 0]))) * 0.7

    top = (lambda P: np.maximum(ball[0](P), -seam(P)), ball[1])
    bot = (lambda P: np.maximum(ball[0](P), seam(P)), ball[1])
    return [
        Piece(H(0xFF4A5A), top, voxel=0.014, hi=0.45),
        Piece(H(0x2E8BFF), bot, voxel=0.014, hi=0.45),
    ]

@item
def ToyBlock():
    s = 0.62
    block = sdf.round_box((0, 0, s), (s, s, s), 0.12)
    stars = []
    for rot, off in (((90, 0, 0), (0, -s, s)), ((90, 0, 90), (s, 0, s)), ((90, 0, 180), (0, s, s)),
                     ((90, 0, -90), (-s, 0, s)), ((0, 0, 0), (0, 0, 2 * s))):
        stars.append(extrude2d(star2d(0.36, 0.48), (-0.4, -0.4, 0.4, 0.4), 0.05, rounding=0.035, center=off, rot=rot))

    def col(co, n):
        c = Vector((0, 0, s))
        q = co - c
        ax = max(range(3), key=lambda i: abs(q[i]))
        others = [abs(q[i]) for i in range(3) if i != ax]
        panel = ss(0.5, 0.44, max(others))
        return mixc(H(0x2F6FD8), H(0x5A9BFF), panel * 0.8)

    return [
        Piece(col, block, voxel=0.024),
        Piece(H(0xFFCC2E), U(*stars, k=0.0), voxel=0.014, weight=1.4),
    ]


@item
def Honeycomb():
    r = 0.19
    cells = [(0, 0)]
    for ring in (1, 2):
        for i in range(6):
            a = math.radians(30 + 60 * i)
            cells.append((2 * r * ring * math.cos(a), 2 * r * ring * math.sin(a)))
    cells = [c for c in cells if math.hypot(*c) < 0.5 or c[0] > 0.2]
    rng = random.Random(5)
    walls, holes, honey = [], [], []
    for i, (x, y) in enumerate(cells):
        h = 0.2 + 0.05 * rng.random() - 0.08 * ss(0.3, 0.8, math.hypot(x, y))
        walls.append(extrude2d(hex2d(r * 1.02), (-r, -r, r, r), h, rounding=0.03, center=(x, y, h)))
        holes.append(extrude2d(hex2d(r * 0.76), (-r, -r, r, r), 0.3, rounding=0.03, center=(x, y, 2 * h + 0.12)))
        if i % 2 == 0:
            honey.append(sdf.ellipsoid((x, y, 2 * h - 0.06), (r * 0.8, r * 0.8, 0.07)))
    comb = sdf.union(*walls)
    comb = sdf.smooth_subtract(comb, sdf.union(*holes), k=0.02)

    def col(co, n):
        return mixc(H(0xD98A14), H(0xFFD45A), ss(0.15, 0.45, co.z) * ss(-0.2, 0.6, n.z))

    drip = U(sdf.ellipsoid((0.2, -0.62, 0.3), (0.1, 0.08, 0.14)), sdf.sphere((0.2, -0.64, 0.12), 0.09), k=0.08)
    return [
        Piece(col, comb, voxel=0.016),
        Piece(lambda co, n: mixc(H(0xE0780A), H(0xFFB21E), ss(0.2, 0.9, n.z)), U(*honey, drip, k=0.0), voxel=0.015, tris=200, hi=0.6),
    ]

@item
def Mushroom():
    stem = sdf.round_cone((0, 0, 0.1), (0, 0, 0.6), 0.25, 0.18)
    stem = U(stem, sdf.ellipsoid((0, 0, 0.1), (0.28, 0.28, 0.12)), k=0.1)
    cap = sdf.ellipsoid((0, 0, 0.66), (0.66, 0.66, 0.46))
    cap = sdf.smooth_subtract(cap, sdf.ellipsoid((0, 0, 0.42), (0.6, 0.6, 0.3)), k=0.08)
    small_stem = sdf.round_cone((0.55, -0.35, 0.0), (0.58, -0.38, 0.32), 0.1, 0.08)
    small_cap = sdf.smooth_subtract(sdf.ellipsoid((0.58, -0.38, 0.34), (0.26, 0.26, 0.18)),
                                    sdf.ellipsoid((0.58, -0.38, 0.24), (0.24, 0.24, 0.12)), k=0.04)

    def cap_col(co, n):
        if n.z < -0.25:
            ang = math.atan2(co.y, co.x)
            return mixc(H(0xD9C2A0), H(0xB89A78), 0.5 + 0.5 * math.sin(ang * 40))
        c = mixc(H(0x8E5A30), H(0xB57A44), ss(0.4, 0.95, n.z))
        return mixc(c, H(0x6E4222), ss(0.3, -0.1, n.z) * 0.6)

    return [
        Piece(lambda co, n: mixc(H(0xF2E6CE), H(0xD9C8A8), ss(0.5, 0.0, co.z)), U(stem, small_stem, k=0.0), voxel=0.016, tris=180),
        Piece(cap_col, U(cap, small_cap, k=0.0), voxel=0.016, hi=0.3),
    ]


@item
def Feather():
    # built standing in the XZ plane (thin along Y) so its face is towards the player
    vane = U(sdf.ellipsoid((0, 0, 0.95), (0.36, 0.07, 0.8)), sdf.ellipsoid((0, 0, 0.45), (0.26, 0.06, 0.3)), k=0.2)
    vane = sdf.smooth_subtract(vane, sdf.round_box((-0.38, 0, 1.2), (0.14, 0.2, 0.035), 0.02, rot=(0, 35, 0)), k=0.02)
    vane = sdf.smooth_subtract(vane, sdf.round_box((0.36, 0, 0.8), (0.12, 0.2, 0.035), 0.02, rot=(0, -35, 0)), k=0.02)
    shaft = chain([(0, -0.02, 0.0), (0, -0.05, 0.3), (0, -0.07, 1.7)], [0.05, 0.045, 0.018], k=0.02)

    def bend(P):
        Q = P.copy()
        Q[:, 0] -= 0.25 * (P[:, 2] / 1.7) ** 2
        Q[:, 1] -= 0.12 * (P[:, 2] / 1.7) ** 2
        return Q

    def col(co, n):
        barbs = 0.5 + 0.5 * math.sin((co.z - abs(co.x) * 1.4) * 26)
        c = mixc(H(0xFFFDF6), H(0xE3DBCC), barbs * 0.4)
        c = mixc(c, H(0x45A6E6), ss(0.95, 1.45, co.z))
        return mixc(c, H(0x1F4E9C), ss(1.55, 1.72, co.z))

    post = M((0, 0, 0), (0, 42, 0))
    return [
        Piece(col, sdf.warp(vane, bend, pad=0.3), voxel=0.014, post=post, lo=0.2, hi=0.15),
        Piece(H(0xDDD2BA), sdf.warp(shaft, bend, pad=0.3), voxel=0.012, post=post, tris=70),
    ]

def box2d(hx, hy):
    def fn(x, y):
        qx, qy = np.abs(x) - hx, np.abs(y) - hy
        return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0)
    return fn


def gear2d(r_body, n_teeth, tooth_len, tooth_w, hole):
    body, tooth = circle2d(r_body), box2d(tooth_len / 2, tooth_w / 2)
    step = 2 * math.pi / n_teeth

    def fn(x, y):
        a = np.arctan2(y, x)
        k = np.round(a / step) * step
        c, s_ = np.cos(-k), np.sin(-k)
        lx, ly = x * c - y * s_, x * s_ + y * c
        d = np.minimum(body(x, y), tooth(lx - r_body - tooth_len * 0.3, ly) - 0.02)
        return np.maximum(d, -(np.sqrt(x * x + y * y) - hole))
    return fn


def helix(R, pitch, r, z0, z1):
    def fn(P):
        rho = np.hypot(P[:, 0], P[:, 1])
        th = np.arctan2(P[:, 1], P[:, 0])
        u = P[:, 2] - pitch * th / (2 * math.pi)
        u = u - pitch * np.round(u / pitch)
        d = np.sqrt((rho - R) ** 2 + (u * 0.95) ** 2) - r
        return np.maximum(d, np.maximum(z0 - P[:, 2], P[:, 2] - z1))
    m = R + r
    return (fn, (np.array([-m, -m, z0], dtype=F32), np.array([m, m, z1], dtype=F32)))


def zslice(shape, z0, z1):
    return (lambda P: np.maximum(shape[0](P), np.maximum(z0 - P[:, 2], P[:, 2] - z1)), shape[1])


def metal(base, rust=None, rust_amt=0.0, seed=1):
    def fn(co, n):
        c = mixc(base, lighter(base, 0.35), ss(0.1, 0.35, n.z) * 0.8)
        c = mixc(c, richer(base, 0.5), ss(-0.05, -0.4, n.z))
        if rust:
            c = mixc(c, rust, ss(0.35, 0.75, wave(co, 7, seed)) * rust_amt)
        return c
    return fn


@item
def Battery():
    ax = (0, 90, 0)
    body = sdf.cylinder((-0.25, 0, 0.44), 0.44, 0.62, rot=ax, rounding=0.1)
    cop = sdf.cylinder((0.6, 0, 0.44), 0.445, 0.3, rot=ax, rounding=0.1)
    nub = sdf.cylinder((0.92, 0, 0.44), 0.17, 0.12, rot=ax, rounding=0.05)
    cap = sdf.cylinder((-0.86, 0, 0.44), 0.3, 0.05, rot=ax, rounding=0.03)
    plus = U(extrude2d(box2d(0.11, 0.03), (-0.2, -0.2, 0.2, 0.2), 0.03, 0.015, center=(0.6, -0.44, 0.52), rot=(90, 0, 0)),
             extrude2d(box2d(0.03, 0.11), (-0.2, -0.2, 0.2, 0.2), 0.03, 0.015, center=(0.6, -0.44, 0.52), rot=(90, 0, 0)), k=0.0)

    def body_col(co, n):
        c = mixc(H(0x2A2A30), H(0x55555E), ss(0.3, 0.9, n.z) * 0.5)
        return mixc(c, H(0xE8B53A), ss(0.06, 0.03, abs(co.x - 0.22)))

    return [
        Piece(body_col, body, voxel=0.02),
        Piece(metal(H(0xD9822B)), cop, voxel=0.02, tris=200),
        Piece(metal(H(0xC8CDD2)), U(nub, cap, k=0.0), voxel=0.016, tris=110),
        Piece(H(0xFFF4DC), plus, voxel=0.01, tris=60),
    ]


@item
def Gear():
    g = extrude2d(gear2d(0.66, 9, 0.26, 0.24, 0.2), (-0.95, -0.95, 0.95, 0.95), 0.16, rounding=0.05, center=(0, 0, 0.16))
    g = sdf.smooth_subtract(g, sdf.torus((0, 0, 0.34), 0.42, 0.05), k=0.03)
    holes = U(*[sdf.cylinder((0.42 * math.cos(a), 0.42 * math.sin(a), 0.16), 0.08, 0.3)
                for a in (math.radians(45 + 90 * i) for i in range(4))], k=0.0)
    g = sdf.smooth_subtract(g, holes, k=0.03)
    return [Piece(metal(H(0x6F7C88), H(0xB5582A), 0.7, 3), g, voxel=0.016, post=M(rot=(28, 0, 0)))]

@item
def ScrapMetal():
    plate = sdf.round_box((0, 0, 0), (0.85, 0.6, 0.08), 0.06)
    plate = sdf.smooth_subtract(plate, U(sdf.sphere((0.85, 0.6, 0), 0.34), sdf.sphere((0.5, 0.64, 0), 0.16),
                                         sdf.sphere((-0.9, -0.5, 0), 0.22), sdf.sphere((0.1, -0.66, 0), 0.12), k=0.0), k=0.02)

    def crumple(P):
        Q = P.copy()
        Q[:, 2] -= 0.28 * np.sin(P[:, 0] * 2.4) + 0.14 * np.cos(P[:, 1] * 3.2 + P[:, 0])
        return Q

    sheet = sdf.warp(plate, crumple, pad=0.45)
    bracket = U(sdf.round_box((0, 0, 0.32), (0.34, 0.08, 0.32), 0.04), sdf.round_box((0, 0.26, 0.05), (0.34, 0.32, 0.07), 0.04), k=0.04)
    pipe = sdf.smooth_subtract(sdf.cylinder((0, 0, 0), 0.16, 0.42, rot=(0, 90, 0), rounding=0.03),
                               sdf.cylinder((0, 0, 0), 0.1, 0.5, rot=(0, 90, 0)), k=0.02)
    rot = M(rot=(12, -8, 0))
    rivets = []
    for x, y in ((-0.6, -0.4), (-0.2, -0.45), (0.2, -0.42), (-0.62, 0.35)):
        p, nn = surface(sheet, (x, y, 1.0))
        rivets.append((rot @ p, rot.to_3x3() @ nn, 0.065, 0.045))
    return [
        Piece(metal(H(0x5F6B76), H(0xC0612B), 1.0, 2), sheet, voxel=0.02, post=rot),
        Piece(metal(H(0x56616B), H(0xB5562A), 0.8, 7), bracket, voxel=0.018, post=M((0.55, -0.1, 0.12), (0, -15, 35)), tris=140),
        Piece(metal(H(0x9A6A45), H(0xC0612B), 0.6, 5), pipe, voxel=0.016, post=M((-0.35, 0.55, 0.35), (0, 10, 25)), tris=150),
        Piece(H(0x4E555C), obj=dots_mesh(rivets, sides=6)),
    ]

@item
def Magnet():
    arc = sdf.torus((0, 0, 0.62), 0.46, 0.22, rot=(90, 0, 0))
    arc = sdf.smooth_subtract(arc, half_space((0, 0, 0.62), (0, 0, 1)), k=0.02)
    legs = sdf.mirror_x(sdf.cylinder((0.46, 0, 0.9), 0.22, 0.3, rounding=0.02))
    red = zslice(U(arc, legs, k=0.02), -1, 1.18)
    tips = sdf.mirror_x(sdf.cylinder((0.46, 0, 1.36), 0.225, 0.2, rounding=0.07))
    return [
        Piece(lambda co, n: mixc(H(0xD8262E), H(0xFF5A5A), ss(0.3, 0.9, -n.y * 0.5 + n.z * 0.5) * 0.5), red, voxel=0.02,
              post=M(rot=(0, 0, 0)), hi=0.35),
        Piece(metal(H(0xC9CFD6)), tips, voxel=0.018, tris=180),
    ]


@item
def OilCan():
    body = U(sdf.cylinder((0, 0, 0.3), 0.66, 0.3, rounding=0.12), sdf.round_cone((0, 0, 0.55), (0, 0, 1.02), 0.6, 0.16), k=0.1)
    collar = sdf.cylinder((0, 0, 1.06), 0.2, 0.08, rounding=0.04)
    spout = chain(curve_points((0.05, 0, 1.08), (1.0, 0, 1.55), (0, 0, -0.1), 5), [0.13, 0.1, 0.085, 0.075, 0.07], k=0.03)
    handle = sdf.torus((-0.55, 0, 0.62), 0.32, 0.085, rot=(90, 0, 0))
    handle = sdf.smooth_subtract(handle, half_space((-0.55, 0, 0.62), (1, 0, 0)), k=0.02)
    drip = U(sdf.sphere((1.06, 0, 1.44), 0.08), sdf.ellipsoid((1.05, 0, 1.3), (0.06, 0.06, 0.1)), k=0.05)

    def col(co, n):
        return metal(H(0xD8392F))(co, n)

    return [
        Piece(col, body, voxel=0.02),
        Piece(metal(H(0xD9A64A)), U(spout, handle, collar, k=0.03), voxel=0.016, tris=260),
        Piece(H(0x1C1A22), drip, voxel=0.012, tris=50, hi=0.6),
    ]

def crack_lines(center, rays, rng_seed=1):
    rng = random.Random(rng_seed)
    segs = []
    for i in range(rays):
        a = 2 * math.pi * i / rays + rng.uniform(-0.3, 0.3)
        p = Vector(center)
        for j in range(3):
            a += rng.uniform(-0.5, 0.5)
            q = p + Vector((math.cos(a), 0, math.sin(a))) * rng.uniform(0.12, 0.2)
            segs.append((p.copy(), q))
            p = q
    return segs


def seg_dist_xz(co, segs):
    best = 9.0
    for a, b in segs:
        ab = b - a
        t = max(0.0, min(1.0, ((co.x - a.x) * ab.x + (co.z - a.z) * ab.z) / (ab.x * ab.x + ab.z * ab.z)))
        best = min(best, math.hypot(co.x - a.x - ab.x * t, co.z - a.z - ab.z * t))
    return best


@item
def BrokenTV():
    cab = sdf.round_box((0, 0, 0.78), (0.95, 0.68, 0.72), 0.22)
    cab = sdf.smooth_subtract(cab, sdf.round_box((-0.2, -0.72, 0.8), (0.62, 0.12, 0.52), 0.14), k=0.04)
    screen = sdf.round_box((-0.2, -0.56, 0.8), (0.6, 0.1, 0.5), 0.16)
    screen = U(screen, sdf.ellipsoid((-0.2, -0.6, 0.8), (0.5, 0.1, 0.42)), k=0.05)
    knobs = U(sdf.cylinder((0.66, -0.7, 1.05), 0.1, 0.06, rot=(90, 0, 0), rounding=0.03),
              sdf.cylinder((0.66, -0.7, 0.72), 0.1, 0.06, rot=(90, 0, 0), rounding=0.03), k=0.0)
    ants = U(chain([(0.0, 0.1, 1.45), (-0.3, 0.2, 1.95), (-0.55, 0.28, 2.3)], 0.035, k=0.02), sdf.sphere((-0.55, 0.28, 2.3), 0.07),
             chain([(0.1, 0.1, 1.45), (0.4, 0.2, 1.85), (0.75, 0.25, 1.95)], 0.035, k=0.02), sdf.sphere((0.75, 0.25, 1.95), 0.07),
             sdf.ellipsoid((0.05, 0.1, 1.48), (0.2, 0.16, 0.08)), k=0.03)
    feet = sdf.mirror_x(sdf.cylinder((0.65, 0.0, 0.05), 0.12, 0.06, rounding=0.03))
    cc = Vector((-0.05, -0.7, 0.9))
    segs = crack_lines(cc, 6, 4)

    def scr(co, n):
        c = mixc(H(0x32424F), H(0x5A7384), ss(0.5, 0.0, math.hypot(co.x + 0.2, co.z - 0.8)) * 0.6)
        c = mixc(c, H(0x223038), ss(0.2, 0.1, math.hypot(co.x - cc.x, co.z - cc.z)) * 0.6)
        return mixc(c, H(0xE8F4FF), ss(0.03, 0.012, seg_dist_xz(co, segs)))

    return [
        Piece(lambda co, n: mixc(H(0xD9853B), H(0xB5652A), ss(0.3, -0.3, n.z)), cab, voxel=0.028),
        Piece(scr, screen, voxel=0.014, tris=260, lit=True, hi=0.1),
        Piece(metal(H(0x3A3A40)), U(knobs, feet, k=0.0), voxel=0.014, tris=90),
        Piece(metal(H(0xB8BEC4)), ants, voxel=0.013, tris=120),
    ]


@item
def Spring():
    coil = helix(0.4, 0.28, 0.09, 0.0, 1.45)
    return [Piece(metal(H(0xB6BDC4), H(0xA0582C), 0.25, 4), coil, voxel=0.018)]


@item
def Bolt():
    head = extrude2d(hex2d(0.3), (-0.4, -0.4, 0.4, 0.4), 0.12, rounding=0.05, center=(-0.62, 0, 0.3), rot=(0, 90, 0))
    shank = sdf.cylinder((0.12, 0, 0.3), 0.17, 0.68, rot=(0, 90, 0), rounding=0.05)

    def threads(P):
        return shank[0](P) + 0.035 * (0.5 + 0.5 * np.sin(P[:, 0] * 2 * math.pi / 0.1))

    shank_t = (lambda P: np.where(P[:, 0] > -0.2, threads(P), shank[0](P)), shank[1])
    nut = extrude2d(hex2d(0.27), (-0.4, -0.4, 0.4, 0.4), 0.1, rounding=0.04, center=(0.3, 0, 0.3), rot=(0, 90, 30))
    nut = sdf.smooth_subtract(nut, sdf.cylinder((0.3, 0, 0.3), 0.15, 0.3, rot=(0, 90, 0)), k=0.01)
    return [
        Piece(metal(H(0xA6ADB5)), U(head, shank_t, k=0.04), voxel=0.014),
        Piece(metal(H(0x8F8A7E), H(0xB0602E), 0.6, 9), nut, voxel=0.014, tris=160),
    ]


@item
def Wire():
    loops = U(sdf.torus((0, 0, 0.1), 0.55, 0.085, rot=(4, 3, 0)), sdf.torus((0.06, 0.04, 0.26), 0.52, 0.085, rot=(-6, 5, 0)),
              sdf.torus((-0.04, 0.02, 0.42), 0.5, 0.085, rot=(8, -6, 0)), k=0.02)
    tail = chain(curve_points((0.5, -0.1, 0.44), (1.05, -0.75, 0.1), (0.25, 0.1, 0.1), 5), 0.085, k=0.03)
    plug = sdf.round_box((1.12, -0.85, 0.14), (0.15, 0.15, 0.13), 0.05, rot=(0, 0, -50))
    prongs = U(sdf.round_box((1.3, -1.02, 0.18), (0.03, 0.13, 0.03), 0.015, rot=(0, 0, -50)),
               sdf.round_box((1.22, -1.1, 0.1), (0.03, 0.13, 0.03), 0.015, rot=(0, 0, -50)), k=0.0)
    return [
        Piece(lambda co, n: mixc(H(0xD8343A), H(0xFF6A5E), ss(0.4, 0.9, n.z) * 0.4), U(loops, tail, k=0.03), voxel=0.018),
        Piece(H(0x34363C), plug, voxel=0.014, tris=80),
        Piece(metal(H(0xE0A24A)), prongs, voxel=0.01, tris=60),
    ]


@item
def Tire():
    ax = (90, 0, 0)
    c = (0, 0, 1.22)
    shell = sdf.cylinder(c, 1.22, 0.45, rot=ax, rounding=0.3)
    shell = sdf.smooth_subtract(shell, sdf.cylinder(c, 0.62, 0.8, rot=ax), k=0.08)
    R = _euler(ax)
    cc = np.asarray(c, dtype=F32)
    step = 2 * math.pi / 22

    def grooves(P):
        Q = (P - cc) @ R
        a = np.arctan2(Q[:, 1], Q[:, 0])
        k = np.round(a / step) * step
        cs, sn = np.cos(-k), np.sin(-k)
        lx, ly = Q[:, 0] * cs - Q[:, 1] * sn, Q[:, 0] * sn + Q[:, 1] * cs
        return np.sqrt(np.maximum(np.abs(lx - 1.25) - 0.16, 0) ** 2 + np.maximum(np.abs(ly) - 0.045, 0) ** 2 +
                       np.maximum(np.abs(Q[:, 2]) - 0.6, 0) ** 2)

    tire = sdf.smooth_subtract(shell, (grooves, shell[1]), k=0.02)
    hub = sdf.cylinder(c, 0.66, 0.3, rot=ax, rounding=0.1)
    hub = sdf.smooth_subtract(hub, sdf.cylinder((0, -0.34, 1.22), 0.42, 0.08, rot=ax), k=0.05)
    cap = sdf.cylinder((0, -0.25, 1.22), 0.16, 0.06, rot=ax, rounding=0.04)

    def rubber(co, n):
        rr = math.hypot(co.x, co.z - 1.22)
        c_ = mixc(H(0x2B2B2E), H(0x4A4A50), ss(0.3, 0.9, n.z) * 0.5)
        return mixc(c_, H(0xD8D8D0), ss(0.05, 0.02, abs(rr - 0.84)) * ss(0.6, 0.9, abs(n.y)))

    return [
        Piece(rubber, tire, voxel=0.028),
        Piece(metal(H(0xB8C0C8)), U(hub, cap, k=0.02), voxel=0.02, tris=200),
    ]


@item
def SodaCan():
    can = sdf.cylinder((0, 0, 0.68), 0.46, 0.68, rounding=0.1)
    can = sdf.smooth_subtract(can, sdf.cylinder((0, 0, 1.38), 0.36, 0.06), k=0.05)
    can = sdf.smooth_subtract(can, sdf.sphere((-0.52, -0.2, 0.5), 0.14), k=0.1)
    rim = sdf.torus((0, 0, 1.33), 0.4, 0.04)
    tab = extrude2d(lambda x, y: np.maximum(box2d(0.11, 0.16)(x, y) - 0.03, -(box2d(0.05, 0.06)(x, y - 0.04))),
                    (-0.2, -0.2, 0.2, 0.2), 0.02, 0.012, center=(0, -0.05, 1.34), rot=(8, 0, 0))
    def wave_band(P, w=0.075):
        a = np.arctan2(P[:, 1], P[:, 0])
        return np.abs(P[:, 2] - 0.7 - 0.16 * np.sin(a * 2 + 0.5)) - w

    red = H(0xD8322F)
    return [
        Piece(metal(H(0xC4CAD0)), zslice(can, 1.2, 2.0), voxel=0.016, tris=150),
        Piece(red, zslice(can, 0.13, 1.2), voxel=0.018, tris=180),
        Piece(metal(H(0xC4CAD0)), zslice(can, -1.0, 0.13), voxel=0.016, tris=90),
        Piece(H(0xFFFFFF), (lambda P: np.maximum(np.maximum(can[0](P) - 0.015, wave_band(P)), -can[0](P) - 0.05), can[1]),
              voxel=0.012, tris=200, hi=0.1),
        Piece(metal(H(0xC4CAD0)), U(rim, tab, k=0.01), voxel=0.012, tris=140),
    ]

@item
def Lightbulb():
    glass = U(sdf.sphere((0, 0, 1.02), 0.56), sdf.round_cone((0, 0, 0.42), (0, 0, 0.82), 0.24, 0.42), k=0.12)

    def screw(P):
        d = sdf.cylinder((0, 0, 0.26), 0.27, 0.22, rounding=0.03)[0](P)
        return d + 0.03 * (0.5 + 0.5 * np.sin(P[:, 2] * 2 * math.pi / 0.1))

    base = (screw, (np.array([-0.3, -0.3, 0.0], dtype=F32), np.array([0.3, 0.3, 0.5], dtype=F32)))
    tipc = sdf.round_cone((0, 0, 0.0), (0, 0, 0.08), 0.1, 0.16)

    def glass_col(co, n):
        c = mixc(H(0xFFE98A), H(0xFFFBEA), ss(0.6, 1.5, co.z))
        return mixc(c, H(0xFFFFFF), ss(0.2, 0.08, math.hypot(co.x + 0.22, co.z - 1.28)))

    return [
        Piece(glass_col, glass, voxel=0.018, hi=0.3, lo=0.15),
        Piece(metal(H(0xB0B6BC)), base, voxel=0.012, tris=200),
        Piece(H(0x3A3A40), tipc, voxel=0.012, tris=40),
    ]

@item
def CircuitBoard():
    board = sdf.round_box((0, 0, 0.07), (1.0, 0.72, 0.07), 0.04)

    def board_col(co, n):
        c = H(0x1E7A48)
        tx = ss(0.02, 0.008, abs(((co.x * 5.0) % 1.0) - 0.5) * 0.2) * (1 if abs(co.y) < 0.62 else 0)
        ty = ss(0.02, 0.008, abs(((co.y * 4.0 + 0.3) % 1.0) - 0.5) * 0.25)
        trace = max(tx * (1 if wave(co, 3, 1) > 0 else 0), ty * (1 if wave(co, 3, 5) > 0.1 else 0))
        c = mixc(c, H(0xD8B04A), trace * ss(0.5, 0.9, n.z))
        for hx, hy in ((0.86, 0.58), (-0.86, 0.58), (0.86, -0.58), (-0.86, -0.58)):
            c = mixc(c, H(0xE8C25A), ss(0.07, 0.05, math.hypot(co.x - hx, co.y - hy)))
        return c

    chips = U(sdf.round_box((-0.35, -0.1, 0.2), (0.3, 0.22, 0.07), 0.03), sdf.round_box((0.4, 0.3, 0.19), (0.2, 0.16, 0.06), 0.03), k=0.0)
    pins = []
    for i in range(5):
        x = -0.59 + i * 0.12
        pins += [sdf.round_box((x, -0.35, 0.16), (0.025, 0.05, 0.03), 0.012), sdf.round_box((x, 0.15, 0.16), (0.025, 0.05, 0.03), 0.012)]
    cap = sdf.cylinder((0.45, -0.35, 0.34), 0.14, 0.2, rounding=0.05)
    led = U(sdf.sphere((0.75, 0.0, 0.26), 0.1), sdf.cylinder((0.75, 0.0, 0.2), 0.1, 0.06), k=0.02)
    res = sdf.capsule((-0.55, 0.45, 0.2), (-0.15, 0.45, 0.2), 0.07)

    def res_col(co, n):
        b = min(abs(co.x + 0.45), abs(co.x + 0.35), abs(co.x + 0.25))
        return mixc(H(0xE0C08A), H(0x8A3A20), ss(0.03, 0.015, b))

    return [
        Piece(board_col, board, voxel=0.018, lo=0.2),
        Piece(lambda co, n: mixc(H(0x2A2A30), H(0x55565E), ss(0.5, 1.0, n.z) * 0.4), chips, voxel=0.014, tris=110),
        Piece(metal(H(0xC0C6CC)), U(*pins, k=0.0), voxel=0.01, tris=150),
        Piece(lambda co, n: H(0xC8CDD2) if co.z > 0.5 else H(0x2E6FD8), cap, voxel=0.014, tris=90),
        Piece(H(0xFF3A3A), led, voxel=0.012, tris=60, hi=0.6),
        Piece(res_col, res, voxel=0.012, tris=60),
    ]


@item
def Clock():
    ax = (90, 0, 0)
    body = sdf.cylinder((0, 0, 0.82), 0.64, 0.3, rot=ax, rounding=0.16)
    face = sdf.cylinder((0, -0.28, 0.82), 0.5, 0.05, rot=ax, rounding=0.03)
    bells = sdf.mirror_x(sdf.smooth_subtract(sdf.sphere((0.42, 0.02, 1.45), 0.26), sdf.sphere((0.5, 0.02, 1.33), 0.22), k=0.03))
    ham = U(sdf.capsule((0, 0.05, 1.3), (0, 0.05, 1.62), 0.045), sdf.sphere((0, 0.05, 1.66), 0.08), k=0.02)
    feet = sdf.mirror_x(sdf.capsule((0.3, 0, 0.2), (0.44, 0, 0.04), 0.08))
    hands = U(sdf.capsule((0, -0.35, 0.82), (0, -0.35, 1.14), 0.045), sdf.capsule((0, -0.35, 0.82), (0.22, -0.35, 0.82), 0.045),
              sdf.sphere((0, -0.35, 0.82), 0.07), k=0.02)
    ticks = [(Vector((0.4 * math.sin(a), -0.33, 0.82 + 0.4 * math.cos(a))), Vector((0, -1, 0)), 0.045, 0.02)
             for a in (math.radians(90 * i) for i in range(4))]
    return [
        Piece(lambda co, n: mixc(H(0xE8413A), H(0xFF7A6A), ss(0.3, 0.9, n.z) * 0.4), body, voxel=0.02),
        Piece(H(0xFFF6E0), face, voxel=0.016, tris=110, hi=0.1),
        Piece(metal(H(0xE8B530)), U(bells, ham, k=0.02), voxel=0.014, tris=200),
        Piece(H(0x2A2A30), hands, voxel=0.013, tris=70),
        Piece(H(0x2A2A30), feet, voxel=0.014, tris=60),
        Piece(H(0x2A2A30), obj=dots_mesh(ticks, sides=6), lit=False),
    ]

@item
def Toaster():
    body = sdf.round_box((0, 0, 0.58), (0.78, 0.5, 0.56), 0.24)
    slots = U(sdf.round_box((0, -0.16, 1.12), (0.5, 0.06, 0.2), 0.04), sdf.round_box((0, 0.16, 1.12), (0.5, 0.06, 0.2), 0.04), k=0.0)
    body = sdf.smooth_subtract(body, slots, k=0.03)

    def chrome(co, n):
        h = n.z + 0.15 * wave(co, 3, 2)
        c = mixc(H(0x6E7780), H(0xE8EEF4), ss(-0.05, 0.08, h))
        c = mixc(c, H(0xFFFFFF), ss(0.55, 0.7, h) * 0.6)
        return mixc(c, H(0xE84B4B), ss(0.05, 0.03, abs(co.z - 0.42)) * ss(0.3, 0.1, abs(n.z)))

    toast = []
    for y, zt in ((-0.16, 1.38), (0.16, 1.28)):
        toast.append(U(sdf.round_box((0, y, zt - 0.25), (0.4, 0.045, 0.3), 0.04),
                       sdf.ellipsoid((-0.2, y, zt + 0.02), (0.22, 0.045, 0.14)), sdf.ellipsoid((0.2, y, zt + 0.02), (0.22, 0.045, 0.14)), k=0.06))

    def toast_col(co, n):
        edge = ss(0.2, 0.9, abs(n.x) + abs(n.z) * 0.8)
        return mixc(H(0xF2C27A), H(0xA8622A), edge)

    lever = U(sdf.round_box((0.84, 0, 0.72), (0.08, 0.1, 0.05), 0.03), sdf.cylinder((0.0, -0.52, 0.3), 0.08, 0.04, rot=(90, 0, 0), rounding=0.02), k=0.0)
    feet = sdf.mirror_x(U(sdf.cylinder((0.5, -0.3, 0.03), 0.08, 0.04, rounding=0.02), sdf.cylinder((0.5, 0.3, 0.03), 0.08, 0.04, rounding=0.02), k=0))
    return [
        Piece(chrome, body, voxel=0.022, lit=False),
        Piece(toast_col, U(*toast, k=0.0), voxel=0.013, tris=260),
        Piece(H(0x2A2A30), U(lever, feet, k=0.0), voxel=0.012, tris=90),
    ]


@item
def TrafficCone():
    cone = sdf.round_cone((0, 0, 0.12), (0, 0, 2.02), 0.6, 0.1)
    base = sdf.round_box((0, 0, 0.08), (0.82, 0.82, 0.08), 0.06)
    orange, white = H(0xFF6A1F), H(0xFAFAF5)
    return [
        Piece(orange, zslice(cone, 0.1, 0.72), voxel=0.02, tris=170),
        Piece(white, zslice(cone, 0.72, 0.98), voxel=0.02, tris=110),
        Piece(orange, zslice(cone, 0.98, 1.34), voxel=0.02, tris=130),
        Piece(white, zslice(cone, 1.34, 1.56), voxel=0.02, tris=90),
        Piece(orange, zslice(cone, 1.56, 2.2), voxel=0.02, tris=110),
        Piece(H(0xE0561A), base, voxel=0.02),
    ]


@item
def Fan():
    base = sdf.ellipsoid((0, 0.1, 0.1), (0.6, 0.5, 0.12))
    neck = chain([(0, 0.15, 0.1), (0, 0.18, 0.7), (0, 0.2, 1.05)], [0.09, 0.08, 0.08], k=0.05)
    motor = sdf.ellipsoid((0, 0.28, 1.3), (0.26, 0.34, 0.26))
    c = (0, -0.14, 1.3)
    ring = U(sdf.torus(c, 0.74, 0.055, rot=(90, 0, 0)), sdf.torus((0, 0.02, 1.3), 0.7, 0.045, rot=(90, 0, 0)), k=0.02)
    spokes = []
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        spokes.append(sdf.capsule((0.14 * math.cos(a), -0.2, 1.3 + 0.14 * math.sin(a)),
                                  (0.72 * math.cos(a), -0.14, 1.3 + 0.72 * math.sin(a)), 0.022))
    badge = sdf.cylinder((0, -0.22, 1.3), 0.15, 0.04, rot=(90, 0, 0), rounding=0.03)
    blades = []
    for i in range(3):
        a = i * 120
        ar = math.radians(a)
        blades.append(sdf.ellipsoid((0.36 * math.cos(ar), -0.08, 1.3 + 0.36 * math.sin(ar)), (0.3, 0.03, 0.17), rot=(0, -a, 0)))
    blades = xform(U(*blades, k=0.05), rot=(0, 0, 0))
    mint = H(0x7FD1BE)
    return [
        Piece(lambda co, n: mixc(mint, lighter(mint, 0.3), ss(0.3, 0.9, n.z) * 0.5), U(base, neck, motor, badge, k=0.05), voxel=0.02),
        Piece(metal(H(0xC8CED4)), U(ring, *spokes, k=0.02), voxel=0.012, weight=1.2),
        Piece(H(0xE6F3FF), blades, voxel=0.013, tris=150, lo=0.2),
    ]


@item
def IceCube():
    cube = sdf.round_box((0, 0, 0.56), (0.56, 0.56, 0.56), 0.15, rot=(0, 0, 18))
    puddle = U(sdf.ellipsoid((0.1, -0.05, 0.02), (0.95, 0.8, 0.035)), sdf.ellipsoid((0.7, -0.5, 0.02), (0.25, 0.2, 0.03)), k=0.15)

    def col(co, n):
        edge = 1.0 - max(abs(n.x), abs(n.y), abs(n.z))
        c = mixc(H(0x9ED8F5), H(0xD6F2FF), ss(0.2, 1.0, co.z) * 0.7)
        c = mixc(c, H(0xFFFFFF), ss(0.08, 0.3, edge))
        streak = ss(0.05, 0.02, abs(co.x * 0.7 + co.z * 0.7 - 0.75))
        return mixc(c, H(0xFFFFFF), streak * 0.8)

    return [
        Piece(col, cube, voxel=0.02, hi=0.4, lo=0.2),
        Piece(lambda co, n: H(0xB8E4F8), puddle, voxel=0.014, tris=110, hi=0.4),
    ]


@item
def Bone():
    shaft = sdf.capsule((-0.62, 0, 0.26), (0.62, 0, 0.26), 0.2)
    knobs = [sdf.sphere((sx * 0.78, sy * 0.19, 0.27), 0.25) for sx in (-1, 1) for sy in (-1, 1)]
    bone = U(shaft, *knobs, k=0.14)
    bone = sdf.smooth_subtract(bone, half_space((0, 0, 0.03), (0, 0, -1)), k=0.05)
    return [Piece(lambda co, n: mixc(H(0xEFE4CA), H(0xFFF8E8), ss(0.2, 0.5, co.z) * 0.6), bone, voxel=0.018,
                  post=M(rot=(0, 0, 25)), hi=0.3)]


@item
def CrystalShard():
    specs = [((0, 0, 0.05), (0.12, -0.05, 1), 0.34, 1.95, 6, 0.28, 0),
             ((0.32, 0.1, 0.05), (0.7, 0.2, 1), 0.2, 1.1, 6, 0.32, 15),
             ((-0.3, 0.12, 0.05), (-0.65, 0.1, 1), 0.17, 0.85, 6, 0.35, 5),
             ((0.05, -0.32, 0.02), (0.1, -0.8, 1), 0.13, 0.6, 5, 0.38, 20)]
    crys = crystal_mesh(specs)
    rock = sdf.noise_bumps(U(sdf.ellipsoid((0, 0, 0.12), (0.6, 0.5, 0.2)), sdf.ellipsoid((0.3, 0.25, 0.1), (0.3, 0.25, 0.16)), k=0.15),
                           amplitude=0.03, frequency=9, seed=3)

    def col(co, n):
        c = mixc(H(0x2FC6E8), H(0x9FF4FF), ss(0.2, 1.6, co.z))
        return mixc(c, H(0xF0FFFF), ss(0.3, 0.85, -n.y * 0.6 - n.x * 0.4))

    return [
        Piece(col, obj=crys, flat=True, face=True, glow=True),
        Piece(lambda co, n: mixc(H(0x4A5566), H(0x6C7888), ss(0.3, 0.9, n.z)), rock, voxel=0.02, tris=500),
    ]


@item
def Fish():
    body = U(sdf.ellipsoid((0, 0, 0.28), (0.72, 0.48, 0.28)), sdf.ellipsoid((-0.3, 0, 0.28), (0.44, 0.42, 0.27)), k=0.2)
    tail = U(sdf.ellipsoid((0.98, 0.22, 0.24), (0.34, 0.2, 0.07), rot=(0, 0, 38)),
             sdf.ellipsoid((0.98, -0.22, 0.24), (0.34, 0.2, 0.07), rot=(0, 0, -38)), sdf.ellipsoid((0.72, 0, 0.26), (0.16, 0.12, 0.08)), k=0.08)
    fins = U(sdf.ellipsoid((0.05, 0.5, 0.26), (0.38, 0.2, 0.06), rot=(0, 0, -12)),
             sdf.ellipsoid((0.15, -0.46, 0.26), (0.2, 0.13, 0.06), rot=(0, 0, 15)),
             sdf.ellipsoid((-0.05, -0.12, 0.56), (0.2, 0.1, 0.05), rot=(0, 20, 30)), k=0.02)

    def body_col(co, n):
        c = mixc(H(0xFFF6E8), H(0x3A95E0), ss(-0.42, -0.15, co.y))
        stripe = ss(0.07, 0.04, abs(co.x - 0.2)) + ss(0.06, 0.03, abs(co.x + 0.12))
        return mixc(c, H(0x1D4E9E), stripe * 0.8 * ss(0.2, 0.5, n.z) * ss(-0.3, -0.1, co.y))

    eye_p, eye_n = surface(body, (-0.44, 0.06, 0.9))
    pupil = (eye_p + eye_n * 0.04 + Vector((-0.03, 0, 0)), eye_n, 0.1, 0.035)
    shine = (eye_p + eye_n * 0.075 + Vector((-0.06, 0.04, 0)), eye_n, 0.035, 0.012)
    mouth = []
    for k in range(3):
        p, nn = surface(body, (-1.0, -0.1 + k * 0.05, 0.42 + (0.03 if k == 1 else 0)))
        mouth.append((p, nn, 0.035, 0.02))
    return [
        Piece(body_col, body, voxel=0.018, hi=0.3),
        Piece(lambda co, n: mixc(H(0xFF8A2A), H(0xFFC46A), ss(0.3, 0.9, abs(co.x) + abs(co.y) * 0.3)), U(tail, fins, k=0.05),
              voxel=0.012, weight=0.9),
        Piece(H(0xFFFFFF), obj=dots_mesh([(eye_p, eye_n, 0.17, 0.06)], sides=10), lo=0.1),
        Piece(H(0x14141A), obj=dots_mesh([pupil], sides=8), lit=False),
        Piece(H(0xFFFFFF), obj=dots_mesh([shine], sides=5), lit=False),
        Piece(H(0x7A2A3A), obj=dots_mesh(mouth, sides=5), lit=False),
    ]

@item
def Coal():
    rng = random.Random(11)

    def lump(c, r, n):
        pts = []
        for _ in range(n):
            v = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
            pts.append(Vector(c) + Vector((v.x * r[0], v.y * r[1], v.z * r[2])) * rng.uniform(0.82, 1.04))
        return hull_mesh(pts)

    obj = fk.join([lump((0, 0, 0.45), (0.6, 0.5, 0.45), 70), lump((0.66, -0.42, 0.2), (0.28, 0.25, 0.2), 30),
                   lump((-0.5, -0.45, 0.14), (0.18, 0.16, 0.14), 18)], _name("coal"))

    def col(co, n):
        r = random.Random(int((co.x * 97 + co.y * 57 + co.z * 31) * 1000)).random()
        c = mixc(H(0x1B1B20), H(0x30323A), r)
        return mixc(c, H(0x6A7488), ss(0.6, 0.95, n.z) * r)

    return [Piece(col, obj=obj, flat=True, face=True, hi=0.1, lo=0.2)]

def crack_slabs(center, radius, specs, width):
    out = []
    for yaw, pitch, off in specs:
        out.append(sdf.round_box(T(Vector(center) + Vector(off)), (radius * 1.2, radius * 0.5, width), width * 0.6, rot=(pitch, 0, yaw)))
    return sdf.union(*out)


@item
def LavaFruit():
    c = (0, 0, 0.7)
    shell = U(sdf.ellipsoid(c, (0.7, 0.7, 0.64)), sdf.ellipsoid((0, 0, 1.2), (0.26, 0.26, 0.2)), k=0.2)
    cracks = crack_slabs(c, 0.7, ((10, 70, (0.1, 0, 0.05)), (80, 60, (0, 0.15, -0.1)), (135, 80, (-0.1, -0.2, 0.0)),
                                  (40, 20, (0, 0, 0.2)), (-30, 110, (0.2, -0.1, -0.2)), (100, 150, (0, 0, 0.3))), 0.045)
    shell = sdf.smooth_subtract(shell, xform(cracks, loc=(0, 0, 0)), k=0.03)
    core = U(sdf.ellipsoid(c, (0.64, 0.64, 0.58)), sdf.sphere((0, 0, 1.2), 0.2), k=0.2)
    crown = []
    for i in range(5):
        a = math.radians(i * 72)
        crown.append(sdf.round_cone((0.14 * math.cos(a), 0.14 * math.sin(a), 1.32), (0.28 * math.cos(a), 0.28 * math.sin(a), 1.55), 0.07, 0.025))
    shell = U(shell, *crown, k=0.05)
    return [
        Piece(lambda co, n: mixc(H(0x2A161C), H(0x4A2430), ss(0.2, 0.9, n.z) * 0.5), shell, voxel=0.016, hi=0.35),
        Piece(lambda co, n: mixc(H(0xFF6A10), H(0xFFD24A), ss(0.5, 1.0, co.z / 1.4)), core, voxel=0.024, glow=True, weight=0.6),
    ]


@item
def StarFragment():
    star = extrude2d(star2d(0.85, 0.52), (-0.9, -0.9, 0.9, 0.9), 0.24, rounding=0.2)
    star = U(star, sdf.ellipsoid((0, 0.02, 0), (0.42, 0.42, 0.3)), k=0.25)

    def col(co, n):
        r = math.hypot(co.x, co.y)
        return mixc(H(0xFFF7C8), mixc(H(0xFFE040), H(0xFFB21E), ss(0.6, 0.9, r)), ss(0.1, 0.55, r))

    return [Piece(col, star, voxel=0.02, post=M((0, 0, 0.8), (78, 0, 0)), glow=True, hi=0.2)]


@item
def MoonMushroom():
    stem = chain(curve_points((0, 0, 0.05), (0.05, 0, 0.75), (-0.08, 0, 0), 4), [0.2, 0.15, 0.13, 0.14], k=0.05)
    stem = U(stem, sdf.ellipsoid((0, 0, 0.08), (0.24, 0.24, 0.1)), k=0.1)
    capc = sdf.ellipsoid((0.05, 0, 0.9), (0.62, 0.62, 0.5))
    cap = sdf.smooth_subtract(capc, sdf.ellipsoid((0.05, 0, 0.64), (0.58, 0.58, 0.34)), k=0.08)
    spots = []
    for a, zz, r in ((-60, 1.1, 0.1), (20, 1.2, 0.09), (100, 1.05, 0.08), (200, 1.15, 0.09), (290, 1.0, 0.08),
                     (-110, 1.28, 0.07), (150, 1.32, 0.065), (250, 1.3, 0.06), (60, 1.32, 0.06)):
        ar = math.radians(a)
        p, nn = surface(capc, (0.05 + math.cos(ar), math.sin(ar), zz))
        spots.append((p, nn, r, 0.035))

    def cap_col(co, n):
        if n.z < -0.3:
            return mixc(H(0x6FD8FF), H(0xBFF2FF), 0.5 + 0.5 * math.sin(math.atan2(co.y, co.x - 0.05) * 36))
        return mixc(H(0x7FA8F0), H(0xB8D4FF), ss(0.9, 1.4, co.z))

    return [
        Piece(lambda co, n: mixc(H(0xCFD8FF), H(0xEDF0FF), ss(0.1, 0.7, co.z)), stem, voxel=0.018, tris=180, glow=True),
        Piece(cap_col, cap, voxel=0.02, glow=True, hi=0.15),
        Piece(H(0xC8FFFF), obj=dots_mesh(spots, sides=7), glow=True, lit=False),
    ]

@item
def Meteorite():
    c = (0, 0, 0.72)
    rock = U(sdf.ellipsoid(c, (0.9, 0.78, 0.7)), sdf.ellipsoid((0.35, -0.2, 0.95), (0.45, 0.4, 0.38)), k=0.25)
    rock = sdf.noise_bumps(rock, amplitude=0.05, frequency=6.0, seed=8)
    craters = U(*[sdf.sphere(T(surface(rock, T(Vector(c) + Vector(d) * 2))[0] + Vector(d).normalized() * r * 0.55), r)
                  for d, r in (((-0.6, -0.8, 0.5), 0.2), ((0.9, -0.2, 0.6), 0.16), ((-0.2, 0.2, 1.0), 0.14), ((0.5, -1.0, -0.1), 0.13))], k=0.0)
    rock = sdf.smooth_subtract(rock, craters, k=0.06)
    veins = crack_slabs(c, 0.95, ((20, 60, (0, 0, 0.1)), (100, 75, (0.1, 0.1, 0)), (160, 120, (-0.1, 0, -0.1)),
                                  (60, 100, (0, -0.2, 0.2)), (-60, 55, (0.2, 0, 0.1))), 0.075)
    rock = sdf.smooth_subtract(rock, veins, k=0.03)
    rock = sdf.smooth_subtract(rock, half_space((0, 0, 0.1), (0, 0, -1)), k=0.1)
    core = sdf.ellipsoid(c, (0.84, 0.72, 0.64))
    return [
        Piece(lambda co, n: mixc(H(0x3A332E), H(0x5A5048), ss(0.3, 0.9, n.z) * 0.6 + 0.2 * wave(co, 8, 2)), rock, voxel=0.022),
        Piece(lambda co, n: mixc(H(0xA040FF), H(0xE8B8FF), ss(0.6, 1.4, co.z)), core, voxel=0.03, glow=True, weight=0.5),
    ]

@item
def CursedSandwich():
    tri = lambda x, y: np.maximum(box2d(0.72, 0.72)(x, y), (x + y) * 0.7071)
    big = lambda x, y: np.maximum(box2d(0.8, 0.8)(x, y), (x + y) * 0.7071 - 0.06)
    bread_b = extrude2d(tri, (-0.8, -0.8, 0.8, 0.8), 0.12, 0.08, center=(0, 0, 0.12))
    bread_t = extrude2d(tri, (-0.8, -0.8, 0.8, 0.8), 0.14, 0.1, center=(0, 0, 0.66))
    bread_t = U(bread_t, sdf.ellipsoid((-0.25, -0.25, 0.74), (0.4, 0.4, 0.12)), k=0.15)

    def frill(P):
        a = np.arctan2(P[:, 1], P[:, 0])
        return big(P[:, 0], P[:, 1]) - 0.04 * np.sin(P[:, 0] * 22) * np.sin(P[:, 1] * 22)

    lettuce = (lambda P: np.maximum(frill(P) + 0.0, np.abs(P[:, 2] - 0.3 - 0.03 * np.sin(P[:, 0] * 14)) - 0.045),
               (np.array([-0.95, -0.95, 0.2], dtype=F32), np.array([0.95, 0.95, 0.4], dtype=F32)))
    ham = extrude2d(tri, (-0.8, -0.8, 0.8, 0.8), 0.05, 0.04, center=(0.02, 0.02, 0.4))
    cheese = extrude2d(lambda x, y: np.maximum(box2d(0.66, 0.66)(x, y), (x - y) * 0.7071 - 0.3), (-0.8, -0.8, 0.8, 0.8), 0.035, 0.02,
                       center=(-0.05, -0.08, 0.49))
    cheese = U(cheese, sdf.round_cone((-0.62, -0.72, 0.48), (-0.66, -0.78, 0.3), 0.06, 0.04), k=0.06)
    wisps = U(chain(curve_points((-0.2, -0.1, 0.95), (-0.35, 0.05, 1.45), (0.2, 0, 0.1), 5), [0.07, 0.06, 0.055, 0.045, 0.035], k=0.03),
              chain(curve_points((0.1, -0.35, 0.95), (0.25, -0.5, 1.3), (-0.15, 0, 0.1), 4), [0.06, 0.05, 0.04, 0.03], k=0.03), k=0.02)
    mold = [(p, nn, r, 0.02) for p, nn, r in (
        (surface(bread_t, (-0.3, -0.35, 1.2))[0], Vector((0, 0, 1)), 0.1), (surface(bread_t, (0.2, -0.45, 1.2))[0], Vector((0, 0, 1)), 0.07),
        (surface(bread_t, (-0.5, 0.15, 1.2))[0], Vector((0, 0, 1)), 0.08))]

    def bread_col(co, n):
        crust = ss(0.4, 0.8, abs(n.x) + abs(n.y))
        return mixc(mixc(H(0xDCD9A0), H(0xC9D98C), 0.5 + 0.5 * wave(co, 6, 3)), H(0x8C7A3A), crust)

    return [
        Piece(bread_col, U(bread_b, k=0.0), voxel=0.018, tris=150),
        Piece(bread_col, bread_t, voxel=0.018),
        Piece(lambda co, n: H(0x7FCC3A), lettuce, voxel=0.014, tris=160, glow=True),
        Piece(H(0xC98A9A), ham, voxel=0.016, tris=90),
        Piece(H(0xD8E04A), cheese, voxel=0.013, tris=90),
        Piece(H(0xB6FF4A), wisps, voxel=0.014, tris=90, glow=True),
        Piece(H(0x8AE83A), obj=dots_mesh(mold, sides=7), glow=True, lit=False),
    ]


@item
def Slime():
    blob = U(sdf.ellipsoid((0, 0, 0.42), (0.72, 0.62, 0.46)), sdf.ellipsoid((0.05, 0.05, 0.85), (0.3, 0.28, 0.22)), k=0.3)
    drips = [sdf.ellipsoid((0.75 * math.cos(a), 0.65 * math.sin(a), 0.07), (0.2, 0.18, 0.08)) for a in
             (math.radians(d) for d in (-70, 20, 110, 200, 290))]
    blob = U(blob, *drips, k=0.2)
    blob = sdf.smooth_subtract(blob, half_space((0, 0, 0.0), (0, 0, -1)), k=0.03)
    eyes, shines = [], []
    for s in (-1, 1):
        p, nn = surface(blob, (s * 0.25, -1.0, 0.72))
        eyes.append((p, nn, 0.12, 0.05))
        shines.append((p + nn * 0.05 + Vector((-0.04, 0, 0.04)), nn, 0.04, 0.015))
    sp, sn = surface(blob, (-0.35, -0.5, 1.2))
    return [
        Piece(lambda co, n: mixc(H(0x46C878), H(0x8DF0B0), ss(0.2, 0.95, co.z)), blob, voxel=0.02, hi=0.45),
        Piece(H(0x13201A), obj=dots_mesh(eyes, sides=8), lit=False),
        Piece(H(0xFFFFFF), obj=dots_mesh(shines, sides=6), lit=False, glow=True),
    ]

def clam_half(rx, ry, depth, thick, ribs=14):
    """Scalloped bowl, rim at z=0 opening +Z, hinge at +Y."""
    outer = sdf.ellipsoid((0, 0, 0), (rx, ry, depth))

    def fn(P):
        a = np.arctan2(P[:, 0], P[:, 1] - ry * 0.9)
        d = outer[0](P) - 0.025 * np.cos(a * ribs)
        inner = sdf.ellipsoid((0, 0, thick * 1.2), (rx - thick, ry - thick, depth))[0](P)
        return np.maximum(np.maximum(d, -inner), P[:, 2])

    return (fn, (np.array([-rx - 0.05, -ry - 0.05, -depth - 0.05], dtype=F32), np.array([rx + 0.05, ry + 0.05, 0.05], dtype=F32)))


@item
def Pearl():
    rx, ry, depth, thick = 0.78, 0.66, 0.34, 0.08
    half = clam_half(rx, ry, depth, thick)
    outer_fn = sdf.ellipsoid((0, 0, 0), (rx, ry, depth))[0]
    inner_fn = sdf.ellipsoid((0, 0, thick * 1.2), (rx - thick, ry - thick, depth))[0]
    hinge = Vector((0, 0.62, 0.34))
    bottom = M((0, 0, 0.34))
    top = M(hinge) @ M(rot=(-62, 0, 0)) @ M(-hinge) @ M((0, 0, 0.36)) @ M(rot=(180, 0, 0))

    def shell_col(co, n):
        P = np.array([T(co)], dtype=F32)
        if abs(float(inner_fn(P)[0])) < abs(float(outer_fn(P)[0])) and co.z < -0.02:
            return mixc(H(0xFFF0F6), H(0xE9D4F2), ss(0.15, 0.6, math.hypot(co.x, co.y)))
        rib = 0.5 + 0.5 * math.cos(math.atan2(co.x, co.y - 0.6) * 14)
        return mixc(H(0xDE8DB8), H(0xF7C6DC), rib * 0.6)

    pearl = sdf.sphere((0, -0.08, 0.46), 0.26)
    return [
        Piece(shell_col, half, voxel=0.016, post=bottom),
        Piece(shell_col, half, voxel=0.016, post=top),
        Piece(lambda co, n: mixc(H(0xF3ECF6), H(0xFFFFFF), ss(0.2, 0.9, n.z - n.y * 0.3)), pearl, voxel=0.014, tris=160, hi=0.6),
    ]

@item
def Coral():
    rng = random.Random(21)
    segs = []

    def branch(p, d, length, r, depth):
        end = p + d * length
        segs.append(sdf.round_cone(T(p), T(end), r, r * 0.78))
        if depth == 0:
            segs.append(sdf.sphere(T(end), r * 0.95))
            return
        for sgn in (-1, 1):
            axis = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)).normalized()
            from mathutils import Quaternion
            q = Quaternion(axis, math.radians(sgn * rng.uniform(24, 38)))
            nd = (q @ d).normalized()
            nd.z = max(nd.z, 0.35)
            branch(end, nd.normalized(), length * rng.uniform(0.7, 0.85), r * 0.78, depth - 1)

    branch(Vector((0, 0, 0)), Vector((0, 0, 1)), 0.55, 0.19, 3)
    branch(Vector((0.1, 0.05, 0)), Vector((0.6, -0.2, 0.8)).normalized(), 0.4, 0.15, 2)
    coral = U(*segs, sdf.ellipsoid((0, 0, 0.05), (0.35, 0.3, 0.1)), k=0.07)
    return [Piece(lambda co, n: mixc(H(0xF0607F), H(0xFFB4C6), ss(0.4, 1.7, co.z)), coral, voxel=0.02, hi=0.3)]


@item
def Jellyfish():
    dz = 1.3
    dome = sdf.ellipsoid((0, 0, dz), (0.72, 0.72, 0.58))

    def frill_cut(P):
        a = np.arctan2(P[:, 1], P[:, 0])
        return P[:, 2] - (dz - 0.06 + 0.06 * np.cos(a * 9))

    bell = sdf.smooth_subtract(dome, (frill_cut, dome[1]), k=0.05)
    bell = sdf.smooth_subtract(bell, sdf.ellipsoid((0, 0, dz - 0.2), (0.58, 0.58, 0.38)), k=0.05)
    tent = []
    for i in range(6):
        a = math.radians(i * 60 + 15)
        r0 = 0.48
        pts = []
        for k in range(6):
            t = k / 5
            rr = r0 * (1 - 0.25 * t)
            aa = a + 0.35 * math.sin(t * 5 + i)
            pts.append(Vector((rr * math.cos(aa), rr * math.sin(aa), (dz - 0.05) * (1 - t) + 0.05)))
        tent.append(chain(pts, [0.07, 0.065, 0.06, 0.055, 0.05, 0.05], k=0.03))
    arms = []
    for i in range(3):
        a = math.radians(i * 120)
        pts = [Vector((0.15 * math.cos(a + 0.6 * math.sin(t * 6)), 0.15 * math.sin(a + 0.6 * math.sin(t * 6)), dz - 0.1 - t * 0.85))
               for t in (k / 5 for k in range(6))]
        arms.append(chain(pts, [0.12, 0.13, 0.12, 0.1, 0.09, 0.07], k=0.05))
    spots = []
    for i in range(7):
        a = math.radians(i * 51)
        p, nn = surface(dome, (math.cos(a), math.sin(a), dz + 0.35 + 0.15 * (i % 2)))
        spots.append((p, nn, 0.07, 0.025))

    def bell_col(co, n):
        c = mixc(H(0xB58CF5), H(0xE6D6FF), ss(dz, dz + 0.55, co.z))
        return mixc(c, H(0x8A5AE0), ss(dz + 0.12, dz - 0.05, co.z))

    return [
        Piece(bell_col, bell, voxel=0.02, hi=0.35, lo=0.1),
        Piece(lambda co, n: mixc(H(0xC8A8FF), H(0xE9DDFF), ss(0.1, 1.1, co.z)), U(*tent, k=0.02), voxel=0.016, weight=0.8, lo=0.1),
        Piece(lambda co, n: mixc(H(0xD68CF0), H(0xF4C8FF), ss(0.3, 1.1, co.z)), U(*arms, k=0.03), voxel=0.018, tris=160, lo=0.1),
        Piece(H(0xFFE0F4), obj=dots_mesh(spots, sides=6), lit=False, glow=True),
    ]


@item
def Seashell():
    def col(co, n):
        a = math.atan2(co.x, co.z)
        r = math.hypot(co.x, co.z)
        rib = 0.5 + 0.5 * math.cos(a * 16)
        c = mixc(H(0xF29A6A), H(0xFFE2C4), rib * 0.7)
        band = ss(0.6, 0.9, math.sin(r * 20))
        c = mixc(c, H(0xE0664A), band * 0.35 * ss(0.2, 0.4, r))
        return mixc(c, H(0xFFF3E4), ss(0.35, 0.05, r) * 0.6)

    return [Piece(col, scallop(), voxel=0.014, post=M((0, 0, 0), (-22, 0, 0)), hi=0.3)]

@item
def Kelp():
    blades, floats = [], []
    specs = ((0.0, 0.0, 2.1, 0.0, 0), (0.22, 0.12, 1.6, 0.9, 20), (-0.2, 0.1, 1.8, 2.1, -25), (0.05, -0.2, 1.3, 3.3, 10))
    for x, y, L, ph, lean in specs:
        rb = sdf.round_box((0, 0, L / 2), (0.17, 0.04, L / 2), 0.035)

        def wiggle(P, ph=ph, L=L, x=x, y=y, lean=lean):
            Q = P.copy()
            Q[:, 0] -= x + 0.14 * np.sin(P[:, 2] * 3.2 + ph) * (P[:, 2] / L) + math.sin(math.radians(lean)) * P[:, 2] * 0.35
            Q[:, 1] -= y + 0.08 * np.cos(P[:, 2] * 2.4 + ph)
            w = 1.0 - 0.45 * np.clip(P[:, 2] / L, 0, 1) ** 2
            Q[:, 0] /= w
            return Q

        blades.append(sdf.warp(rb, wiggle, pad=0.45))
        floats.append(sdf.sphere((x + math.sin(math.radians(lean)) * 0.2, y + 0.06, 0.55 + 0.1 * ph % 0.3), 0.085))
    hold = sdf.noise_bumps(U(sdf.ellipsoid((0, 0, 0.1), (0.4, 0.35, 0.14)), sdf.ellipsoid((0.15, -0.1, 0.18), (0.18, 0.16, 0.12)), k=0.1),
                           amplitude=0.02, frequency=12, seed=6)
    return [
        Piece(lambda co, n: mixc(H(0x4E7F24), H(0xB0CC4A), ss(0.2, 2.0, co.z)), U(*blades, k=0.02), voxel=0.013, weight=1.0),
        Piece(H(0xC9A83A), U(*floats, k=0.0), voxel=0.012, tris=90, hi=0.4),
        Piece(H(0x5E5A2A), hold, voxel=0.016, tris=110),
    ]


@item
def Starfish():
    arm_star = extrude2d(star2d(0.92, 0.42), (-1, -1, 1, 1), 0.13, rounding=0.12, center=(0, 0, 0))
    star = U(arm_star, sdf.ellipsoid((0, 0, 0.02), (0.36, 0.36, 0.2)), k=0.2)

    def curl(P):
        Q = P.copy()
        r = np.hypot(P[:, 0], P[:, 1])
        Q[:, 2] -= 0.1 * (r / 0.9) ** 2
        return Q

    star = sdf.warp(star, curl, pad=0.2)
    star = xform(star, loc=(0, 0, 0.16), rot=(0, 0, 18))
    bumps = []
    for i in range(5):
        a = math.radians(90 + 18 + i * 72)
        for k, rr in enumerate((0.25, 0.45, 0.63, 0.78)):
            p, nn = surface(star, (rr * math.cos(a), rr * math.sin(a), 0.8))
            bumps.append((p, nn, 0.055 - k * 0.007, 0.035))
    p, nn = surface(star, (0, 0, 0.9))
    bumps.append((p, nn, 0.06, 0.035))
    return [
        Piece(lambda co, n: mixc(H(0xF26A2E), H(0xFF9C5A), ss(0.1, 0.35, co.z)), star, voxel=0.016, hi=0.3),
        Piece(H(0xFFE2B8), obj=dots_mesh(bumps, sides=5), lo=0.1),
    ]


@item
def Crab():
    body = sdf.ellipsoid((0, 0, 0.45), (0.62, 0.46, 0.32))
    body = sdf.smooth_subtract(body, half_space((0, 0, 0.2), (0, 0, -1)), k=0.08)
    stalks = sdf.mirror_x(U(sdf.round_cone((0.16, -0.25, 0.66), (0.22, -0.34, 0.95), 0.06, 0.045), k=0.02))
    arms = sdf.mirror_x(chain([(0.5, -0.12, 0.45), (0.75, -0.3, 0.5), (0.85, -0.5, 0.62)], [0.09, 0.08, 0.08], k=0.04))
    claw = U(sdf.ellipsoid((0.9, -0.62, 0.72), (0.22, 0.26, 0.2), rot=(0, 0, -20)), k=0.0)
    claw = sdf.smooth_subtract(claw, sdf.ellipsoid((0.96, -0.86, 0.76), (0.14, 0.2, 0.05), rot=(0, 0, -20)), k=0.03)
    claws = sdf.mirror_x(claw)
    legs = []
    for y in (-0.05, 0.15, 0.33):
        legs.append(chain([(0.45, y, 0.3), (0.78, y + 0.12, 0.3), (0.92, y + 0.2, 0.03)], [0.06, 0.05, 0.045], k=0.03))
    legs = sdf.mirror_x(U(*legs, k=0.02))
    whites = sdf.mirror_x(sdf.sphere((0.22, -0.36, 1.0), 0.11))
    pupils = [(Vector((s * 0.23, -0.47, 1.01)), Vector((0, -1, 0.1)), 0.055, 0.025) for s in (-1, 1)]
    smile = []
    for k in range(5):
        x = -0.12 + k * 0.06
        p, nn = surface(body, (x, -1.0, 0.44 - 0.04 * (1 - abs(x) / 0.12)))
        smile.append((p, nn, 0.032, 0.02))
    blush = []
    for s in (-1, 1):
        p, nn = surface(body, (s * 0.3, -1.0, 0.5))
        blush.append((p, nn, 0.07, 0.015))
    red = H(0xE8483A)
    return [
        Piece(lambda co, n: mixc(red, H(0xFF7F5E), ss(0.4, 0.9, n.z) * 0.5), U(body, stalks, k=0.05), voxel=0.018),
        Piece(lambda co, n: mixc(H(0xD83A2E), H(0xFF8A66), ss(0.5, 0.9, co.z)), U(arms, claws, legs, k=0.04), voxel=0.016, weight=0.9),
        Piece(H(0xFFFFFF), whites, voxel=0.012, tris=80, lo=0.1),
        Piece(H(0x15151A), obj=dots_mesh(pupils + smile, sides=6), lit=False),
        Piece(H(0xFF9AA8), obj=dots_mesh(blush, sides=6), lit=False),
    ]


def scallop(R=0.9, spread=0.95, ribs=16):
    def fn(P):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        a = np.arctan2(x, z)
        r = np.hypot(x, z)
        d2 = np.maximum(r - (R + 0.035 * np.cos(a * ribs)), (np.abs(a) - spread) * np.maximum(r, 0.15))
        d2 = np.minimum(d2, box2d(0.3, 0.09)(x, z - 0.09))
        bulge = np.clip(1 - (r / (R * 1.05)) ** 2, 0, 1) * np.clip(r / 0.25, 0, 1)
        th = 0.05 + 0.16 * bulge + 0.025 * np.cos(a * ribs) * np.clip(r / 0.3, 0, 1)
        dy = np.abs(y + th * 0.5) - th * 0.5
        rr = 0.02
        d2 = d2 + rr
        dy = dy + rr
        return np.sqrt(np.maximum(d2, 0) ** 2 + np.maximum(dy, 0) ** 2) + np.minimum(np.maximum(d2, dy), 0) - rr
    return (fn, (np.array([-R - 0.1, -0.3, -0.1], dtype=F32), np.array([R + 0.1, 0.1, R + 0.1], dtype=F32)))


@item
def SunkenCoin():
    face_rot = (90, 0, 0)
    c = (0, 0, 0.72)

    def wobble(P):
        return P

    coin = sdf.cylinder(c, 0.72, 0.11, rot=face_rot, rounding=0.06)
    coin = (lambda P, s=coin: s[0](P) + 0.02 * np.sin(np.arctan2(P[:, 2] - 0.72, P[:, 0]) * 5), coin[1])
    coin = sdf.smooth_subtract(coin, sdf.cylinder((0, -0.13, 0.72), 0.56, 0.035, rot=face_rot), k=0.02)
    coin = sdf.smooth_subtract(coin, sdf.cylinder((0, 0.13, 0.72), 0.56, 0.035, rot=face_rot), k=0.02)
    cross = U(sdf.round_box((0, -0.1, 0.72), (0.08, 0.04, 0.34), 0.03), sdf.round_box((0, -0.1, 0.72), (0.34, 0.04, 0.08), 0.03),
              *[sdf.sphere((0.36 * sx, -0.1, 0.72 + 0.36 * sz), 0.07) for sx, sz in ((1, 1), (-1, 1), (1, -1), (-1, -1))], k=0.02)

    def gold(co, n):
        c_ = mixc(H(0xA8700E), H(0xFFC83A), ss(0.0, 0.8, n.z * 0.5 - n.y * 0.5 + 0.1))
        return mixc(c_, H(0x4F9A7A), ss(0.4, 0.75, wave(co, 9, 4)) * 0.8)

    return [
        Piece(gold, coin, voxel=0.016, post=M((0, 0, 0), (-16, 0, 12)), hi=0.4),
        Piece(lambda co, n: mixc(H(0xE8B032), H(0xFFE27A), ss(0.2, 0.9, -n.y)), cross, voxel=0.013, tris=170,
              post=M((0, 0, 0), (-16, 0, 12)), hi=0.4),
    ]


@item
def Amethyst():
    rock = sdf.noise_bumps(U(sdf.ellipsoid((0, 0, 0.2), (0.72, 0.58, 0.3)), sdf.ellipsoid((-0.3, 0.2, 0.3), (0.35, 0.3, 0.25)), k=0.2),
                           amplitude=0.04, frequency=8, seed=12)
    rock = sdf.smooth_subtract(rock, half_space((0, 0, 0.02), (0, 0, -1)), k=0.05)
    specs = [((0.05, 0, 0.3), (0.05, -0.1, 1), 0.26, 1.35, 6, 0.3, 0), ((0.35, 0.05, 0.28), (0.55, 0.0, 1), 0.2, 1.0, 6, 0.32, 20),
             ((-0.28, -0.08, 0.3), (-0.5, -0.2, 1), 0.2, 0.95, 6, 0.33, 10), ((0.1, 0.3, 0.3), (0.1, 0.6, 1), 0.17, 0.8, 6, 0.35, 5),
             ((-0.05, -0.35, 0.22), (0.0, -0.8, 1), 0.15, 0.7, 6, 0.36, 30), ((0.45, -0.3, 0.2), (0.7, -0.6, 1), 0.12, 0.55, 5, 0.4, 0),
             ((-0.45, 0.25, 0.3), (-0.6, 0.5, 1), 0.13, 0.6, 5, 0.38, 12)]

    def col(co, n):
        r = random.Random(int((co.x * 71 + co.y * 43 + co.z * 29) * 1000)).random()
        c = mixc(H(0x7B3FC4), H(0xC89BFF), ss(0.3, 1.5, co.z))
        c = mixc(c, H(0xE8D4FF), ss(0.4, 0.9, -n.y * 0.6 - n.x * 0.3 + n.z * 0.3) * 0.6)
        return mixc(c, richer(c, 0.4), r * 0.4)

    return [
        Piece(col, obj=crystal_mesh(specs), flat=True, face=True, hi=0.1, lo=0.2),
        Piece(lambda co, n: mixc(H(0x6E6258), H(0x938678), ss(0.2, 0.9, n.z)), rock, voxel=0.02, tris=380),
    ]


@item
def Glowworm():
    pts = [Vector(p) for p in ((0.75, 0.3, 0.1), (0.45, 0.5, 0.12), (0.05, 0.4, 0.14), (-0.15, 0.05, 0.15),
                               (0.05, -0.25, 0.16), (-0.1, -0.5, 0.3), (-0.35, -0.5, 0.52))]
    radii = [0.17, 0.13, 0.13, 0.14, 0.14, 0.14, 0.15]
    body = chain(pts, radii, k=0.06)
    bulb = sdf.sphere((0.8, 0.32, 0.18), 0.22)
    hc = Vector((-0.42, -0.52, 0.66))
    head = sdf.ellipsoid(T(hc), (0.19, 0.18, 0.18))
    body = U(body, head, k=0.1)
    ant = sdf.mirror_x(U(chain([(0.07, 0, 0.14), (0.14, -0.02, 0.32)], 0.025, k=0.01), sdf.sphere((0.14, -0.02, 0.34), 0.05), k=0.02))
    ant = xform(ant, loc=T(hc), rot=(0, 0, 0))

    def col(co, n):
        t = polyline_t(pts, co)
        ring = ss(0.7, 0.95, math.sin(t * 60))
        c = mixc(H(0x3E9A3A), H(0x9CFF6A), ss(0.9, 0.2, t))
        return mixc(c, H(0xD8FFB0), ring * 0.5 * ss(0.8, 0.3, t))

    eyes = []
    for s in (-1, 1):
        p, nn = surface(body, T(hc + Vector((s * 0.09, -0.3, 0.04))))
        eyes.append((p, nn, 0.045, 0.025))
    return [
        Piece(col, body, voxel=0.018, glow=True),
        Piece(lambda co, n: mixc(H(0xC8FF7A), H(0xF4FFD8), ss(0.1, 0.35, co.z)), bulb, voxel=0.016, tris=150, glow=True),
        Piece(H(0x3E8A36), ant, voxel=0.012, tris=60),
        Piece(H(0x10180E), obj=dots_mesh(eyes, sides=6), lit=False),
    ]


@item
def Geode():
    c = Vector((0, 0, 0.7))
    rock = sdf.noise_bumps(sdf.ellipsoid(T(c), (0.8, 0.72, 0.72)), amplitude=0.04, frequency=7, seed=5)
    cut_n = Vector((0, -0.75, 0.66)).normalized()
    rock = sdf.smooth_subtract(rock, half_space(T(c + cut_n * 0.12), T(cut_n)), k=0.03)
    cavity = sdf.noise_bumps(sdf.ellipsoid(T(c + cut_n * 0.05), (0.56, 0.5, 0.5)), amplitude=0.035, frequency=18, seed=2)
    geode = sdf.smooth_subtract(rock, cavity, k=0.02)
    geode = sdf.smooth_subtract(geode, half_space((0, 0, 0.05), (0, 0, -1)), k=0.08)
    outer_fn = sdf.ellipsoid(T(c), (0.8, 0.72, 0.72))[0]
    cav_fn = sdf.ellipsoid(T(c + cut_n * 0.05), (0.56, 0.5, 0.5))[0]

    def col(co, n):
        P = np.array([T(co)], dtype=F32)
        dc = float(cav_fn(P)[0])
        if dc < 0.05:
            s_ = 0.5 + 0.5 * wave(co, 20, 3)
            return mixc(mixc(H(0x6A2FB8), H(0xC48AFF), ss(-0.1, 0.05, dc)), H(0xEAD8FF), s_ * 0.35)
        if (co - c).dot(cut_n) > 0.08 and dc < 0.16:
            return H(0xF4EEF8)
        return mixc(H(0x7E7266), H(0xA39686), ss(0.2, 0.9, n.z) * 0.6 + 0.2 * wave(co, 9, 1))

    return [Piece(col, geode, voxel=0.018)]


@item
def Fossil():
    disc = sdf.noise_bumps(sdf.ellipsoid((0, 0, 0.8), (0.82, 0.28, 0.8)), amplitude=0.02, frequency=8, seed=9)
    pts, radii = [], []
    for i in range(34):
        th = 0.3 + i * 0.3
        rho = 0.06 * math.exp(0.2 * th)
        pts.append(Vector((rho * math.cos(th), -0.2, 0.8 + rho * math.sin(th))))
        radii.append(0.45 * rho + 0.025)
    tube = chain(pts, radii, k=0.02)

    def ribs(P):
        a = np.arctan2(P[:, 2] - 0.8, P[:, 0])
        rr = np.hypot(P[:, 2] - 0.8, P[:, 0])
        return tube[0](P) + 0.022 * np.clip(rr / 0.3, 0, 1) * np.cos(a * 26)

    shell = (ribs, tube[1])

    def shell_col(co, n):
        a = math.atan2(co.z - 0.8, co.x)
        return mixc(H(0xF2E2C0), H(0xB0906A), ss(0.2, 0.9, math.cos(a * 26)) * 0.8)

    def stone_col(co, n):
        return mixc(H(0x9C8C78), H(0xC4B49A), ss(0.2, 0.9, -n.y * 0.4 + n.z * 0.6) + 0.15 * wave(co, 10, 2))

    lean = M((0, 0, 0), (-18, 0, 0))
    return [
        Piece(stone_col, disc, voxel=0.02, post=lean, weight=0.7),
        Piece(shell_col, shell, voxel=0.013, post=lean, weight=1.4),
    ]

@item
def CaveMoss():
    rock = sdf.noise_bumps(U(sdf.ellipsoid((0, 0, 0.18), (0.75, 0.6, 0.26)), sdf.ellipsoid((0.3, 0.15, 0.28), (0.35, 0.3, 0.22)), k=0.2),
                           amplitude=0.03, frequency=8, seed=3)
    rock = sdf.smooth_subtract(rock, half_space((0, 0, 0.02), (0, 0, -1)), k=0.05)
    rng = random.Random(17)
    puffs = []
    for i in range(34):
        a = i * math.pi * (3 - math.sqrt(5))
        rr = math.sqrt((i + 0.5) / 34) * 0.66
        x, y = rr * math.cos(a) * 1.05, rr * math.sin(a) * 0.9
        q = max(0.0, 1 - (x / 0.8) ** 2 - (y / 0.65) ** 2)
        z = 0.18 + 0.28 * math.sqrt(q)
        puffs.append(sdf.sphere((x, y, z), rng.uniform(0.12, 0.19) * (0.7 + 0.3 * math.sqrt(q))))
    moss = U(*puffs, k=0.07)
    sprouts = U(*[U(chain([(x, y, 0.45), (x + dx, y, 0.78)], 0.03, k=0.01), sdf.sphere((x + dx, y, 0.8), 0.065), k=0.02)
                  for x, y, dx in ((-0.12, -0.1, -0.05), (0.22, -0.05, 0.06), (0.05, 0.22, 0.0))], k=0.0)

    def moss_col(co, n):
        return mixc(mixc(H(0x23857B), H(0x4FC0AA), ss(0.25, 0.6, co.z)), H(0x9CEBD6), ss(0.3, 0.8, wave(co, 16, 6)) * 0.45)

    return [
        Piece(lambda co, n: mixc(H(0x4F5560), H(0x6A7280), ss(0.2, 0.9, n.z)), rock, voxel=0.02, tris=180),
        Piece(moss_col, moss, voxel=0.016, weight=1.2),
        Piece(lambda co, n: mixc(H(0x2E8A7A), H(0xB8FFEA), ss(0.7, 0.8, co.z)), sprouts, voxel=0.012, tris=110),
    ]

@item
def Glowcap():
    mound = sdf.noise_bumps(sdf.ellipsoid((0, 0, 0.02), (0.55, 0.45, 0.14)), amplitude=0.02, frequency=10, seed=7)
    stems, caps, spots = [], [], []
    for (x, y, h, r, lean) in ((0.0, 0.05, 0.85, 0.3, 0), (0.32, -0.18, 0.55, 0.22, 18), (-0.3, -0.12, 0.45, 0.19, -20)):
        top = Vector((x + math.sin(math.radians(lean)) * h * 0.4, y, h))
        stems.append(chain(curve_points((x, y, 0.05), T(top), (0.03, 0, 0), 3), [0.08 * r / 0.3 + 0.03, 0.07 * r / 0.3 + 0.02, 0.06 * r / 0.3 + 0.02], k=0.02))
        cap = U(sdf.ellipsoid(T(top + Vector((0, 0, r * 0.35))), (r, r, r * 0.75)),
                sdf.round_cone(T(top + Vector((0, 0, r * 0.4))), T(top + Vector((0, 0, r * 1.25))), r * 0.55, r * 0.12), k=r * 0.3)
        cap = sdf.smooth_subtract(cap, sdf.ellipsoid(T(top + Vector((0, 0, r * 0.05))), (r * 0.9, r * 0.9, r * 0.4)), k=0.03)
        caps.append(cap)
        for k in range(4):
            a = math.radians(k * 90 + 30)
            p, nn = surface(cap, T(top + Vector((math.cos(a), math.sin(a), 0.9))))
            spots.append((p, nn, r * 0.16, 0.02))
    return [
        Piece(lambda co, n: mixc(H(0x2E2A3A), H(0x4A4258), ss(0.3, 0.9, n.z)), mound, voxel=0.018, tris=120),
        Piece(lambda co, n: mixc(H(0xD8C8F0), H(0xF2EAFF), ss(0.1, 0.6, co.z)), U(*stems, k=0.0), voxel=0.012, tris=150, glow=True),
        Piece(lambda co, n: mixc(H(0x9A48F0), H(0xD9A8FF), ss(0.2, 0.9, n.z)), U(*caps, k=0.0), voxel=0.014, glow=True),
        Piece(H(0xF4E0FF), obj=dots_mesh(spots, sides=5), glow=True, lit=False),
    ]


@item
def Cookie():
    cookie = U(sdf.cylinder((0, 0, 0.17), 0.7, 0.14, rounding=0.12), sdf.ellipsoid((0, 0, 0.24), (0.6, 0.6, 0.12)), k=0.1)
    cookie = sdf.noise_bumps(cookie, amplitude=0.018, frequency=11, seed=5)
    bite = U(sdf.sphere((-0.72, -0.35, 0.2), 0.2), sdf.sphere((-0.5, -0.62, 0.2), 0.19), sdf.sphere((-0.8, -0.05, 0.2), 0.15), k=0.0)
    cookie = sdf.smooth_subtract(cookie, bite, k=0.02)
    rng = random.Random(8)
    chips = []
    for i in range(11):
        a = i * 2.4 + rng.uniform(-0.3, 0.3)
        rr = 0.12 + 0.5 * math.sqrt((i + 0.3) / 11)
        x, y = rr * math.cos(a), rr * math.sin(a)
        if bite[0](np.array([[x, y, 0.2]], dtype=F32))[0] < 0.06:
            continue
        p, nn = surface(cookie, (x, y, 1.0))
        chips.append(sdf.ellipsoid(T(p + nn * 0.01), (0.085, 0.08, 0.06), rot=(0, 0, rng.uniform(0, 90))))

    def col(co, n):
        c = mixc(H(0xC98A48), H(0xE8B878), ss(0.1, 0.8, n.z))
        return mixc(c, H(0xA86A30), ss(0.35, 0.8, wave(co, 13, 2)) * 0.4)

    return [
        Piece(col, cookie, voxel=0.016, post=M(rot=(-14, 6, 0))),
        Piece(lambda co, n: mixc(H(0x3A2014), H(0x6A4028), ss(0.4, 1.0, n.z)), U(*chips, k=0.0), voxel=0.012, tris=200,
              post=M(rot=(-14, 6, 0)), hi=0.4),
    ]


@item
def Cupcake():
    def pleat(P):
        base = sdf.round_cone((0, 0, 0.06), (0, 0, 0.62), 0.42, 0.56)[0](P)
        return base + 0.025 * np.cos(np.arctan2(P[:, 1], P[:, 0]) * 18)

    wrap = (pleat, (np.array([-0.62, -0.62, 0], dtype=F32), np.array([0.62, 0.62, 0.7], dtype=F32)))
    wrap = zslice(wrap, 0.0, 0.64)
    cake = sdf.ellipsoid((0, 0, 0.66), (0.56, 0.56, 0.16))
    frost = U(sdf.torus((0, 0, 0.78), 0.44, 0.17), sdf.torus((0.02, 0, 0.99), 0.31, 0.15), sdf.torus((0.03, 0, 1.18), 0.18, 0.12),
              sdf.round_cone((0.03, 0, 1.2), (0.06, 0, 1.42), 0.14, 0.05), sdf.ellipsoid((0, 0, 0.82), (0.45, 0.45, 0.2)), k=0.08)
    cherry = sdf.sphere((0.05, -0.02, 1.52), 0.16)
    stem = chain(curve_points((0.06, 0, 1.62), (0.22, 0.12, 1.9), (0, 0, 0.04), 4), 0.028, k=0.01)
    rng = random.Random(4)
    spr = {0: [], 1: [], 2: []}
    for i in range(18):
        a = rng.uniform(0, 2 * math.pi)
        zz = rng.uniform(0.8, 1.3)
        p, nn = surface(frost, (math.cos(a) * 1.2, math.sin(a) * 1.2, zz + 0.3))
        spr[i % 3].append((p, nn, 0.04, 0.025))
    return [
        Piece(lambda co, n: mixc(H(0x7FBEEB), H(0xCDEBFF), 0.5 + 0.5 * math.cos(math.atan2(co.y, co.x) * 18)), wrap, voxel=0.016, tris=210),
        Piece(H(0xB06A3A), cake, voxel=0.02, tris=40),
        Piece(lambda co, n: mixc(H(0xFF8FBF), H(0xFFD0E4), ss(0.2, 0.9, n.z)), frost, voxel=0.018, weight=1.0),
        Piece(H(0xE01E3C), cherry, voxel=0.013, tris=110, hi=0.6),
        Piece(H(0x5A7A2A), stem, voxel=0.01, tris=40),
        Piece(H(0xFFE14A), obj=dots_mesh(spr[0], sides=4), lit=False),
        Piece(H(0x5AC8FF), obj=dots_mesh(spr[1], sides=4), lit=False),
        Piece(H(0xFFFFFF), obj=dots_mesh(spr[2], sides=4), lit=False),
    ]


@item
def Cheese():
    tip, b1, b2 = (-0.9, 0.0), (0.62, -0.62), (0.62, 0.62)

    def tri(x, y):
        def edge(a, b):
            ex, ey = b[0] - a[0], b[1] - a[1]
            L = math.hypot(ex, ey)
            return ((x - a[0]) * ey - (y - a[1]) * ex) / L
        d = np.maximum(np.maximum(edge(tip, b1), edge(b1, b2)), edge(b2, tip))
        return d

    wedge = extrude2d(tri, (-1, -1, 1, 1), 0.38, rounding=0.07, center=(0, 0, 0.38))
    holes = []
    rng = random.Random(6)
    for p0, r in (((-0.1, -0.1, 0.8), 0.14), ((0.3, 0.2, 0.8), 0.18), ((-0.45, 0.05, 0.8), 0.09), ((0.25, -0.62, 0.35), 0.15),
                  ((-0.2, -0.36, 0.5), 0.11), ((0.66, 0.1, 0.4), 0.16), ((0.0, 0.42, 0.25), 0.12), ((0.45, -0.25, 0.8), 0.1)):
        p, nn = surface(wedge, p0)
        holes.append(sdf.sphere(T(p - nn * r * 0.2), r))
    wedge = sdf.smooth_subtract(wedge, U(*holes, k=0.0), k=0.03)

    def col(co, n):
        rind = ss(0.52, 0.6, co.x) * ss(0.5, 0.9, n.x)
        c = mixc(H(0xFFC83D), H(0xFFE07A), ss(0.3, 0.9, n.z))
        return mixc(c, H(0xF09A1A), rind)

    return [Piece(col, wedge, voxel=0.018, post=M(rot=(0, 0, -25)))]


@item
def Sock():
    # a flat L: leg along +Y, heel at the corner, foot along +X; tipped up so the player sees its face
    leg = sdf.round_box((-0.3, 0.42, 0.0), (0.3, 0.58, 0.14), 0.13)
    foot = sdf.round_box((0.18, -0.34, 0.0), (0.56, 0.28, 0.14), 0.13)
    heel = sdf.ellipsoid((-0.36, -0.3, 0.0), (0.32, 0.36, 0.15))
    toe = sdf.ellipsoid((0.66, -0.34, 0.0), (0.2, 0.28, 0.14))
    sock = U(leg, foot, heel, toe, k=0.18)
    cuff = sdf.round_box((-0.3, 1.02, 0.0), (0.33, 0.12, 0.16), 0.1)

    def col(co, n):
        if (co - Vector((-0.4, -0.36, 0))).length < 0.3 or co.x > 0.55:
            return H(0x2E6FD0)
        s_ = co.y if co.y > -0.05 else -co.x
        return mixc(H(0xF8F4EC), H(0xE8403A), ss(-0.25, 0.25, math.sin(s_ * 17)))

    post = M((0, 0, 0.5), (40, 0, 12))
    return [
        Piece(col, sock, voxel=0.018, post=post),
        Piece(lambda co, n: mixc(H(0xF8F4EC), H(0xD8D0C4), 0.5 + 0.5 * math.sin(co.x * 40)), cuff, voxel=0.016, post=post, tris=120),
    ]

@item
def Balloon():
    body = U(sdf.ellipsoid((0, 0, 1.78), (0.64, 0.64, 0.76)), sdf.round_cone((0, 0, 1.05), (0, 0, 1.5), 0.08, 0.45), k=0.25)
    knot = U(sdf.round_cone((0, 0, 0.92), (0, 0, 1.06), 0.1, 0.06), k=0.0)
    string = chain(curve_points((0, 0, 0.95), (0.18, -0.1, 0.02), (0.25, 0.1, 0), 7), 0.035, k=0.01)
    hp, hn = surface(body, (-0.6, -0.8, 2.3))

    def col(co, n):
        return mixc(H(0xD81E34), H(0xFF4A58), ss(0.2, 0.9, n.z - n.y * 0.3))

    return [
        Piece(col, body, voxel=0.024, hi=0.55),
        Piece(H(0xC0182C), knot, voxel=0.012, tris=60),
        Piece(H(0xF2EEE6), string, voxel=0.012, tris=90),
    ]


def xslice(shape, x0, x1):
    return (lambda P: np.maximum(shape[0](P), np.maximum(x0 - P[:, 0], P[:, 0] - x1)), shape[1])


@item
def Crayon():
    L = 0.85
    wax = U(sdf.cylinder((0, 0, 0), 0.26, L, rot=(0, 90, 0), rounding=0.05),
            sdf.round_cone((L - 0.05, 0, 0), (L + 0.45, 0, 0), 0.24, 0.07), k=0.03)
    paper = sdf.cylinder((-0.1, 0, 0), 0.285, 0.64, rot=(0, 90, 0), rounding=0.02)
    purple, dark, label = H(0x6A30B8), H(0x2A1448), H(0xE6D8FF)
    post = M((0, 0, 0.28), (0, -4, 28))
    bands = ((-0.8, -0.58, dark), (-0.58, -0.22, purple), (-0.22, 0.02, label), (0.02, 0.36, purple), (0.36, 0.6, dark))
    return [Piece(lambda co, n: mixc(H(0x9A5AE8), H(0xC09AF8), ss(0.3, 0.9, n.z) * 0.4), wax, voxel=0.016, post=post, tris=330)] + \
        [Piece(c, xslice(paper, a, b), voxel=0.014, post=post, tris=100, hi=0.15) for a, b, c in bands]


@item
def Bell():
    bell = U(sdf.round_cone((0, 0, 0.28), (0, 0, 1.0), 0.62, 0.3), sdf.sphere((0, 0, 1.0), 0.32),
             sdf.torus((0, 0, 0.2), 0.6, 0.1), k=0.12)
    bell = sdf.smooth_subtract(bell, sdf.round_cone((0, 0, 0.0), (0, 0, 0.85), 0.55, 0.2), k=0.05)
    bell = sdf.smooth_subtract(bell, half_space((0, 0, 0.1), (0, 0, -1)), k=0.02)
    clapper = U(sdf.sphere((0.05, -0.1, 0.18), 0.13), sdf.capsule((0, 0, 0.8), (0.05, -0.1, 0.2), 0.04), k=0.03)
    handle = U(sdf.cylinder((0, 0, 1.55), 0.13, 0.28, rounding=0.05), sdf.sphere((0, 0, 1.9), 0.19), k=0.08)
    collar = sdf.cylinder((0, 0, 1.28), 0.18, 0.06, rounding=0.03)

    def gold(co, n):
        h = n.z * 0.6 - n.y * 0.3 - n.x * 0.3 + 0.1 * wave(co, 4, 1)
        c = mixc(H(0x9A6A10), H(0xF2B830), ss(-0.35, 0.25, h))
        c = mixc(c, H(0xFFF0A0), ss(0.45, 0.75, h) * 0.8)
        return mixc(c, H(0x7A5208), ss(0.32, 0.2, co.z) * 0.5)

    return [
        Piece(gold, bell, voxel=0.018, lit=False),
        Piece(metal(H(0x9A7A30)), U(clapper, collar, k=0.0), voxel=0.014, tris=110),
        Piece(lambda co, n: mixc(H(0x8A4E2A), H(0xB87444), ss(0.2, 0.9, n.z)), handle, voxel=0.016, tris=150),
    ]

@item
def RubberBoot():
    shaft = sdf.round_box((0, 0.2, 0.92), (0.34, 0.38, 0.64), 0.22)
    foot = sdf.round_box((0, -0.22, 0.26), (0.34, 0.58, 0.24), 0.22)
    boot = U(shaft, foot, k=0.22)
    boot = sdf.smooth_subtract(boot, sdf.ellipsoid((0, 0.2, 1.6), (0.24, 0.28, 0.3)), k=0.05)
    upper = sdf.smooth_subtract(boot, half_space((0, 0, 0.14), (0, 0, -1)), k=0.02)
    sole = zslice(sdf.offset(boot, 0.025), 0.0, 0.16)
    rim = stretch(sdf.torus((0, 0.2, 1.5), 0.3, 0.06), (0, 0.2, 1.5), (1.05, 0.9, 1.0))

    def col(co, n):
        return mixc(H(0xF5B814), H(0xFFDC4A), ss(0.1, 0.8, n.z * 0.5 - n.y * 0.5 + 0.2))

    return [
        Piece(col, upper, voxel=0.022),
        Piece(H(0x5A4636), sole, voxel=0.018, tris=150),
        Piece(H(0xFFE88A), rim, voxel=0.014, tris=110),
    ]

@item
def Obsidian():
    rng = random.Random(33)

    def shard(base, top, w, n, flat=0.7):
        pts = [Vector(top)]
        b = Vector(base)
        ax = Vector(top) - b
        for i in range(n):
            t = rng.uniform(0.0, 0.8) ** 1.4
            a = rng.uniform(0, 2 * math.pi)
            r = w * (1 - t * 0.85) * rng.uniform(0.75, 1.0)
            pts.append(b + ax * t + Vector((math.cos(a) * r, math.sin(a) * r * flat, 0)))
        return hull_mesh(pts)

    obj = fk.join([shard((0, 0, 0), (0.1, -0.05, 1.55), 0.55, 40), shard((0.5, 0.15, 0), (0.85, 0.25, 0.8), 0.34, 22),
                   shard((-0.5, -0.1, 0), (-0.7, -0.2, 0.62), 0.3, 18)], _name("obs"))

    def col(co, n):
        r = random.Random(int((co.x * 83 + co.y * 61 + co.z * 37) * 1000)).random()
        c = mixc(H(0x141019), H(0x2A2238), r)
        c = mixc(c, H(0x6A5AA8), ss(0.3, 0.9, -n.y * 0.5 - n.x * 0.5) * 0.7)
        return mixc(c, H(0xD8D0FF), ss(0.8, 0.97, n.z * 0.4 - n.y * 0.6 - n.x * 0.3) * 0.8)

    return [Piece(col, obj=obj, flat=True, face=True, hi=0.2, lo=0.1)]

@item
def CloudBerry():
    rng = random.Random(9)
    puffs = [sdf.sphere((0, 0, 0.55), 0.42)]
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(22):
        z = 1 - 2 * (i + 0.5) / 22
        rr = math.sqrt(1 - z * z)
        a = i * golden
        if z < -0.6:
            continue
        puffs.append(sdf.sphere((0.42 * rr * math.cos(a), 0.42 * rr * math.sin(a), 0.55 + 0.42 * z), rng.uniform(0.17, 0.22)))
    berry = U(*puffs, k=0.07)
    leaves = []
    for i in range(5):
        a = math.radians(i * 72 + 10)
        leaves.append(leaf_shape((0.05 * math.cos(a), 0.05 * math.sin(a), 1.12), (0.42 * math.cos(a), 0.42 * math.sin(a), 1.02), 0.12, 0.035))
    stem = chain(curve_points((0, 0, 1.08), (0.08, 0.05, 1.35), (0.03, 0, 0.02), 3), 0.045, k=0.01)
    return [
        Piece(lambda co, n: mixc(H(0x9CC4F5), H(0xFBFDFF), ss(0.2, 1.0, co.z) * 0.7 + ss(-0.2, 0.8, n.z) * 0.3), berry, voxel=0.018, hi=0.3),
        Piece(H(0x5FB08A), U(*leaves, stem, k=0.03), voxel=0.012, tris=170),
    ]


@item
def AlienGoo():
    puddle = U(sdf.ellipsoid((0, 0, 0.05), (0.8, 0.62, 0.08)), sdf.ellipsoid((0.6, 0.35, 0.04), (0.35, 0.25, 0.07)),
               sdf.ellipsoid((-0.55, -0.35, 0.04), (0.32, 0.28, 0.07)), sdf.ellipsoid((-0.35, 0.5, 0.04), (0.24, 0.18, 0.06)),
               sdf.ellipsoid((0.3, -0.25, 0.1), (0.35, 0.3, 0.12)), k=0.2)
    puddle = sdf.smooth_subtract(puddle, half_space((0, 0, 0.0), (0, 0, -1)), k=0.02)
    bubble = sdf.sphere((-0.1, 0.05, 0.22), 0.36)
    small = U(sdf.sphere((0.45, -0.1, 0.18), 0.14), sdf.sphere((0.95, -0.35, 0.05), 0.07), sdf.sphere((-0.9, 0.1, 0.05), 0.06), k=0.0)
    hp, hn = surface(bubble, (-0.4, -0.3, 0.8))
    return [
        Piece(lambda co, n: mixc(H(0x7EDB1A), H(0xC8FF4A), ss(0.02, 0.18, co.z)), U(puddle, small, k=0.08), voxel=0.016, glow=True),
        Piece(lambda co, n: mixc(H(0xB0FF50), H(0xEEFFB8), ss(0.2, 0.55, co.z)), bubble, voxel=0.016, tris=200, glow=True, hi=0.4),
        Piece(H(0xFFFFFF), obj=dots_mesh([(hp, hn, 0.08, 0.02)], sides=6), lit=False, glow=True),
    ]


EGG_C, EGG_R = 1.52, (1.0, 1.0, 1.42)


def egg_shape(c=EGG_C, r=EGG_R, taper=0.16):
    base = sdf.ellipsoid((0, 0, c), r)

    def fn(P):
        Q = P.copy()
        f = 1.0 - taper * np.clip((P[:, 2] - c) / r[2], -1, 1)
        Q[:, 0] = P[:, 0] / f
        Q[:, 1] = P[:, 1] / f
        return base[0](Q) * np.minimum(f, 1.0)

    return (fn, (np.array([-r[0] * 1.2, -r[1] * 1.2, c - r[2] - 0.05], dtype=F32), np.array([r[0] * 1.2, r[1] * 1.2, c + r[2] + 0.05], dtype=F32)))


def make_egg(base_hex, spot_hex, seed):
    egg = egg_shape()
    tilt = M((0, 0, 0.1), (5, -6, 0))
    rng = random.Random(seed)
    spots = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(11):
        z = 0.9 - 1.45 * (i + 0.5) / 11
        rr = math.sqrt(max(0.0, 1 - z * z))
        a = i * golden + rng.uniform(-0.3, 0.3)
        spots.append(((2.5 * rr * math.cos(a), 2.5 * rr * math.sin(a), EGG_C + 2.0 * z), rng.uniform(0.13, 0.25)))
    straws = []
    for i in range(30):
        a = i * 2 * math.pi / 30 + rng.uniform(-0.1, 0.1)
        rr = rng.uniform(0.62, 0.9)
        cx, cy = rr * math.cos(a), rr * math.sin(a)
        ta = a + math.pi / 2 + rng.uniform(-0.6, 0.6)
        L = rng.uniform(0.28, 0.42)
        z = rng.uniform(0.05, 0.2)
        straws.append(sdf.capsule((cx - math.cos(ta) * L, cy - math.sin(ta) * L, z + rng.uniform(-0.04, 0.08)),
                                  (cx + math.cos(ta) * L, cy + math.sin(ta) * L, z + rng.uniform(-0.04, 0.12)), rng.uniform(0.055, 0.075)))
    straw = U(*straws, k=0.02)
    base_c, spot_c = H(base_hex), H(spot_hex)

    def egg_col(co, n):
        return mixc(richer(base_c, 0.15), lighter(base_c, 0.18), ss(0.4, 2.6, co.z))

    return [
        Piece(egg_col, egg, voxel=0.035, post=tilt, weight=1.0, hi=0.3),
        Piece(spot_c, obj=decal_mesh(egg, spots), post=tilt, hi=0.3),
        Piece(lambda co, n: mixc(H(0xC8963A), H(0xF2D27A), ss(0.05, 0.25, co.z) * 0.7 + 0.3 * (0.5 + 0.5 * wave(co, 20, 1))),
              straw, voxel=0.016, tris=210),
    ]


@item
def Egg_Pink():
    return make_egg(0xF4A0C0, 0xFFCFE2, 1)


@item
def Egg_Grey():
    return make_egg(0xA3ABB6, 0xD6DCE4, 2)


@item
def Egg_Purple():
    return make_egg(0xAE84DE, 0xD8C4F8, 3)


EGG_CRACK_Z, EGG_CRACK_AMP, EGG_TEETH = 1.62, 0.17, 8


def shell_parts(upper):
    egg = egg_shape()
    inner = egg_shape(r=(EGG_R[0] - 0.09, EGG_R[1] - 0.09, EGG_R[2] - 0.09))

    def fn(P):
        shell = np.maximum(egg[0](P), -inner[0](P))
        a = np.arctan2(P[:, 1], P[:, 0]) * EGG_TEETH / (2 * math.pi)
        tri = 2 * np.abs(a - np.floor(a) - 0.5) * 2 - 1
        f = (P[:, 2] - (EGG_CRACK_Z + EGG_CRACK_AMP * tri)) * 0.55
        return np.maximum(shell, -f if upper else f)

    return (fn, egg[1])


def eggshell_col(co, n):
    inner = egg_shape(r=(EGG_R[0] - 0.09, EGG_R[1] - 0.09, EGG_R[2] - 0.09))
    d = float(inner[0](np.array([T(co)], dtype=F32))[0])
    if d < 0.03:
        return H(0xEDE0C4)
    return mixc(H(0xF3ECDC), H(0xFFFCF4), ss(0.2, 2.6, co.z))


@item
def EggShell_Top():
    return [Piece(eggshell_col, shell_parts(True), voxel=0.024, hi=0.25)]


@item
def EggShell_Bottom():
    return [Piece(eggshell_col, shell_parts(False), voxel=0.024, hi=0.25)]


# ═══ ORDER (ingredient ids — these ARE the FBX object names) ══════════════════════

ORDER = [
    # Meadow
    "Apple", "Strawberry", "Watermelon", "Blueberry", "Carrot", "Pumpkin", "Daisy", "Sunflower", "Clover", "Beetle",
    "Butterfly", "Worm", "Stick", "Acorn", "MudClump", "Pebble", "RubberDuck", "BouncyBall", "ToyBlock", "Honeycomb",
    "Mushroom", "Feather",
    # Junkyard
    "Battery", "Gear", "ScrapMetal", "Magnet", "OilCan", "BrokenTV", "Spring", "Bolt", "Wire", "Tire", "SodaCan",
    "Lightbulb", "CircuitBoard", "Clock", "Toaster", "TrafficCone", "Fan",
    # Strange / rare
    "IceCube", "Bone", "CrystalShard", "Fish", "Coal", "LavaFruit", "StarFragment", "MoonMushroom", "Meteorite",
    "CursedSandwich", "Slime",
    # New ingredients
    "Pearl", "Coral", "Jellyfish", "Seashell", "Kelp", "Starfish", "Crab", "SunkenCoin", "Amethyst", "Glowworm", "Geode",
    "Fossil", "CaveMoss", "Glowcap", "Cookie", "Cupcake", "Cheese", "Sock", "Balloon", "Crayon", "Bell", "RubberBoot",
    "Obsidian", "CloudBerry", "AlienGoo",
    # Hatching
    "Egg_Pink", "Egg_Grey", "Egg_Purple", "EggShell_Top", "EggShell_Bottom",
]


# ═══ PREVIEW ═══════════════════════════════════════════════════════════════════

COMPOSE = r'''
import json, sys
from PIL import Image, ImageDraw, ImageFont
spec = json.load(open(sys.argv[1]))
tile, cols = spec["tile"], spec["cols"]
rows = (len(spec["tiles"]) + cols - 1) // cols
sheet = Image.new("RGB", (tile * cols, tile * rows), (40, 44, 52))
font = None
for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
    try:
        font = ImageFont.truetype(f, max(11, tile // 13)); break
    except Exception:
        pass
font = font or ImageFont.load_default()
for i, (path, label) in enumerate(spec["tiles"]):
    im = Image.open(path).convert("RGB").resize((tile, tile))
    x, y = (i % cols) * tile, (i // cols) * tile
    sheet.paste(im, (x, y))
    d = ImageDraw.Draw(sheet, "RGBA")
    h = max(14, tile // 9)
    d.rectangle([x, y + tile - h, x + tile - 1, y + tile - 1], fill=(20, 22, 28, 170))
    d.text((x + 5, y + tile - h + 1), label, fill=(255, 255, 255, 255), font=font)
sheet.save(spec["out"], optimize=True)
'''


def setup_preview():
    fk.preview_studio(floor_color=(0.55, 0.62, 0.5))
    sc = bpy.context.scene
    try:
        sc.eevee.taa_render_samples = 24
    except Exception:
        pass
    floor = bpy.data.materials.get("PreviewFloorMat")
    if floor:
        bsdf = next(n for n in floor.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (0.2, 0.26, 0.17, 1)
    return fk.vcol_material()


def bounds(obj):
    xs = [v.co for v in obj.data.vertices]
    lo = Vector((min(c.x for c in xs), min(c.y for c in xs), min(c.z for c in xs)))
    hi = Vector((max(c.x for c in xs), max(c.y for c in xs), max(c.z for c in xs)))
    return lo, hi


def render_sheet(objs, out, cols=5, tile=280, render_res=None):
    setup_preview()
    tmp = tempfile.mkdtemp(prefix="kit_props_tiles_")
    res = render_res or tile
    tiles = []
    for o in objs:
        fk.preview_tint(o, (1, 1, 1))
    for o in objs:
        for p in objs:
            p.hide_render = p is not o
        lo, hi = bounds(o)
        c = (lo + hi) / 2
        rad = max((hi - lo).length / 2, 0.45)
        d = rad / math.sin(math.atan(18 / 50)) * 1.02
        fk.look_setup(target=T(c), distance=d, yaw=-30, pitch=24, lens=50)
        path = os.path.join(tmp, f"{o.name}.png")
        fk.render_png(path, res=(res, res))
        tiles.append((path, f"{len(tiles) + 1}. {o.name}" + (f"  {fk.triangle_count(o)}" if tile >= 250 else "")))
    for p in objs:
        p.hide_render = False
    spec = os.path.join(tmp, "spec.json")
    json.dump({"tile": tile, "cols": cols, "tiles": tiles, "out": out}, open(spec, "w"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    py = shutil.which("python3") or "/usr/bin/python3"
    script = os.path.join(tmp, "compose.py")
    open(script, "w").write(COMPOSE)
    r = subprocess.run([py, script, spec], capture_output=True, text=True)
    if r.returncode != 0:
        print("[kit_props] PIL compose failed, writing unlabelled sheet:", r.stderr[-400:])
        _compose_numpy(tiles, out, cols, res)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _compose_numpy(tiles, out, cols, res):
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.zeros((rows * res, cols * res, 4), dtype=np.float32)
    sheet[..., 3] = 1
    for i, (path, _) in enumerate(tiles):
        img = bpy.data.images.load(path, check_existing=False)
        px = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
        bpy.data.images.remove(img)
        r, c = rows - 1 - i // cols, i % cols
        sheet[r * res:(r + 1) * res, c * res:(c + 1) * res] = px
    im = bpy.data.images.new("_sheet", width=cols * res, height=rows * res, alpha=True)
    im.pixels = sheet.ravel()
    im.filepath_raw = out
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def render_scale_lineup(objs, out):
    """Every item in a row (real size) beside a 5-stud avatar capsule."""
    setup_preview()
    for o in objs:
        fk.preview_tint(o, (1, 1, 1))
    cap = sdf.to_mesh("_Avatar", sdf.capsule((0, 0, 0.5), (0, 0, 4.5), 0.5), voxel=0.08)
    fk.solid_color(cap, to_lin((0.9, 0.9, 0.95)))
    fk.preview_tint(cap, (1, 1, 1))
    x = 0.0
    placed = [(cap, 0.0)]
    x = 1.2
    for o in objs:
        lo, hi = bounds(o)
        w = hi.x - lo.x
        x += w / 2 + 0.25
        o.location = (x, 0, 0)
        x += w / 2
    width = x + 1.0
    fk.look_setup(target=(width / 2 - 0.6, 0, 1.6), distance=width * 1.45, yaw=0, pitch=6, lens=50)
    sc = bpy.context.scene
    fk.render_png(out, res=(1400, 380))
    for o in objs:
        o.location = (0, 0, 0)
    bpy.data.objects.remove(cap, do_unlink=True)


# ═══ MAIN ═══════════════════════════════════════════════════════════════════════

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"only": None, "sheet": None, "cols": 8, "tile": 175, "scale": None}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k in opts and i + 1 < len(argv):
            opts[k] = argv[i + 1]
            i += 2
        else:
            i += 1
    names = opts["only"].split(",") if opts["only"] else ORDER
    missing = [n for n in names if n not in ITEMS]
    if missing:
        raise SystemExit(f"unknown items: {missing}")
    t0 = time.time()
    objs = []
    for n in names:
        t = time.time()
        o = build(n, ITEMS[n]())
        tris = fk.triangle_count(o)
        lo, hi = bounds(o)
        dims = hi - lo
        flag = "" if tris <= TRI_CAP and o.name == n else "  <-- PROBLEM"
        print(f"[kit_props] {n:16s} {tris:4d} tris  size {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f}  "
              f"({time.time() - t:.1f}s){flag}")
        objs.append(o)
    print(f"[kit_props] built {len(objs)} items in {time.time() - t0:.0f}s")

    if not opts["only"]:
        path = fk.export_fbx(objs, FBX_NAME)
        print(f"[kit_props] exported {path}")
    if opts["scale"]:
        render_scale_lineup(objs, opts["scale"])
        print(f"[kit_props] lineup {opts['scale']}")
        return
    out = opts["sheet"] or (PREVIEW if not opts["only"] else None)
    if out:
        cols = int(opts["cols"]) if opts["sheet"] else 8
        tile = int(opts["tile"]) if opts["sheet"] else 175
        render_sheet(objs, out, cols=cols, tile=tile, render_res=max(tile, 280) if opts["sheet"] else 350)
        print(f"[kit_props] sheet {out}")


main()
