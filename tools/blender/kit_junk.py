"""kit_junk — JUNKYARD + CRYSTAL CAVES static world meshes for Feed a Monster!

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/kit_junk.py
      -> art/build/kit_junk.fbx        (every asset, one object each, origin at base centre)
      -> art/previews/kit_junk.png     (contact sheet, list order, 5-stud capsule per tile)

Iterating on a few assets (no export, scratch sheet):
    KIT_ONLY=Tire_Single,OilDrum KIT_SHEET=/tmp/x.png Blender -b --factory-startup -P kit_junk.py

Style notes: junk is cheerful, chunky and toy-like (faded paint + rust accents); caves are
blue-grey rock with the only saturated "glow" colours in the game on crystals, glow caps,
glowworms and the ghost membrane. Colours are authored as sRGB hex and converted to the
linear values Blender's colour attributes expect, so the FBX carries the intended sRGB.
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
from mathutils.bvhtree import BVHTree

ROOT = "/Users/malik/rob"
KIT = "kit_junk"


# ═══ COLOUR ═══════════════════════════════════════════════════════════════════

def hexc(h):
    h = h.lstrip("#")
    s = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in s)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def lift(c, t):
    return mix(c, (1.0, 0.98, 0.95), t)


def dark(c, t):
    t = max(0.0, min(1.0, t))
    return tuple(x * (1.0 - t) for x in c)


def tone(c, n, hi=0.16, lo=0.38):
    """Base colour + fake sky light on top + darker underside."""
    z = n.z
    return lift(c, hi * z) if z > 0 else dark(c, lo * -z)


def ss(a, b, x):
    return fk.smoothstep(a, b, x)


def noise3(p, f=1.0, seed=0.0):
    """Cheap smooth-ish value in roughly [-1, 1] for blotches (rust, lichen)."""
    x, y, z = p[0] * f + seed * 1.7, p[1] * f - seed * 0.9, p[2] * f + seed * 0.37
    a = math.sin(x * 1.7 + math.sin(y * 1.1)) * math.sin(y * 1.9 + math.sin(z * 1.3)) * math.sin(z * 1.5 + math.sin(x * 0.9))
    b = math.sin(x * 3.1 + y * 0.7) * math.sin(y * 2.7 - z * 0.5) * math.sin(z * 3.3 + x * 0.4)
    return a * 0.75 + b * 0.35


# junkyard palette
RUBBER = hexc("#4a4650")
RUBBER_HI = hexc("#6d6874")
RUST = hexc("#b0643a")
RUST_DK = hexc("#80472e")
TEAL = hexc("#5fb0a4")
RED_FADED = hexc("#cf5d4d")
MUSTARD = hexc("#e3b448")
CREAM = hexc("#ece2c6")
MINT = hexc("#a6d6bf")
METAL = hexc("#9aa5ae")
METAL_DK = hexc("#5f6a74")
CHROME = hexc("#c9d1d6")
WOOD = hexc("#d29a5c")
WOOD_DK = hexc("#a26a3a")
GLASS = hexc("#44606a")
GLASS_HI = hexc("#a9d2dc")
OIL = hexc("#3a3343")
CONCRETE = hexc("#b1aca2")
EARTH = hexc("#b88c5e")
EARTH_DK = hexc("#4a3226")
DEAD_BLUE = hexc("#7888a0")
DEAD_BLUE_DK = hexc("#56647a")
BULB_OFF = hexc("#b9a656")
HAZARD_Y = hexc("#f0c233")
HAZARD_K = hexc("#34303a")

# cave palette
ROCK = hexc("#6f7b92")
ROCK_HI = hexc("#9aa7bd")
ROCK_DK = hexc("#454d5f")
BONE = hexc("#ede2c7")
BONE_DK = hexc("#c4b393")
CYAN = (hexc("#137fa6"), hexc("#2cc6e0"), hexc("#d2fbff"))
PURPLE = (hexc("#5a2fb0"), hexc("#9b5ef0"), hexc("#efdcff"))
PINK = (hexc("#b52f7d"), hexc("#f06cb6"), hexc("#ffe0f1"))
GLOW_TEAL = hexc("#3fe6cc")
GLOW_VIOLET = hexc("#b67af5")
GHOST = hexc("#d9c9fa")


# ═══ SDF HELPERS (kit-local) ══════════════════════════════════════════════════

def _R(rot):
    return sdf._rot_matrix(rot)


def cbounds(center, ext):
    c = np.asarray(center, dtype=np.float32)
    e = np.asarray(ext, dtype=np.float32) if not np.isscalar(ext) else np.full(3, ext, dtype=np.float32)
    return (c - e, c + e)


def rbox2(qx, qy, hx, hy, r):
    dx = np.abs(qx) - (hx - r)
    dy = np.abs(qy) - (hy - r)
    return np.hypot(np.maximum(dx, 0), np.maximum(dy, 0)) + np.minimum(np.maximum(dx, dy), 0) - r


def extrude(d2, z, h, r=0.0):
    wx = d2 + r
    wy = np.abs(z) - (h - r)
    return np.minimum(np.maximum(wx, wy), 0) + np.hypot(np.maximum(wx, 0), np.maximum(wy, 0)) - r


def euler_to(direction):
    """Euler degrees rotating +Z onto `direction`."""
    q = Vector((0, 0, 1)).rotation_difference(Vector(direction).normalized())
    return tuple(math.degrees(a) for a in q.to_euler())


def cyl_ab(a, b, r, rounding=0.0):
    a, b = Vector(a), Vector(b)
    c = (a + b) * 0.5
    return sdf.cylinder(tuple(c), r, (b - a).length * 0.5, rot=euler_to(b - a), rounding=rounding)


def tyre(center, R=1.0, hw=0.45, hh=0.42, rot=None, r=0.26, tread=0.07, n=18):
    """Chunky tyre: rounded-rectangle profile revolved about local Z, grooved tread."""
    Rm = _R(rot)

    def fn(P):
        Q = sdf._local(P, center, Rm)
        rho = np.hypot(Q[:, 0], Q[:, 1])
        d = rbox2(rho - R, Q[:, 2], hw, hh, r)
        if tread:
            ang = np.arctan2(Q[:, 1], Q[:, 0])
            g = np.clip(np.sin(ang * n) * 3.0, 0, 1)
            outer = np.clip((rho - R - hw + 0.22) / 0.22, 0, 1)
            d = d + tread * g * outer
        return d

    e = R + hw + 0.1
    return (fn, cbounds(center, max(e, hh + 0.1)))


def gear(center, r, hz, teeth, tooth=0.3, hole=0.25, holes=0, hole_r=0.2, rot=None, rounding=0.06):
    Rm = _R(rot)

    def fn(P):
        Q = sdf._local(P, center, Rm)
        rho = np.hypot(Q[:, 0], Q[:, 1])
        ang = np.arctan2(Q[:, 1], Q[:, 0])
        prof = r + tooth * 0.5 * np.clip(np.sin(ang * teeth) * 2.2, -1, 1)
        d2 = rho - prof
        if hole:
            d2 = np.maximum(d2, hole - rho)
        for i in range(holes):
            a = i / holes * math.tau
            hx, hy = math.cos(a) * r * 0.55, math.sin(a) * r * 0.55
            d2 = np.maximum(d2, hole_r - np.hypot(Q[:, 0] - hx, Q[:, 1] - hy))
        return extrude(d2, Q[:, 2], hz, rounding)

    return (fn, cbounds(center, r + tooth))


def tri_prism(center, half_side, hz, rot=None, rounding=0.1):
    """Equilateral triangle (point up, in local XZ... local X/Y plane) extruded along local Z."""
    Rm = _R(rot)
    k = math.sqrt(3.0)
    rr = half_side - rounding * k

    def fn(P):
        Q = sdf._local(P, center, Rm)
        px = np.abs(Q[:, 0]) - rr
        py = Q[:, 1] + rr / k
        cond = px + k * py > 0
        px2 = np.where(cond, (px - k * py) / 2, px)
        py2 = np.where(cond, (-k * px - py) / 2, py)
        px2 = px2 - np.clip(px2, -2 * rr, 0)
        d2 = -np.hypot(px2, py2) * np.sign(py2) - rounding
        return extrude(d2, Q[:, 2], hz, min(rounding, hz * 0.9))

    return (fn, cbounds(center, half_side * 1.3 + hz))


def stretch(shape, center, factors):
    c = np.asarray(center, dtype=np.float32)
    f = np.asarray(factors, dtype=np.float32)
    lo, hi = shape[1]
    span = np.maximum(np.abs(lo - c), np.abs(hi - c)) / np.minimum(f, 1.0)
    return (lambda P: shape[0]((P - c) * f + c) * float(min(1.0 / f.max(), 1.0)), (c - span, c + span))


def clip_ground(shape, z=0.0, k=0.0):
    """Cut everything below z (flat base)."""
    lo, hi = shape[1]
    plane = (lambda P: z - P[:, 2], (np.array([lo[0], lo[1], z - 0.5], np.float32), hi))
    return sdf.smooth_intersect(shape, plane, k=k) if k else (lambda P: np.maximum(shape[0](P), z - P[:, 2]), (np.array([lo[0], lo[1], z - 0.1], np.float32), hi))


def chain(points, radii, k=0.05):
    shapes = [sdf.round_cone(tuple(points[i]), tuple(points[i + 1]), radii[i], radii[i + 1]) for i in range(len(points) - 1)]
    return sdf.smooth_union(*shapes, k=k) if k else sdf.union(*shapes)


def bezier(a, m, b, n=8):
    a, m, b = Vector(a), Vector(m), Vector(b)
    return [a * (1 - t) ** 2 + m * 2 * t * (1 - t) + b * t * t for t in (i / (n - 1) for i in range(n))]


# ═══ PARTS ════════════════════════════════════════════════════════════════════

def _setup_part(o, paint, col, flat, ao, hi, lo):
    if flat:
        fk.shade_flat(o)
    if paint is None:
        paint = (lambda co, n, c=col: tone(c, n, hi, lo))
    fk.paint(o, paint)
    if ao is not None:
        o["ao"] = ao
    return o


def decim(o, tris):
    """fk.decimate_to overshoots ~10% on quad meshes; re-run until under target."""
    target = tris
    for _ in range(5):
        o = fk.decimate_to(o, target)
        n = fk.triangle_count(o)
        if n <= tris:
            break
        target = int(target * tris / n * 0.98)
    return o


def part(shape, voxel, tris, col=None, paint=None, flat=False, ao=None, hi=0.16, lo=0.38):
    o = sdf.to_mesh("_part", shape, voxel=voxel)
    o = decim(o, tris)
    return _setup_part(o, paint, col, flat, ao, hi, lo)


def paint_regions(obj, regions, blend=0.0):
    """regions: [(shape, painter(co, n))]. Each vertex takes the painter of the nearest shape."""
    me = obj.data
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    D = np.stack([s[0](co) for s, _ in regions])
    idx = np.argmin(D, axis=0)
    cols = [regions[idx[i]][1](v.co, v.normal) for i, v in enumerate(me.vertices)]
    layer = fk.ensure_color_layer(obj)
    for poly in me.polygons:
        for li in poly.loop_indices:
            c = cols[me.loops[li].vertex_index]
            layer.data[li].color = (c[0], c[1], c[2], 1.0)
    return obj


def region_part(shape, regions, voxel, tris, ao=None, flat=False):
    o = sdf.to_mesh("_part", shape, voxel=voxel)
    o = decim(o, tris)
    if flat:
        fk.shade_flat(o)
    paint_regions(o, regions)
    if ao is not None:
        o["ao"] = ao
    return o


def bm_object(bm, name="_part"):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    fk.link(o)
    return o


def _frame(tangent):
    t = Vector(tangent).normalized()
    up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    u = t.cross(up).normalized()
    v = t.cross(u).normalized()
    return u, v


def tube_part(points, radius, sides=6, col=None, paint=None, caps=True, ao=None, hi=0.16, lo=0.38, smooth=True):
    """Low-poly tube along a polyline (wires, cables, antennas). radius may be a list."""
    pts = [Vector(p) for p in points]
    radii = radius if isinstance(radius, (list, tuple)) else [radius] * len(pts)
    bm = bmesh.new()
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[-1] - pts[-2]
        else:
            t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
        u, v = _frame(t)
        ring = [bm.verts.new(p + (u * math.cos(a) + v * math.sin(a)) * radii[i])
                for a in (j / sides * math.tau for j in range(sides))]
        rings.append(ring)
    for i in range(len(rings) - 1):
        for j in range(sides):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % sides], rings[i + 1][(j + 1) % sides], rings[i + 1][j]))
    if caps:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    bm.normal_update()
    o = bm_object(bm)
    if smooth:
        fk.shade_smooth(o)
    return _setup_part(o, paint, col, not smooth, ao, hi, lo)


def crystal_part(base, direction, length, radius, colors, seed=0, tip=0.3, spin=None, ao=0.15):
    """Faceted hexagonal prism with a pointed tip. colors = (deep, mid, tip)."""
    rng = random.Random(seed)
    axis = Vector(direction).normalized()
    u, v = _frame(axis)
    spin = rng.uniform(0, math.tau) if spin is None else spin
    base = Vector(base)
    rings_def = ((0.0, 0.82), (0.45, 1.0), (1.0 - tip, 0.97), (1.0 - tip * 0.72, 0.72))
    bm = bmesh.new()
    rings = []
    for t, rf in rings_def:
        c = base + axis * length * t
        rings.append([bm.verts.new(c + (u * math.cos(a + spin) + v * math.sin(a + spin)) * radius * rf)
                      for a in (j / 6 * math.tau for j in range(6))])
    tip_off = (u * rng.uniform(-0.12, 0.12) + v * rng.uniform(-0.12, 0.12)) * radius
    apex = bm.verts.new(base + axis * length + tip_off)
    for i in range(len(rings) - 1):
        for j in range(6):
            bm.faces.new((rings[i][j], rings[i][(j + 1) % 6], rings[i + 1][(j + 1) % 6], rings[i + 1][j]))
    for j in range(6):
        bm.faces.new((rings[-1][j], rings[-1][(j + 1) % 6], apex))
    bm.faces.new(list(reversed(rings[0])))
    bm.normal_update()
    o = bm_object(bm)
    fk.shade_flat(o)
    deep, midc, tipc = colors
    L = Vector((-0.45, -0.55, 0.7)).normalized()
    me = o.data
    layer = fk.ensure_color_layer(o)
    for poly in me.polygons:
        facet = 0.82 + 0.3 * max(0.0, poly.normal.dot(L)) + (0.05 if poly.index % 2 else -0.03)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            t = max(0.0, min(1.0, (co - base).dot(axis) / length))
            c = mix(deep, midc, t / 0.5) if t < 0.5 else mix(midc, tipc, ((t - 0.5) / 0.5) ** 1.6)
            c = tuple(min(1.0, x * facet) for x in c)
            layer.data[li].color = (c[0], c[1], c[2], 1.0)
    o["ao"] = ao
    return o


def xform(o, loc=(0, 0, 0), rot=(0, 0, 0), pivot=(0, 0, 0)):
    pv = Vector(pivot)
    m = Matrix.Translation(Vector(loc) + pv) @ Euler([math.radians(a) for a in rot]).to_matrix().to_4x4() @ Matrix.Translation(-pv)
    o.data.transform(m)
    o.data.update()
    return o


def join_keep(objs, name):
    """Join without forcing smooth shading (crystals stay faceted)."""
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    for o in objs:
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    fk.link(obj)
    obj.name = name
    me.name = name
    return obj


def _coords(o):
    co = np.empty(len(o.data.vertices) * 3, dtype=np.float32)
    o.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def finish(name, parts, ao=0.45, dist=1.2, samples=16, centre=True):
    parts = [p for p in parts if p is not None]
    allc = np.concatenate([_coords(p) for p in parts])
    lo, hi = allc.min(axis=0), allc.max(axis=0)
    off = Vector((-(lo[0] + hi[0]) / 2 if centre else 0.0, -(lo[1] + hi[1]) / 2 if centre else 0.0, -lo[2]))
    for p in parts:
        p.data.transform(Matrix.Translation(off))
        p.data.update()
    for p in parts:
        others = [q for q in parts if q is not p]
        fk.bake_ao(p, occluders=others, samples=samples, distance=p.get("ao_dist", dist),
                   strength=p.get("ao", ao), floor_z=0.0)
    obj = join_keep(parts, name)
    fk.box_uv(obj, 2.0)
    obj.data.materials.clear()
    return obj


# ═══ REGISTRY ═════════════════════════════════════════════════════════════════

ASSETS = []


def asset(name, budget):
    def deco(fn):
        ASSETS.append((name, budget, fn))
        return fn
    return deco


# ══════════════════════════════════════════════════════════════════════════════
# JUNKYARD
# ══════════════════════════════════════════════════════════════════════════════

def rust_mix(c, co, amount=0.5, f=0.9, seed=0.0, low=0.0):
    """Blend rust blotches into a paint colour. low: extra rust near the ground (z below)."""
    nval = noise3(co, f, seed)
    t = ss(0.55 - amount * 0.5, 0.75 - amount * 0.5, nval)
    if low:
        t = max(t, ss(low, 0.0, co.z) * 0.8)
    return mix(c, mix(RUST, RUST_DK, 0.5 + 0.5 * noise3(co, f * 2.3, seed + 3)), t)


def tyre_paint(center, rot=None, R=1.0, whitewall=False):
    Rinv = Euler([math.radians(a) for a in (rot or (0, 0, 0))]).to_matrix().inverted()
    c = Vector(center)

    def fn(co, n):
        q = Rinv @ (co - c)
        rho = math.hypot(q.x, q.y)
        col = RUBBER
        if whitewall and abs(q.z) > 0.3 and R - 0.08 < rho < R + 0.16:
            col = hexc("#cfc6b6")
        nl = (Rinv @ n)
        rim = abs(nl.z)  # sidewalls a touch lighter than tread
        col = mix(col, RUBBER_HI, 0.25 * rim if not whitewall or col is RUBBER else 0.0)
        return tone(col, n, 0.22, 0.4)

    return fn


@asset("Tire_Single", 1500)
def build_tire_single(name):
    c = (0, 0, 1.45)
    rot = (90, 0, 0)
    t = part(tyre(c, R=1.0, hw=0.47, hh=0.46, rot=rot, tread=0.08, n=20), 0.035, 1250,
             paint=tyre_paint(c, rot, 1.0))
    # flatten the contact a hair so it sits
    return finish(name, [t], ao=0.5, dist=0.8)


@asset("Tire_Stack", 3500)
def build_tire_stack(name):
    parts = []
    specs = (((0.0, 0.0, 0.46), (0, 0, 0), False),
             ((0.22, -0.12, 1.32), (0, 0, 20), True),
             ((-0.12, 0.16, 2.22), (5, -3, 40), False))
    for c, rot, ww in specs:
        parts.append(part(tyre(c, R=0.98, hw=0.46, hh=0.44, rot=rot, tread=0.07, n=18), 0.04, 1050,
                          paint=tyre_paint(c, rot, 0.98, whitewall=ww)))
    return finish(name, parts, ao=0.5, dist=0.9)


@asset("CarWreck", 8000)
def build_car(name):
    parts = []

    def crush(x, z):
        """Something heavy sat on the roof: the cabin folds down in the middle."""
        return 1.05 * math.exp(-(x / 3.2) ** 2) * min(1.0, max(0.0, (z - 1.6) / 2.0))

    def crushed(shape):
        def P2(P):
            Q = P.copy()
            w = np.clip((P[:, 2] - 1.6) / 2.0, 0, 1)
            Q[:, 2] = P[:, 2] + 1.05 * np.exp(-(P[:, 0] / 3.2) ** 2) * w
            return Q
        return sdf.warp(shape, P2, pad=0.2)

    lower = sdf.round_box((0, 0, 1.7), (5.6, 2.55, 1.2), 0.9)
    body = sdf.smooth_subtract(lower, sdf.sphere((4.4, -0.7, 3.2), 1.15), k=0.5)
    body = sdf.smooth_subtract(body, sdf.sphere((-4.6, 1.1, 3.05), 0.85), k=0.4)
    for x in (-3.55, 3.55):
        for ys in (-1, 1):
            body = sdf.smooth_subtract(body, cyl_ab((x, ys * 1.7, 1.0), (x, ys * 3.2, 1.0), 1.25), k=0.15)
    cabin = sdf.round_box((-0.4, 0.0, 3.2), (2.8, 2.2, 1.35), 1.0)
    win_side = [((-2.55, -0.65), 3.55), ((-0.3, 1.6), 3.55)]
    for ys in (-1, 1):
        for (x0, x1), z in win_side:
            cabin = sdf.smooth_subtract(cabin, sdf.round_box(((x0 + x1) / 2, ys * 2.25, z), ((x1 - x0) / 2, 0.25, 0.62), 0.22), k=0.05)
    cabin = sdf.smooth_subtract(cabin, sdf.round_box((2.3, 0, 3.55), (0.3, 1.7, 0.62), 0.22, rot=(0, -30, 0)), k=0.05)
    cabin = sdf.smooth_subtract(cabin, sdf.round_box((-3.1, 0, 3.55), (0.3, 1.7, 0.55), 0.22, rot=(0, 28, 0)), k=0.05)
    shell = crushed(sdf.smooth_union(body, cabin, k=0.45))

    def body_paint(co, n):
        well = min(math.hypot(co.x - 3.55, co.z - 1.0), math.hypot(co.x + 3.55, co.z - 1.0))
        if well < 1.32 and abs(co.y) < 2.45 and co.z < 2.3:
            return hexc("#34383e")
        c = rust_mix(TEAL, co, amount=0.4, f=0.5, seed=2.0, low=0.9)
        return tone(c, n, 0.2, 0.42)

    parts.append(part(shell, 0.07, 4400, paint=body_paint))

    def glare(cx, cz):
        return lambda co, n: mix(GLASS, GLASS_HI, 0.7 if abs((co.x - cx) - (co.z - cz) * 0.9) < 0.2 else 0.0)

    for ys in (-1, 1):
        for (x0, x1), z in win_side:
            cx = (x0 + x1) / 2
            parts.append(part(crushed(sdf.round_box((cx, ys * 2.13, z), ((x1 - x0) / 2 + 0.05, 0.15, 0.66), 0.14)), 0.05, 120,
                              paint=glare(cx, z), ao=0.2))
    parts.append(part(crushed(sdf.round_box((2.25, 0, 3.55), (0.2, 1.75, 0.66), 0.14, rot=(0, -30, 0))), 0.05, 140,
                      paint=lambda co, n: mix(GLASS, GLASS_HI, 0.7 if abs(co.y * 0.8 + (co.z - 3.3) * 1.2) < 0.22 else 0.0), ao=0.2))
    parts.append(part(crushed(sdf.round_box((-3.05, 0, 3.55), (0.2, 1.75, 0.58), 0.14, rot=(0, 28, 0))), 0.05, 120,
                      col=GLASS, ao=0.2))
    for x, rz in ((5.75, -4), (-5.75, 5)):
        parts.append(part(sdf.round_box((x, 0, 1.15), (0.4, 2.7, 0.36), 0.3, rot=(0, 0, rz)), 0.05, 260,
                          paint=lambda co, n: tone(rust_mix(METAL, co, 0.3, 1.2, 5.0), n, 0.25, 0.4)))
    # big round cartoon headlights: one bright, one dead and droopy
    parts.append(part(sdf.ellipsoid((5.55, -1.55, 2.25), (0.4, 0.55, 0.52)), 0.04, 160,
                      paint=lambda co, n: tone(hexc("#f6e9b4"), n, 0.3, 0.2), ao=0.2))
    parts.append(part(sdf.ellipsoid((5.5, 1.55, 2.05), (0.4, 0.5, 0.42), rot=(20, 0, 0)), 0.04, 160,
                      paint=lambda co, n: tone(hexc("#a9a58c"), n, 0.2, 0.3), ao=0.2))
    for ys in (-1, 1):
        parts.append(part(sdf.round_box((-5.72, ys * 1.8, 2.2), (0.24, 0.45, 0.32), 0.15), 0.04, 100,
                          col=hexc("#d8544a"), ao=0.2))
    for x in (-3.55, 3.55):
        c = (x, 2.25, 1.0)
        rot = (90, 0, 0)
        parts.append(part(tyre(c, R=0.6, hw=0.38, hh=0.4, rot=rot, r=0.22, tread=0.06, n=14), 0.04, 560,
                          paint=tyre_paint(c, rot, 0.6)))
        parts.append(part(sdf.cylinder((x, 2.66, 1.0), 0.52, 0.08, rot=(90, 0, 0), rounding=0.06), 0.035, 120,
                          paint=lambda co, n: tone(CHROME, n, 0.2, 0.3)))
    for ys in (-1, 1):
        parts.append(part(sdf.capsule((0.3, ys * 2.58, 2.55), (0.85, ys * 2.58, 2.55), 0.1), 0.03, 70, col=CHROME, ao=0.2))
    for p in parts:
        xform(p, rot=(7.0, 0, 0))
    return finish(name, parts, ao=0.5, dist=1.6)


def plank_paint(base, axis=2, period=0.72, groove=0.1):
    def fn(co, n):
        v = co[axis] / period
        f = abs(v - round(v))
        c = base if f > groove else dark(base, 0.3)
        grain = 0.04 * math.sin(co[(axis + 1) % 3] * 3.1 + co[axis] * 7.0)
        c = tuple(min(1, x * (1 + grain)) for x in c)
        return tone(c, n, 0.18, 0.4)
    return fn


def battery_part(a, d, length, r, tris=220):
    a = Vector(a)
    axis = Vector(d).normalized()
    b = a + axis * length
    shape = sdf.union(cyl_ab(a, b, r, rounding=r * 0.3), cyl_ab(b - axis * 0.05, b + axis * r * 0.45, r * 0.38, rounding=r * 0.12))

    def fn(co, n):
        t = (co - a).dot(axis)
        if t > length - 0.02:
            return tone(CHROME, n, 0.25, 0.3)
        return tone(MUSTARD if t > length * 0.62 else HAZARD_K, n, 0.25, 0.4)

    return part(shape, 0.03, tris, paint=fn, ao=0.35)


@asset("Crate_A", 1500)
def build_crate_a(name):
    h = 1.5
    core = sdf.round_box((0, 0, h), (h - 0.1, h - 0.1, h - 0.1), 0.12)
    boards = []
    e = h - 0.2
    for a in range(3):
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                c = [0.0, 0.0, 0.0]
                half = [0.2, 0.2, 0.2]
                half[a] = h
                o = [i for i in range(3) if i != a]
                c[o[0]] = s1 * e
                c[o[1]] = s2 * e
                c[2] += h
                boards.append(sdf.round_box(tuple(c), tuple(half), 0.1))
    # diagonal braces on the four sides
    diag = []
    for ax, s in ((0, -1), (0, 1), (1, -1), (1, 1)):
        c = [0.0, 0.0, h]
        c[ax] = s * (h - 0.06)
        half = [0.14, 0.14, 0.14]
        half[ax] = 0.09
        half[1 - ax] = 1.7
        rot = (0, 45 * s, 0) if ax == 1 else (45 * s, 0, 0)
        if ax == 1:
            half = (1.7, 0.09, 0.19)
        else:
            half = (0.09, 1.7, 0.19)
        diag.append(sdf.round_box(tuple(c), half, 0.08, rot=rot))
    inner = sdf.round_box((0, 0, h), (h - 0.3, h - 0.3, h - 0.3), 0.05)
    diag_clip = sdf.smooth_intersect(sdf.union(*diag), sdf.round_box((0, 0, h), (h, h, h - 0.25), 0.05), k=0.0)
    frame = sdf.union(*boards, diag_clip)
    shape = sdf.union(core, frame)
    regions = [
        (core, plank_paint(WOOD, axis=2, period=0.66)),
        (sdf.offset(frame, 0.035), lambda co, n: tone(rust_mix(WOOD_DK, co, 0.15, 1.3, 7.0), n, 0.18, 0.4)),
    ]
    o = region_part(shape, regions, 0.04, 1450)
    return finish(name, [o], ao=0.5, dist=0.8)


@asset("Crate_B", 1500)
def build_crate_b(name):
    hx, hy, hz = 1.6, 1.3, 1.1
    parts = []
    slats = []
    for i, z in enumerate((0.42, 1.12, 1.82)):
        for ys in (-1, 1):
            slats.append(sdf.round_box((0, ys * hy, z), (hx - 0.1, 0.1, 0.3), 0.08, rot=(0, (1.5 if i == 1 else -1) * ys, 0)))
        for xs in (-1, 1):
            slats.append(sdf.round_box((xs * hx, 0, z), (0.1, hy - 0.1, 0.3), 0.08))
    posts = [sdf.round_box((xs * (hx - 0.05), ys * (hy - 0.05), hz), (0.2, 0.2, hz + 0.05), 0.1) for xs in (-1, 1) for ys in (-1, 1)]
    wood = sdf.union(*slats, *posts, sdf.round_box((0, 0, 0.12), (hx - 0.05, hy - 0.05, 0.12), 0.06))
    parts.append(region_part(wood, [
        (sdf.union(*slats), lambda co, n: tone(mix(WOOD, hexc("#e0b27a"), 0.3 + 0.2 * math.sin(co.x * 5 + co.z * 3)), n, 0.2, 0.4)),
        (sdf.union(*posts), lambda co, n: tone(WOOD_DK, n, 0.18, 0.4)),
    ], 0.04, 900))
    # dark interior visible through the gaps
    parts.append(part(sdf.round_box((0, 0, 1.0), (hx - 0.2, hy - 0.2, 0.95), 0.05), 0.08, 60, col=hexc("#3b2c26"), ao=0.0))
    # chunky batteries poking out of the top (black body, gold cap, chrome + nub)
    for (x, y, tilt, spin) in ((-0.55, -0.15, 16, 20), (0.55, 0.3, -12, -40)):
        a = Vector((x, y, 1.0))
        d = Euler((math.radians(tilt), 0, math.radians(spin))).to_matrix() @ Vector((0, 0, 1))
        parts.append(battery_part(a, d, 1.9, 0.45))
    return finish(name, parts, ao=0.5, dist=0.9)


@asset("OilDrum", 1500)
def build_oildrum(name):
    R, H = 1.12, 3.5
    body = sdf.cylinder((0, 0, H / 2), R, H / 2, rounding=0.14)
    ribs = [sdf.torus((0, 0, z), R - 0.02, 0.11) for z in (1.18, 2.32)]
    rim = sdf.torus((0, 0, H - 0.1), R - 0.08, 0.12)
    drum = sdf.smooth_union(body, *ribs, rim, k=0.06)
    drum = sdf.smooth_subtract(drum, sdf.cylinder((0, 0, H + 0.02), R - 0.2, 0.12), k=0.06)
    drum = sdf.smooth_subtract(drum, sdf.sphere((-0.95, -1.15, 2.55), 0.6), k=0.35)
    drum = sdf.smooth_subtract(drum, sdf.sphere((1.2, 0.75, 0.75), 0.4), k=0.25)
    bung = sdf.cylinder((0.45, 0.35, H - 0.08), 0.2, 0.1, rounding=0.04)
    shape = sdf.union(drum, bung)

    def paint_fn(co, n):
        c = RED_FADED
        if 1.33 < co.z < 2.17:
            c = hexc("#e2bf6e")
        if co.z > H - 0.2 and math.hypot(co.x, co.y) < R - 0.12:
            c = hexc("#9c4a42")
        if math.hypot(co.x - 0.45, co.y - 0.35) < 0.24 and co.z > H - 0.2:
            c = METAL
        c = rust_mix(c, co, amount=0.35, f=1.1, seed=11.0, low=0.5)
        return tone(c, n, 0.18, 0.4)

    parts = [part(shape, 0.035, 1250, paint=paint_fn)]
    blobs = [sdf.ellipsoid(c, (r, r * 0.8, 0.09)) for c, r in (((0.9, -1.2, 0.0), 0.8), ((1.6, -1.7, 0.0), 0.55), ((0.3, -1.75, 0.0), 0.45))]
    puddle = clip_ground(sdf.smooth_union(*blobs, k=0.3))
    parts.append(part(puddle, 0.035, 260, paint=lambda co, n: mix(OIL, hexc("#8a7fa0"), 0.6) if math.hypot(co.x - 1.0, co.y + 1.35) < 0.25 else OIL, ao=0.15))
    return finish(name, parts, ao=0.5, dist=0.9)


# ── scrap piles ──────────────────────────────────────────────────────────────

def mound_part(center, radii, seed, lumps, tris, voxel=0.06):
    rng = random.Random(seed)
    cx, cy, cz = center
    shapes = [sdf.ellipsoid(center, radii)]
    for i in range(lumps):
        a = rng.uniform(0, math.tau)
        r = rng.uniform(0.25, 0.65)
        c = (cx + math.cos(a) * radii[0] * r, cy + math.sin(a) * radii[1] * r, cz + rng.uniform(0.0, radii[2] * 0.35))
        s = rng.uniform(0.35, 0.5)
        shapes.append(sdf.ellipsoid(c, (radii[0] * s, radii[1] * s, radii[2] * rng.uniform(0.55, 0.8))))
    shape = clip_ground(sdf.noise_bumps(sdf.smooth_union(*shapes, k=0.9), 0.07, 2.0, seed))
    bits = (TEAL, MUSTARD, RED_FADED, METAL)

    def fn(co, n):
        c = mix(hexc("#7c7068"), hexc("#958a80"), 0.5 + 0.5 * noise3(co, 1.8, seed))
        c = rust_mix(c, co, amount=0.6, f=1.1, seed=seed + 1)
        v = noise3(co, 2.6, seed + 5)
        if v > 0.5:
            c = mix(c, bits[int((co.x * 3 + co.y * 5) % 4)], 0.65)
        return tone(c, n, 0.2, 0.45)

    return part(shape, voxel, tris, paint=fn)


def sheet_part(center, half, rot, col, tris=160, seed=0.0, holes=0):
    shape = sdf.round_box((0, 0, 0), (half[0], 0.1, half[1]), 0.09)
    for i in range(holes):
        shape = sdf.smooth_subtract(shape, sdf.cylinder((-half[0] * 0.5 + i * half[0], 0, half[1] * 0.35), 0.16, 0.3, rot=(90, 0, 0)), k=0.03)

    def fn(co, n):
        edge = max(abs(co.x) / half[0], abs(co.z) / half[1])
        c = rust_mix(col, co, amount=0.3, f=1.4, seed=seed)
        c = mix(c, RUST, ss(0.78, 0.98, edge) * 0.8)
        return tone(c, n, 0.22, 0.4)

    o = part(shape, 0.04, tris, paint=fn)
    return xform(o, loc=center, rot=rot)


def pipe_part(a, b, r, col, tris=260, wall=0.1, seed=0.0):
    a, b = Vector(a), Vector(b)
    axis = (b - a).normalized()
    shape = sdf.smooth_subtract(cyl_ab(a, b, r, rounding=0.06), cyl_ab(a - axis, b + axis, r - wall * 1.6), k=0.03)

    def fn(co, n):
        rel = co - a
        radial = (rel - axis * rel.dot(axis)).length
        if radial < r - wall * 1.2:
            return hexc("#2e2a30")
        return tone(rust_mix(col, co, 0.35, 1.2, seed), n, 0.22, 0.4)

    return part(shape, 0.035, tris, paint=fn)


def gear_part(center, r, rot, col=METAL, teeth=10, tris=320, seed=0.0, hz=0.18):
    shape = gear((0, 0, 0), r, hz, teeth, tooth=r * 0.28, hole=r * 0.2, holes=4 if r > 0.8 else 0, hole_r=r * 0.14)
    o = part(shape, 0.035, tris, paint=lambda co, n: tone(rust_mix(col, co, 0.5, 1.6, seed), n, 0.22, 0.4))
    return xform(o, loc=center, rot=rot)


def horseshoe_part(center, rot, Rm=0.55, rm=0.24, L=0.55, tris=300, tip_col=None):
    arc = sdf.torus((0, 0, 0), Rm, rm, rot=(90, 0, 0))
    arc = (lambda P, f=arc[0]: np.maximum(f(P), -P[:, 2]), arc[1])
    legs = [cyl_ab((s * Rm, 0, 0.05), (s * Rm, 0, -L), rm, rounding=0.05) for s in (-1, 1)]
    shape = sdf.smooth_union(arc, *legs, k=0.05)

    def fn(co, n):
        c = (tip_col or CHROME) if co.z < -L + 0.32 else hexc("#dc4a3e")
        return tone(c, n, 0.25, 0.4)

    o = part(shape, 0.03, tris, paint=fn, ao=0.3)
    return xform(o, loc=center, rot=rot)


def hubcap_part(center, rot, r=0.6, tris=140):
    shape = sdf.smooth_union(sdf.cylinder((0, 0, 0), r, 0.07, rounding=0.05), sdf.ellipsoid((0, 0, 0.05), (r * 0.4, r * 0.4, 0.2)), k=0.1)
    o = part(shape, 0.03, tris, paint=lambda co, n: tone(CHROME, n, 0.3, 0.35), ao=0.3)
    return xform(o, loc=center, rot=rot)


@asset("ScrapPile_A", 3500)
def build_scrap_a(name):
    parts = [mound_part((0, 0, 0), (3.4, 2.7, 1.7), 3, 5, 1300)]
    parts.append(gear_part((-1.3, 0.4, 1.25), 1.25, (78, 0, 18), col=RUST, teeth=10, tris=520, seed=1))
    parts.append(sheet_part((1.25, -0.5, 1.55), (1.25, 0.95), (-28, 18, 30), TEAL, seed=2, holes=2, tris=220))
    parts.append(sheet_part((0.4, 1.3, 1.6), (1.05, 0.8), (32, -22, -12), MUSTARD, seed=3, tris=160))
    parts.append(pipe_part((-3.3, -1.1, 0.35), (0.6, -1.9, 1.35), 0.42, hexc("#7f99ad"), tris=300, seed=4))
    c = (2.55, 0.9, 0.85)
    parts.append(part(tyre(c, R=0.75, hw=0.36, hh=0.34, rot=(62, 0, -35), r=0.2, tread=0.05, n=14), 0.04, 420,
                      paint=tyre_paint(c, (62, 0, -35), 0.75)))
    parts.append(battery_part((-0.3, -1.9, 0.75), (0.9, 0.35, 0.55), 1.3, 0.34, tris=160))
    return finish(name, parts, ao=0.5, dist=1.1)


@asset("ScrapPile_B", 3500)
def build_scrap_b(name):
    parts = [mound_part((0, 0, 0), (2.5, 2.3, 2.1), 9, 4, 1200)]
    parts.append(part(sdf.ellipsoid((0.1, 0.1, 2.0), (1.5, 1.4, 1.1)), 0.06, 1, col=RUST) if False else None)
    parts.append(sheet_part((0.35, 0.25, 3.15), (0.85, 1.15), (6, -14, 28), RED_FADED, seed=5, holes=1, tris=200))
    parts.append(pipe_part((-1.5, 0.7, 0.9), (-0.55, 1.35, 3.9), 0.34, TEAL, tris=260, seed=6))
    parts.append(gear_part((1.45, -1.05, 1.55), 0.85, (38, 24, 0), col=METAL, teeth=9, tris=340, seed=7))
    parts.append(horseshoe_part((-0.95, -1.55, 1.65), (18, -30, 12), tris=300))
    parts.append(hubcap_part((1.55, 1.1, 1.35), (-40, 30, 0), 0.6))
    parts.append(sheet_part((-1.3, -0.3, 2.3), (0.7, 0.55), (-10, 50, -20), MUSTARD, seed=8, tris=130))
    return finish(name, parts, ao=0.5, dist=1.1)


@asset("ScrapPile_C", 3500)
def build_scrap_c(name):
    parts = [mound_part((0, 0, 0), (3.9, 2.3, 1.5), 17, 6, 1250)]
    # old car door, window hole and all
    door = sdf.smooth_subtract(sdf.round_box((0, 0, 0), (1.45, 0.14, 1.05), 0.2),
                               sdf.round_box((0.15, 0, 0.5), (1.0, 0.4, 0.42), 0.18), k=0.04)

    def door_paint(co, n):
        c = rust_mix(TEAL, co, 0.4, 1.3, 12.0)
        return tone(c, n, 0.22, 0.4)

    d = part(door, 0.035, 300, paint=door_paint)
    xform(d, loc=(-1.9, -0.35, 1.45), rot=(-22, 4, 14))
    parts.append(d)
    parts.append(part(sdf.capsule((-1.9 + 0.8, -0.63, 1.1), (-1.9 + 1.2, -0.66, 1.12), 0.08), 0.03, 50, col=CHROME, ao=0.2))
    parts.append(pipe_part((0.4, -1.75, 0.55), (3.7, 0.25, 1.05), 0.36, hexc("#7f99ad"), tris=240, seed=13))
    parts.append(pipe_part((0.7, -1.2, 1.05), (3.3, 0.9, 1.6), 0.3, MUSTARD, tris=220, seed=14))
    parts.append(gear_part((2.35, 1.05, 1.35), 0.8, (80, 0, -10), col=RUST, teeth=8, tris=320, seed=15))
    # little squashed CRT
    tv = sdf.smooth_subtract(sdf.round_box((0, 0, 0), (0.75, 0.62, 0.62), 0.22),
                             sdf.round_box((-0.12, -0.62, 0.05), (0.48, 0.2, 0.4), 0.14), k=0.05)
    tvp = part(tv, 0.035, 240, paint=lambda co, n: tone(CREAM if co.y > -0.5 else hexc("#3c4f52"), n, 0.2, 0.4))
    xform(tvp, loc=(0.3, 0.7, 1.75), rot=(-8, 12, 25))
    parts.append(tvp)
    parts.append(battery_part((-3.1, 0.6, 0.6), (0.2, -0.4, 0.9), 1.1, 0.3, tris=150))
    return finish(name, parts, ao=0.5, dist=1.1)


# ── appliances ───────────────────────────────────────────────────────────────

@asset("Fridge_Old", 3500)
def build_fridge(name):
    W, D, H = 1.4, 1.2, 5.5
    zc = H / 2 + 0.2
    body = sdf.round_box((0, 0, zc), (W, D, H / 2), 0.62)
    body = sdf.smooth_subtract(body, sdf.round_box((0, -D, 4.05), (W + 0.2, 0.14, 0.06), 0.03), k=0.03)
    body = sdf.smooth_subtract(body, sdf.sphere((1.35, -1.05, 1.7), 0.55), k=0.35)
    body = sdf.smooth_subtract(body, sdf.sphere((-1.0, 0.4, 5.9), 0.5), k=0.3)

    def body_paint(co, n):
        c = MINT
        if -D - 0.2 < co.y < -D + 0.12 and abs(co.z - 4.05) < 0.08:
            c = dark(MINT, 0.5)
        c = rust_mix(c, co, amount=0.25, f=1.3, seed=21.0, low=0.9)
        return tone(c, n, 0.2, 0.4)

    parts = [part(body, 0.04, 1900, paint=body_paint)]
    handle = sdf.smooth_union(sdf.capsule((0.95, -D - 0.36, 2.25), (0.95, -D - 0.36, 3.55), 0.14),
                              sdf.capsule((0.95, -D - 0.36, 2.35), (0.95, -D + 0.1, 2.35), 0.09),
                              sdf.capsule((0.95, -D - 0.36, 3.45), (0.95, -D + 0.1, 3.45), 0.09), k=0.08)
    parts.append(part(handle, 0.03, 220, col=CHROME, hi=0.35, ao=0.3))
    fh = sdf.smooth_union(sdf.capsule((0.3, -D - 0.32, 4.55), (1.0, -D - 0.32, 4.55), 0.12),
                          sdf.capsule((0.35, -D - 0.32, 4.55), (0.35, -D + 0.1, 4.55), 0.08),
                          sdf.capsule((0.95, -D - 0.32, 4.55), (0.95, -D + 0.1, 4.55), 0.08), k=0.06)
    parts.append(part(fh, 0.03, 160, col=CHROME, hi=0.35, ao=0.3))
    parts.append(part(sdf.round_box((-0.55, -D - 0.08, 5.0), (0.45, 0.12, 0.16), 0.08), 0.03, 80, col=CHROME, ao=0.2))
    for (x, z, col) in ((-0.6, 3.3, hexc("#e8524a")), (-0.05, 2.75, HAZARD_Y), (-0.75, 2.35, hexc("#5a9ee0"))):
        parts.append(part(sdf.cylinder((x, -D - 0.1, z), 0.22, 0.09, rot=(90, 0, 0), rounding=0.06), 0.025, 70, col=col, hi=0.3, ao=0.2))
    for xs in (-1, 1):
        for ys in (-1, 1):
            parts.append(part(sdf.cylinder((xs * 0.95, ys * 0.8, 0.14), 0.2, 0.14, rounding=0.05), 0.04, 50, col=METAL_DK, ao=0.2))
    return finish(name, parts, ao=0.45, dist=1.0)


def crt_parts(w, h, d, casing, seed=0, antenna=False, tris=650):
    """Old CRT TV, base at z=0, screen facing -Y."""
    parts = []
    shell = sdf.round_box((0, 0, h / 2), (w / 2, d / 2, h / 2), 0.32)
    shell = sdf.smooth_union(shell, sdf.round_box((0, d * 0.45, h * 0.5), (w * 0.32, d * 0.35, h * 0.32), 0.35), k=0.3)
    sw, sh, sx, sz = w * 0.6, h * 0.66, -w * 0.13, h * 0.52
    shell = sdf.smooth_subtract(shell, sdf.round_box((sx, -d / 2, sz), (sw / 2, 0.24, sh / 2), 0.26), k=0.08)

    def shell_paint(co, n):
        c = rust_mix(casing, co, 0.2, 1.8, seed)
        # speaker grille stripes on the control side
        if co.y < -d / 2 + 0.1 and co.x > w * 0.27 and 0.15 * h < co.z < 0.35 * h:
            c = dark(c, 0.35 if (co.z * 9) % 1 < 0.5 else 0.1)
        return tone(c, n, 0.2, 0.4)

    parts.append(part(shell, 0.04, tris, paint=shell_paint))
    scr = sdf.ellipsoid((sx, -d / 2 + 0.14, sz), (sw / 2 * 0.97, 0.22, sh / 2 * 0.97))

    def screen_paint(co, n):
        u = (co.x - sx) / (sw / 2)
        v = (co.z - sz) / (sh / 2)
        c = mix(GLASS, hexc("#5e7d7c"), 0.3)
        if (u + 0.35) ** 2 * 2.5 + (v - 0.45) ** 2 * 6 < 0.35:
            c = mix(c, GLASS_HI, 0.8)
        return c

    parts.append(part(scr, 0.035, 140, paint=screen_paint, ao=0.25))
    for kz in (0.66, 0.46):
        parts.append(part(sdf.cylinder((w * 0.36, -d / 2 - 0.06, h * kz), 0.15 * min(1.0, h / 2.3) + 0.03, 0.08, rot=(90, 0, 0), rounding=0.05),
                          0.025, 50, col=hexc("#3b3840"), ao=0.2))
    if antenna:
        parts.append(part(sdf.ellipsoid((0, 0.1, h), (0.35, 0.3, 0.2)), 0.03, 70, col=hexc("#3b3840"), ao=0.2))
        for s in (-1, 1):
            tip = Vector((s * 0.9, 0.35, h + 1.35))
            parts.append(tube_part([(s * 0.1, 0.1, h + 0.1), tip], 0.06, sides=5, col=CHROME, hi=0.3))
            parts.append(part(sdf.sphere(tuple(tip), 0.11), 0.03, 40, col=CHROME, hi=0.3))
    return parts


@asset("TV_Pile", 3500)
def build_tv_pile(name):
    parts = []
    stack = ((3.2, 2.5, 2.4, hexc("#9b6c4b"), (0, 0, 0), 0, False, 820),
             (2.6, 2.1, 2.0, hexc("#d98b4e"), (0.25, -0.1, 2.45), 14, False, 720),
             (2.1, 1.7, 1.7, hexc("#6aaea8"), (-0.15, 0.05, 4.5), -12, True, 560))
    for i, (w, h, d, col, loc, rz, ant, tris) in enumerate(stack):
        for p in crt_parts(w, h, d, col, seed=30 + i, antenna=ant, tris=tris):
            xform(p, loc=loc, rot=(0, 0, rz))
            parts.append(p)
    return finish(name, parts, ao=0.5, dist=1.0)


@asset("WashingMachine", 3500)
def build_washer(name):
    parts = []
    body = sdf.round_box((0, 0, 1.75), (1.5, 1.45, 1.6), 0.4)
    body = sdf.smooth_union(body, sdf.round_box((0, 1.0, 3.45), (1.5, 0.45, 0.42), 0.26), k=0.1)
    body = sdf.smooth_subtract(body, sdf.sphere((1.55, 0.2, 2.4), 0.55), k=0.3)
    body = sdf.smooth_subtract(body, sdf.cylinder((0, -1.45, 1.6), 0.86, 0.2, rot=(90, 0, 0)), k=0.05)

    def body_paint(co, n):
        c = rust_mix(CREAM, co, amount=0.22, f=1.2, seed=41.0, low=0.8)
        if co.z > 3.3 and co.y > 0.5:
            c = hexc("#a9bfd0")
        return tone(c, n, 0.18, 0.4)

    parts.append(part(body, 0.04, 1500, paint=body_paint))
    parts.append(part(sdf.torus((0, -1.47, 1.6), 0.95, 0.19, rot=(90, 0, 0)), 0.03, 420, col=CHROME, hi=0.3, ao=0.3))

    def glass_paint(co, n):
        c = mix(hexc("#3d5a78"), hexc("#6d8fae"), 0.3)
        if (co.x + 0.3) ** 2 * 2 + (co.z - 1.95) ** 2 * 5 < 0.2:
            c = mix(c, GLASS_HI, 0.85)
        return c

    parts.append(part(sdf.ellipsoid((0, -1.32, 1.6), (0.84, 0.2, 0.84)), 0.03, 180, paint=glass_paint, ao=0.3))
    for x, col in ((-0.95, hexc("#3b3840")), (-0.35, hexc("#3b3840")), (0.85, hexc("#e8524a"))):
        r = 0.2 if x < 0 else 0.1
        parts.append(part(sdf.cylinder((x, 0.52, 3.5), r, 0.08, rot=(90, 0, 0), rounding=0.04), 0.025, 50, col=col, hi=0.3, ao=0.2))
    parts.append(part(sdf.round_box((-0.8, -1.5, 3.05), (0.5, 0.1, 0.18), 0.07), 0.03, 70, col=hexc("#d8d0bb"), ao=0.2))
    # a stripy sock caught in the door
    pts = [Vector(p) for p in ((0.45, -1.55, 0.95), (0.62, -1.7, 0.55), (0.72, -1.78, 0.25), (1.05, -1.9, 0.15))]
    sock = chain(pts, (0.15, 0.16, 0.17, 0.17), k=0.08)

    def sock_paint(co, n):
        z = co.z
        c = hexc("#e8524a")
        if z > 0.82 or (0.55 < z < 0.66):
            c = CREAM
        if co.x > 0.95:
            c = CREAM
        return tone(c, n, 0.2, 0.4)

    parts.append(part(sock, 0.025, 200, paint=sock_paint, ao=0.3))
    for xs in (-1, 1):
        for ys in (-1, 1):
            parts.append(part(sdf.cylinder((xs * 1.15, ys * 1.1, 0.1), 0.18, 0.1, rounding=0.04), 0.04, 40, col=METAL_DK, ao=0.2))
    return finish(name, parts, ao=0.45, dist=1.0)


@asset("Pipe_Segment", 3500)
def build_pipe(name):
    R, cz = 1.25, 1.62
    inner = sdf.cylinder((0, 0, cz), R - 0.32, 5.0, rot=(0, 90, 0))
    tubeb = sdf.cylinder((0, 0, cz), R, 3.65, rot=(0, 90, 0), rounding=0.1)
    flanges = [sdf.cylinder((s * 3.5, 0, cz), 1.6, 0.26, rot=(0, 90, 0), rounding=0.1) for s in (-1, 1)]
    bolts = [sdf.sphere((s * 3.2, math.cos(a) * 1.42, cz + math.sin(a) * 1.42), 0.13)
             for s in (-1, 1) for a in (i / 8 * math.tau + 0.39 for i in range(8))]
    shape = sdf.smooth_subtract(sdf.smooth_union(tubeb, *flanges, k=0.12), inner, k=0.05)
    shape = sdf.union(shape, *bolts)
    shape = sdf.smooth_subtract(shape, sdf.sphere((0.9, -1.35, cz + 0.95), 0.5), k=0.3)

    def fn(co, n):
        radial = math.hypot(co.y, co.z - cz)
        if radial < R - 0.22 and abs(co.x) < 3.72:
            return mix(hexc("#2d2a33"), hexc("#4a4552"), ss(2.6, 3.7, abs(co.x)))
        c = hexc("#7f99ad")
        if abs(co.x) > 3.15:
            c = RUST if radial > 1.3 else hexc("#8f7f76")
        if abs(co.x - 0.2) < 0.45 and abs(co.x) < 3.1:
            c = mix(HAZARD_Y, c, 0.25)
        c = rust_mix(c, co, amount=0.35, f=0.9, seed=51.0)
        return tone(c, n, 0.22, 0.42)

    return finish(name, [part(shape, 0.045, 2400, paint=fn)], ao=0.5, dist=1.2)


@asset("Sign_Danger", 1500)
def build_sign(name):
    parts = []
    parts.append(part(sdf.round_box((0, 0, 0.3), (0.75, 0.7, 0.3), 0.2), 0.05, 120,
                      paint=lambda co, n: tone(mix(CONCRETE, hexc("#8f8a82"), 0.5 + 0.5 * noise3(co, 3.0, 2)), n, 0.2, 0.4)))
    parts.append(part(sdf.round_box((0, 0.08, 2.5), (0.16, 0.16, 2.35), 0.1), 0.04, 160,
                      paint=lambda co, n: tone(rust_mix(METAL, co, 0.4, 1.4, 61.0), n, 0.2, 0.4)))
    zc = 3.95
    sign = []
    sign.append(part(tri_prism((0, -0.18, zc), 1.62, 0.1, rot=(90, 0, 0), rounding=0.28), 0.03, 260, col=HAZARD_K, hi=0.2, ao=0.2))
    sign.append(part(tri_prism((0, -0.26, zc), 1.3, 0.06, rot=(90, 0, 0), rounding=0.18), 0.03, 200, col=HAZARD_Y, hi=0.25, ao=0.2))
    mark = sdf.union(sdf.round_cone((0, -0.33, zc - 0.12), (0, -0.33, zc + 0.62), 0.1, 0.15), sdf.sphere((0, -0.33, zc - 0.42), 0.14))
    sign.append(part(stretch(mark, (0, -0.33, zc), (1.0, 2.2, 1.0)), 0.025, 160, col=HAZARD_K, hi=0.2, ao=0.1))
    for s in sign:
        xform(s, rot=(0, 8, 0), pivot=(0, 0, zc))
    parts += sign
    for z in (zc - 0.25, zc + 0.45):
        parts.append(part(sdf.sphere((0, -0.1, z), 0.001 + 0.0), 0.05, 1, col=METAL) if False else None)
    return finish(name, parts, ao=0.45, dist=0.8)


# ══════════════════════════════════════════════════════════════════════════════
# PREVIEW
# ══════════════════════════════════════════════════════════════════════════════

def _ref_capsule():
    o = sdf.to_mesh("_RefCapsule", sdf.capsule((0, 0, 0.75), (0, 0, 4.25), 0.75), voxel=0.08)
    o = fk.decimate_to(o, 500)
    fk.solid_color(o, hexc("#e58fb5"))
    fk.preview_tint(o, (1, 1, 1))
    return o


def _label(cam):
    mat = bpy.data.materials.new("_LabelMat")
    mat.use_nodes = True
    nt = mat.node_tree
    for nd in list(nt.nodes):
        if nd.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(nd)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (0.02, 0.02, 0.03, 1)
    out = next(nd for nd in nt.nodes if nd.type == "OUTPUT_MATERIAL")
    nt.links.new(em.outputs[0], out.inputs[0])
    cu = bpy.data.curves.new("_Label", "FONT")
    cu.size = 0.034
    txt = bpy.data.objects.new("_Label", cu)
    fk.link(txt)
    txt.data.materials.append(mat)
    txt.parent = cam
    txt.location = (-0.345, 0.325, -1.0)
    return txt


def render_sheet(objs, path, cols=5, tile=280, yaw=-32, pitch=20, scratch=None):
    scene = bpy.context.scene
    fk.preview_studio()
    try:
        scene.eevee.taa_render_samples = 24
    except Exception:
        pass
    floor = bpy.data.objects["PreviewFloor"]
    floor.scale = (4, 4, 1)
    for o in objs:
        fk.preview_tint(o, (1, 1, 1))
        o.hide_render = True
    cap = _ref_capsule()
    fk.look_setup(target=(0, 0, 1), distance=10)
    cam = scene.camera
    cam.data.clip_end = 1000
    label = _label(cam)
    tmp = scratch or os.path.join(os.path.dirname(path), "_kit_junk_tile.png")
    half_fov = math.atan(18.0 / 50.0)
    tiles = []
    for o in objs:
        o.hide_render = False
        co = _coords(o)
        lo, hi = co.min(axis=0), co.max(axis=0)
        cap_x = hi[0] + 1.4
        cap_y = lo[1] + 0.9
        cap.location = (cap_x, cap_y, 0)
        lo2 = np.minimum(lo, [cap_x - 0.8, cap_y - 0.8, 0])
        hi2 = np.maximum(hi, [cap_x + 0.8, cap_y + 0.8, 5.0])
        centre = (lo2 + hi2) / 2
        radius = float(np.linalg.norm(hi2 - lo2)) / 2
        dist = radius / math.sin(half_fov) * 0.92
        fk.look_setup(target=tuple(centre), distance=dist, yaw=yaw, pitch=pitch, lens=50)
        label.data.body = f"{o.name}  {fk.triangle_count(o)}"
        fk.render_png(tmp, res=(tile, tile))
        img = bpy.data.images.load(tmp, check_existing=False)
        tiles.append(np.array(img.pixels[:], dtype=np.float32).reshape(tile, tile, 4))
        bpy.data.images.remove(img)
        o.hide_render = True
    rows = math.ceil(len(tiles) / cols)
    sheet = np.ones((rows * tile, cols * tile, 4), dtype=np.float32)
    for i, px in enumerate(tiles):
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * tile
        sheet[y0:y0 + tile, c * tile:(c + 1) * tile] = px
    out = bpy.data.images.new("_sheet", width=cols * tile, height=rows * tile, alpha=True)
    out.pixels = sheet.ravel()
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    try:
        os.remove(tmp)
    except OSError:
        pass
    for o in objs:
        o.hide_render = False
    return path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    only = [s for s in os.environ.get("KIT_ONLY", "").split(",") if s]
    built = []
    for name, budget, fn in ASSETS:
        if only and name not in only:
            continue
        t0 = time.time()
        obj = fn(name)
        tris = fk.triangle_count(obj)
        assert obj.name == name, (obj.name, name)
        assert tris <= budget, f"{name}: {tris} tris > budget {budget}"
        dims = _coords(obj).max(axis=0) - _coords(obj).min(axis=0)
        print(f"[{KIT}] {name:24s} {tris:5d}/{budget:<5d} size {dims[0]:5.1f} x {dims[1]:5.1f} x {dims[2]:5.1f}  {time.time() - t0:5.1f}s", flush=True)
        built.append(obj)
    if only:
        sheet = os.environ.get("KIT_SHEET")
        if sheet:
            render_sheet(built, sheet, cols=int(os.environ.get("KIT_COLS", "4")), tile=int(os.environ.get("KIT_TILE", "340")))
            print(f"[{KIT}] sheet -> {sheet}")
        return
    for o in built:
        o.data.materials.clear()
        assert tuple(o.location) == (0, 0, 0) and tuple(o.rotation_euler) == (0, 0, 0) and tuple(o.scale) == (1, 1, 1)
    path = fk.export_fbx(built, f"{KIT}.fbx")
    print(f"[{KIT}] fbx -> {path}")
    prev_dir = os.path.join(ROOT, "art", "previews")
    os.makedirs(prev_dir, exist_ok=True)
    render_sheet(built, os.path.join(prev_dir, f"{KIT}.png"), cols=5, tile=280)
    print(f"[{KIT}] preview -> {os.path.join(prev_dir, KIT + '.png')}")


main()
