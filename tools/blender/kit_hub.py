"""kit_hub — Hub, Sanctuary and Trials world kit for Feed a Monster! (ART_KIT_SPEC.md)

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/kit_hub.py
      -> art/build/kit_hub.fbx      every asset, one object each, origin at base centre
      -> art/previews/kit_hub.png   labelled contact sheet (5-stud capsule for scale)

Iterating (no export):  KIT_ONLY=Fountain,Lamp_Post KIT_SHEET=/tmp/x.png Blender -b ... -P kit_hub.py

Placement notes for the world builder:
  * Portal_Disc is modelled IN PLACE inside Portal_Arch (same origin). It is a true disc,
    axis along Y, centred at PORTAL_DISC_CENTRE, so it may spin about its own centre.
  * Windmill_Sails is built with its hub at the origin, sails in the XZ plane (facing -Y),
    spinning about Y. Mount it at WINDMILL_HUB relative to Windmill's origin.
  * Bunting_Span / Lantern_String hang between their end points (+-10, 0, 10) / (+-8, 0, 8).
  * Race_Ring stands in the XZ plane facing -Y, bottom of the ring at Z = 0.
"""
import sys; sys.path.insert(0, "/Users/malik/rob/tools/blender")
import bpy, bmesh, math, numpy as np
from mathutils import Vector
import famkit as fk, sdf
fk.reset_scene()

import os
import random
import time
from mathutils import Euler, Matrix

ROOT = "/Users/malik/rob"
FBX_NAME = "kit_hub.fbx"
PREVIEW = os.path.join(ROOT, "art", "previews", "kit_hub.png")
SMALL, MEDIUM, LARGE = 1500, 3500, 8000

PORTAL_DISC_CENTRE = (0.0, 0.0, 5.7)
WINDMILL_HUB = (0.0, -3.35, 11.0)

F32 = np.float32


# ═══ COLOUR ═══════════════════════════════════════════════════════════════════

def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def mul(a, k):
    return tuple(min(1.0, c * k) for c in a)


def ss(a, b, x):
    return fk.smoothstep(a, b, x)


SKY = (1.0, 0.98, 0.9)
SHADOW = (0.34, 0.28, 0.42)

PAL = dict(
    stone=(0.80, 0.76, 0.69), stone_d=(0.64, 0.60, 0.56), stone_b=(0.64, 0.70, 0.75),
    marble=(0.95, 0.92, 0.85),
    wood=(0.76, 0.51, 0.31), wood_d=(0.55, 0.36, 0.22), wood_l=(0.90, 0.71, 0.47), bark=(0.50, 0.34, 0.23),
    cream=(0.99, 0.94, 0.81), white=(0.97, 0.96, 0.92),
    red=(0.90, 0.31, 0.27), coral=(0.97, 0.53, 0.43), orange=(0.99, 0.62, 0.24), yellow=(0.99, 0.82, 0.30),
    leaf=(0.56, 0.78, 0.28), leaf_d=(0.36, 0.60, 0.23), moss=(0.47, 0.66, 0.30),
    teal=(0.25, 0.65, 0.65), teal_d=(0.19, 0.44, 0.47), iron=(0.23, 0.34, 0.37),
    blue=(0.36, 0.58, 0.88), navy=(0.29, 0.34, 0.60), purple=(0.60, 0.46, 0.82), pink=(0.97, 0.60, 0.72),
    lavender=(0.72, 0.64, 0.90),
    water=(0.37, 0.71, 0.91), water_d=(0.22, 0.48, 0.76), foam=(0.90, 0.97, 1.0),
    gold=(0.98, 0.77, 0.30), silver=(0.80, 0.83, 0.87), bronze=(0.84, 0.53, 0.32), metal=(0.55, 0.58, 0.60),
    rust=(0.68, 0.41, 0.27), glow=(1.0, 0.91, 0.58), soil=(0.44, 0.30, 0.20), glass=(0.74, 0.93, 0.95),
    terracotta=(0.86, 0.50, 0.34), dark=(0.20, 0.16, 0.18), straw=(0.93, 0.80, 0.50),
)


def tone(base, hi=0.30, lo=0.30):
    """Base colour, lighter as the surface faces the sky, darker (slightly cool) underneath."""
    base = tuple(base)
    top = mix(base, SKY, hi)
    bot = mix(mul(base, 1.0 - lo), SHADOW, 0.08)

    def fn(co, n):
        if n.z >= 0:
            return mix(base, top, ss(0.15, 0.95, n.z))
        return mix(base, bot, ss(0.0, -0.85, n.z))
    return fn


def jitter(col, amt, rng):
    k = 1.0 + rng.uniform(-amt, amt)
    return tuple(min(1.0, max(0.0, c * k + rng.uniform(-amt, amt) * 0.15)) for c in col)


# ═══ SDF PRIMITIVES WITH TIGHT BOUNDS ═════════════════════════════════════════
# sdf.round_box / cylinder / ellipsoid bound themselves with a cube of their largest size,
# which explodes the voxel grid for long thin parts. These wrappers keep the maths but
# give rotation-aware axis-aligned bounds.

def _R(rot):
    if not rot or all(a == 0 for a in rot):
        return None
    return np.array(Euler([math.radians(a) for a in rot]).to_matrix(), dtype=F32)


def _aabb(lo, hi, R=None, loc=(0, 0, 0)):
    lo = np.asarray(lo, F32)
    hi = np.asarray(hi, F32)
    c = (lo + hi) * 0.5
    h = (hi - lo) * 0.5
    if R is not None:
        c = R @ c
        h = np.abs(R) @ h
    c = c + np.asarray(loc, F32)
    return (c - h, c + h)


def sph(c, r):
    return sdf.sphere(c, r)


def ell(c, radii, rot=None):
    s = sdf.ellipsoid(c, radii, rot)
    r = np.asarray(radii, F32)
    return (s[0], _aabb(-r, r, _R(rot), c))


def box(c, half, r=0.1, rot=None):
    r = min(r, min(half) * 0.98)
    s = sdf.round_box(c, half, r, rot)
    h = np.asarray(half, F32)
    return (s[0], _aabb(-h, h, _R(rot), c))


def cyl(c, radius, hh, r=0.0, rot=None):
    r = min(r, radius * 0.98, hh * 0.98)
    s = sdf.cylinder(c, radius, hh, rot, rounding=r)
    return (s[0], _aabb((-radius, -radius, -hh), (radius, radius, hh), _R(rot), c))


def tor(c, major, minor, rot=None):
    s = sdf.torus(c, major, minor, rot)
    m = major + minor
    return (s[0], _aabb((-m, -m, -minor), (m, m, minor), _R(rot), c))


def cap(a, b, r):
    return sdf.capsule(tuple(a), tuple(b), r)


def rcone(a, b, ra, rb):
    return sdf.round_cone(tuple(a), tuple(b), ra, rb)


def rod(a, b, radius, r=0.0):
    """Capped cylinder between two points, edges rounded by r."""
    a = np.asarray(a, F32)
    b = np.asarray(b, F32)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    r = min(r, radius * 0.95, L * 0.45)
    a2 = a + u * r
    b2 = b - u * r
    rr = radius - r
    ba = b2 - a2
    baba = float(ba @ ba)

    def fn(P):
        pa = P - a2
        paba = pa @ ba
        x = np.linalg.norm(pa * baba - np.outer(paba, ba), axis=1) - rr * baba
        y = np.abs(paba - baba * 0.5) - baba * 0.5
        x2 = x * x
        y2 = y * y * baba
        d = np.where(np.maximum(x, y) < 0, -np.minimum(x2, y2), np.where(x > 0, x2, 0) + np.where(y > 0, y2, 0))
        return (np.sign(d) * np.sqrt(np.abs(d)) / baba - r).astype(F32)

    return (fn, (np.minimum(a, b) - radius, np.maximum(a, b) + radius))


def frustum(z0, z1, r0, r1, cx=0.0, cy=0.0, r=0.0):
    """Vertical capped cone from z0 (radius r0) to z1 (radius r1), edges rounded by r."""
    h = (z1 - z0) * 0.5 - r
    zc = (z0 + z1) * 0.5
    ra, rb = max(r0 - r, 1e-3), max(r1 - r, 1e-3)
    k1 = np.array([rb, h], F32)
    k2 = np.array([rb - ra, 2 * h], F32)
    k2d = float(k2 @ k2)

    def fn(P):
        qx = np.sqrt((P[:, 0] - cx) ** 2 + (P[:, 1] - cy) ** 2)
        qy = P[:, 2] - zc
        cax = qx - np.minimum(qx, np.where(qy < 0, ra, rb))
        cay = np.abs(qy) - h
        t = np.clip(((k1[0] - qx) * k2[0] + (k1[1] - qy) * k2[1]) / k2d, 0, 1)
        cbx = qx - k1[0] + k2[0] * t
        cby = qy - k1[1] + k2[1] * t
        s = np.where((cbx < 0) & (cay < 0), -1.0, 1.0)
        return (s * np.sqrt(np.minimum(cax * cax + cay * cay, cbx * cbx + cby * cby)) - r).astype(F32)

    m = max(r0, r1)
    return (fn, (np.array([cx - m, cy - m, z0], F32), np.array([cx + m, cy + m, z1], F32)))


def slab(zmin=None, zmax=None, size=400.0):
    """Half-space helper for INT(): keeps z >= zmin and/or z <= zmax (bounds are huge, only
    use as the second argument of INT, which keeps the first shape's bounds)."""
    def fn(P):
        d = np.full(len(P), -size, F32)
        if zmin is not None:
            d = np.maximum(d, zmin - P[:, 2])
        if zmax is not None:
            d = np.maximum(d, P[:, 2] - zmax)
        return d
    return (fn, (np.array([-size] * 3, F32), np.array([size] * 3, F32)))


def halfspace(normal, point):
    """Keeps the side the normal points AWAY from (d = dot(P - point, n))."""
    n = np.asarray(normal, F32)
    n = n / np.linalg.norm(n)
    p = np.asarray(point, F32)
    return (lambda P: ((P - p) @ n).astype(F32), (np.array([-400] * 3, F32), np.array([400] * 3, F32)))


# ── 2D shapes (u, v arrays -> distance) and extrusion ─────────────────────────

def c2(cx, cy, r):
    return lambda u, v: np.sqrt((u - cx) ** 2 + (v - cy) ** 2) - r


def b2(cx, cy, hx, hy, r=0.0):
    def f(u, v):
        qx = np.abs(u - cx) - hx + r
        qy = np.abs(v - cy) - hy + r
        return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - r
    return f


def poly2(pts):
    pts = np.asarray(pts, F32)
    n = len(pts)

    def f(u, v):
        d = (u - pts[0, 0]) ** 2 + (v - pts[0, 1]) ** 2
        s = np.ones_like(u)
        j = n - 1
        for i in range(n):
            e = pts[j] - pts[i]
            wx = u - pts[i, 0]
            wy = v - pts[i, 1]
            t = np.clip((wx * e[0] + wy * e[1]) / float(e @ e), 0, 1)
            bx = wx - e[0] * t
            by = wy - e[1] * t
            d = np.minimum(d, bx * bx + by * by)
            ca = v >= pts[i, 1]
            cb = v < pts[j, 1]
            cc = e[0] * wy > e[1] * wx
            flip = (ca & cb & cc) | (~ca & ~cb & ~cc)
            s = np.where(flip, -s, s)
            j = i
        return s * np.sqrt(d)
    return f


def u2(*fs):
    return lambda u, v: np.min(np.stack([f(u, v) for f in fs]), axis=0)


def i2(*fs):
    return lambda u, v: np.max(np.stack([f(u, v) for f in fs]), axis=0)


def sub2(a, *cut):
    return lambda u, v: np.max(np.stack([a(u, v)] + [-c(u, v) for c in cut]), axis=0)


_AXES = {"x": (1, 2, 0), "y": (0, 2, 1), "z": (0, 1, 2)}


def extrude(f2, lo2, hi2, d0, d1, axis="y", r=0.0, loc=(0, 0, 0), rot=None):
    """2D shape in the plane perpendicular to `axis` ('y': u=x, v=z), depth d0..d1 along it."""
    R = _R(rot)
    L = np.asarray(loc, F32)
    ia = _AXES[axis]
    wc = (d0 + d1) * 0.5
    wh = (d1 - d0) * 0.5 - r

    def fn(P):
        Q = P - L
        if R is not None:
            Q = Q @ R
        d2 = f2(Q[:, ia[0]], Q[:, ia[1]]) + r
        dw = np.abs(Q[:, ia[2]] - wc) - wh
        return (np.sqrt(np.maximum(d2, 0) ** 2 + np.maximum(dw, 0) ** 2) + np.minimum(np.maximum(d2, dw), 0) - r).astype(F32)

    lo = [0.0, 0.0, 0.0]
    hi = [0.0, 0.0, 0.0]
    lo[ia[0]], lo[ia[1]], lo[ia[2]] = lo2[0], lo2[1], d0
    hi[ia[0]], hi[ia[1]], hi[ia[2]] = hi2[0], hi2[1], d1
    return (fn, _aabb(lo, hi, R, loc))


def star2(cx, cy, ro, ri, n=5, phase=90.0):
    pts = []
    for i in range(n * 2):
        a = math.radians(phase + i * 180.0 / n)
        rr = ro if i % 2 == 0 else ri
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    return poly2(pts)


# ── combinators ───────────────────────────────────────────────────────────────

def U(*shapes, k=0.0):
    """Smooth union that only evaluates each child near its own bounds (fast for many parts)."""
    shapes = [s for s in shapes if s is not None]
    if len(shapes) == 1:
        return shapes[0]
    pad = k + 0.3

    def fn(P):
        d = np.full(len(P), 50.0, F32)
        for f, (lo, hi) in shapes:
            m = np.all((P >= lo - pad) & (P <= hi + pad), axis=1)
            if not m.any():
                continue
            idx = np.nonzero(m)[0]
            e = f(P[idx])
            dd = d[idx]
            if k <= 0:
                d[idx] = np.minimum(dd, e)
            else:
                h = np.maximum(k - np.abs(dd - e), 0.0) / k
                d[idx] = np.minimum(dd, e) - h * h * k * 0.25
        return d

    lo = np.min(np.stack([s[1][0] for s in shapes]), axis=0)
    hi = np.max(np.stack([s[1][1] for s in shapes]), axis=0)
    return (fn, (lo, hi))


def SUB(base, *cutters, k=0.0):
    out = base
    for c in cutters:
        out = sdf.smooth_subtract(out, c, k=k) if k > 0 else (
            (lambda a, b: (lambda P: np.maximum(a[0](P), -b[0](P))))(out, c), out[1])
    return out


def INT(a, b, k=0.0):
    if k > 0:
        s = sdf.smooth_intersect(a, b, k=k)
        return (s[0], a[1])
    return ((lambda P: np.maximum(a[0](P), b[0](P))), a[1])


def XF(shape, loc=(0, 0, 0), rot=None, scale=1.0):
    """Rigid transform (+ uniform scale) of a shape built around the origin."""
    R = _R(rot)
    L = np.asarray(loc, F32)
    s = float(scale)

    def fn(P):
        Q = P - L
        if R is not None:
            Q = Q @ R
        return shape[0](Q / s) * s

    lo, hi = shape[1]
    b = _aabb(np.asarray(lo) * s, np.asarray(hi) * s, R, loc)
    return (fn, b)


def grow(shape, amt):
    return (lambda P: shape[0](P) - amt, (shape[1][0] - amt, shape[1][1] + amt))


def bumps(shape, amp=0.05, freq=2.0, seed=1):
    return sdf.noise_bumps(shape, amplitude=amp, frequency=freq, seed=seed)


def chain(points, radii, k=0.05):
    if isinstance(radii, (int, float)):
        radii = [radii] * len(points)
    return U(*[rcone(points[i], points[i + 1], radii[i], radii[i + 1]) for i in range(len(points) - 1)], k=k)


def sag_points(a, b, sag, n=9):
    a, b = Vector(a), Vector(b)
    out = []
    for i in range(n):
        t = i / (n - 1)
        p = a.lerp(b, t)
        p.z -= sag * 4 * t * (1 - t)
        out.append(p)
    return out


def arc_points(a, b, lift, n=8):
    """Parabolic arc from a to b whose midpoint is raised by `lift`."""
    a, b = Vector(a), Vector(b)
    return [a.lerp(b, t) + Vector((0, 0, lift * 4 * t * (1 - t))) for t in (i / (n - 1) for i in range(n))]


# ═══ MESH HELPERS ═════════════════════════════════════════════════════════════

def decimate(obj, target):
    for _ in range(6):
        if fk.triangle_count(obj) <= target:
            break
        obj = fk.decimate_to(obj, target)
    return obj


def tube_mesh(points, radius, sides=6, name="tube_tmp"):
    """Low-poly tube along a polyline (ropes, strings, wires)."""
    bm = bmesh.new()
    pts = [Vector(p) for p in points]
    rings = []
    for i, p in enumerate(pts):
        d = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        x = d.cross(ref).normalized()
        y = d.cross(x).normalized()
        rings.append([bm.verts.new(p + (x * math.cos(a) + y * math.sin(a)) * radius)
                      for a in (2 * math.pi * s / sides for s in range(sides))])
    for i in range(len(rings) - 1):
        for s in range(sides):
            bm.faces.new((rings[i][s], rings[i][(s + 1) % sides], rings[i + 1][(s + 1) % sides], rings[i + 1][s]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return fk.mesh_object(name, bm)


def disc_mesh(radius, half_t, rings=10, segs=40, name="disc_tmp"):
    """Two-sided disc in the XZ plane (normal along Y) with even vertex density for painting."""
    bm = bmesh.new()
    faces = {}
    for side, y in ((-1, -half_t), (1, half_t)):
        centre = bm.verts.new((0, y, 0))
        grid = []
        for ri in range(1, rings + 1):
            rr = radius * ri / rings
            grid.append([bm.verts.new((math.cos(2 * math.pi * s / segs) * rr, y, math.sin(2 * math.pi * s / segs) * rr))
                         for s in range(segs)])
        for s in range(segs):
            bm.faces.new((centre, grid[0][s], grid[0][(s + 1) % segs]))
        for ri in range(rings - 1):
            for s in range(segs):
                bm.faces.new((grid[ri][s], grid[ri + 1][s], grid[ri + 1][(s + 1) % segs], grid[ri][(s + 1) % segs]))
        faces[side] = grid[-1]
    for s in range(segs):
        a, b = faces[-1][s], faces[-1][(s + 1) % segs]
        c, d = faces[1][(s + 1) % segs], faces[1][s]
        bm.faces.new((a, b, c, d))
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return fk.mesh_object(name, bm)


# ═══ ASSET BUILD ══════════════════════════════════════════════════════════════

class Part:
    """shape (SDF) or obj (ready mesh), colour or paint fn, optional instances.

    inst: list of (loc, rot_deg) or (loc, rot_deg, scale); cols: per-instance colours.
    w: share weight for the triangle budget; fixed: exact triangles (skips allocation)."""

    def __init__(self, shape=None, col=(1, 1, 1), voxel=0.05, w=1.0, inst=None, cols=None, obj=None,
                 paint=None, sharp=None, min_tris=40, fixed=None, hi=0.30, lo=0.30, smooth=3):
        self.shape, self.col, self.voxel, self.w = shape, col, voxel, w
        self.inst, self.cols, self.obj, self.paint = inst, cols, obj, paint
        self.sharp, self.min_tris, self.fixed, self.hi, self.lo = sharp, min_tris, fixed, hi, lo
        self.smooth = smooth


def _allocate(target, weights, mins, caps):
    def total(W):
        return sum(min(c, max(m, W * w)) for w, m, c in zip(weights, mins, caps))
    lo, hi = 0.0, 1e12
    for _ in range(80):
        mid = (lo + hi) * 0.5
        if total(mid) > target:
            hi = mid
        else:
            lo = mid
    return [min(c, max(m, lo * w)) for w, m, c in zip(weights, mins, caps)]


BUILT = {}


def build(name, parts, budget, ao=(1.0, 0.5), floor=True, center=True, target=0.93):
    t0 = time.time()
    metas = []
    for p in parts:
        if p.obj is not None:
            o = p.obj
        else:
            # voxel stair-stepping blocks edge collapses on thin parts: relax it first
            o = fk.smooth(sdf.to_mesh(f"{name}__tmp", p.shape, voxel=p.voxel), p.smooth)
        n = len(p.inst) if p.inst else 1
        area = sum(poly.area for poly in o.data.polygons)
        metas.append((o, n, area, fk.triangle_count(o)))
    free = [i for i, p in enumerate(parts) if p.fixed is None]
    fixed_total = sum((parts[i].fixed or 0) * metas[i][1] for i in range(len(parts)) if parts[i].fixed is not None)
    alloc = [0] * len(parts)
    if free:
        weights = [parts[i].w * max(metas[i][2], 1e-4) ** 0.8 * metas[i][1] for i in free]
        mins = [parts[i].min_tris * metas[i][1] for i in free]
        caps = [metas[i][3] * metas[i][1] for i in free]
        got = _allocate(budget * target - fixed_total, weights, mins, caps)
        for i, g in zip(free, got):
            alloc[i] = g
    pieces = []
    for i, p in enumerate(parts):
        o, n, _, _ = metas[i]
        per = p.fixed if p.fixed is not None else max(12, int(alloc[i] / n))
        raw = fk.triangle_count(o)
        o = decimate(o, per)
        if os.environ.get("KIT_DEBUG"):
            print(f"   part {i}: raw {raw} alloc {per} got {fk.triangle_count(o)} x{n}", flush=True)
        if p.sharp:
            o.data.set_sharp_from_angle(angle=math.radians(p.sharp))
        if not p.inst:
            fk.paint(o, p.paint or tone(p.col, p.hi, p.lo))
            pieces.append(o)
            continue
        for j, tr in enumerate(p.inst):
            me = o.data.copy()
            c = bpy.data.objects.new(f"{name}__inst", me)
            fk.link(c)
            loc, rot = tr[0], tr[1]
            sc = tr[2] if len(tr) > 2 else 1.0
            sc = (sc, sc, sc) if isinstance(sc, (int, float)) else sc
            fk.transform(c, loc, rot or (0, 0, 0), sc)
            col = p.cols[j] if p.cols else p.col
            fk.paint(c, p.paint or tone(col, p.hi, p.lo))
            pieces.append(c)
        bpy.data.objects.remove(o, do_unlink=True)
    obj = fk.join(pieces, name)
    if center:
        vs = np.empty(len(obj.data.vertices) * 3, F32)
        obj.data.vertices.foreach_get("co", vs)
        vs = vs.reshape(-1, 3)
        mid = (vs.min(axis=0) + vs.max(axis=0)) * 0.5
        fk.transform(obj, (-float(mid[0]), -float(mid[1]), -float(vs[:, 2].min()) if floor else 0.0))
    fk.bake_ao(obj, floor_z=0.0 if floor else None, samples=20, distance=ao[0], strength=ao[1])
    fk.box_uv(obj, 2.0)
    obj.data.materials.clear()
    tris = fk.triangle_count(obj)
    assert obj.name == name, obj.name
    assert tris <= budget, f"{name}: {tris} > {budget}"
    BUILT[name] = tris
    print(f"[kit_hub] {name:18s} {tris:5d} tris  ({time.time() - t0:.1f}s)", flush=True)
    return obj


# ═══ HUB ══════════════════════════════════════════════════════════════════════

def stream_shape(r0, z0, r1, z1, lift, rad0, rad1, n=7):
    pts = arc_points((r0, 0, z0), (r1, 0, z1), lift, n)
    radii = [rad0 + (rad1 - rad0) * i / (n - 1) for i in range(n)]
    return chain(pts, radii, k=0.05)


def a_fountain():
    P = []
    # basin: stone wall with a fat rounded lip, a teal tile band, a darker foot
    wall = SUB(cyl((0, 0, 0.8), 7.0, 0.8, r=0.3), cyl((0, 0, 1.6), 6.25, 1.2, r=0.2))
    lip = tor((0, 0, 1.55), 6.62, 0.46)
    P.append(Part(U(wall, lip, k=0.25), PAL["stone"], voxel=0.07, w=1.0))
    P.append(Part(cyl((0, 0, 0.16), 7.35, 0.16, r=0.1), PAL["stone_d"], voxel=0.07, w=0.4))
    band = SUB(cyl((0, 0, 0.72), 7.07, 0.2, r=0.06), cyl((0, 0, 0.72), 6.8, 0.4))
    P.append(Part(band, PAL["teal"], voxel=0.05, w=0.5))
    P.append(Part(cyl((0, 0, 0.8), 6.4, 0.45), PAL["water"], voxel=0.08, w=0.25, hi=0.2))
    # centre column + tier 2 chalice
    col1 = U(rcone((0, 0, 0.5), (0, 0, 4.4), 1.35, 0.75), tor((0, 0, 1.75), 1.12, 0.3), k=0.25)
    P.append(Part(col1, PAL["stone"], voxel=0.05, w=0.8))
    bowl2 = U(cyl((0, 0, 4.85), 3.9, 0.38, r=0.3), frustum(3.9, 4.8, 0.8, 3.7, r=0.1), k=0.45)
    bowl2 = SUB(bowl2, cyl((0, 0, 5.55), 3.35, 0.55, r=0.2))
    bowl2 = U(bowl2, tor((0, 0, 5.18), 3.62, 0.3), k=0.2)
    P.append(Part(bowl2, PAL["stone"], voxel=0.05, w=1.0))
    P.append(Part(cyl((0, 0, 5.02), 3.45, 0.1), PAL["water"], voxel=0.05, w=0.2, hi=0.2))
    # column 2 + tier 3
    col2 = U(rcone((0, 0, 5.0), (0, 0, 7.2), 0.7, 0.45), tor((0, 0, 6.0), 0.58, 0.18), k=0.15)
    P.append(Part(col2, PAL["stone"], voxel=0.04, w=0.6))
    bowl3 = U(cyl((0, 0, 7.45), 2.25, 0.26, r=0.2), frustum(6.9, 7.4, 0.45, 2.1, r=0.06), k=0.3)
    bowl3 = SUB(bowl3, cyl((0, 0, 7.95), 1.85, 0.3, r=0.12))
    bowl3 = U(bowl3, tor((0, 0, 7.68), 2.04, 0.2), k=0.12)
    P.append(Part(bowl3, PAL["stone"], voxel=0.04, w=0.9))
    P.append(Part(cyl((0, 0, 7.66), 1.95, 0.06), PAL["water"], voxel=0.04, w=0.15, hi=0.2))
    # the little stone monster statue, cheering, spouting water
    z = 7.6
    body = ell((0, 0.05, z + 0.75), (0.95, 0.85, 0.8))
    head = ell((0, -0.12, z + 1.8), (0.92, 0.86, 0.8))
    ears = U(rcone((0.52, -0.05, z + 2.35), (0.85, 0.0, z + 2.95), 0.3, 0.13),
             rcone((-0.52, -0.05, z + 2.35), (-0.85, 0.0, z + 2.95), 0.3, 0.13), k=0.0)
    arms = U(cap((0.75, -0.05, z + 1.0), (1.2, -0.3, z + 1.75), 0.22), cap((-0.75, -0.05, z + 1.0), (-1.2, -0.3, z + 1.75), 0.22))
    feet = U(ell((0.45, -0.62, z + 0.18), (0.32, 0.36, 0.22)), ell((-0.45, -0.62, z + 0.18), (0.32, 0.36, 0.22)))
    cheeks = U(sph((0.5, -0.72, z + 1.55), 0.3), sph((-0.5, -0.72, z + 1.55), 0.3))
    statue = U(body, head, ears, arms, feet, cheeks, k=0.28)
    statue = SUB(statue, sph((0, -0.98, z + 1.52), 0.22), sph((0.34, -0.93, z + 2.0), 0.13),
                 sph((-0.34, -0.93, z + 2.0), 0.13), k=0.06)
    P.append(Part(statue, PAL["stone_b"], voxel=0.03, w=2.2, hi=0.35))
    # water: jet from the statue's mouth into tier 2, overflow streams, splash foam
    jet = chain(arc_points((0, -1.0, z + 1.52), (0, -2.9, 5.1), 0.9, 8), [0.17, 0.2, 0.2, 0.19, 0.18, 0.17, 0.16, 0.2], k=0.05)
    P.append(Part(jet, PAL["foam"], voxel=0.035, w=0.8, hi=0.1))
    s2 = stream_shape(3.72, 5.25, 5.25, 1.05, 0.25, 0.2, 0.17)
    P.append(Part(s2, PAL["foam"], voxel=0.04, w=0.8, hi=0.1,
                  inst=[((0, 0, 0), (0, 0, 30 + 60 * i)) for i in range(6)]))
    s3 = stream_shape(2.0, 7.72, 2.75, 5.05, 0.12, 0.13, 0.12)
    P.append(Part(s3, PAL["foam"], voxel=0.03, w=0.8, hi=0.1,
                  inst=[((0, 0, 0), (0, 0, 60 * i)) for i in range(6)]))
    splash = ell((0, 0, 0), (0.55, 0.55, 0.14))
    spl = [((5.25 * math.cos(math.radians(30 + 60 * i)), 5.25 * math.sin(math.radians(30 + 60 * i)), 1.2), (0, 0, 0)) for i in range(6)]
    spl.append(((0, -2.9, 5.14), (0, 0, 0), 0.7))
    P.append(Part(splash, PAL["white"], voxel=0.04, w=0.5, inst=spl, min_tris=30))
    return build("Fountain", P, LARGE, ao=(1.4, 0.5))


def a_lamp_post():
    iron, gold = PAL["iron"], PAL["gold"]
    P = [
        Part(U(frustum(0, 1.0, 0.85, 0.55, r=0.14), tor((0, 0, 1.0), 0.5, 0.14), k=0.1), iron, voxel=0.03, w=1.0),
        Part(U(cap((0, 0, 0.9), (0, 0, 7.2), 0.24), tor((0, 0, 3.6), 0.27, 0.12), tor((0, 0, 6.7), 0.27, 0.12),
               frustum(6.95, 7.45, 0.26, 0.6, r=0.1), k=0.1), iron, voxel=0.03, w=1.0),
        Part(ell((0, 0, 8.02), (0.52, 0.52, 0.62)), PAL["glow"], voxel=0.03, w=0.6, hi=0.4, lo=0.1),
        Part(U(cyl((0, 0, 7.45), 0.66, 0.1, r=0.06), frustum(8.55, 9.05, 0.9, 0.22, r=0.1),
               *[rod((0.6 * math.cos(a), 0.6 * math.sin(a), 7.4), (0.6 * math.cos(a), 0.6 * math.sin(a), 8.62), 0.09, r=0.04)
                 for a in (math.radians(45 + 90 * i) for i in range(4))], k=0.05), iron, voxel=0.025, w=1.0),
        Part(U(sph((0, 0, 9.22), 0.22), tor((0, 0, 8.58), 0.84, 0.08), k=0.0), gold, voxel=0.025, w=0.5),
    ]
    return build("Lamp_Post", P, SMALL, ao=(0.6, 0.45))


def a_bench_park():
    wood, iron = PAL["wood"], PAL["iron"]
    slats = U(*[box((0, y, 1.82), (2.95, 0.27, 0.11), r=0.08) for y in (-0.6, 0.0, 0.6)])
    back = U(box((0, 0.98, 2.7), (2.95, 0.1, 0.26), r=0.08, rot=(-12, 0, 0)),
             box((0, 1.12, 3.4), (2.95, 0.1, 0.26), r=0.08, rot=(-12, 0, 0)))
    frames = []
    for x in (-2.45, 2.45):
        frames += [
            rcone((x, -0.72, 0.1), (x, -0.62, 1.75), 0.16, 0.13),
            chain([(x, 0.78, 0.1), (x, 0.82, 1.7), (x, 1.02, 2.6), (x, 1.22, 3.75)], [0.16, 0.14, 0.13, 0.12], k=0.05),
            cap((x, -0.95, 2.45), (x, 0.9, 2.6), 0.13),
            sph((x, -1.0, 2.42), 0.2),
            cap((x, -0.7, 1.62), (x, 0.85, 1.62), 0.1),
            ell((x, -0.75, 0.08), (0.24, 0.34, 0.1)), ell((x, 0.8, 0.08), (0.24, 0.34, 0.1)),
        ]
    P = [
        Part(slats, PAL["wood"], voxel=0.03, w=1.0),
        Part(back, PAL["wood"], voxel=0.03, w=1.0),
        Part(U(*frames, k=0.08), iron, voxel=0.025, w=1.2),
    ]
    return build("Bench_Park", P, SMALL, ao=(0.7, 0.5))


def a_treasure_chest():
    wood, gold = PAL["wood"], PAL["gold"]
    body = box((0, 0, 0.78), (1.5, 1.0, 0.78), r=0.12)
    lid = U(INT(cyl((0, 0, 1.55), 1.0, 1.48, r=0.1, rot=(0, 90, 0)), slab(zmin=1.55)),
            box((0, 0, 1.6), (1.48, 1.0, 0.1), r=0.06), k=0.05)
    bands = []
    for x in (-0.95, 0.95):
        bands.append(box((x, 0, 0.78), (0.15, 1.05, 0.8), r=0.05))
        bands.append(INT(cyl((x, 0, 1.55), 1.08, 0.15, r=0.05, rot=(0, 90, 0)), slab(zmin=1.5)))
    trim = U(box((0, 0, 1.52), (1.56, 1.07, 0.09), r=0.06), box((0, 0, 0.1), (1.56, 1.07, 0.1), r=0.06))
    plate = box((0, -1.06, 1.42), (0.3, 0.1, 0.38), r=0.1)
    P = [
        Part(body, wood, voxel=0.025, w=1.0),
        Part(lid, PAL["wood_l"], voxel=0.025, w=1.0),
        Part(U(*bands, trim, plate), gold, voxel=0.02, w=1.3),
        Part(U(ell((0, -1.16, 1.48), (0.08, 0.04, 0.08)), box((0, -1.16, 1.34), (0.04, 0.03, 0.1), r=0.03)),
             PAL["dark"], voxel=0.015, w=0.3, min_tris=30),
    ]
    return build("Treasure_Chest", P, SMALL, ao=(0.5, 0.5))


def a_portal():
    cz = PORTAL_DISC_CENTRE[2]
    Ri, Ro, N = 4.55, 5.95, 14
    half_t = 1.05

    def ring_blocks(parity):
        period = 2 * math.pi / N
        gap = 0.07

        def f(u, v):
            du, dv = u, v - cz
            rho = np.sqrt(du * du + dv * dv)
            phi = np.arctan2(dv, du) + period * 0.5 + (period if parity else 0.0)
            phi = np.mod(phi, 2 * period) - period
            d_rad = np.abs(rho - (Ri + Ro) * 0.5) - (Ro - Ri) * 0.5
            d_ang = (np.abs(phi) - (period * 0.5)) * rho + gap
            return np.sqrt(np.maximum(d_rad, 0) ** 2 + np.maximum(d_ang, 0) ** 2) + np.minimum(np.maximum(d_rad, d_ang), 0)
        s = extrude(f, (-Ro, cz - Ro), (Ro, cz + Ro), -half_t, half_t, axis="y", r=0.2)
        return INT(s, slab(zmin=0.6))

    plinth = box((0, 0, 0.45), (6.3, 1.75, 0.45), r=0.22)
    feet = U(box((5.2, 0, 1.6), (1.0, 1.35, 1.0), r=0.3), box((-5.2, 0, 1.6), (1.0, 1.35, 1.0), r=0.3))
    key = extrude(poly2([(-0.95, cz + Ri - 0.1), (0.95, cz + Ri - 0.1), (1.35, cz + Ro + 0.55), (-1.35, cz + Ro + 0.55)]),
                  (-1.4, cz + Ri - 0.2), (1.4, cz + Ro + 0.6), -1.3, 1.3, axis="y", r=0.22)
    cradle = U(ell((0, 0, cz + Ro + 0.65), (0.8, 0.55, 0.3)), k=0.0)
    gem = U(rcone((0, 0, cz + Ro + 0.55), (0, 0, cz + Ro + 1.5), 0.08, 0.62), rcone((0, 0, cz + Ro + 1.5), (0, 0, cz + Ro + 2.35), 0.62, 0.05), k=0.1)
    runes = []
    for i in range(N):
        a = 2 * math.pi * (i + 0.5) / N
        x, zz = math.cos(a) * (Ri + Ro) * 0.5, cz + math.sin(a) * (Ri + Ro) * 0.5
        if zz < 1.6:
            continue
        for y in (-half_t - 0.02, half_t + 0.02):
            runes.append(((x, y, zz), (90, 0, 0)))
    moss = U(ell((-3.2, -0.2, cz + 4.95), (1.0, 1.2, 0.35), rot=(0, 32, 0)),
             ell((4.3, 0.3, cz + 4.0), (0.8, 1.1, 0.3), rot=(0, -48, 0)),
             ell((-5.5, -0.3, 2.75), (0.7, 1.0, 0.35)), k=0.0)
    moss = bumps(moss, 0.06, 4.0, seed=3)
    rng = random.Random(4)
    P = [
        Part(plinth, PAL["stone_d"], voxel=0.06, w=1.0),
        Part(feet, PAL["stone"], voxel=0.06, w=0.8),
        Part(ring_blocks(0), PAL["stone"], voxel=0.05, w=1.3),
        Part(ring_blocks(1), mix(PAL["stone"], PAL["stone_b"], 0.45), voxel=0.05, w=1.3),
        Part(key, PAL["stone"], voxel=0.05, w=0.8),
        Part(cradle, PAL["gold"], voxel=0.04, w=0.3),
        Part(gem, (0.55, 0.88, 0.95), voxel=0.03, w=0.4, sharp=25, hi=0.4, lo=0.15),
        Part(cyl((0, 0, 0), 0.2, 0.06, r=0.03), (0.62, 0.92, 0.98), voxel=0.02, w=0.2, inst=runes, min_tris=20, fixed=24, hi=0.3, lo=0.05),
        Part(moss, PAL["moss"], voxel=0.05, w=0.6),
    ]
    arch = build("Portal_Arch", P, LARGE, ao=(1.2, 0.5), center=False)

    disc = disc_mesh(Ri + 0.12, 0.14, rings=11, segs=44)
    fk.transform(disc, PORTAL_DISC_CENTRE)
    c_edge, c_mid, c_core = (0.36, 0.52, 0.92), (0.52, 0.84, 0.96), (0.96, 0.98, 1.0)
    c_violet = (0.66, 0.46, 0.92)

    def swirl(co, n):
        du, dv = co.x, co.z - cz
        rho = math.sqrt(du * du + dv * dv) / (Ri + 0.12)
        phi = math.atan2(dv, du)
        t = 0.5 + 0.5 * math.sin(3 * phi + rho * 7.5)
        base = mix(c_edge, c_violet, 0.5 + 0.5 * math.sin(phi + 1.0)) if rho > 0.6 else c_mid
        arm = mix(base, c_mid, t * 0.8)
        return mix(c_core, arm, ss(0.05, 0.55, rho))
    return arch, build("Portal_Disc", [Part(obj=disc, paint=swirl, fixed=10 ** 6)], MEDIUM, ao=(0.3, 0.0), floor=False, center=False)


def a_market_stall():
    P = []
    wood, wood_d, wood_l = PAL["wood"], PAL["wood_d"], PAL["wood_l"]
    P.append(Part(box((0, -0.9, 1.55), (4.3, 1.1, 1.55), r=0.15), wood_d, voxel=0.05, w=0.6))
    planks = [box((0, -2.02, 0.5 + i * 1.0), (4.4, 0.1, 0.44), r=0.08) for i in range(3)]
    P.append(Part(U(*planks), wood, voxel=0.04, w=0.8,
                  inst=None))
    P.append(Part(box((0, -1.0, 3.2), (4.75, 1.45, 0.15), r=0.1), wood_l, voxel=0.04, w=0.7))
    posts = [rod((x, y, 0), (x, y, 7.05 if y < 0 else 7.95), 0.22, r=0.08) for x in (-4.5, 4.5) for y in (-2.2, 2.2)]
    P.append(Part(U(*posts), wood_d, voxel=0.035, w=0.8))
    back = U(box((0, 2.2, 2.2), (4.3, 0.18, 2.2), r=0.12), box((0, 1.85, 3.9), (4.3, 0.45, 0.09), r=0.06))
    P.append(Part(back, wood, voxel=0.04, w=0.6))
    jars = [((x, 1.85, 4.0), (0, 0, 0)) for x in (-3.0, -1.5, 1.5, 3.0)]
    P.append(Part(U(cyl((0, 0, 0.38), 0.34, 0.38, r=0.15), cyl((0, 0, 0.82), 0.25, 0.1, r=0.04)), PAL["glass"], voxel=0.025,
                  inst=jars, cols=[PAL["coral"], PAL["yellow"], PAL["leaf"], PAL["pink"]], w=0.4, min_tris=40))
    # awning: sloped canopy with red stripes and a scalloped edge
    tilt = math.degrees(math.atan2(1.35, 6.2))
    aw = box((0, -0.55, 7.55), (5.05, 3.15, 0.13), r=0.1, rot=(tilt, 0, 0))
    P.append(Part(aw, PAL["cream"], voxel=0.035, w=1.0))
    shell = grow(aw, 0.035)
    reds = U(*[box((-4.375 + 1.25 * i, -0.55, 7.55), (0.625, 3.6, 2.0), r=0.0) for i in range(0, 8, 2)])
    P.append(Part(INT(shell, reds), PAL["red"], voxel=0.035, w=1.0))
    zf = 7.55 - math.sin(math.radians(tilt)) * 3.15
    yf = -0.55 - math.cos(math.radians(tilt)) * 3.15
    sc = extrude(i2(c2(0, 0, 0.64), b2(0, -1, 2, 1)), (-0.7, -0.7), (0.7, 0.05), -0.07, 0.07, axis="y", r=0.03)
    P.append(Part(sc, PAL["red"], voxel=0.02, w=0.4, min_tris=30,
                  inst=[((-4.375 + 1.25 * i, yf, zf), (0, 0, 0)) for i in range(0, 8, 2)]))
    P.append(Part(sc, PAL["cream"], voxel=0.02, w=0.4, min_tris=30,
                  inst=[((-4.375 + 1.25 * i, yf, zf), (0, 0, 0)) for i in range(1, 8, 2)]))
    ridge = cap((-5.1, 2.6, 8.05), (5.1, 2.6, 8.05), 0.2)
    P.append(Part(ridge, PAL["red"], voxel=0.03, w=0.3))
    # produce crates on the counter + a crate and sack on the ground
    crate = SUB(box((0, 0, 0.45), (0.95, 0.7, 0.45), r=0.08), box((0, 0, 0.75), (0.8, 0.55, 0.45), r=0.05))
    P.append(Part(crate, wood_l, voxel=0.03, w=0.6, inst=[((-2.7, -1.3, 3.35), (0, 0, 6)), ((2.7, -1.3, 3.35), (0, 0, -5))]))
    fruit = sph((0, 0, 0), 0.3)
    apples = [((-2.7 + dx, -1.3 + dy, 4.08 + dz), (0, 0, 0)) for dx, dy, dz in
              ((-0.45, -0.25, 0), (0.15, -0.25, 0), (0.55, 0.2, 0), (-0.25, 0.25, 0), (0.1, 0.0, 0.3))]
    P.append(Part(fruit, PAL["red"], voxel=0.02, w=0.4, inst=apples, min_tris=40))
    oranges = [((2.7 + dx, -1.3 + dy, 4.08 + dz), (0, 0, 0)) for dx, dy, dz in
               ((-0.45, -0.25, 0), (0.15, -0.25, 0), (0.55, 0.2, 0), (-0.25, 0.25, 0), (0.1, 0.0, 0.3))]
    P.append(Part(fruit, PAL["orange"], voxel=0.02, w=0.4, inst=oranges, min_tris=40))
    melon = ell((0, -1.2, 3.95), (0.75, 0.6, 0.6))
    P.append(Part(melon, (0.45, 0.72, 0.3), voxel=0.03, w=0.4))
    gcrate = box((0, 0, 0.8), (0.8, 0.8, 0.8), r=0.1)
    P.append(Part(gcrate, wood_l, voxel=0.035, w=0.5, inst=[((-3.3, -3.35, 0), (0, 0, 12))]))
    sack = U(ell((0, 0, 0.75), (0.75, 0.65, 0.75)), rcone((0, 0, 1.3), (0, 0, 1.75), 0.3, 0.18), k=0.2)
    P.append(Part(bumps(sack, 0.03, 5.0), PAL["straw"], voxel=0.035, w=0.5, inst=[((3.4, -3.2, 0), (0, 0, 0))]))
    return build("Market_Stall", P, LARGE, ao=(1.0, 0.5))


# ═══ REGISTRY ═════════════════════════════════════════════════════════════════

BUILDERS = [
    ("Fountain", a_fountain), ("Lamp_Post", a_lamp_post), ("Bench_Park", a_bench_park),
    ("Market_Stall", a_market_stall), ("Portal_Arch", a_portal),
    ("Treasure_Chest", a_treasure_chest),
]
ORDER = [
    "Fountain", "Parade_Runway", "Parade_Arch", "Research_Board", "Quest_Board", "Market_Stall", "Portal_Arch",
    "Portal_Disc", "Lamp_Post", "Bench_Park", "Planter_Box", "Balloon_Cluster", "Bunting_Span", "Tent_Striped",
    "Statue_Pedestal",
    "Nest", "Food_Bowl", "Pet_Bed", "Pond_Small", "StonePath_Tile", "Garden_Bed", "Greenhouse", "Observatory",
    "Treehouse", "Windmill", "Windmill_Sails", "Lantern_String", "Trophy_Shelf", "Sanctuary_Sign",
    "Race_StartGate", "Race_Ring", "Obstacle_Hurdle", "Obstacle_Bumper", "Smash_Crate", "Smash_Pillar",
    "Treasure_Chest", "Podium", "Balance_Beam",
]


# ═══ CONTACT SHEET ════════════════════════════════════════════════════════════

def _ref_capsule():
    o = sdf.to_mesh("REF_Capsule", cap((0, 0, 1.0), (0, 0, 4.0), 1.0), voxel=0.08)
    o = decimate(o, 400)
    fk.solid_color(o, (0.62, 0.55, 0.78))
    fk.preview_tint(o, (1, 1, 1))
    return o


def render_sheet(names, out, cols=4, tile=420, yaw=-32.0, pitch=20.0):
    scene = bpy.context.scene
    fk.preview_studio(floor_color=(0.86, 0.9, 0.8))
    bpy.data.objects["PreviewFloor"].scale = (8, 8, 1)
    # famkit's studio is tuned for greyscale-tinted creatures; real final colours clip, so
    # dim it until a white surface in full sun sits just under 1.0
    bpy.data.objects["KeyLight"].data.energy = 2.3
    bpy.data.objects["FillLight"].data.energy = 0.6
    bg = next(n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[1].default_value = 0.6
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    ref = _ref_capsule()
    label = bpy.data.objects.new("REF_Label", bpy.data.curves.new("REF_Label", "FONT"))
    fk.link(label)
    mat = bpy.data.materials.new("REF_LabelMat")
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.03, 1)
    bsdf.inputs["Roughness"].default_value = 1.0
    label.data.materials.append(mat)
    label.data.size = 0.042
    kit = [bpy.data.objects[n] for n in names]
    for o in kit:
        fk.preview_tint(o, (1, 1, 1))
    tmp = os.path.join(os.path.dirname(out), "_kit_hub_tile.png")
    tiles = []
    for name in names:
        o = bpy.data.objects[name]
        for other in kit:
            other.hide_render = other is not o
        vs = np.empty(len(o.data.vertices) * 3, F32)
        o.data.vertices.foreach_get("co", vs)
        vs = vs.reshape(-1, 3)
        lo, hi = vs.min(axis=0), vs.max(axis=0)
        ref.location = (float(hi[0]) + 1.6, float(lo[1] + hi[1]) * 0.5, 0.0)
        lo2 = np.minimum(lo, np.array([hi[0] + 0.6, (lo[1] + hi[1]) * 0.5 - 1, 0], F32))
        hi2 = np.maximum(hi, np.array([hi[0] + 2.6, (lo[1] + hi[1]) * 0.5 + 1, 5], F32))
        centre = (lo2 + hi2) * 0.5
        radius = float(np.linalg.norm(hi2 - lo2)) * 0.5
        dist = radius / math.sin(math.radians(19.5)) * 0.97
        cam = fk.look_setup(target=tuple(float(c) for c in centre), distance=dist, yaw=yaw, pitch=pitch, lens=50)
        cam.data.clip_start = 0.1
        cam.data.clip_end = dist * 6
        label.parent = cam
        label.location = (-0.34, -0.345, -1.0)
        label.rotation_euler = (0, 0, 0)
        label.data.body = f"{name}  ({BUILT.get(name, fk.triangle_count(o))})"
        fk.render_png(tmp, res=(tile, tile))
        img = bpy.data.images.load(tmp, check_existing=False)
        tiles.append(np.array(img.pixels[:], dtype=np.float32).reshape(tile, tile, 4))
        bpy.data.images.remove(img)
    os.remove(tmp)
    blank = np.ones((tile, tile, 4), np.float32)
    while len(tiles) % cols:
        tiles.append(blank)
    rows = [np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)]
    sheet = np.concatenate(rows[::-1], axis=0)
    h, w = sheet.shape[:2]
    img = bpy.data.images.new("_kit_sheet", width=w, height=h, alpha=True)
    img.pixels = sheet.ravel()
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    for o in kit:
        o.hide_render = False
    print(f"[kit_hub] sheet -> {out}", flush=True)


# ═══ MAIN ═════════════════════════════════════════════════════════════════════

def main():
    only = [s for s in os.environ.get("KIT_ONLY", "").split(",") if s]
    t0 = time.time()
    for name, fn in BUILDERS:
        if only and name not in only:
            continue
        fn()
    names = [n for n in ORDER if n in bpy.data.objects]
    if only:
        sheet = os.environ.get("KIT_SHEET")
        if sheet:
            render_sheet(names, sheet, cols=int(os.environ.get("KIT_COLS", "3")), tile=int(os.environ.get("KIT_TILE", "460")))
        print(f"[kit_hub] partial build done in {time.time() - t0:.0f}s", flush=True)
        return
    missing = [n for n in ORDER if n not in bpy.data.objects]
    assert not missing, f"missing assets: {missing}"
    objs = [bpy.data.objects[n] for n in ORDER]
    path = fk.export_fbx(objs, FBX_NAME)
    print(f"[kit_hub] exported {len(objs)} objects -> {path}", flush=True)
    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    render_sheet(ORDER, PREVIEW, cols=5, tile=280)
    for n in ORDER:
        print(f"[kit_hub] {n}: {BUILT[n]}")
    print(f"[kit_hub] done in {time.time() - t0:.0f}s", flush=True)


main()
