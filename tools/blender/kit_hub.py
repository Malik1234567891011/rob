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


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb_paint(obj, fn):
    """fk.paint writes ByteColorAttribute.color, which is SCENE LINEAR; Blender re-encodes it
    to sRGB bytes (what the FBX carries). Palette values here are real sRGB, so linearise."""
    return fk.paint(obj, lambda co, n: tuple(_lin(x) for x in fn(co, n)))


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

def _verts(o, offset=(0, 0, 0)):
    vs = np.empty(len(o.data.vertices) * 3, F32)
    o.data.vertices.foreach_get("co", vs)
    return vs.reshape(-1, 3) + np.asarray(offset, F32)


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
    fixed_total = sum(min(parts[i].fixed, metas[i][3]) * metas[i][1] for i in range(len(parts)) if parts[i].fixed is not None)
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
            srgb_paint(o, p.paint or tone(p.col, p.hi, p.lo))
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
            srgb_paint(c, p.paint or tone(col, p.hi, p.lo))
            pieces.append(c)
        bpy.data.objects.remove(o, do_unlink=True)
    obj = fk.join(pieces, name)
    if center:
        vs = np.empty(len(obj.data.vertices) * 3, F32)
        obj.data.vertices.foreach_get("co", vs)
        vs = vs.reshape(-1, 3)
        mid = (vs.min(axis=0) + vs.max(axis=0)) * 0.5
        fk.transform(obj, (-float(mid[0]), -float(mid[1]), -float(vs[:, 2].min()) if floor else 0.0))
    elif floor:
        # modelled in place (paired with another object): snap sub-voxel overshoot onto the ground
        for v in obj.data.vertices:
            if -0.12 < v.co.z < 0.0:
                v.co.z = 0.0
    fk.bake_ao(obj, floor_z=0.0 if floor else None, samples=20, distance=ao[0], strength=ao[1])
    fk.box_uv(obj, 2.0)
    obj.data.materials.clear()
    tris = fk.triangle_count(obj)
    assert obj.name == name, obj.name
    assert tris <= budget, f"{name}: {tris} > {budget}"
    BUILT[name] = tris
    vs = _verts(obj)
    size = vs.max(axis=0) - vs.min(axis=0)
    print(f"[kit_hub] {name:18s} {tris:5d} tris  size {size[0]:5.1f} x {size[1]:5.1f} x {size[2]:5.1f}  z {vs[:, 2].min():5.2f}..{vs[:, 2].max():5.2f}  ({time.time() - t0:.1f}s)", flush=True)
    return obj


# ═══ HUB ══════════════════════════════════════════════════════════════════════

def fall_points(r0, z0, r1, z1, n=8, x_pow=0.7):
    """Water leaving a spout horizontally then falling: radius eases out, height drops as t^2."""
    return [Vector((r0 + (r1 - r0) * (t ** x_pow), 0, z0 - (z0 - z1) * t * t)) for t in (i / (n - 1) for i in range(n))]


def stream_shape(r0, z0, r1, z1, rad0, rad1, n=8):
    pts = fall_points(r0, z0, r1, z1, n)
    radii = [rad0 + (rad1 - rad0) * (i / (n - 1)) ** 1.5 for i in range(n)]
    return chain(pts, radii, k=0.08)


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
    z = 7.62
    q = 1.18
    def S(x, y, zz):
        return (x * q, y * q, z + zz * q)
    body = ell(S(0, 0.05, 0.75), (0.95 * q, 0.85 * q, 0.8 * q))
    head = ell(S(0, -0.12, 1.8), (0.95 * q, 0.86 * q, 0.8 * q))
    ears = U(rcone(S(0.55, -0.02, 2.3), S(1.05, 0.05, 2.75), 0.3 * q, 0.14 * q),
             rcone(S(-0.55, -0.02, 2.3), S(-1.05, 0.05, 2.75), 0.3 * q, 0.14 * q))
    horns = U(rcone(S(0.25, -0.25, 2.45), S(0.32, -0.3, 3.05), 0.17 * q, 0.07 * q),
              rcone(S(-0.25, -0.25, 2.45), S(-0.32, -0.3, 3.05), 0.17 * q, 0.07 * q))
    arms = U(cap(S(0.75, -0.05, 1.0), S(1.25, -0.3, 1.8), 0.24 * q), cap(S(-0.75, -0.05, 1.0), S(-1.25, -0.3, 1.8), 0.24 * q))
    feet = U(ell(S(0.45, -0.62, 0.18), (0.34 * q, 0.38 * q, 0.22 * q)), ell(S(-0.45, -0.62, 0.18), (0.34 * q, 0.38 * q, 0.22 * q)))
    belly = ell(S(0, -0.55, 0.72), (0.62 * q, 0.4 * q, 0.55 * q))
    tail = rcone(S(0, 0.8, 0.35), S(0, 1.35, 0.9), 0.24 * q, 0.1 * q)
    statue = U(body, head, ears, arms, feet, belly, tail, k=0.26)
    statue = U(statue, horns, k=0.08)
    statue = SUB(statue, sph(S(0, -0.97, 1.5), 0.24 * q), sph(S(0.36, -0.9, 2.0), 0.14 * q),
                 sph(S(-0.36, -0.9, 2.0), 0.14 * q), k=0.06)
    P.append(Part(statue, mix(PAL["stone_d"], PAL["moss"], 0.18), voxel=0.03, w=2.4, hi=0.35))
    # water: an arcing jet from the statue's mouth, spouts overflowing each tier, splash foam
    water_l = (0.66, 0.87, 0.98)
    mouth = Vector(S(0, -1.02, 1.5))
    jet = chain(arc_points(mouth, (0, -2.95, 5.05), 1.1, 9), [0.2, 0.22, 0.23, 0.23, 0.23, 0.22, 0.22, 0.24, 0.3], k=0.08)
    P.append(Part(jet, water_l, voxel=0.035, w=0.7, hi=0.35))
    s2 = stream_shape(4.25, 4.95, 5.35, 1.1, 0.2, 0.32)
    P.append(Part(s2, water_l, voxel=0.04, w=0.7, hi=0.35,
                  inst=[((0, 0, 0), (0, 0, 30 + 60 * i)) for i in range(6)]))
    spout = rod((3.5, 0, 4.95), (4.4, 0, 4.95), 0.3, r=0.1)
    P.append(Part(SUB(spout, cap((3.7, 0, 4.95), (4.7, 0, 4.95), 0.17)), PAL["stone"], voxel=0.03, w=0.4, min_tris=40,
                  inst=[((0, 0, 0), (0, 0, 30 + 60 * i)) for i in range(6)]))
    s3 = stream_shape(2.2, 7.78, 2.85, 5.1, 0.14, 0.22, n=7)
    P.append(Part(s3, water_l, voxel=0.03, w=0.6, hi=0.35,
                  inst=[((0, 0, 0), (0, 0, 60 * i + 30)) for i in range(0, 6) if i != 4]))
    splash = U(ell((0, 0, 0), (0.62, 0.62, 0.12)), sph((0.18, 0.1, 0.12), 0.2), sph((-0.2, -0.05, 0.1), 0.17), k=0.1)
    spl = [((5.35 * math.cos(math.radians(30 + 60 * i)), 5.35 * math.sin(math.radians(30 + 60 * i)), 1.28), (0, 0, 60 * i)) for i in range(6)]
    spl += [((2.85 * math.cos(math.radians(30 + 60 * i)), 2.85 * math.sin(math.radians(30 + 60 * i)), 5.14), (0, 0, 60 * i), 0.6)
            for i in range(6) if i != 4]
    spl.append(((0, -2.95, 5.14), (0, 0, 0), 0.75))
    P.append(Part(splash, PAL["white"], voxel=0.03, w=0.5, inst=spl, min_tris=36))
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


def crate_shape(h):
    """Chunky slatted crate, base at z=0, half size h: frame edges proud of recessed slats."""
    core = box((0, 0, h), (h * 0.92, h * 0.92, h * 0.98), r=h * 0.08)
    grooves = [box((0, 0, h + dz * h), (h * 1.2, h * 1.2, h * 0.035), r=0.0) for dz in (-0.33, 0.33)]
    grooves += [box((dx * h, 0, h * 2.0), (h * 0.035, h * 1.2, h * 0.08), r=0.0) for dx in (-0.3, 0.3)]
    core = SUB(core, U(*grooves), k=0.02)
    frame = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            frame.append(box((sx * h * 0.88, sy * h * 0.88, h), (h * 0.12, h * 0.12, h), r=h * 0.08))
    for sz in (0.06, 1.94):
        frame.append(box((0, h * 0.88, sz * h), (h, h * 0.12, h * 0.1), r=h * 0.06))
        frame.append(box((0, -h * 0.88, sz * h), (h, h * 0.12, h * 0.1), r=h * 0.06))
        frame.append(box((h * 0.88, 0, sz * h), (h * 0.12, h, h * 0.1), r=h * 0.06))
        frame.append(box((-h * 0.88, 0, sz * h), (h * 0.12, h, h * 0.1), r=h * 0.06))
    return U(core, *frame, k=0.02)


def pumpkin_shapes(r):
    lobes = [ell((math.cos(a) * r * 0.42, math.sin(a) * r * 0.42, r * 0.72), (r * 0.62, r * 0.62, r * 0.7), rot=(0, 0, math.degrees(a)))
             for a in (2 * math.pi * i / 8 for i in range(8))]
    body = SUB(U(*lobes, k=r * 0.15), sph((0, 0, r * 1.52), r * 0.22), k=r * 0.2)
    stem = U(rcone((0, 0, r * 1.2), (r * 0.12, 0.05, r * 1.72), r * 0.16, r * 0.11), k=0.0)
    return body, stem


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
    P.append(Part(crate_shape(0.85), wood_l, voxel=0.03, w=0.6, inst=[((-3.3, -3.35, 0), (0, 0, 12))]))
    P.append(Part(crate_shape(0.62), wood, voxel=0.03, w=0.5, inst=[((-2.2, -4.25, 0), (0, 0, -20))]))
    pumpkin, stem = pumpkin_shapes(0.95)
    P.append(Part(pumpkin, PAL["orange"], voxel=0.03, w=0.6, inst=[((3.35, -3.35, 0), (0, 0, 20))]))
    P.append(Part(stem, PAL["leaf_d"], voxel=0.02, w=0.2, min_tris=30, inst=[((3.35, -3.35, 0), (0, 0, 20))]))
    return build("Market_Stall", P, LARGE, ao=(1.0, 0.5), target=0.8)


def sector_mask(n, cx=0.0, cy=0.0, phase_deg=0.0):
    """Keeps every other one of 2n equal angular sectors about a vertical axis (stripes)."""
    period = math.pi / n
    ph = math.radians(phase_deg)

    def fn(P):
        du = P[:, 0] - cx
        dv = P[:, 1] - cy
        rho = np.maximum(np.sqrt(du * du + dv * dv), 0.05)
        phi = np.mod(np.arctan2(dv, du) - ph, 2 * period)
        return ((np.abs(phi - period * 0.5) - period * 0.5) * rho).astype(F32)
    return (fn, (np.array([-400] * 3, F32), np.array([400] * 3, F32)))


def helix_mask(cx, cy, radius, pitch, duty=0.5):
    g = math.sqrt((1 / (2 * math.pi * radius)) ** 2 + (1 / pitch) ** 2)

    def fn(P):
        phi = np.arctan2(P[:, 1] - cy, P[:, 0] - cx) / (2 * math.pi)
        u = np.mod(phi + P[:, 2] / pitch, 1.0)
        return ((np.abs(u - 0.5) - duty * 0.5) / g).astype(F32)
    return (fn, (np.array([-400] * 3, F32), np.array([400] * 3, F32)))


FESTIVE = [PAL["red"], PAL["yellow"], PAL["teal"], PAL["coral"], PAL["purple"], PAL["leaf"], PAL["orange"], PAL["blue"]]


def flag_shape(w=0.62, h=1.35, t=0.06):
    return extrude(poly2([(-w, 0.08), (w, 0.08), (0, -h)]), (-w, -h), (w, 0.1), -t, t, axis="y", r=0.035)


def bunting_parts(a, b, sag, n_flags, cols=FESTIVE, rad=0.08, w=0.62, h=1.35, string_col=(0.96, 0.93, 0.85)):
    a, b = Vector(a), Vector(b)
    string = tube_mesh(sag_points(a, b, sag, n=25), rad, sides=6)
    inst, cc = [], []
    for i in range(n_flags):
        t = (i + 0.5) / n_flags
        pnt = a.lerp(b, t)
        pnt.z -= sag * 4 * t * (1 - t) - 0.02
        slope = -sag * 4 * (1 - 2 * t) / (b.x - a.x)
        inst.append((tuple(pnt), (0, -math.degrees(math.atan(slope)), 0)))
        cc.append(cols[i % len(cols)])
    return [Part(obj=string, col=string_col, fixed=10 ** 6),
            Part(flag_shape(w, h), cols=cc, inst=inst, voxel=0.025, w=0.8, min_tris=24, hi=0.25)]


def glossy(base, amount=0.65):
    t = tone(base, 0.22, 0.3)
    L = Vector((-0.45, -0.6, 0.66)).normalized()

    def fn(co, n):
        return mix(t(co, n), (1, 1, 1), ss(0.84, 0.97, n.dot(L)) * amount)
    return fn


def a_parade_runway():
    P = []
    L0, L1, PC, PR = -17.6, 13.0, 13.0, 7.0
    ym, yh = (L0 + L1) * 0.5, (L1 - L0) * 0.5
    body = U(box((0, ym, 0.7), (5.0, yh, 0.7), r=0.25), cyl((0, PC, 0.7), PR, 0.7, r=0.25), k=0.4)
    P.append(Part(body, PAL["navy"], voxel=0.07, w=0.8))
    top = U(box((0, ym, 1.45), (5.3, yh + 0.3, 0.15), r=0.13), cyl((0, PC, 1.45), PR + 0.3, 0.15, r=0.13), k=0.5)
    P.append(Part(top, PAL["wood_l"], voxel=0.05, w=1.0))
    steps = U(box((0, -19.3, 0.27), (4.2, 0.7, 0.27), r=0.14), box((0, -18.35, 0.56), (4.2, 0.85, 0.56), r=0.14))
    P.append(Part(steps, PAL["wood"], voxel=0.05, w=0.6))
    carpet = U(box((0, (L0 + 0.4 + PC) * 0.5, 1.63), (1.9, (PC - L0 - 0.4) * 0.5, 0.07), r=0.035),
               cyl((0, PC, 1.63), 4.0, 0.07, r=0.035))
    P.append(Part(carpet, PAL["red"], voxel=0.035, w=0.7, hi=0.2))
    trim = U(tor((0, PC, 1.66), 4.05, 0.1),
             cap((1.95, L0 + 0.4, 1.66), (1.95, PC - 3.55, 1.66), 0.1), cap((-1.95, L0 + 0.4, 1.66), (-1.95, PC - 3.55, 1.66), 0.1))
    P.append(Part(trim, PAL["gold"], voxel=0.03, w=0.6))
    bulbs = [(x, L0 + 0.8 + i * 2.33) for x in (-4.72, 4.72) for i in range(11)]
    bulbs += [(math.cos(math.radians(a)) * 6.75, PC + math.sin(math.radians(a)) * 6.75)
              for a in (-35 + i * 250 / 11 for i in range(12))]
    zt = 1.6
    P.append(Part(cyl((0, 0, 0.1), 0.2, 0.12, r=0.05), PAL["gold"], voxel=0.02, fixed=20,
                  inst=[((x, y, zt), None) for x, y in bulbs]))
    P.append(Part(sph((0, 0, 0.42), 0.32), PAL["glow"], voxel=0.02, fixed=60, hi=0.45, lo=0.12,
                  inst=[((x, y, zt), None) for x, y in bulbs]))
    star = extrude(star2(0, 0, 0.55, 0.25), (-0.56, -0.56), (0.56, 0.56), -0.08, 0.08, axis="y", r=0.05)
    stars = [((sx * 5.0, y, 0.72), (0, 0, sx * 90)) for sx in (-1, 1) for y in (-15, -11, -7, -3, 1, 5)]
    stars += [((math.cos(math.radians(a)) * 7.0, PC + math.sin(math.radians(a)) * 7.0, 0.72), (0, 0, a + 90))
              for a in (-20 + i * 220 / 8 for i in range(9))]
    P.append(Part(star, PAL["gold"], voxel=0.025, fixed=44, inst=stars))
    return build("Parade_Runway", P, LARGE, ao=(1.2, 0.5))


def a_parade_arch():
    P = []
    X = 7.0
    P.append(Part(U(*[box((sx * X, 0, 0.55), (1.35, 1.35, 0.55), r=0.28) for sx in (-1, 1)]), PAL["cream"], voxel=0.04, w=0.7))
    cols = [rod((sx * X, 0, 0.9), (sx * X, 0, 10.3), 0.8, r=0.1) for sx in (-1, 1)]
    P.append(Part(U(*cols), PAL["white"], voxel=0.04, w=1.0))
    stripes = U(*[INT(grow(cols[i], 0.04), helix_mask(sx * X, 0, 0.8, 3.2 * sx, duty=0.42)) for i, sx in enumerate((-1, 1))])
    P.append(Part(stripes, PAL["red"], voxel=0.035, w=1.2))
    rings = U(*[tor((sx * X, 0, z), 0.86, 0.2) for sx in (-1, 1) for z in (1.25, 10.25)])
    P.append(Part(rings, PAL["gold"], voxel=0.03, w=0.6))
    P.append(Part(U(*[sph((sx * X, 0, 11.15), 0.95) for sx in (-1, 1)]), PAL["yellow"], voxel=0.035, w=0.6, hi=0.35))
    beam = chain(arc_points((-X, 0, 11.3), (X, 0, 11.3), 2.0, 15), 0.52, k=0.05)
    P.append(Part(beam, PAL["teal"], voxel=0.04, w=1.0))
    # medallion with a big paw print (the game's mark, word-free)
    mz = 12.4
    P.append(Part(cyl((0, -0.1, mz), 1.6, 0.3, r=0.12, rot=(90, 0, 0)), PAL["cream"], voxel=0.03, w=0.6))
    P.append(Part(tor((0, -0.1, mz), 1.6, 0.2, rot=(90, 0, 0)), PAL["gold"], voxel=0.03, w=0.6))
    paw = U(ell((0, 0, -0.35), (0.62, 0.2, 0.48)),
            *[ell((math.sin(math.radians(a)) * 0.78, 0, 0.12 + math.cos(math.radians(a)) * 0.62), (0.21, 0.2, 0.27), rot=(0, a * 0.8, 0))
              for a in (-62, -22, 22, 62)], k=0.0)
    P.append(Part(XF(paw, (0, -0.42, mz)), PAL["coral"], voxel=0.025, w=0.6))
    P += bunting_parts((-X + 0.75, -0.9, 9.9), (X - 0.75, -0.9, 9.9), 1.7, 11)
    return build("Parade_Arch", P, LARGE, ao=(1.0, 0.5))


def notice_board(name, hw, post_r, post_top, cz, face_hw, face_hh, roof_hw, roof_hd, roof_ang, budget, emblem):
    P = []
    posts = U(*[box((sx * hw, 0, post_top * 0.5), (post_r, post_r, post_top * 0.5), r=post_r * 0.4) for sx in (-1, 1)])
    P.append(Part(posts, PAL["wood_d"], voxel=0.04, w=0.8))
    feet = U(*[box((sx * hw, 0, 0.35), (post_r + 0.3, post_r + 0.3, 0.35), r=0.18) for sx in (-1, 1)])
    P.append(Part(feet, PAL["stone"], voxel=0.04, w=0.4))
    frame = box((0, 0, cz), (face_hw + 0.55, 0.38, face_hh + 0.5), r=0.26)
    frame = SUB(frame, box((0, -0.5, cz), (face_hw, 0.3, face_hh), r=0.08))
    backs = U(*[box((0, 0.4, cz + dz * face_hh), (face_hw + 0.3, 0.1, 0.22), r=0.08) for dz in (-0.55, 0.55)])
    P.append(Part(U(frame, backs), PAL["wood"], voxel=0.04, w=1.0))
    P.append(Part(box((0, -0.24, cz), (face_hw + 0.05, 0.06, face_hh + 0.05), r=0.03), PAL["cream"], voxel=0.04, w=0.4, hi=0.12, lo=0.1))
    P.append(Part(box((0, 0, post_top - 0.3), (hw + post_r + 0.25, 0.32, 0.26), r=0.12), PAL["wood_d"], voxel=0.04, w=0.5))
    a = math.radians(roof_ang)
    hl = roof_hd / math.cos(a) * 0.5
    Rz = post_top + 0.3 + roof_hd * math.tan(a)
    slabs = []
    for sy in (-1, 1):
        slabs.append(box((0, sy * hl * math.cos(a), Rz - hl * math.sin(a)), (roof_hw, hl + 0.12, 0.16), r=0.12, rot=(-sy * roof_ang, 0, 0)))
    P.append(Part(U(*slabs, k=0.1), PAL["red"], voxel=0.04, w=1.0))
    P.append(Part(cap((-roof_hw - 0.1, 0, Rz + 0.08), (roof_hw + 0.1, 0, Rz + 0.08), 0.24), PAL["cream"], voxel=0.03, w=0.3))
    P += emblem(Rz + 0.25)
    return build(name, P, budget, ao=(1.0, 0.5), target=0.65 if budget == LARGE else 0.93)


def a_research_board():
    def emblem(z):
        c = (0, 0, z + 1.05)
        return [Part(U(tor(c, 0.7, 0.18, rot=(90, 0, 0)), cap((0.55, 0, z + 0.52), (1.0, 0, z - 0.05), 0.21)), PAL["gold"], voxel=0.03, w=0.5),
                Part(cyl(c, 0.58, 0.08, rot=(90, 0, 0)), PAL["glass"], voxel=0.03, w=0.2, hi=0.5)]
    return notice_board("Research_Board", hw=7.3, post_r=0.48, post_top=8.9, cz=5.05, face_hw=6.45, face_hh=2.9,
                        roof_hw=7.95, roof_hd=1.55, roof_ang=24, budget=LARGE, emblem=emblem)


def a_quest_board():
    def emblem(z):
        c = (0, 0, z + 0.95)
        bang = U(cap((0, -0.2, c[2] + 0.42), (0, -0.2, c[2] - 0.08), 0.13), sph((0, -0.2, c[2] - 0.38), 0.14))
        return [Part(cyl(c, 0.88, 0.14, r=0.08, rot=(90, 0, 0)), PAL["yellow"], voxel=0.025, w=1.2),
                Part(tor(c, 0.88, 0.1, rot=(90, 0, 0)), PAL["orange"], voxel=0.025, w=0.3),
                Part(bang, PAL["dark"], voxel=0.02, w=0.3)]
    return notice_board("Quest_Board", hw=3.0, post_r=0.3, post_top=6.1, cz=3.75, face_hw=2.2, face_hh=1.45,
                        roof_hw=3.35, roof_hd=1.2, roof_ang=28, budget=MEDIUM, emblem=emblem)


def a_planter_box():
    P = []
    body = box((0, 0, 0.8), (2.0, 2.0, 0.8), r=0.2)
    body = SUB(body, SUB(box((0, 0, 0.8), (2.2, 2.2, 0.045), r=0.0), box((0, 0, 0.8), (1.93, 1.93, 0.2), r=0.0)))
    P.append(Part(body, PAL["wood"], voxel=0.03, w=1.0))
    rim = SUB(box((0, 0, 1.62), (2.2, 2.2, 0.15), r=0.1), box((0, 0, 1.62), (1.82, 1.82, 0.4), r=0.02))
    P.append(Part(rim, PAL["wood_l"], voxel=0.03, w=0.7))
    P.append(Part(bumps(box((0, 0, 1.5), (1.86, 1.86, 0.12), r=0.05), 0.03, 4.0), PAL["soil"], voxel=0.03, w=0.2))
    clumps = [((0, 0.35, 2.55), 1.0), ((-0.85, 0.5, 2.2), 0.78), ((0.88, 0.45, 2.25), 0.8), ((0.05, 0.75, 3.3), 0.72),
              ((-0.55, -0.35, 2.05), 0.62), ((0.6, -0.3, 2.05), 0.6)]
    bush = U(*[sph(c, r) for c, r in clumps], k=0.1)
    P.append(Part(bush, PAL["leaf"], voxel=0.03, w=2.2, hi=0.45))
    petals = U(*[ell((math.cos(a) * 0.27, math.sin(a) * 0.27, 0), (0.22, 0.22, 0.09)) for a in (2 * math.pi * i / 5 for i in range(5))], k=0.03)
    spots = [((-1.3, -1.25, 2.25), (-20, 10, 0)), ((0.05, -1.45, 2.35), (-25, 0, 0)), ((1.35, -1.2, 2.2), (-20, -12, 0)),
             ((-1.5, 0.6, 2.4), (0, 25, 0)), ((1.5, 0.8, 2.45), (0, -25, 0))]
    stems = U(*[cap((x, y, 1.55), (x, y, z - 0.05), 0.07) for (x, y, z), _ in spots])
    P.append(Part(stems, PAL["leaf_d"], voxel=0.02, w=0.3))
    P.append(Part(petals, cols=[PAL["pink"], PAL["yellow"], PAL["lavender"], PAL["coral"], PAL["pink"]],
                  voxel=0.015, fixed=80, inst=spots))
    P.append(Part(sph((0, 0, 0.06), 0.14), PAL["orange"], voxel=0.015, fixed=24, inst=spots))
    return build("Planter_Box", P, SMALL, ao=(0.6, 0.5))


def a_balloon_cluster():
    P = []
    P.append(Part(box((0, 0, 0.5), (0.6, 0.6, 0.5), r=0.12), PAL["coral"], voxel=0.025, w=0.6))
    P.append(Part(U(box((0, 0, 0.5), (0.64, 0.17, 0.53), r=0.06), box((0, 0, 0.5), (0.17, 0.64, 0.53), r=0.06),
                    ell((0.25, 0, 1.08), (0.27, 0.12, 0.15), rot=(0, -25, 0)), ell((-0.25, 0, 1.08), (0.27, 0.12, 0.15), rot=(0, 25, 0))),
                  PAL["yellow"], voxel=0.02, w=0.6))
    spots = [((-1.0, 0.3, 5.65), PAL["red"]), ((0.95, -0.15, 6.0), PAL["yellow"]), ((0.1, -0.95, 4.9), PAL["teal"])]
    balloon = U(ell((0, 0, 0), (0.85, 0.85, 1.0)), rcone((0, 0, -0.9), (0, 0, -1.16), 0.14, 0.1), k=0.12)
    for c, col in spots:
        P.append(Part(balloon, voxel=0.03, fixed=260, paint=glossy(col), inst=[(c, None)]))
        knot = Vector(c) - Vector((0, 0, 1.12))
        a = Vector((0, 0, 1.1))
        mid = (a + knot) * 0.5 + Vector((c[0] * 0.25, c[1] * 0.25, 0))
        pts = [a * (1 - t) ** 2 + mid * 2 * t * (1 - t) + knot * t * t for t in (i / 7 for i in range(8))]
        P.append(Part(obj=tube_mesh(pts, 0.05, sides=5), col=(0.96, 0.95, 0.9), fixed=10 ** 6))
    return build("Balloon_Cluster", P, SMALL, ao=(0.5, 0.35))


def a_bunting_span():
    P = bunting_parts((-10, 0, 10), (10, 0, 10), 1.8, 14)
    P.append(Part(U(tor((-10.05, 0, 10.0), 0.24, 0.08, rot=(90, 0, 0)), tor((10.05, 0, 10.0), 0.24, 0.08, rot=(90, 0, 0))),
                  PAL["iron"], voxel=0.02, fixed=60))
    return build("Bunting_Span", P, MEDIUM, ao=(0.3, 0.25), floor=False, center=False)


def a_tent_striped():
    P = []
    Rw, Hw = 4.3, 3.4
    wall = cyl((0, 0, Hw * 0.5), Rw, Hw * 0.5, r=0.12)
    door = extrude(u2(b2(0, 1.0, 0.95, 1.0), c2(0, 2.0, 0.95)), (-0.95, -0.1), (0.95, 3.0), -Rw - 1.0, -Rw + 1.4, axis="y", r=0.0)
    wall = SUB(wall, door, k=0.08)
    roof = frustum(Hw - 0.25, 8.2, 5.05, 0.28, r=0.18)
    canvas = U(wall, roof, k=0.0)
    P.append(Part(canvas, PAL["cream"], voxel=0.05, w=1.0))
    ph = -90 - 11.25
    P.append(Part(INT(grow(canvas, 0.045), sector_mask(8, phase_deg=ph)), PAL["red"], voxel=0.045, w=1.0))
    P.append(Part(cyl((0, 0, 1.55), Rw - 0.25, 1.55), (0.3, 0.2, 0.32), voxel=0.06, w=0.2, hi=0.0, lo=0.0))
    sc = extrude(i2(c2(0, 0, 0.98), b2(0, -1, 2, 1)), (-1.0, -1.0), (1.0, 0.05), -0.08, 0.08, axis="y", r=0.035)
    inst, cols = [], []
    for i in range(16):
        a = ph + 11.25 + i * 22.5
        inst.append(((math.cos(math.radians(a)) * 5.0, math.sin(math.radians(a)) * 5.0, Hw - 0.18), (0, 0, a + 90)))
        cols.append(PAL["red"] if i % 2 == 0 else PAL["cream"])
    P.append(Part(sc, cols=cols, inst=inst, voxel=0.025, fixed=60))
    flaps = U(cap((1.2, -Rw - 0.08, 0.35), (1.1, -Rw - 0.02, 2.7), 0.26), cap((-1.2, -Rw - 0.08, 0.35), (-1.1, -Rw - 0.02, 2.7), 0.26))
    P.append(Part(flaps, PAL["red"], voxel=0.03, w=0.4))
    ties = U(tor((1.16, -Rw - 0.06, 1.6), 0.27, 0.07), tor((-1.16, -Rw - 0.06, 1.6), 0.27, 0.07))
    P.append(Part(ties, PAL["yellow"], voxel=0.02, w=0.2))
    P.append(Part(U(rod((0, 0, 8.0), (0, 0, 9.35), 0.1, r=0.04), sph((0, 0, 9.4), 0.22)), PAL["gold"], voxel=0.02, w=0.3))
    pennant = extrude(poly2([(0.08, 9.22), (1.35, 8.92), (0.08, 8.6)]), (0, 8.55), (1.4, 9.3), -0.05, 0.05, axis="y", r=0.03)
    P.append(Part(pennant, PAL["yellow"], voxel=0.02, w=0.3))
    return build("Tent_Striped", P, LARGE, ao=(1.0, 0.5), target=0.8)


def a_statue_pedestal():
    P = [
        Part(cyl((0, 0, 0.22), 2.05, 0.22, r=0.1), PAL["stone_d"], voxel=0.03, w=0.7),
        Part(cyl((0, 0, 1.05), 1.68, 0.72, r=0.1), PAL["marble"], voxel=0.03, w=1.0),
        Part(cyl((0, 0, 1.8), 2.05, 0.2, r=0.1), PAL["marble"], voxel=0.03, w=0.8),
        Part(U(tor((0, 0, 1.55), 1.72, 0.08), tor((0, 0, 0.47), 1.74, 0.08)), PAL["gold"], voxel=0.02, w=0.5),
        Part(box((0, -1.67, 1.0), (0.8, 0.14, 0.36), r=0.09), PAL["gold"], voxel=0.02, w=0.4),
        Part(box((0, -1.8, 1.0), (0.6, 0.03, 0.2), r=0.02), mix(PAL["gold"], PAL["bronze"], 0.55), voxel=0.02, w=0.2, min_tris=20),
    ]
    return build("Statue_Pedestal", P, SMALL, ao=(0.6, 0.5))


# ═══ SANCTUARY ════════════════════════════════════════════════════════════════

def a_nest():
    P = []
    rng = random.Random(11)
    base = U(tor((0, 0, 0.5), 1.45, 0.5), cyl((0, 0, 0.22), 1.35, 0.22, r=0.15), k=0.3)
    P.append(Part(bumps(base, 0.05, 6.0, seed=5), PAL["bark"], voxel=0.03, w=0.8))
    twigs = []
    for layer, (z, rr) in enumerate(((0.35, 1.75), (0.72, 1.62), (1.0, 1.4))):
        n = 11 - layer
        for i in range(n):
            a = 2 * math.pi * (i + 0.5 * layer + rng.uniform(-0.15, 0.15)) / n
            half = rng.uniform(0.55, 0.8)
            ta = Vector((-math.sin(a), math.cos(a), 0))
            c = Vector((math.cos(a) * rr, math.sin(a) * rr, z + rng.uniform(-0.08, 0.08)))
            tilt = Vector((0, 0, rng.uniform(-0.3, 0.3)))
            twigs.append(cap(tuple(c - (ta + tilt) * half), tuple(c + (ta + tilt) * half), rng.uniform(0.1, 0.14)))
    for i in range(5):
        a = 2 * math.pi * (i + 0.3) / 5
        c = Vector((math.cos(a) * 1.85, math.sin(a) * 1.85, 0.9))
        out = Vector((math.cos(a + 0.9), math.sin(a + 0.9), 0.35))
        twigs.append(rcone(tuple(c), tuple(c + out * 0.45), 0.09, 0.06))
    P.append(Part(U(*twigs, k=0.04), PAL["wood"], voxel=0.025, w=1.4))
    lining = bumps(ell((0, 0, 0.62), (1.28, 1.28, 0.3)), 0.03, 7.0, seed=8)
    P.append(Part(lining, PAL["straw"], voxel=0.03, w=0.6, hi=0.35))
    feather = U(ell((0, 0, 0), (0.12, 0.4, 0.04)), cap((0, -0.42, 0), (0, -0.58, 0.02), 0.025))
    P.append(Part(feather, cols=[PAL["cream"], PAL["pink"]], voxel=0.012, fixed=40,
                  inst=[((0.95, -1.1, 1.08), (15, 0, 35)), ((-1.15, 0.85, 1.02), (-10, 5, -60))]))
    return build("Nest", P, SMALL, ao=(0.5, 0.55))


def paw_shape(scale=1.0, depth=0.08):
    """Paw print facing -Y (pad + four toe beans), centred on the origin."""
    s = scale
    pad = ell((0, 0, -0.12 * s), (0.34 * s, depth, 0.26 * s))
    toes = [ell((math.sin(math.radians(a)) * 0.42 * s, 0, 0.14 * s + math.cos(math.radians(a)) * 0.3 * s), (0.11 * s, depth, 0.14 * s),
                rot=(0, a * 0.7, 0)) for a in (-62, -21, 21, 62)]
    return U(pad, *toes)


def a_food_bowl():
    P = []
    outer = frustum(0.0, 0.95, 1.08, 1.38, r=0.2)
    bowl = SUB(outer, frustum(0.28, 1.4, 0.88, 1.18, r=0.1), k=0.06)
    coral, cream = PAL["coral"], PAL["cream"]
    t_out, t_in = tone(coral, 0.3, 0.3), tone(cream, 0.2, 0.2)

    def bowl_paint(co, n):
        radial = n.x * co.x + n.y * co.y
        if co.z > 0.3 and radial < -0.05:
            return t_in(co, n)
        return t_out(co, n)
    P.append(Part(bowl, paint=bowl_paint, voxel=0.02, w=1.2))
    P.append(Part(tor((0, 0, 0.1), 1.08, 0.1), mul(coral, 0.8), voxel=0.02, w=0.3))
    kibble = bumps(ell((0, 0, 0.68), (1.0, 1.0, 0.3)), 0.05, 9.0, seed=4)
    P.append(Part(kibble, (0.78, 0.5, 0.28), voxel=0.025, w=0.5))
    bits = [((math.cos(a) * rr, math.sin(a) * rr, 0.9 + 0.12 * (1 - rr)), (0, 30, math.degrees(a)))
            for a, rr in ((0.3, 0.2), (1.9, 0.45), (3.3, 0.3), (4.4, 0.6), (5.6, 0.5), (2.6, 0.75), (0.9, 0.7))]
    P.append(Part(ell((0, 0, 0), (0.16, 0.13, 0.1)), (0.66, 0.38, 0.22), voxel=0.015, fixed=24, inst=bits))
    P.append(Part(paw_shape(0.78, 0.09), cream, voxel=0.015, w=0.8,
                  inst=[((0, -1.27, 0.5), (17, 0, 0)), ((0, 1.27, 0.5), (17, 0, 180))]))
    return build("Food_Bowl", P, SMALL, ao=(0.35, 0.5))


def a_pet_bed():
    P = []
    bolster = U(tor((0, 0, 0.55), 1.52, 0.52), cyl((0, 0, 0.2), 1.75, 0.2, r=0.15), k=0.3)
    P.append(Part(bolster, PAL["lavender"], voxel=0.03, w=1.2))
    P.append(Part(tor((0, 0, 0.55), 2.05, 0.06), PAL["cream"], voxel=0.015, w=0.4))
    cushion = SUB(ell((0, 0, 0.45), (1.3, 1.3, 0.3)), *[sph((math.cos(a) * 0.55, math.sin(a) * 0.55, 0.78), 0.1)
                                                       for a in (0.785 + 1.571 * i for i in range(4))], k=0.08)
    P.append(Part(cushion, PAL["cream"], voxel=0.025, w=0.8))
    bone = U(cap((-0.42, 0, 0), (0.42, 0, 0), 0.12), sph((-0.5, 0.11, 0), 0.15), sph((-0.5, -0.11, 0), 0.15),
             sph((0.5, 0.11, 0), 0.15), sph((0.5, -0.11, 0), 0.15), k=0.06)
    P.append(Part(bone, PAL["white"], voxel=0.015, w=0.4, inst=[((0.55, -0.35, 0.78), (0, 8, 28))]))
    return build("Pet_Bed", P, SMALL, ao=(0.5, 0.5))


def pond_r(theta):
    a, b = 4.35, 3.15
    re = a * b / math.sqrt((b * math.cos(theta)) ** 2 + (a * math.sin(theta)) ** 2)
    d = math.atan2(math.sin(theta - math.pi / 2), math.cos(theta - math.pi / 2))
    return re * (1 - 0.3 * math.exp(-(d / 0.55) ** 2))


def pond2(offset=0.0):
    def f(u, v):
        th = np.arctan2(v, u)
        a, b = 4.35, 3.15
        re = a * b / np.sqrt((b * np.cos(th)) ** 2 + (a * np.sin(th)) ** 2)
        d = np.arctan2(np.sin(th - math.pi / 2), np.cos(th - math.pi / 2))
        r = re * (1 - 0.3 * np.exp(-(d / 0.55) ** 2))
        return (np.sqrt(u * u + v * v) - r) * 0.85 - offset
    return f


def a_pond_small():
    P = []
    water = extrude(pond2(0.1), (-4.6, -3.4), (4.6, 3.4), 0.05, 0.52, axis="z", r=0.04)
    P.append(Part(water, mix(PAL["water_d"], PAL["navy"], 0.25), voxel=0.05, w=0.3, hi=0.3))
    band = pond2(0.0)
    rim = extrude(lambda u, v: np.abs(band(u, v)) - 0.42, (-5.2, -4.0), (5.2, 4.0), 0.0, 0.56, axis="z", r=0.2)
    P.append(Part(bumps(rim, 0.04, 3.0), PAL["stone_d"], voxel=0.05, w=0.9))
    rng = random.Random(21)
    inst, cols = [], []
    n = 17
    for i in range(n):
        th = 2 * math.pi * (i + rng.uniform(-0.2, 0.2)) / n
        rr = pond_r(th) + 0.12
        x, y = math.cos(th) * rr, math.sin(th) * rr
        tang = math.degrees(th) + 90
        sc = rng.uniform(0.85, 1.2)
        inst.append(((x, y, 0.3), (rng.uniform(-6, 6), rng.uniform(-6, 6), tang + rng.uniform(-15, 15)), (sc, sc * rng.uniform(0.85, 1.05), sc * rng.uniform(0.85, 1.1))))
        cols.append(jitter(mix(PAL["stone"], PAL["stone_b"], rng.uniform(0, 0.5)), 0.06, rng))
    stone = bumps(ell((0, 0, 0), (0.62, 0.46, 0.36)), 0.035, 5.0, seed=6)
    P.append(Part(stone, cols=cols, inst=inst, voxel=0.03, fixed=90))
    pad = extrude(sub2(c2(0, 0, 0.62), poly2([(0, 0), (0.9, 0.25), (0.9, -0.2)])), (-0.65, -0.65), (0.65, 0.65), -0.04, 0.04, axis="z", r=0.02)
    P.append(Part(pad, PAL["leaf"], voxel=0.02, fixed=60, inst=[((-1.6, -0.6, 0.55), (0, 0, 30)), ((1.9, 0.5, 0.55), (0, 0, 200), 0.8),
                                                                 ((0.3, -1.6, 0.55), (0, 0, 120), 0.7)]))
    lotus = U(*[ell((math.cos(a) * 0.17, math.sin(a) * 0.17, 0.14), (0.2, 0.09, 0.14), rot=(0, -35, math.degrees(a))) for a in (2 * math.pi * i / 6 for i in range(6))],
              k=0.02)
    P.append(Part(lotus, PAL["pink"], voxel=0.012, fixed=120, inst=[((-1.6, -0.6, 0.55), None)]))
    P.append(Part(sph((0, 0, 0.16), 0.1), PAL["yellow"], voxel=0.012, fixed=20, inst=[((-1.6, -0.6, 0.55), None)]))
    return build("Pond_Small", P, MEDIUM, ao=(0.6, 0.45))


def a_stonepath_tile():
    def f(u, v):
        th = np.arctan2(v, u)
        r = 1.38 + 0.12 * np.sin(3 * th + 1.0) + 0.07 * np.sin(5 * th + 2.0)
        return (np.sqrt(u * u + v * v) - r) * 0.9
    slab_ = extrude(f, (-1.6, -1.6), (1.6, 1.6), 0.0, 0.34, axis="z", r=0.13)
    top = U(slab_, ell((0.05, 0.0, 0.26), (1.15, 1.05, 0.17)), k=0.15)
    chips = [sph((1.35, -0.55, 0.45), 0.3), sph((-0.6, -1.35, 0.44), 0.25)]
    crack = chain([(-0.2, 0.5, 0.45), (0.15, 0.1, 0.46), (0.05, -0.3, 0.45), (0.45, -0.75, 0.42)], 0.045, k=0.01)
    stone = SUB(bumps(top, 0.025, 3.0, seed=9), U(*chips, crack), k=0.05)
    rock = mix(PAL["stone"], PAL["stone_b"], 0.2)
    base_t = tone(rock, 0.35, 0.3)

    def speckle(co, n):
        c = base_t(co, n)
        k = math.sin(co.x * 7.3 + 1.1) * math.sin(co.y * 6.1 + 0.4) * math.sin((co.x + co.y) * 4.7)
        return mul(c, 0.88) if k > 0.3 else c
    P = [Part(stone, paint=speckle, voxel=0.025, w=1.0),
         Part(bumps(ell((-0.95, 0.8, 0.26), (0.55, 0.38, 0.13), rot=(0, 0, 40)), 0.03, 6.0), PAL["moss"], voxel=0.02, w=0.25),
         Part(sph((0, 0, 0), 0.13), PAL["leaf"], voxel=0.015, fixed=20, inst=[((-1.25, 0.35, 0.3), None), ((-0.55, 1.2, 0.3), None, 0.8)])]
    return build("StonePath_Tile", P, SMALL, ao=(0.35, 0.55), target=0.4)


def a_garden_bed():
    P = []
    boards = []
    for z in (0.36, 1.02):
        for sy in (-1, 1):
            boards.append(box((0, sy * 1.85, z), (3.75, 0.2, 0.31), r=0.1))
        for sx in (-1, 1):
            boards.append(box((sx * 3.85, 0, z), (0.2, 1.75, 0.31), r=0.1))
    P.append(Part(U(*boards), PAL["wood"], voxel=0.035, w=1.0))
    posts = U(*[box((sx * 3.9, sy * 1.9, 0.72), (0.3, 0.3, 0.72), r=0.12) for sx in (-1, 1) for sy in (-1, 1)])
    P.append(Part(posts, PAL["wood_d"], voxel=0.03, w=0.6))
    soil = U(box((0, 0, 1.05), (3.7, 1.7, 0.2), r=0.1), cap((-3.2, 0.8, 1.22), (3.2, 0.8, 1.22), 0.32),
             cap((-3.2, -0.8, 1.22), (3.2, -0.8, 1.22), 0.32), k=0.2)
    P.append(Part(bumps(soil, 0.04, 5.0), PAL["soil"], voxel=0.035, w=0.6))
    sprout = U(cap((0, 0, 0), (0, 0, 0.42), 0.055),
               ell((0.2, 0, 0.5), (0.26, 0.11, 0.05), rot=(0, -28, 0)), ell((-0.2, 0, 0.5), (0.26, 0.11, 0.05), rot=(0, 28, 0)), k=0.04)
    P.append(Part(sprout, PAL["leaf"], voxel=0.012, fixed=90, hi=0.35,
                  inst=[((x, 0.8, 1.45), (0, 0, 20 * i)) for i, x in enumerate((-2.8, -1.4, 0.0, 1.4, 2.8))]))
    carrot = U(sph((0, 0, 0.08), 0.24), rcone((0, 0, 0.1), (0, 0, -0.2), 0.24, 0.14), k=0.05)
    carrots = [((x, -0.8, 1.45), (0, 0, 0)) for x in (-2.4, -0.8, 0.8, 2.4)]
    P.append(Part(carrot, PAL["orange"], voxel=0.015, fixed=60, inst=carrots))
    tuft = U(*[rcone((0, 0, 0.2), (math.cos(a) * 0.22, math.sin(a) * 0.22, 0.85), 0.06, 0.035) for a in (0.3, 2.4, 4.5)], k=0.03)
    P.append(Part(tuft, PAL["leaf_d"], voxel=0.012, fixed=70, inst=carrots))
    return build("Garden_Bed", P, MEDIUM, ao=(0.7, 0.5))


def a_greenhouse():
    P = []
    W, D, Hw, Hr = 6.9, 4.9, 5.0, 8.0
    white = PAL["white"]
    P.append(Part(box((0, 0, 0.55), (W + 0.15, D + 0.15, 0.55), r=0.18), PAL["terracotta"], voxel=0.06, w=0.5))
    glass_walls = box((0, 0, 3.0), (W - 0.05, D - 0.05, 2.0), r=0.02)
    gable = extrude(poly2([(-D + 0.05, Hw - 0.05), (D - 0.05, Hw - 0.05), (0, Hr - 0.1)]), (-D, Hw - 0.1), (D, Hr), -W + 0.05, W - 0.05, axis="x", r=0.02)
    P.append(Part(U(glass_walls, gable), PAL["glass"], voxel=0.07, w=0.4, hi=0.25, lo=0.15))
    beam = 0.13
    xs = [-W, -4.6, -2.3, 0.0, 2.3, 4.6, W]
    ys = [-D, -2.45, 0.0, 2.45, D]
    for sy in (-1, 1):   # long walls
        y = sy * D
        parts = [box((x, y, 3.05), (beam, beam, 1.95), r=0.06) for x in xs if not (sy < 0 and abs(x) < 0.1)]
        parts += [box((0, y, z), (W, beam, beam), r=0.06) for z in (1.15, 3.1, Hw)]
        if sy < 0:
            parts = [q for q in parts]
        P.append(Part(U(*parts), white, voxel=0.035, w=1.0))
    for sx in (-1, 1):   # gable ends
        x = sx * W
        parts = [box((x, y, 3.05), (beam, beam, 1.95), r=0.06) for y in ys[1:-1]]
        parts += [box((x, 0, z), (beam, D, beam), r=0.06) for z in (1.15, 3.1)]
        parts += [rod((x, -D, Hw), (x, 0, Hr), beam * 1.1, r=0.05), rod((x, D, Hw), (x, 0, Hr), beam * 1.1, r=0.05)]
        parts += [rod((x, y, Hw), (x, y, Hw + (Hr - Hw) * (1 - abs(y) / D)), beam, r=0.05) for y in (-2.45, 0.0, 2.45)]
        P.append(Part(U(*parts), white, voxel=0.035, w=1.0))
    for sy in (-1, 1):   # roof slopes
        parts = [rod((x, sy * D, Hw), (x, 0, Hr), beam, r=0.05) for x in xs]
        parts.append(rod((-W, sy * D * 0.5, (Hw + Hr) * 0.5), (W, sy * D * 0.5, (Hw + Hr) * 0.5), beam, r=0.05))
        P.append(Part(U(*parts), white, voxel=0.035, w=1.0))
    P.append(Part(U(cap((-W - 0.1, 0, Hr), (W + 0.1, 0, Hr), 0.2), sph((-W - 0.15, 0, Hr + 0.25), 0.3), sph((W + 0.15, 0, Hr + 0.25), 0.3), k=0.05),
                  white, voxel=0.03, w=0.5))
    # door (front, -Y)
    door = SUB(box((0, -D - 0.05, 2.75), (1.05, 0.2, 1.65), r=0.1), box((0, -D - 0.4, 2.85), (0.75, 0.3, 1.3), r=0.08))
    P.append(Part(door, white, voxel=0.03, w=0.6))
    P.append(Part(box((0, -D - 0.02, 2.85), (0.8, 0.07, 1.35), r=0.03), mix(PAL["glass"], PAL["teal"], 0.3), voxel=0.03, w=0.2))
    P.append(Part(sph((0.55, -D - 0.28, 2.7), 0.13), PAL["gold"], voxel=0.015, fixed=30))
    # glass glints (diagonal highlights) on the front, sides and front roof slope
    def glint_mask(axis_u):
        def fn(Pp):
            u = Pp[:, axis_u] + Pp[:, 2] * 0.9
            return ((np.abs(np.mod(u, 2.3) - 1.15) - 0.13) * 0.74).astype(F32)
        return (fn, (np.array([-400] * 3, F32), np.array([400] * 3, F32)))
    g = [INT(box((0, -D + 0.02, 3.05), (W, 0.035, 1.85), r=0.0), glint_mask(0)),
         INT(box((W - 0.02, 0, 3.05), (0.035, D, 1.85), r=0.0), glint_mask(1)),
         INT(box((-W + 0.02, 0, 3.05), (0.035, D, 1.85), r=0.0), glint_mask(1))]
    P.append(Part(U(*g), (0.93, 0.99, 1.0), voxel=0.03, w=0.5, hi=0.1, lo=0.05, smooth=1))
    # potted plants flanking the door
    pot = U(frustum(0, 0.8, 0.45, 0.62, r=0.08), tor((0, 0, 0.78), 0.6, 0.1), k=0.05)
    plant = bumps(U(sph((0, 0, 1.25), 0.62), sph((0.25, 0.15, 1.7), 0.42), k=0.2), 0.04, 5.0)
    pots = [((-2.0, -D - 1.0, 0), (0, 0, 0)), ((2.0, -D - 1.0, 0), (0, 0, 40))]
    P.append(Part(pot, PAL["terracotta"], voxel=0.02, fixed=160, inst=pots))
    P.append(Part(plant, PAL["leaf"], voxel=0.025, fixed=220, inst=pots, hi=0.4))
    return build("Greenhouse", P, LARGE, ao=(1.0, 0.45))


def a_observatory():
    P = []
    P.append(Part(cyl((0, 0, 0.5), 6.0, 0.5, r=0.22), PAL["stone_d"], voxel=0.06, w=0.6))
    tower = frustum(0.8, 9.2, 5.2, 4.8, r=0.2)

    def rz(z):
        return 5.2 + (4.8 - 5.2) * (z - 0.8) / 8.4
    door2 = u2(b2(0, 1.95, 1.05, 1.15), c2(0, 3.1, 1.05))
    frame2 = u2(b2(0, 1.9, 1.45, 1.2), c2(0, 3.1, 1.45))
    tower = SUB(tower, extrude(door2, (-1.1, 0.8), (1.1, 4.2), -rz(1.5) - 1.0, -rz(1.5) + 0.35, axis="y"))
    P.append(Part(tower, (0.98, 0.88, 0.68), voxel=0.06, w=2.2))
    P.append(Part(U(tor((0, 0, 1.15), rz(1.15) + 0.02, 0.26), cyl((0, 0, 9.3), 5.45, 0.32, r=0.16), k=0.0), PAL["stone"], voxel=0.05, w=0.8))
    P.append(Part(extrude(frame2, (-1.5, 0.7), (1.5, 4.6), -rz(1.5) - 0.3, -rz(1.5) + 0.6, axis="y", r=0.12), PAL["stone"], voxel=0.035, w=0.5))
    P.append(Part(extrude(door2, (-1.1, 0.8), (1.1, 4.2), -rz(1.5) - 0.02, -rz(1.5) + 0.5, axis="y", r=0.05), PAL["wood_d"], voxel=0.035, w=0.5))
    P.append(Part(box((0, -rz(0.5) - 0.55, 0.3), (1.7, 0.7, 0.3), r=0.12), PAL["stone"], voxel=0.035, w=0.3))
    win_ring = tor((0, 0, 0), 0.72, 0.16, rot=(90, 0, 0))
    win_glass = cyl((0, 0.05, 0), 0.66, 0.07, rot=(90, 0, 0))
    wins = [((math.cos(math.radians(a)) * rz(6.0), math.sin(math.radians(a)) * rz(6.0), 6.0), (0, 0, a + 90)) for a in (-40, -140, 40, 140)]
    wins.append(((0, -rz(6.3), 6.3), (0, 0, 0)))
    P.append(Part(win_ring, PAL["stone"], voxel=0.025, fixed=90, inst=wins))
    P.append(Part(win_glass, PAL["navy"], voxel=0.025, fixed=40, inst=wins, hi=0.35))
    # dome with a slit, dark inside, a brass telescope poking out, gold stars
    dome = INT(sph((0, 0, 9.6), 4.6), slab(zmin=9.55))
    slit = box((0, -3.2, 13.6), (0.85, 3.3, 3.4), r=0.1)
    P.append(Part(SUB(dome, slit, k=0.1), (0.38, 0.42, 0.74), voxel=0.05, w=1.2))
    P.append(Part(INT(sph((0, 0, 9.6), 4.25), slab(zmin=9.6)), (0.16, 0.16, 0.3), voxel=0.08, w=0.15, hi=0.0, lo=0.0))
    tdir = Vector((0, -0.62, 0.78)).normalized()
    t0 = Vector((0, -0.6, 11.2))
    t1 = t0 + tdir * 6.3
    scope = U(rcone(tuple(t0), tuple(t1), 0.42, 0.62), cyl((0, 0, 0), 1, 1) if False else sph(tuple(t0), 0.5), k=0.05)
    P.append(Part(scope, PAL["gold"], voxel=0.03, w=0.8, hi=0.35))
    bands = U(*[XF(tor((0, 0, 0), 0.5 + 0.17 * f, 0.1), tuple(t0 + tdir * (6.3 * f)), rot=(-math.degrees(math.atan2(0.62, 0.78)) * 1.0, 0, 0))
                for f in (0.35, 0.7)], XF(tor((0, 0, 0), 0.66, 0.15), tuple(t1), rot=(-math.degrees(math.atan2(0.62, 0.78)), 0, 0)))
    P.append(Part(bands, PAL["bronze"], voxel=0.025, w=0.5))
    P.append(Part(XF(cyl((0, 0, 0), 0.56, 0.05), tuple(t1 + tdir * 0.05), rot=(-math.degrees(math.atan2(0.62, 0.78)), 0, 0)),
                  (0.62, 0.86, 0.96), voxel=0.025, w=0.2, hi=0.5))
    star = extrude(star2(0, 0, 0.42, 0.18), (-0.43, -0.43), (0.43, 0.43), -0.09, 0.09, axis="y", r=0.04)
    stars = []
    for az, el in ((200, 30), (240, 55), (320, 22), (20, 45), (60, 25), (110, 50), (160, 22), (340, 58), (290, 40)):
        n = Vector((math.cos(math.radians(el)) * math.cos(math.radians(az)), math.cos(math.radians(el)) * math.sin(math.radians(az)), math.sin(math.radians(el))))
        stars.append((tuple(Vector((0, 0, 9.6)) + n * 4.6), (-el, 0, az + 90)))
    P.append(Part(star, PAL["gold"], voxel=0.02, fixed=40, inst=stars))
    P.append(Part(U(sph((0, 0, 14.35), 0.42), rcone((0, 0, 14.5), (0, 0, 15.9), 0.18, 0.04), k=0.08), PAL["gold"], voxel=0.025, w=0.3))
    return build("Observatory", P, LARGE, ao=(1.2, 0.5))


def a_treehouse():
    P = []
    trunk = chain([(0, 1.1, 0), (0.1, 1.0, 3.0), (-0.1, 1.1, 6.5), (0, 1.3, 10.5)], [1.35, 1.0, 0.85, 0.7], k=0.3)
    roots = [rcone((0, 1.1, 0.35), (math.cos(a) * 2.1, 1.1 + math.sin(a) * 2.1, 0.05), 0.6, 0.22) for a in (0.4, 1.9, 3.3, 4.6, 5.7)]
    branches = [rcone((0, 1.2, 9.2), (2.9, 1.2, 12.6), 0.55, 0.3), rcone((0, 1.2, 9.6), (-2.8, 1.7, 12.9), 0.55, 0.3),
                rcone((0, 1.3, 10.0), (0.4, 3.2, 13.2), 0.5, 0.3)]
    P.append(Part(bumps(U(trunk, *roots, *branches, k=0.35), 0.04, 3.0), PAL["bark"], voxel=0.05, w=1.0))
    crown = [((0, 1.0, 13.9), 3.5), ((3.1, 1.0, 13.1), 2.6), ((-3.1, 1.4, 13.3), 2.7), ((0.4, 3.4, 13.4), 2.6),
             ((-1.3, -1.2, 14.7), 2.2), ((1.6, -0.6, 15.0), 2.1), ((0.1, 1.2, 15.7), 1.5)]
    P.append(Part(bumps(U(*[sph(c, r) for c, r in crown], k=0.5), 0.1, 1.6, seed=3), PAL["leaf"], voxel=0.07, w=1.4, hi=0.4))
    # platform + struts
    P.append(Part(box((0, -0.4, 6.25), (3.7, 3.4, 0.22), r=0.12), PAL["wood_l"], voxel=0.04, w=0.8))
    struts = U(rod((0, 0.9, 3.6), (2.8, -2.8, 6.1), 0.18, r=0.06), rod((0, 0.9, 3.6), (-2.8, -2.8, 6.1), 0.18, r=0.06),
               rod((0, 1.1, 4.0), (0, -3.4, 6.1), 0.18, r=0.06))
    P.append(Part(struts, PAL["wood_d"], voxel=0.035, w=0.4))
    rail_posts = [((x, -3.6, 6.45), None) for x in (-3.5, -1.8, 1.8, 3.5)] + [((sx * 3.5, y, 6.45), None) for sx in (-1, 1) for y in (-1.8, 0.2, 2.5)]
    P.append(Part(cyl((0, 0, 0.55), 0.13, 0.55, r=0.05), PAL["wood_d"], voxel=0.02, fixed=40, inst=rail_posts))
    rails = U(cap((-3.5, -3.6, 7.45), (-1.3, -3.6, 7.45), 0.12), cap((1.3, -3.6, 7.45), (3.5, -3.6, 7.45), 0.12),
              cap((-3.5, -3.6, 7.45), (-3.5, 2.5, 7.45), 0.12), cap((3.5, -3.6, 7.45), (3.5, 2.5, 7.45), 0.12))
    P.append(Part(rails, PAL["wood"], voxel=0.025, w=0.4))
    # the house
    hy = -0.2
    house = box((0, hy, 8.35), (2.3, 1.9, 1.95), r=0.18)
    P.append(Part(house, (0.98, 0.84, 0.5), voxel=0.04, w=1.0))
    corners = U(*[box((sx * 2.3, hy + sy * 1.9, 8.35), (0.2, 0.2, 2.0), r=0.08) for sx in (-1, 1) for sy in (-1, 1)])
    P.append(Part(corners, PAL["wood"], voxel=0.03, w=0.4))
    a = math.radians(33)
    hl = 2.5 / math.cos(a) * 0.5 + 0.35
    slabs = [box((sx * hl * math.cos(a), hy, 10.35 + 1.62 - hl * math.sin(a)), (hl + 0.1, 2.45, 0.16), r=0.12, rot=(0, sx * roof_a, 0))
             for sx in (-1, 1) for roof_a in (33,)]
    P.append(Part(U(*slabs, k=0.1), PAL["red"], voxel=0.04, w=0.8))
    gables = extrude(poly2([(-2.3, 10.25), (2.3, 10.25), (0, 11.8)]), (-2.3, 10.2), (2.3, 11.9), hy - 1.9, hy + 1.9, axis="y", r=0.08)
    P.append(Part(gables, (0.98, 0.84, 0.5), voxel=0.04, w=0.4))
    door = extrude(u2(b2(-0.85, 7.4, 0.62, 0.9), c2(-0.85, 8.3, 0.62)), (-1.5, 6.4), (-0.2, 9.0), hy - 2.02, hy - 1.7, axis="y", r=0.05)
    P.append(Part(door, (0.36, 0.62, 0.62), voxel=0.025, w=0.4))
    P.append(Part(XF(tor((0, 0, 0), 0.55, 0.12, rot=(90, 0, 0)), (1.1, hy - 1.95, 8.6)), PAL["wood"], voxel=0.02, w=0.3))
    P.append(Part(cyl((1.1, hy - 1.92, 8.6), 0.5, 0.05, rot=(90, 0, 0)), PAL["glow"], voxel=0.02, w=0.2, hi=0.3))
    # ladder leaning on the platform
    lx, b0, t0z = 2.3, Vector((0, -5.0, 0.0)), Vector((0, -3.55, 6.4))
    lad = [rod((lx - 0.55, b0.y, 0.0), (lx - 0.55, t0z.y, 7.1), 0.12, r=0.05), rod((lx + 0.55, b0.y, 0.0), (lx + 0.55, t0z.y, 7.1), 0.12, r=0.05)]
    for i in range(1, 10):
        f = i / 10.5
        y, z = b0.y + (t0z.y - b0.y) * f * 7.1 / 6.4, 7.1 * f
        lad.append(rod((lx - 0.55, y, z), (lx + 0.55, y, z), 0.08, r=0.03))
    P.append(Part(U(*lad), PAL["wood"], voxel=0.025, w=0.7))
    return build("Treehouse", P, LARGE, ao=(1.2, 0.5))


def a_windmill():
    P = []

    def rz(z):
        return 3.6 + (2.6 - 3.6) * (z - 0.6) / 9.9
    P.append(Part(cyl((0, 0, 0.35), 3.95, 0.35, r=0.15), PAL["stone_d"], voxel=0.04, w=0.5))
    door2 = u2(b2(0, 1.5, 0.8, 0.9), c2(0, 2.4, 0.8))
    tower = SUB(frustum(0.6, 10.6, 3.6, 2.6, r=0.25), extrude(door2, (-0.85, 0.5), (0.85, 3.3), -rz(1.5) - 1.0, -rz(1.5) + 0.3, axis="y"))
    P.append(Part(tower, PAL["white"], voxel=0.045, w=2.2))
    P.append(Part(U(tor((0, 0, 0.8), rz(0.8) + 0.02, 0.2), tor((0, 0, 5.6), rz(5.6) + 0.02, 0.15), k=0.0), PAL["wood"], voxel=0.03, w=0.5))
    P.append(Part(extrude(door2, (-0.85, 0.5), (0.85, 3.3), -rz(1.5) - 0.05, -rz(1.5) + 0.5, axis="y", r=0.05), PAL["wood_d"], voxel=0.025, w=0.4))
    win2 = u2(b2(0, 0, 0.42, 0.35), c2(0, 0.35, 0.42))
    wins = []
    for a, z in ((-90, 7.4), (0, 3.6), (180, 3.6), (-35, 4.0)):
        r0 = rz(z)
        wins.append(((math.cos(math.radians(a)) * r0, math.sin(math.radians(a)) * r0, z), (0, 0, a + 90)))
    P.append(Part(extrude(win2, (-0.45, -0.4), (0.45, 0.8), -0.12, 0.3, axis="y", r=0.04), PAL["navy"], voxel=0.02, fixed=80, inst=wins))
    shutters = U(box((-0.72, -0.05, 0.2), (0.26, 0.08, 0.58), r=0.06), box((0.72, -0.05, 0.2), (0.26, 0.08, 0.58), r=0.06))
    P.append(Part(shutters, PAL["teal"], voxel=0.02, fixed=100, inst=wins))
    roof = U(INT(ell((0, 0, 10.4), (3.05, 3.05, 2.7)), slab(zmin=10.3)), tor((0, 0, 10.45), 2.95, 0.28), k=0.1)
    P.append(Part(roof, (0.80, 0.36, 0.28), voxel=0.04, w=1.0))
    P.append(Part(U(sph((0, 0, 13.15), 0.3), rcone((0, 0, 13.3), (0, 0, 14.2), 0.1, 0.03)), PAL["gold"], voxel=0.02, w=0.2))
    hx, hy, hz = WINDMILL_HUB
    P.append(Part(rod((0, -1.8, hz), (0, hy + 0.25, hz), 0.42, r=0.12), PAL["wood_d"], voxel=0.03, w=0.4))
    P.append(Part(U(*[sph((math.cos(a) * 3.2, math.sin(a) * 3.2, 0.36), 0.35) for a in (0.6, 2.2, 3.9, 5.1)]), PAL["leaf"], voxel=0.03, w=0.3))
    mill = build("Windmill", P, LARGE, ao=(1.0, 0.5), center=False)

    S = []
    S.append(Part(U(cyl((0, 0, 0), 0.7, 0.3, r=0.12, rot=(90, 0, 0)), sph((0, -0.35, 0), 0.42), k=0.1), PAL["wood_d"], voxel=0.02, w=0.5))
    S.append(Part(sph((0, -0.72, 0), 0.2), PAL["gold"], voxel=0.015, fixed=40))
    arm = rod((0, 0, 0.4), (0, 0, 5.25), 0.17, r=0.06)
    panel = box((0.66, -0.12, 3.25), (0.62, 0.05, 1.95), r=0.05)
    slats = U(*[box((0.66, -0.2, z), (0.7, 0.07, 0.08), r=0.035) for z in (1.55, 2.55, 3.55, 4.55)], box((1.3, -0.2, 3.25), (0.07, 0.07, 1.95), r=0.035))
    blades = [((0, 0, 0), (0, 45 + 90 * i, 0)) for i in range(4)]
    S.append(Part(arm, PAL["wood"], voxel=0.025, w=1.0, inst=blades))
    S.append(Part(panel, PAL["cream"], voxel=0.025, w=1.0, inst=blades, hi=0.2))
    S.append(Part(slats, PAL["wood"], voxel=0.02, w=1.0, inst=blades))
    sails = build("Windmill_Sails", S, MEDIUM, ao=(0.4, 0.35), floor=False, center=False)
    return mill, sails


def a_lantern_string():
    P = []
    a, b, sag = Vector((-8, 0, 8)), Vector((8, 0, 8)), 1.3
    P.append(Part(obj=tube_mesh(sag_points(a, b, sag, n=21), 0.07, sides=6), col=PAL["wood_d"], fixed=10 ** 6))
    n = 7
    inst, cols = [], []
    for i in range(n):
        t = (i + 0.5) / n
        p = a.lerp(b, t)
        p.z -= sag * 4 * t * (1 - t)
        inst.append((tuple(p), None))
        cols.append([PAL["orange"], PAL["glow"], PAL["coral"]][i % 3])
    L = 1.35
    body = ell((0, 0, -0.95 * L), (0.46 * L, 0.46 * L, 0.55 * L))
    ribs = U(*[tor((0, 0, (-0.95 + dz) * L), (0.46 * math.sqrt(1 - (dz / 0.55) ** 2) + 0.01) * L, 0.04) for dz in (-0.25, 0.0, 0.25)])
    P.append(Part(body, cols=cols, inst=inst, voxel=0.02, fixed=160, hi=0.35, lo=0.12))
    P.append(Part(ribs, cols=[mul(c, 0.8) for c in cols], inst=inst, voxel=0.012, fixed=90))
    caps = U(cyl((0, 0, -0.4 * L), 0.22 * L, 0.08, r=0.03), cyl((0, 0, -1.5 * L), 0.2 * L, 0.08, r=0.03), cap((0, 0, 0.0), (0, 0, -0.35 * L), 0.045),
             rcone((0, 0, -1.55 * L), (0, 0, -1.9 * L), 0.08, 0.03))
    P.append(Part(caps, PAL["red"], voxel=0.012, fixed=90, inst=inst))
    P.append(Part(U(tor((-8.05, 0, 8.0), 0.2, 0.07, rot=(90, 0, 0)), tor((8.05, 0, 8.0), 0.2, 0.07, rot=(90, 0, 0))), PAL["iron"], voxel=0.02, fixed=60))
    return build("Lantern_String", P, MEDIUM, ao=(0.3, 0.25), floor=False, center=False)


def trophy_shape():
    """Unit trophy (about 2.2 tall) at the origin: returns (cup_and_stem, base)."""
    base = box((0, 0, 0.22), (0.5, 0.5, 0.22), r=0.08)
    stem = U(frustum(0.4, 0.62, 0.36, 0.2, r=0.05), rcone((0, 0, 0.6), (0, 0, 1.05), 0.12, 0.2), k=0.08)
    cup = SUB(INT(ell((0, 0, 1.55), (0.62, 0.62, 0.62)), slab(zmax=1.85)), ell((0, 0, 1.78), (0.5, 0.5, 0.45)), k=0.04)
    rim = tor((0, 0, 1.85), 0.55, 0.07)
    handles = U(tor((0.62, 0, 1.55), 0.24, 0.07, rot=(90, 0, 0)), tor((-0.62, 0, 1.55), 0.24, 0.07, rot=(90, 0, 0)))
    return U(stem, cup, rim, handles, k=0.04), base


def a_trophy_shelf():
    P = []
    cab = box((0, 0, 1.6), (3.0, 0.9, 1.6), r=0.18)
    cab = SUB(cab, box((0, -0.75, 2.3), (2.65, 0.6, 0.6), r=0.08), box((0, -0.75, 0.95), (2.65, 0.6, 0.55), r=0.08))
    P.append(Part(cab, PAL["wood"], voxel=0.035, w=1.0))
    P.append(Part(box((0, 0, 3.25), (3.18, 1.02, 0.12), r=0.08), PAL["wood_l"], voxel=0.03, w=0.5))
    rng = random.Random(3)
    books, bcols = [], []
    x = -2.45
    while x < 2.2:
        w = rng.uniform(0.18, 0.28)
        h = rng.uniform(0.62, 0.9)
        books.append(((x + w, -0.35, 0.4), (0, rng.uniform(-4, 4) if x < 1.5 else -14, 0), (w / 0.25, 1.0, h / 0.8)))
        bcols.append(rng.choice([PAL["red"], PAL["teal"], PAL["yellow"], PAL["purple"], PAL["leaf"], PAL["coral"]]))
        x += w * 2 + 0.03
    P.append(Part(box((0, 0, 0.4), (0.25, 0.45, 0.4), r=0.05), cols=bcols, inst=books, voxel=0.025, fixed=24))
    medal = U(cyl((0, 0, 0), 0.32, 0.06, r=0.03, rot=(90, 0, 0)))
    ribbon = U(box((-0.12, 0.02, 0.45), (0.1, 0.03, 0.3), r=0.02, rot=(0, 20, 0)), box((0.12, 0.02, 0.45), (0.1, 0.03, 0.3), r=0.02, rot=(0, -20, 0)))
    medals = [((-1.6, -0.5, 2.25), None), ((0.0, -0.5, 2.3), None), ((1.6, -0.5, 2.25), None)]
    P.append(Part(medal, cols=[PAL["silver"], PAL["gold"], PAL["bronze"]], inst=medals, voxel=0.015, fixed=50))
    P.append(Part(ribbon, cols=[PAL["blue"], PAL["red"], PAL["leaf"]], inst=medals, voxel=0.015, fixed=40))
    stands = [((-1.6, 0.0, 1.7), None), ((0.0, 0.0, 1.75), None), ((1.6, 0.0, 1.7), None)]
    P.append(Part(box((0, 0, 0), (0.28, 0.12, 0.3), r=0.04, rot=(-15, 0, 0)), PAL["wood_d"], voxel=0.02, fixed=24, inst=stands))
    cup, base = trophy_shape()
    tro = [((0, -0.05, 3.37), (0, 0, 0), 1.0), ((-2.0, -0.05, 3.37), (0, 0, 15), 0.78), ((2.0, -0.05, 3.37), (0, 0, -15), 0.7)]
    P.append(Part(cup, cols=[PAL["gold"], PAL["silver"], PAL["bronze"]], inst=tro, voxel=0.02, fixed=420, hi=0.4))
    P.append(Part(base, PAL["wood_d"], inst=tro, voxel=0.02, fixed=40))
    stars = extrude(star2(0, 0, 0.2, 0.09), (-0.2, -0.2), (0.2, 0.2), -0.04, 0.04, axis="y", r=0.015)
    P.append(Part(stars, PAL["yellow"], voxel=0.01, fixed=30, inst=[((0, -0.53, 3.59), None), ((-2.0 + 0.1, -0.44, 3.54), (0, 0, 15), 0.8), ((2.0 - 0.1, -0.45, 3.52), (0, 0, -15), 0.7)]))
    P.append(Part(U(*[sph((sx * 2.7, sy * 0.65, 0.08), 0.2) for sx in (-1, 1) for sy in (-1, 1)]), PAL["wood_d"], voxel=0.02, w=0.2))
    return build("Trophy_Shelf", P, MEDIUM, ao=(0.6, 0.5))


def a_sanctuary_sign():
    P = []
    px = -3.9
    P.append(Part(box((px, 0, 4.1), (0.34, 0.34, 4.1), r=0.14), PAL["wood_d"], voxel=0.03, w=0.8))
    P.append(Part(box((px, 0, 0.35), (0.62, 0.62, 0.35), r=0.18), PAL["stone"], voxel=0.03, w=0.3))
    P.append(Part(U(box((-0.2, 0, 7.55), (3.95, 0.26, 0.24), r=0.12), rod((px + 0.1, 0, 5.8), (px + 1.7, 0, 7.45), 0.15, r=0.06)),
                  PAL["wood"], voxel=0.03, w=0.8))
    P.append(Part(sph((px, 0, 8.35), 0.34), PAL["wood_l"], voxel=0.02, w=0.2))
    board = box((0.35, 0, 4.85), (3.05, 0.24, 1.5), r=0.3)
    board = SUB(board, box((0.35, -0.42, 4.85), (2.65, 0.25, 1.12), r=0.12))
    P.append(Part(board, PAL["wood"], voxel=0.03, w=1.0))
    P.append(Part(box((0.35, -0.15, 4.85), (2.7, 0.05, 1.17), r=0.03), PAL["wood_l"], voxel=0.03, w=0.3, hi=0.15))
    ropes = []
    for x in (-1.9, 2.6):
        ropes.append(Part(obj=tube_mesh([(x, 0, 7.4), (x + 0.02, 0, 6.85), (x, 0, 6.3)], 0.07, sides=6), col=PAL["straw"], fixed=10 ** 6))
    P += ropes
    P.append(Part(U(tor((-1.9, 0, 6.3), 0.14, 0.05, rot=(90, 0, 0)), tor((2.6, 0, 6.3), 0.14, 0.05, rot=(90, 0, 0))), PAL["iron"], voxel=0.012, fixed=60))
    leaves = []
    for i, (z, a) in enumerate(((1.2, 30), (2.2, 150), (3.3, 60), (4.4, 200), (5.6, 100), (6.8, 250))):
        c = (px + math.cos(math.radians(a)) * 0.38, math.sin(math.radians(a)) * 0.38, z)
        leaves.append((c, (0, 25 if i % 2 else -25, a)))
    P.append(Part(ell((0.25, 0, 0), (0.32, 0.16, 0.06)), PAL["leaf"], voxel=0.012, fixed=36, inst=leaves))
    vine = chain([(px + 0.36, -0.1, 0.8), (px - 0.2, -0.37, 2.0), (px - 0.38, 0.15, 3.2), (px + 0.2, 0.36, 4.5), (px + 0.37, -0.1, 5.7), (px - 0.1, -0.38, 7.0)], 0.06, k=0.02)
    P.append(Part(vine, PAL["leaf_d"], voxel=0.015, w=0.3))
    P.append(Part(petal_flower := U(*[ell((math.cos(a) * 0.15, math.sin(a) * 0.15, 0), (0.13, 0.13, 0.05)) for a in (2 * math.pi * i / 5 for i in range(5))]),
                  PAL["pink"], voxel=0.012, fixed=60, inst=[((px - 0.2, -0.4, 7.25), (80, 0, 0))]))
    return build("Sanctuary_Sign", P, MEDIUM, ao=(0.8, 0.5))


# ═══ TRIALS ═══════════════════════════════════════════════════════════════════

def a_race_startgate():
    P = []
    X = 9.0
    feet = U(*[ell((sx * X, 0, 0.5), (1.6, 1.9, 0.6)) for sx in (-1, 1)])
    P.append(Part(feet, PAL["yellow"], voxel=0.05, w=0.6))
    pillars = []
    for sx in (-1, 1):
        pillars.append(cap((sx * X, 0, 1.0), (sx * X, 0, 10.2), 1.0))
    P.append(Part(U(*pillars), PAL["red"], voxel=0.05, w=1.2))
    rings = U(*[tor((sx * X, 0, z), 1.02, 0.26) for sx in (-1, 1) for z in (2.6, 4.9, 7.2)])
    P.append(Part(rings, PAL["yellow"], voxel=0.04, w=0.8))
    P.append(Part(cap((-X, 0, 10.7), (X, 0, 10.7), 0.95), PAL["red"], voxel=0.05, w=1.2))
    P.append(Part(U(*[sph((sx * X, 0, 10.9), 1.2) for sx in (-1, 1)]), PAL["yellow"], voxel=0.04, w=0.6))
    bw, bh, bz = 7.2, 1.2, 8.65
    P.append(Part(box((0, 0, bz), (bw, 0.12, bh), r=0.06), PAL["white"], voxel=0.03, w=0.8, hi=0.15))
    sq = bw * 2 / 12
    blacks = [box((-bw + sq * (i + 0.5), 0, bz - bh + sq * (j + 0.5)), (sq * 0.5, 0.16, sq * 0.5), r=0.02)
              for i in range(12) for j in range(2) if (i + j) % 2 == 0]
    P.append(Part(U(*blacks), (0.16, 0.15, 0.2), voxel=0.03, w=0.8, hi=0.2))
    P.append(Part(U(*[cap((x, 0, bz + bh - 0.05), (x, 0, 10.0), 0.08) for x in (-6.2, -2.1, 2.1, 6.2)]), PAL["white"], voxel=0.02, w=0.2))
    poles = U(*[rod((sx * X, 0, 11.9), (sx * X, 0, 13.6), 0.08, r=0.03) for sx in (-1, 1)])
    P.append(Part(poles, PAL["white"], voxel=0.02, w=0.2))
    pen = extrude(poly2([(0.08, 13.55), (1.45, 13.2), (0.08, 12.85)]), (0, 12.8), (1.5, 13.6), -0.05, 0.05, axis="y", r=0.03)
    P.append(Part(pen, PAL["teal"], voxel=0.02, fixed=40, inst=[((-X, 0, 0), (0, 0, 0)), ((X, 0, 0), (0, 0, 0))]))
    return build("Race_StartGate", P, LARGE, ao=(1.0, 0.5), target=0.7)


def a_race_ring():
    P = []
    cz, R, r = 5.02, 4.36, 0.62
    ring = tor((0, 0, cz), R, r, rot=(90, 0, 0))
    P.append(Part(ring, PAL["white"], voxel=0.035, w=1.0))

    def seg_mask(n, phase):
        period = math.pi / n

        def fn(Pp):
            phi = np.mod(np.arctan2(Pp[:, 2] - cz, Pp[:, 0]) - phase, 2 * period)
            return ((np.abs(phi - period * 0.5) - period * 0.5) * R).astype(F32)
        return (fn, (np.array([-400] * 3, F32), np.array([400] * 3, F32)))
    P.append(Part(INT(grow(ring, 0.04), seg_mask(8, math.radians(90 - 11.25))), PAL["orange"], voxel=0.035, w=1.0))
    P.append(Part(tor((0, 0, cz), R - r + 0.06, 0.16, rot=(90, 0, 0)), (0.55, 0.9, 0.95), voxel=0.025, w=0.5, hi=0.35, lo=0.1))
    bulbs = [((math.cos(a) * R, -r + 0.02, cz + math.sin(a) * R), None) for a in (2 * math.pi * (i + 0.5) / 16 for i in range(16))]
    bulbs += [((math.cos(a) * R, r - 0.02, cz + math.sin(a) * R), None) for a in (2 * math.pi * (i + 0.5) / 16 for i in range(16))]
    P.append(Part(sph((0, 0, 0), 0.2), PAL["glow"], voxel=0.015, fixed=24, inst=bulbs, hi=0.4, lo=0.1))
    return build("Race_Ring", P, MEDIUM, ao=(0.5, 0.3), floor=False, center=False)


def coil_points(c, radius, z0, z1, turns, n_per=10):
    pts = []
    total = int(turns * n_per)
    for i in range(total + 1):
        t = i / total
        a = 2 * math.pi * turns * t
        pts.append((c[0] + math.cos(a) * radius, c[1] + math.sin(a) * radius, z0 + (z1 - z0) * t))
    return pts


def a_obstacle_hurdle():
    P = []
    X = 3.6
    P.append(Part(U(*[ell((sx * X, 0, 0.32), (0.75, 1.35, 0.36)) for sx in (-1, 1)]), PAL["blue"], voxel=0.03, w=0.8))
    coils = U(*[chain(coil_points((sx * X, 0), 0.34, 0.55, 1.45, 3.5), 0.08, k=0.0) for sx in (-1, 1)])
    P.append(Part(coils, PAL["metal"], voxel=0.018, w=0.9))
    P.append(Part(U(*[cap((sx * X, 0, 1.45), (sx * X, 0, 3.05), 0.3) for sx in (-1, 1)]), PAL["white"], voxel=0.03, w=0.7))
    P.append(Part(U(*[sph((sx * X, 0, 3.2), 0.42) for sx in (-1, 1)]), PAL["yellow"], voxel=0.025, w=0.5))
    bar = cap((-X + 0.1, 0, 2.7), (X - 0.1, 0, 2.7), 0.46)
    P.append(Part(bar, PAL["white"], voxel=0.03, w=1.0))
    bands = U(*[INT(grow(bar, 0.04), box((x, 0, 2.7), (0.5, 1, 1), r=0.0)) for x in (-2.2, 0.0, 2.2)])
    P.append(Part(bands, PAL["red"], voxel=0.03, w=0.8))
    return build("Obstacle_Hurdle", P, MEDIUM, ao=(0.6, 0.45))


def a_obstacle_bumper():
    P = []
    P.append(Part(cyl((0, 0, 0.15), 1.6, 0.15, r=0.1), (0.36, 0.38, 0.5), voxel=0.025, w=0.4))
    P.append(Part(rcone((0, 0, 0.3), (0, 0, 1.45), 0.95, 0.8), PAL["cream"], voxel=0.025, w=0.6))
    dome = U(INT(ell((0, 0, 1.55), (2.0, 2.0, 1.35)), slab(zmin=1.55)), cyl((0, 0, 1.62), 1.96, 0.16, r=0.14), k=0.1)
    P.append(Part(dome, PAL["red"], voxel=0.025, w=1.2))
    P.append(Part(tor((0, 0, 1.58), 1.98, 0.26), PAL["yellow"], voxel=0.02, w=0.6))
    spots = []
    for az, el, sc in ((30, 55, 1.0), (150, 50, 0.9), (270, 45, 1.1), (210, 20, 0.7), (90, 22, 0.75), (330, 22, 0.8), (0, 90, 0.9)):
        n = Vector((math.cos(math.radians(el)) * math.cos(math.radians(az)), math.cos(math.radians(el)) * math.sin(math.radians(az)), math.sin(math.radians(el))))
        pnt = Vector((n.x * 2.0, n.y * 2.0, 1.55 + n.z * 1.35))
        spots.append((tuple(pnt), (90 - el, 0, az + 90), sc))
    P.append(Part(ell((0, 0, 0), (0.34, 0.08, 0.34)), PAL["cream"], voxel=0.015, fixed=40, inst=[(p_, (r_[0] - 90, 0, r_[2]), sc_) for p_, r_, sc_ in spots]))
    return build("Obstacle_Bumper", P, SMALL, ao=(0.5, 0.5))


def a_smash_crate():
    P = [Part(crate_shape(2.0), PAL["wood_l"], voxel=0.035, w=1.2)]
    corners = [((sx * 1.78, sy * 1.78, z), None) for sx in (-1, 1) for sy in (-1, 1) for z in (0.34, 3.66)]
    P.append(Part(box((0, 0, 0), (0.42, 0.42, 0.38), r=0.1), PAL["metal"], voxel=0.02, fixed=60, inst=corners, hi=0.35))
    rivets = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for z in (0.34, 3.66):
                rivets.append(((sx * 1.78, sy * 2.2, z), None))
                rivets.append(((sx * 2.2, sy * 1.78, z), None))
    P.append(Part(sph((0, 0, 0), 0.09), PAL["rust"], voxel=0.012, fixed=16, inst=rivets))
    return build("Smash_Crate", P, SMALL, ao=(0.6, 0.5))


def a_smash_pillar():
    P = []
    P.append(Part(box((0, 0, 0.42), (1.55, 1.55, 0.42), r=0.16), PAL["stone_d"], voxel=0.035, w=0.6))
    col = cyl((0, 0, 4.1), 1.08, 3.35, r=0.05)
    flutes = U(*[cap((math.cos(a) * 1.13, math.sin(a) * 1.13, 1.2), (math.cos(a) * 1.13, math.sin(a) * 1.13, 7.0), 0.13)
                 for a in (2 * math.pi * (i + 0.5) / 12 for i in range(12))])
    capital = box((0, 0, 7.55), (1.5, 1.5, 0.45), r=0.16)
    chunk = sph((1.25, -1.2, 7.95), 0.95)
    crack1 = chain([(-0.35, -1.12, 6.6), (0.05, -1.14, 5.8), (-0.2, -1.12, 5.1), (0.25, -1.1, 4.2), (0.0, -1.1, 3.5)], 0.08, k=0.01)
    crack2 = chain([(0.85, -0.75, 3.0), (0.55, -0.98, 2.3), (0.9, -0.72, 1.6)], 0.07, k=0.01)
    body = SUB(U(SUB(col, flutes, k=0.08), capital), chunk, crack1, crack2, k=0.06)
    P.append(Part(bumps(body, 0.02, 2.5), mix(PAL["stone"], PAL["stone_b"], 0.35), voxel=0.035, w=1.5))
    rubble = bumps(box((0, 0, 0), (0.42, 0.34, 0.26), r=0.12), 0.03, 4.0)
    P.append(Part(rubble, mix(PAL["stone"], PAL["stone_b"], 0.35), voxel=0.02, fixed=80,
                  inst=[((1.95, -1.3, 0.24), (8, 5, 30)), ((-1.8, -1.7, 0.2), (-5, 10, -20), 0.8), ((1.5, -2.2, 0.18), (0, -12, 70), 0.6),
                        ((-2.05, 0.9, 0.2), (10, 0, 15), 0.75)]))
    P.append(Part(bumps(ell((-0.9, 0.9, 0.88), (0.7, 0.55, 0.16)), 0.03, 5.0), PAL["moss"], voxel=0.02, w=0.2))
    return build("Smash_Pillar", P, MEDIUM, ao=(0.8, 0.5))


def digit_strokes(d, cx, cz, y, s=1.0, r=0.13):
    def arc(c, rad, a0, a1, n=7):
        return [(cx + (c[0] + math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))) * rad) * s, y,
                 cz + (c[1] + math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))) * rad) * s) for i in range(n)]
    if d == 1:
        return U(cap((cx + 0.08 * s, y, cz - 0.6 * s), (cx + 0.08 * s, y, cz + 0.62 * s), r),
                 cap((cx + 0.08 * s, y, cz + 0.62 * s), (cx - 0.32 * s, y, cz + 0.3 * s), r),
                 cap((cx - 0.3 * s, y, cz - 0.62 * s), (cx + 0.46 * s, y, cz - 0.62 * s), r))
    if d == 2:
        top = arc((0, 0.28), 0.34, 160, -35)
        return U(chain(top, r, k=0.0), cap(top[-1], (cx - 0.4 * s, y, cz - 0.6 * s), r), cap((cx - 0.4 * s, y, cz - 0.62 * s), (cx + 0.45 * s, y, cz - 0.62 * s), r))
    return U(chain(arc((0, 0.32), 0.3, 150, -90), r, k=0.0), chain(arc((0, -0.3), 0.33, 90, -150), r, k=0.0))


def a_podium():
    P = []
    blocks = [(0.0, 3.0, 1, PAL["gold"]), (-4.05, 2.0, 2, PAL["silver"]), (4.05, 1.3, 3, PAL["bronze"])]
    P.append(Part(U(*[box((x, 0, h * 0.5), (2.02, 2.0, h * 0.5), r=0.22) for x, h, _, _ in blocks]), PAL["navy"], voxel=0.045, w=1.2))
    P.append(Part(U(*[box((x, 0, h - 0.02), (2.08, 2.06, 0.2), r=0.12) for x, h, _, _ in blocks]), PAL["cream"], voxel=0.035, w=0.8))
    for x, h, d, col in blocks:
        P.append(Part(box((x, 0, h + 0.18), (1.85, 1.85, 0.08), r=0.06), col, voxel=0.03, w=0.4, hi=0.35))
        sz = 0.95 if d == 1 else 0.8
        zc = h * 0.5 if d != 3 else h * 0.5 - 0.02
        if d == 3:
            sz = 0.62
        P.append(Part(digit_strokes(d, x, zc, -2.02, s=sz, r=0.14 * sz / 0.95 + 0.02), col, voxel=0.02, w=0.5, hi=0.35))
    P.append(Part(U(*[box((x, 0, 0.12), (2.06, 2.04, 0.12), r=0.08) for x, h, _, _ in blocks]), PAL["cream"], voxel=0.03, w=0.4))
    star = extrude(star2(0, 0, 0.5, 0.22), (-0.5, -0.5), (0.5, 0.5), -0.07, 0.07, axis="y", r=0.04)
    P.append(Part(star, PAL["yellow"], voxel=0.02, fixed=40, inst=[((0, -2.03, 3.0 * 0.5 + 0.95), None, 0.7)]))
    return build("Podium", P, MEDIUM, ao=(1.0, 0.5))


def a_balance_beam():
    P = []
    log = rod((0, -8.0, 3.05), (0, 8.0, 3.05), 0.68, r=0.18)
    P.append(Part(bumps(log, 0.04, 2.2, seed=12), PAL["bark"], voxel=0.035, w=1.2))
    ends = U(*[cyl((0, sy * 7.99, 3.05), 0.56, 0.04, rot=(90, 0, 0)) for sy in (-1, 1)])
    P.append(Part(ends, PAL["wood_l"], voxel=0.015, w=0.3))
    rings = U(*[tor((0, sy * 8.02, 3.05), rr, 0.035, rot=(90, 0, 0)) for sy in (-1, 1) for rr in (0.18, 0.36)])
    P.append(Part(rings, PAL["wood"], voxel=0.012, w=0.3))
    legs = []
    for y in (-6.0, 0.0, 6.0):
        legs += [rod((-1.65, y, 0.0), (0.45, y, 3.05), 0.22, r=0.08), rod((1.65, y, 0.0), (-0.45, y, 3.05), 0.22, r=0.08),
                 rod((-1.25, y, 0.75), (1.25, y, 0.75), 0.16, r=0.06)]
    P.append(Part(U(*legs), PAL["wood"], voxel=0.03, w=1.0))
    P.append(Part(U(*[ell((sx * 1.65, y, 0.1), (0.4, 0.35, 0.12)) for sx in (-1, 1) for y in (-6.0, 0.0, 6.0)]), PAL["stone"], voxel=0.025, w=0.3))
    stem = rcone((0, 0, 0), (0, 0, 0.35), 0.08, 0.06)
    capm = U(INT(ell((0, 0, 0.35), (0.3, 0.3, 0.22)), slab(zmin=0.3)), k=0.0)
    shrooms = [((0.55, -7.2, 3.55), (0, 30, 0)), ((0.66, -6.8, 3.4), (0, 45, 0), 0.7)]
    P.append(Part(stem, PAL["cream"], voxel=0.012, fixed=24, inst=shrooms))
    P.append(Part(capm, PAL["red"], voxel=0.012, fixed=50, inst=shrooms))
    P.append(Part(bumps(ell((-0.35, 3.0, 3.66), (0.45, 0.9, 0.12)), 0.03, 6.0), PAL["moss"], voxel=0.02, w=0.2))
    return build("Balance_Beam", P, MEDIUM, ao=(0.8, 0.5))


# ═══ REGISTRY ═════════════════════════════════════════════════════════════════

BUILDERS = [
    ("Fountain", a_fountain), ("Parade_Runway", a_parade_runway), ("Parade_Arch", a_parade_arch),
    ("Research_Board", a_research_board), ("Quest_Board", a_quest_board), ("Market_Stall", a_market_stall),
    ("Portal_Arch", a_portal), ("Lamp_Post", a_lamp_post), ("Bench_Park", a_bench_park),
    ("Planter_Box", a_planter_box), ("Balloon_Cluster", a_balloon_cluster), ("Bunting_Span", a_bunting_span),
    ("Tent_Striped", a_tent_striped), ("Statue_Pedestal", a_statue_pedestal),
    ("Nest", a_nest), ("Food_Bowl", a_food_bowl), ("Pet_Bed", a_pet_bed), ("Pond_Small", a_pond_small),
    ("StonePath_Tile", a_stonepath_tile), ("Garden_Bed", a_garden_bed), ("Greenhouse", a_greenhouse),
    ("Observatory", a_observatory), ("Treehouse", a_treehouse), ("Windmill", a_windmill),
    ("Lantern_String", a_lantern_string), ("Trophy_Shelf", a_trophy_shelf), ("Sanctuary_Sign", a_sanctuary_sign),
    ("Race_StartGate", a_race_startgate), ("Race_Ring", a_race_ring), ("Obstacle_Hurdle", a_obstacle_hurdle),
    ("Obstacle_Bumper", a_obstacle_bumper), ("Smash_Crate", a_smash_crate), ("Smash_Pillar", a_smash_pillar),
    ("Treasure_Chest", a_treasure_chest), ("Podium", a_podium), ("Balance_Beam", a_balance_beam),
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
    srgb_paint(o, lambda co, n: (0.62, 0.55, 0.78))
    fk.preview_tint(o, (1, 1, 1))
    return o


COMPANIONS = {"Portal_Arch": [("Portal_Disc", (0, 0, 0))], "Windmill": [("Windmill_Sails", WINDMILL_HUB)]}


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
        comp = [(bpy.data.objects[c], off) for c, off in COMPANIONS.get(name, []) if c in bpy.data.objects]
        for other in kit:
            other.hide_render = other is not o and other not in [c for c, _ in comp]
            other.location = (0, 0, 0)
        vs = _verts(o)
        for c, off in comp:
            c.location = off
            vs = np.concatenate([vs, _verts(c, off)])
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
        o.location = (0, 0, 0)
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
