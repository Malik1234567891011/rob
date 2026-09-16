import sys; sys.path.insert(0, "/Users/malik/rob/tools/blender")
import bpy, bmesh, math, numpy as np
from mathutils import Vector
import famkit as fk, sdf
fk.reset_scene()

"""kit_meadow — the starter backyard, the Meadow biome and the four ability gates.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/kit_meadow.py
        -> art/build/kit_meadow.fbx, art/previews/kit_meadow.png

Iteration flags (after `--`):
    --only Tree_Puffy_A,Shack   build a subset (no export, no final preview)
    --sheet PATH                contact sheet of the built assets
    --cols N --tile PX          sheet layout
    --capsule                   put a 5-stud reference capsule beside every asset
    --vignette PATH             backyard scene render of whatever was built

Every asset is one object, base at Z=0, centred on X/Y, front facing -Y, colour baked into
vertex colours (sRGB), AO baked, box UVs, under its triangle budget.
"""

import argparse
import os
import time

from mathutils import Euler

ROOT = "/Users/malik/rob"
FBX_NAME = "kit_meadow.fbx"
PREVIEW = os.path.join(ROOT, "art", "previews", "kit_meadow.png")
SCRATCH = os.environ.get("MEADOW_SCRATCH", "/tmp")

FAR = 8.0


# ═══ SDF HELPERS ══════════════════════════════════════════════════════════════

def f32(v):
    return np.asarray(v, dtype=np.float32)


def rotm(rot):
    return np.array(Euler([math.radians(a) for a in rot]).to_matrix(), dtype=np.float32)


def U(*shapes, k=0.0, pad=None):
    """Smooth union that only evaluates each primitive inside its own bounds.
    Same result as sdf.smooth_union near the surface, much faster for scattered detail."""
    shapes = [s for s in shapes if s is not None]
    if len(shapes) == 1:
        return shapes[0]
    pad = (k + 0.2) if pad is None else pad
    boxes = [(f32(s[1][0]) - pad, f32(s[1][1]) + pad) for s in shapes]

    def fn(P):
        d = np.full(len(P), FAR, dtype=np.float32)
        for (f, _), (lo, hi) in zip(shapes, boxes):
            m = np.all((P >= lo) & (P <= hi), axis=1)
            if not m.any():
                continue
            idx = np.nonzero(m)[0]
            e = f(P[idx]).astype(np.float32)
            a = d[idx]
            if k > 0:
                h = np.maximum(k - np.abs(a - e), 0.0) / k
                d[idx] = np.minimum(a, e) - h * h * k * 0.25
            else:
                d[idx] = np.minimum(a, e)
        return d

    return (fn, sdf._merge_bounds(*[s[1] for s in shapes]))


def placed(shape, center=(0, 0, 0), rot=None, R=None):
    """Shape authored around the origin, rotated by R (local->world) and moved to center."""
    if R is None:
        R = rotm(rot or (0, 0, 0))
    R = f32(R)
    c = f32(center)
    lo, hi = f32(shape[1][0]), f32(shape[1][1])
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], np.float32)
    w = corners @ R.T + c
    return (lambda P: shape[0]((P - c) @ R), (w.min(0), w.max(0)))


def frame(n, hint=(0, 0, 1)):
    """Rotation whose local Z is n."""
    n = f32(n) / np.linalg.norm(n)
    h = f32(hint)
    if abs(float(n @ h)) > 0.95:
        h = f32((0, 1, 0)) if abs(n[1]) < 0.9 else f32((1, 0, 0))
    t = np.cross(h, n)
    t /= np.linalg.norm(t)
    b = np.cross(n, t)
    return np.stack([t, b, n], axis=1)


def flat_bottom(shape, z0=0.0, k=0.06):
    def fn(P):
        a = shape[0](P)
        b = z0 - P[:, 2]
        h = np.maximum(k - np.abs(a - b), 0.0) / k
        return np.maximum(a, b) + h * h * k * 0.25
    lo, hi = f32(shape[1][0]).copy(), f32(shape[1][1])
    lo[2] = max(lo[2], z0 - 0.2)
    return (fn, (lo, hi))


def region_above(zfn, bounds):
    """Inside where P.z > zfn(P)."""
    return (lambda P: zfn(P) - P[:, 2], bounds)


def squash_below(shape, zc, f):
    def fn(P):
        Q = P.copy()
        m = Q[:, 2] < zc
        Q[m, 2] = zc + (Q[m, 2] - zc) * f
        return shape[0](Q)
    return (fn, shape[1])


def ridges(shape, amp, n, axis="z", center=(0.0, 0.0), twist=0.0):
    """Soft bark ridges running along an axis."""
    cx, cy = center

    def fn(P):
        if axis == "z":
            a = np.arctan2(P[:, 1] - cy, P[:, 0] - cx)
            along = P[:, 2]
        else:  # x axis
            a = np.arctan2(P[:, 2] - cy, P[:, 1] - cx)
            along = P[:, 0]
        return shape[0](P) + amp * np.sin(a * n + along * twist)
    return (fn, shape[1])


def soft_cone(center, half_h, r_bot, r_top, rounding=0.3):
    """Capped cone along Z with rounded rims (iq's sdCappedCone, shrunk then inflated)."""
    c = f32(center)
    rr = rounding
    h = half_h - rr
    r1 = max(r_bot - rr, 0.01)
    r2 = max(r_top - rr, 0.01)
    k1 = np.array([r2, h], np.float32)
    k2 = np.array([r2 - r1, 2 * h], np.float32)
    k2d = float(k2 @ k2)

    def fn(P):
        Q = P - c
        qx = np.sqrt(Q[:, 0] ** 2 + Q[:, 1] ** 2)
        qy = Q[:, 2]
        rsel = np.where(qy < 0, r1, r2)
        cax = qx - np.minimum(qx, rsel)
        cay = np.abs(qy) - h
        t = np.clip(((k1[0] - qx) * k2[0] + (k1[1] - qy) * k2[1]) / k2d, 0.0, 1.0)
        cbx = qx - k1[0] + k2[0] * t
        cby = qy - k1[1] + k2[1] * t
        s = np.where((cbx < 0) & (cay < 0), -1.0, 1.0)
        return s * np.sqrt(np.minimum(cax * cax + cay * cay, cbx * cbx + cby * cby)) - rr

    m = max(r_bot, r_top)
    return (fn, (c - f32((m, m, half_h)), c + f32((m, m, half_h))))


def torus(center, major, minor, rot=None):
    """sdf.torus with bounds that survive rotation (sdf's are axis-aligned to the unrotated ring)."""
    t = sdf.torus(center, major, minor, rot=rot)
    m = major + minor
    return (t[0], (f32(center) - m, f32(center) + m))


def band_x(x0, half_yz, radius, thick, width, zc):
    """Ring around the X axis following a rounded-rectangle cross-section (bale strings, grooves)."""
    hy, hz = half_yz

    def fn(P):
        qy = np.abs(P[:, 1]) - (hy - radius)
        qz = np.abs(P[:, 2] - zc) - (hz - radius)
        d2 = np.sqrt(np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2) + np.minimum(np.maximum(qy, qz), 0) - radius
        return np.maximum(np.abs(d2) - thick, np.abs(P[:, 0] - x0) - width)
    m = f32((width + 0.1, hy + thick + 0.1, hz + thick + 0.1))
    c = f32((x0, 0, zc))
    return (fn, (c - m, c + m))


def chain(points, radii, k=0.05):
    shapes = [sdf.round_cone(tuple(points[i]), tuple(points[i + 1]), radii[i], radii[i + 1]) for i in range(len(points) - 1)]
    return U(*shapes, k=k)


def arc(a, b, bend, n=5):
    a, b, bend = f32(a), f32(b), f32(bend)
    mid = (a + b) * 0.5 + bend
    return [tuple(a * (1 - t) ** 2 + mid * 2 * t * (1 - t) + b * t * t) for t in np.linspace(0, 1, n)]


def hit(shape, origin, direction, tmax=30.0, step=0.02):
    """March a ray against an SDF; returns the first surface point (np) or None."""
    o = f32(origin)
    d = f32(direction)
    d = d / np.linalg.norm(d)
    t = np.arange(0.0, tmax, step, dtype=np.float32)
    P = o + t[:, None] * d
    v = shape[0](P)
    idx = np.nonzero(v <= 0)[0]
    if len(idx) == 0:
        return None
    i = idx[0]
    if i == 0:
        return o
    t0, t1, v0, v1 = t[i - 1], t[i], v[i - 1], v[i]
    return o + (t0 + (t1 - t0) * v0 / (v0 - v1)) * d


def grad(shape, p, e=0.01):
    p = f32(p)
    offs = np.eye(3, dtype=np.float32) * e
    P = np.concatenate([p + offs, p - offs])
    v = shape[0](P)
    g = v[:3] - v[3:]
    return g / (np.linalg.norm(g) + 1e-9)


def ground_ring(r, n, seed, jitter=0.25):
    rng = np.random.default_rng(seed)
    a0 = rng.uniform(0, 2 * math.pi)
    return [a0 + i * 2 * math.pi / n + rng.uniform(-jitter, jitter) for i in range(n)]


# ═══ COLOUR (vectorised, authored in sRGB) ════════════════════════════════════

def C(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


def sst(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * np.asarray(t, np.float32)[:, None]


def tone(base, light, dark, lift=0.55, sink=0.55, bottom=None, var=0.05, freq=0.8, seed=0, top=None):
    """Base colour, lighter as the surface faces the sky, darker underneath, optional
    darkening toward the ground, gentle low-frequency variation."""
    b, l, d = C(base), C(light), C(dark)

    def fn(P, N):
        nz = N[:, 2]
        c = np.tile(b, (len(P), 1))
        c = lerp(c, l, sst(0.0, 1.0, nz) * lift)
        c = lerp(c, d, sst(0.0, 1.0, -nz) * sink)
        if bottom:
            z0, z1, amt = bottom
            c = lerp(c, d, (1.0 - sst(z0, z1, P[:, 2])) * amt)
        if top:
            z0, z1, amt = top
            c = lerp(c, l, sst(z0, z1, P[:, 2]) * amt)
        if var:
            v = (np.sin(P[:, 0] * freq + seed) * np.sin(P[:, 1] * freq * 1.13 + 2.1 * seed + 1.0)
                 * np.sin(P[:, 2] * freq * 0.87 + 3.3 * seed + 2.0))
            c = c * (1.0 + var * v)[:, None]
        return c
    return fn


def flat(hexcol):
    col = C(hexcol)
    return lambda P, N: np.tile(col, (len(P), 1))


def vpaint(obj, fn):
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    no = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("normal", no)
    col = np.clip(np.asarray(fn(co.reshape(-1, 3), no.reshape(-1, 3)), np.float32), 0.0, 1.0)
    linear = np.where(col <= 0.04045, col / 12.92, ((col + 0.055) / 1.055) ** 2.4)
    layer = fk.ensure_color_layer(obj)
    li = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", li)
    rgba = np.ones((len(me.loops), 4), np.float32)
    rgba[:, :3] = linear[li]
    layer.data.foreach_set("color", rgba.ravel())
    return obj


# Palette (sRGB): greens lean yellow, woods warm, stones warm grey.
LEAF = ("#5FAE3B", "#A8D85A", "#2E7034")
BUSH = ("#55A843", "#9CD15E", "#2C6E35")
PINE = ("#3A9457", "#7DC266", "#225A43")
BARK = ("#8E5C39", "#BD8554", "#5A3823")
WOOD = ("#C98C52", "#EAB880", "#8A5A34")
WOOD_D = ("#9A6841", "#C8925F", "#62412A")
CREAM = ("#F2E5CC", "#FFFAEE", "#B8A487")
STONE = ("#ABA398", "#D8D1C4", "#6F6962")
MOSS = ("#6BAA3E", "#A3D05E", "#3F7A33")
ROOF = ("#D9574A", "#F59173", "#983832")
METAL = ("#71767E", "#A6ABB2", "#45494F")
HAY = ("#E9C35B", "#FCE49C", "#B08433")
DIRT = ("#8F6B4A", "#B38C64", "#5B422E")
GRASS = ("#6DB944", "#AEDD62", "#468A37")
BLACK = "#0C0A10"


# ═══ ASSEMBLY ═════════════════════════════════════════════════════════════════

def part(shape, voxel, tris, paint, glow=False):
    o = sdf.to_mesh("_part", shape, voxel=voxel)
    for _ in range(4):  # collapse undershoots its ratio on meshes with many small shells
        if fk.triangle_count(o) <= tris * 1.03:
            break
        o = fk.decimate_to(o, tris)
    vpaint(o, paint)
    o["glow"] = glow
    return o


def _loop_colors(obj):
    layer = obj.data.color_attributes["Col"]
    a = np.empty(len(obj.data.loops) * 4, np.float32)
    layer.data.foreach_get("color", a)
    return a.reshape(-1, 4)


def finish(name, parts, ao=(1.0, 0.5), samples=20, x_extent=None, y_extent=None, center=True):
    """Join parts, snap base to Z=0 and centre X/Y, bake AO (skipping glowing parts), UVs."""
    glow = []
    start = 0
    for p in parts:
        nl = len(p.data.loops)
        if p.get("glow"):
            glow.append((start, _loop_colors(p)))
        start += nl
    obj = fk.join(parts, "_joined")
    me = obj.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(0), co.max(0)
    if center:
        co[:, 0] -= (lo[0] + hi[0]) * 0.5
        co[:, 1] -= (lo[1] + hi[1]) * 0.5
    co[:, 2] -= lo[2]
    if x_extent:
        co[:, 0] *= x_extent / np.abs(co[:, 0]).max()
    if y_extent:
        co[:, 1] *= y_extent / np.abs(co[:, 1]).max()
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    if ao:
        fk.bake_ao(obj, floor_z=0.0, samples=samples, distance=ao[0], strength=ao[1])
    if glow:
        cols = _loop_colors(obj)
        for s, c in glow:
            cols[s:s + len(c)] = c
        me.color_attributes["Col"].data.foreach_set("color", cols.ravel())
    obj.data.materials.clear()
    fk.box_uv(obj, 2.0)
    fk.shade_smooth(obj)
    obj.name = name
    obj.data.name = name
    return obj


# ═══ SHARED BUILDING BLOCKS ═══════════════════════════════════════════════════

def trunk_shape(h, r0, r1, bend=(0.0, 0.0), roots=4, seed=1, reach=1.65, ridge=True):
    bx, by = bend
    pts = [(0, 0, -0.3), (bx * 0.1, by * 0.1, h * 0.35), (bx * 0.55, by * 0.55, h * 0.7), (bx, by, h)]
    main = chain(pts, [r0, r0 * 0.8 + r1 * 0.2, (r0 + r1) * 0.5 * 0.95, r1], k=0.2)
    rng = np.random.default_rng(seed)
    rs = []
    for a in ground_ring(1, roots, seed):
        rch = r0 * reach * rng.uniform(0.85, 1.15)
        rs.append(sdf.round_cone((math.cos(a) * r0 * 0.2, math.sin(a) * r0 * 0.2, r0 * 1.3),
                                 (math.cos(a) * rch, math.sin(a) * rch, r0 * 0.12), r0 * 0.55, r0 * 0.3))
    s = U(main, *rs, k=r0 * 0.7)
    if ridge:
        s = ridges(s, 0.03 * r0 / 0.8, 9, twist=0.15)
    return flat_bottom(s, 0.0)


def puffs(spheres, k=0.6, amp=0.1, freq=0.9, seed=1):
    s = U(*[sdf.sphere(c, r) for c, r in spheres], k=k)
    return sdf.noise_bumps(s, amplitude=amp, frequency=freq, seed=seed)


def canopy_tone(z0, z1, pal=LEAF, seed=0):
    base = tone(*pal, lift=0.5, sink=0.7, bottom=(z0, z1, 0.45), var=0.07, freq=0.5, seed=seed)
    return base


def stick(shape, origin, target, embed=0.0):
    """Surface point hit from `origin` toward `target`, pushed back out by -embed along the ray."""
    d = f32(target) - f32(origin)
    p = hit(shape, origin, d, tmax=float(np.linalg.norm(d)) + 5, step=0.02)
    if p is None:
        return None, None
    n = grad(shape, p)
    return p - n * embed, n


def chunk_shape(boxes, amp=0.03, freq=2.5, seed=1, k=0.3, z0=0.0, taper=0.0, height=1.0):
    """Soft chunky stylised rock: rotated round boxes melted together, narrower toward the top."""
    s = U(*[sdf.round_box(c, h, r, rot=rot) for c, h, r, rot in boxes], k=k)
    if taper:
        def tap(P):
            Q = P.copy()
            f = 1.0 + taper * np.clip(P[:, 2] / height, 0.0, 1.2)
            Q[:, 0] *= f
            Q[:, 1] *= f
            return Q
        s = sdf.warp(s, tap, pad=0.1)
    s = sdf.noise_bumps(s, amplitude=amp, frequency=freq, seed=seed)
    s = sdf.noise_bumps(s, amplitude=amp * 0.6, frequency=freq * 2.3, seed=seed + 5)
    return flat_bottom(s, z0)


def moss_patch(shape, blobs, thick=0.04, k=0.03):
    """Moss that hugs the surface inside a few soft blobs (no drips)."""
    region = U(*[sdf.ellipsoid(c, r) for c, r in blobs], k=0.25)
    region = sdf.noise_bumps(region, amplitude=0.05, frequency=4.0, seed=3)
    return sdf.smooth_intersect(sdf.offset(shape, thick), region, k=k)


def rock_shape(blobs, amp=0.04, freq=2.5, seed=1, k=0.3, z0=0.0):
    s = U(*[sdf.ellipsoid(c, r, rot=rot) for c, r, rot in blobs], k=k)
    s = sdf.noise_bumps(s, amplitude=amp, frequency=freq, seed=seed)
    s = sdf.noise_bumps(s, amplitude=amp * 0.5, frequency=freq * 2.1, seed=seed + 7)
    return flat_bottom(s, z0)


def moss_cap(shape, zc, wave=0.3, thick=0.06, bounds=None, seed=0):
    ph = seed * 1.7

    def zfn(P):
        a = np.arctan2(P[:, 1], P[:, 0])
        return zc + wave * np.sin(a * 3 + ph) + wave * 0.6 * np.sin(a * 7 + 2 * ph) + 0.15 * wave * np.sin(P[:, 0] * 3.1)
    lo, hi = f32(shape[1][0]), f32(shape[1][1])
    return sdf.smooth_intersect(sdf.offset(shape, thick), region_above(zfn, (lo, hi)), k=0.04)


def rings_paint(inner, outer, axis_fn, freq=20.0):
    """End-grain rings: axis_fn(P) -> radial distance from the log's axis."""
    ci, co = C(inner), C(outer)

    def fn(P, N):
        r = axis_fn(P)
        t = 0.5 + 0.5 * np.sin(r * freq)
        return lerp(np.tile(ci, (len(P), 1)), co, t * 0.55)
    return fn


def mix_paint(a, b, mask_fn):
    def fn(P, N):
        m = np.clip(mask_fn(P, N), 0, 1)
        return lerp(a(P, N), b(P, N), m) if callable(b) else lerp(a(P, N), C(b), m)
    return fn


# ═══ ASSETS ═══════════════════════════════════════════════════════════════════

ASSETS = {}


def asset(name):
    def deco(fn):
        ASSETS[name] = fn
        return fn
    return deco


# ── Trees ────────────────────────────────────────────────────────────────────

@asset("Tree_Puffy_A")
def tree_puffy_a():
    trunk = part(trunk_shape(7.4, 0.85, 0.5, bend=(0.3, 0.15), seed=1), 0.06, 900, tone(*BARK, bottom=(0, 1.2, 0.25)))
    can = puffs([((0.3, 0.1, 9.4), 3.1), ((2.6, 0.3, 8.2), 2.2), ((-2.1, -0.6, 8.4), 2.3), ((0.6, 2.1, 8.3), 2.1),
                 ((-0.5, -2.1, 8.6), 2.0), ((0.9, 0.4, 11.5), 2.1), ((-1.5, 1.0, 10.7), 1.9), ((1.9, -1.3, 10.4), 1.7)],
                k=0.55, seed=2)
    return finish("Tree_Puffy_A", [trunk, part(can, 0.1, 2600, canopy_tone(6.0, 10.0))], ao=(2.2, 0.55))


@asset("Tree_Puffy_B")
def tree_puffy_b():
    trunk = part(trunk_shape(8.4, 0.8, 0.45, bend=(-0.35, 0.2), seed=3), 0.06, 900, tone(*BARK, bottom=(0, 1.2, 0.25)))
    can = U(sdf.ellipsoid((-0.3, 0.2, 10.6), (2.8, 2.8, 3.8)),
            sdf.sphere((1.9, -0.9, 9.0), 1.9), sdf.sphere((-2.1, 1.0, 9.5), 1.9), sdf.sphere((0.2, -1.8, 10.2), 1.7),
            sdf.sphere((0.9, 1.5, 12.2), 1.8), sdf.sphere((-1.2, -1.0, 12.5), 1.7), sdf.sphere((-0.3, 0.2, 14.1), 1.45),
            k=0.5)
    can = sdf.noise_bumps(can, amplitude=0.1, frequency=0.9, seed=4)
    return finish("Tree_Puffy_B", [trunk, part(can, 0.1, 2600, canopy_tone(6.5, 11.0, seed=1))], ao=(2.2, 0.55))


@asset("Tree_Puffy_C")
def tree_puffy_c():
    main = trunk_shape(3.8, 0.95, 0.7, seed=5, ridge=False)
    br = U(chain([(0.1, 0, 3.2), (-1.4, 0.2, 5.1), (-2.7, 0.3, 6.9)], [0.58, 0.44, 0.34], k=0.1),
           chain([(0.1, 0, 3.2), (1.4, -0.2, 5.3), (2.8, -0.3, 7.3)], [0.58, 0.44, 0.34], k=0.1),
           chain([(0.0, 0, 3.4), (0.2, 0.4, 6.6)], [0.5, 0.36], k=0.1), k=0.4)
    wood = ridges(U(main, br, k=0.5), 0.03, 9, twist=0.15)
    trunk = part(flat_bottom(wood), 0.06, 1100, tone(*BARK, bottom=(0, 1.2, 0.25)))
    left = U(sdf.sphere((-2.9, 0.3, 7.9), 2.1), sdf.sphere((-4.1, 0.5, 7.5), 1.45), sdf.sphere((-2.4, -0.8, 8.8), 1.55),
             sdf.sphere((-3.2, 1.1, 8.7), 1.4), k=0.45)
    right = U(sdf.sphere((2.9, -0.3, 8.3), 2.3), sdf.sphere((4.2, -0.1, 7.8), 1.5), sdf.sphere((2.6, 0.8, 9.5), 1.65),
              sdf.sphere((3.3, -1.3, 9.1), 1.35), k=0.45)
    topc = U(sdf.sphere((0.2, 0.5, 9.4), 1.9), sdf.sphere((0.6, -0.3, 10.5), 1.45), k=0.45)
    can = sdf.noise_bumps(U(left, right, topc, k=0.3), amplitude=0.09, frequency=1.0, seed=6)
    return finish("Tree_Puffy_C", [trunk, part(can, 0.09, 2800, canopy_tone(6.0, 9.5, seed=2))], ao=(2.0, 0.55))


def pine(name, tiers, trunk_h, seed, lean=0.0):
    trunk = part(trunk_shape(trunk_h, 0.55, 0.42, seed=seed, reach=1.9), 0.05, 700, tone(*BARK, bottom=(0, 1.0, 0.25)))
    shapes = [soft_cone((0, 0, z0 + h * 0.5), h * 0.5, rb, rt, rounding=min(0.55, rb * 0.22)) for z0, h, rb, rt in tiers]
    top = tiers[-1][0] + tiers[-1][1]
    body = U(*shapes, k=0.2)
    rim = body

    def scallop(P):
        Q = P.copy()
        a = np.arctan2(Q[:, 1], Q[:, 0])
        r = np.sqrt(Q[:, 0] ** 2 + Q[:, 1] ** 2)
        f = 1.0 + 0.045 * np.sin(a * 7 + Q[:, 2] * 0.9)
        Q[:, 0] *= f
        Q[:, 1] *= f
        return Q
    body = sdf.warp(rim, scallop, pad=0.3)
    body = sdf.noise_bumps(body, amplitude=0.05, frequency=1.4, seed=seed)
    if lean:
        z1 = tiers[0][0]
        span = top - z1

        def bend(P):
            Q = P.copy()
            t = np.clip((Q[:, 2] - z1) / span, 0, 1)
            Q[:, 0] -= lean * t * t
            return Q
        body = sdf.warp(body, bend, pad=abs(lean) + 0.3)
    return finish(name, [trunk, part(body, 0.08, 2600, tone(*PINE, lift=0.8, sink=0.7, bottom=(tiers[0][0], tiers[0][0] + 4, 0.25), var=0.05, freq=0.6, seed=seed))], ao=(1.8, 0.55))


@asset("Tree_Pine_A")
def tree_pine_a():
    return pine("Tree_Pine_A", [(1.8, 4.0, 3.5, 1.0), (4.4, 3.7, 2.9, 0.8), (6.8, 3.4, 2.3, 0.6), (9.0, 3.4, 1.6, 0.3)], 2.6, 11)


@asset("Tree_Pine_B")
def tree_pine_b():
    return pine("Tree_Pine_B", [(2.4, 4.3, 3.1, 0.9), (5.3, 4.0, 2.65, 0.75), (7.9, 3.7, 2.2, 0.6), (10.3, 3.5, 1.7, 0.45),
                                (12.5, 3.5, 1.2, 0.22)], 3.2, 12, lean=0.7)


@asset("Tree_Fruit")
def tree_fruit():
    trunk = part(trunk_shape(6.6, 0.8, 0.5, bend=(0.2, -0.1), seed=7), 0.06, 900, tone(*BARK, bottom=(0, 1.2, 0.25)))
    can = puffs([((0, 0, 8.6), 3.3), ((2.3, 0.4, 7.9), 2.1), ((-2.2, -0.3, 8.0), 2.2), ((0.3, 2.1, 7.8), 2.0),
                 ((-0.2, -2.1, 8.0), 2.0), ((0.6, -0.2, 10.8), 2.1), ((-1.2, 0.8, 10.2), 1.8)], k=0.55, seed=8)
    canopy = part(can, 0.1, 2400, canopy_tone(5.5, 9.5, seed=3))
    apples, stems = [], []
    for az, el in ((-95, -8), (-55, 18), (-135, 28), (-15, -12), (35, 22), (160, 5), (100, -14), (-78, -38), (215, 30), (-118, -30), (-40, 45)):
        a, e = math.radians(az), math.radians(el)
        d = np.array([math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)], np.float32)
        c0 = f32((0, 0, 8.8))
        p, n = stick(can, c0 + d * 9.0, c0, embed=-0.3)
        if p is None:
            continue
        apples.append(sdf.smooth_subtract(sdf.ellipsoid(tuple(p), (0.6, 0.6, 0.55)), sdf.sphere(tuple(p + f32((0, 0, 0.6))), 0.16), k=0.1))
        stems.append(sdf.capsule(tuple(p + f32((0, 0, 0.35))), tuple(p + f32((0.08, 0, 0.8))), 0.07))
    ap = part(U(*apples), 0.03, 900, tone("#E0392F", "#FF8A66", "#9E2019", lift=0.6, sink=0.5, var=0.0))
    st = part(U(*stems), 0.02, 250, flat("#6A4428"))
    return finish("Tree_Fruit", [trunk, canopy, ap, st], ao=(2.0, 0.5))


# ── Bushes ───────────────────────────────────────────────────────────────────

def dots_on(shape, center, dirs, radius, embed=0.05):
    out = []
    for d in dirs:
        d = f32(d) / np.linalg.norm(d)
        p, n = stick(shape, f32(center) + d * 6, center, embed=radius * 0.3 + embed)
        if p is not None:
            out.append((p, n))
    return out


def fib_dirs(n, zmin=-0.2, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    i = 0
    while len(out) < n and i < n * 20:
        z = rng.uniform(zmin, 0.95)
        a = rng.uniform(0, 2 * math.pi)
        r = math.sqrt(1 - z * z)
        out.append((r * math.cos(a), r * math.sin(a), z))
        i += 1
    return out


@asset("Bush_A")
def bush_a():
    s = flat_bottom(puffs([((0, 0, 1.0), 1.05), ((0.85, 0.25, 0.8), 0.8), ((-0.8, -0.05, 0.78), 0.82),
                           ((0.15, 0.55, 1.35), 0.75), ((-0.2, -0.45, 1.45), 0.7)], k=0.3, amp=0.04, freq=2.4, seed=1))
    return finish("Bush_A", [part(s, 0.04, 1100, tone(*BUSH, lift=0.75, sink=0.6, bottom=(0, 1.0, 0.3), var=0.05, freq=1.2))], ao=(0.9, 0.55))


@asset("Bush_B")
def bush_b():
    s = flat_bottom(puffs([((0, 0, 1.45), 1.2), ((0, 0.1, 2.45), 0.92), ((0.8, -0.3, 1.1), 0.8), ((-0.8, 0.3, 1.2), 0.85),
                           ((0.35, -0.6, 2.15), 0.68), ((-0.5, -0.5, 1.9), 0.7)], k=0.3, amp=0.04, freq=2.2, seed=2))
    body = part(s, 0.045, 1200, tone(*BUSH, lift=0.75, sink=0.6, bottom=(0, 1.2, 0.3), var=0.05, freq=1.2, seed=1))
    petals, centers = [], []
    for p, n in dots_on(s, (0, 0, 1.6), fib_dirs(12, zmin=-0.3, seed=3), 0.0, embed=0.0):
        R = frame(n)
        for i in range(5):
            a = i * 2 * math.pi / 5
            petals.append(placed(sdf.ellipsoid((math.cos(a) * 0.15, math.sin(a) * 0.15, 0.02), (0.14, 0.11, 0.06), rot=(0, -12, math.degrees(a))), p, R=R))
        centers.append(sdf.sphere(tuple(p + n * 0.07), 0.08))
    fl = part(U(*petals, k=0.02), 0.022, 900, tone("#FF96C2", "#FFD3E6", "#D8588E", lift=0.5, sink=0.4, var=0))
    ce = part(U(*centers), 0.02, 250, flat("#FFD447"))
    return finish("Bush_B", [body, fl, ce], ao=(1.0, 0.5))


@asset("Bush_C")
def bush_c():
    s = flat_bottom(puffs([((-1.1, 0, 0.9), 0.95), ((0.2, 0.1, 1.05), 1.1), ((1.35, -0.1, 0.85), 0.88), ((-0.35, -0.55, 1.5), 0.68),
                           ((0.8, 0.5, 1.45), 0.7), ((-0.4, 0.6, 1.3), 0.7)], k=0.3, amp=0.04, freq=2.2, seed=4))
    body = part(s, 0.045, 1200, tone(*BUSH, lift=0.75, sink=0.6, bottom=(0, 1.0, 0.3), var=0.06, freq=1.0, seed=2))
    berries = []
    rng = np.random.default_rng(5)
    for cx, cy, cz in ((-1.1, 0, 0.9), (0.2, 0.1, 1.05), (1.35, -0.1, 0.85)):
        for p, n in dots_on(s, (cx, cy, cz), fib_dirs(4, zmin=-0.1, seed=int(rng.integers(100))), 0.0, embed=0.0):
            berries.append(sdf.sphere(tuple(p + n * 0.1), 0.17))
    be = part(U(*berries), 0.02, 800, tone("#E8413B", "#FF9A80", "#A42320", lift=0.6, sink=0.5, var=0))
    return finish("Bush_C", [body, be], ao=(1.0, 0.5))


# ── Flowers, grass, small plants ─────────────────────────────────────────────

def flower_head(kind):
    """Local head shapes (petals, centre), facing +Z, base of the head at the origin."""
    petals, center = [], None
    if kind == "Yellow":
        for i in range(5):
            a = i * 72
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            petals.append(sdf.ellipsoid((ca * 0.14, sa * 0.14, 0.02), (0.13, 0.11, 0.045), rot=(0, -14, a)))
        center = sdf.sphere((0, 0, 0.06), 0.07)
    elif kind == "Pink":
        for i in range(3):
            for ring, off, rad, hgt in ((0, 0, 0.075, 0.2), (1, 60, 0.04, 0.18)):
                a = i * 120 + off
                ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
                petals.append(sdf.ellipsoid((ca * rad, sa * rad, 0.17), (0.1, 0.075, hgt), rot=(0, 12 - ring * 6, a)))
        center = sdf.sphere((0, 0, 0.02), 0.05)
    elif kind == "Blue":
        for i in range(5):
            a = i * 72 + 18
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            petals.append(sdf.ellipsoid((ca * 0.095, sa * 0.095, 0.02), (0.095, 0.08, 0.04), rot=(0, -12, a)))
        center = sdf.sphere((0, 0, 0.045), 0.05)
    else:  # White daisy
        for i in range(9):
            a = i * 40
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            petals.append(sdf.ellipsoid((ca * 0.17, sa * 0.17, 0.02), (0.15, 0.075, 0.045), rot=(0, -10, a)))
        center = sdf.ellipsoid((0, 0, 0.05), (0.1, 0.1, 0.07))
    return U(*petals, k=0.015), center


FLOWER_COLS = {
    "Yellow": (("#FFD23A", "#FFF08E", "#DC9A1C"), "#F08A24"),
    "Pink": (("#FF84B3", "#FFC6DD", "#D5507F"), "#FFD447"),
    "Blue": (("#6FA4FF", "#B9D5FF", "#4A6FD6"), "#FFF1B8"),
    "White": (("#FBF6EE", "#FFFFFF", "#BDB3A6"), "#FFC23A"),
}


def flower_patch(name, kind, seed):
    rng = np.random.default_rng(seed)
    n = {"Yellow": 5, "Pink": 5, "Blue": 7, "White": 6}[kind]
    hs = {"Yellow": (0.55, 1.0), "Pink": (0.6, 1.05), "Blue": (0.45, 0.8), "White": (0.5, 0.95)}[kind]
    scale = {"Yellow": 1.25, "Pink": 1.25, "Blue": 1.3, "White": 1.15}[kind]
    petal_local, center_local = flower_head(kind)
    petals, centers, green = [], [], []
    angs = ground_ring(1, n, seed, jitter=0.35)
    for i, a in enumerate(angs):
        rad = 0.2 if i == 0 else rng.uniform(0.45, 0.75)
        if i == 0:
            x, y = 0.0, 0.0
        else:
            x, y = math.cos(a) * rad, math.sin(a) * rad
        h = rng.uniform(*hs) * (1.15 if i == 0 else 1.0)
        top = f32((x * 1.15, y * 1.15, h))
        green.append(chain(arc((x * 0.5, y * 0.5, 0.0), tuple(top), (x * 0.08, y * 0.08, 0.0), 4), [0.06, 0.055, 0.05, 0.045], k=0.02))
        nrm = f32((x * 0.5, y * 0.5 - 0.3, 1.0))
        petals.append(_scaled(petal_local, top, frame(nrm), scale))
        centers.append(_scaled(center_local, top, frame(nrm), scale))
    for a in ground_ring(1, 6, seed + 9, jitter=0.3):
        green.append(sdf.ellipsoid((math.cos(a) * 0.3, math.sin(a) * 0.3, 0.08), (0.34, 0.14, 0.05), rot=(0, -28, math.degrees(a))))
    pal, cc = FLOWER_COLS[kind]
    g = part(flat_bottom(U(*green, k=0.04)), 0.02, 420, tone("#5DAE3F", "#9ED45E", "#34702E", lift=0.5, sink=0.4, top=(0.0, 0.9, 0.35), var=0))
    p = part(U(*petals), 0.018, 650, tone(*pal, lift=0.45, sink=0.35, var=0))
    c = part(U(*centers), 0.018, 180, tone(cc, "#FFFFFF", "#B86A10", lift=0.25, sink=0.3, var=0))
    return finish(name, [g, p, c], ao=(0.35, 0.45))


def _scaled(shape, center, R, s):
    """Uniformly scaled placement (SDF value rescaled so the surface stays correct)."""
    base = placed(shape, (0, 0, 0), R=R)
    c = f32(center)
    lo, hi = f32(base[1][0]) * s + c, f32(base[1][1]) * s + c
    return (lambda P: base[0]((P - c) / s) * s, (lo, hi))


@asset("FlowerPatch_Yellow")
def fp_yellow():
    return flower_patch("FlowerPatch_Yellow", "Yellow", 21)


@asset("FlowerPatch_Pink")
def fp_pink():
    return flower_patch("FlowerPatch_Pink", "Pink", 22)


@asset("FlowerPatch_Blue")
def fp_blue():
    return flower_patch("FlowerPatch_Blue", "Blue", 23)


@asset("FlowerPatch_White")
def fp_white():
    return flower_patch("FlowerPatch_White", "White", 24)


def grass_tuft(name, n, hs, spread, seed, radii=(0.085, 0.07, 0.05, 0.025)):
    rng = np.random.default_rng(seed)
    blades = []
    for a in ground_ring(1, n, seed, jitter=0.4):
        h = rng.uniform(*hs)
        out = rng.uniform(*spread)
        base = (math.cos(a) * 0.12, math.sin(a) * 0.12, -0.02)
        tip = (math.cos(a) * out, math.sin(a) * out, h)
        blades.append(chain(arc(base, tip, (-math.cos(a) * out * 0.35, -math.sin(a) * out * 0.35, 0.1), 4), list(radii), k=0.02))
    blades.append(sdf.ellipsoid((0, 0, 0.0), (0.22, 0.22, 0.08)))
    s = flat_bottom(U(*blades, k=0.03))
    return finish(name, [part(s, 0.016, 360, tone("#4F9B39", "#C2E46A", "#2F6A2C", lift=0.3, sink=0.3, top=(0.05, max(hs) * 0.95, 0.85), var=0))], ao=(0.3, 0.45))


@asset("GrassTuft_A")
def grass_a():
    return grass_tuft("GrassTuft_A", 7, (0.65, 1.05), (0.4, 0.62), 31, radii=(0.075, 0.06, 0.042, 0.02))


@asset("GrassTuft_B")
def grass_b():
    return grass_tuft("GrassTuft_B", 9, (0.4, 0.7), (0.35, 0.6), 32, radii=(0.09, 0.075, 0.055, 0.03))


@asset("Mushroom_Red")
def mushroom_red():
    stems, caps, spots = [], [], []
    for (cx, cy), s, tilt in (((0, 0), 1.0, (0, 0, 0)), ((0.62, 0.3), 0.58, (0, 14, 20))):
        R = rotm(tilt)
        stem = placed(sdf.round_cone((0, 0, 0), (0, 0, 0.82 * s), 0.2 * s, 0.14 * s), (cx, cy, 0), R=R)
        cap_l = sdf.smooth_subtract(sdf.ellipsoid((0, 0, 0.92 * s), (0.56 * s, 0.56 * s, 0.44 * s)),
                                    sdf.ellipsoid((0, 0, 0.66 * s), (0.54 * s, 0.54 * s, 0.26 * s)), k=0.06 * s)
        cap = placed(cap_l, (cx, cy, 0), R=R)
        stems.append(stem)
        caps.append(cap)
        top = f32((cx, cy, 0)) + R @ f32((0, 0, 0.92 * s))
        for d in ((0, 0, 1), (0.8, 0.1, 0.55), (-0.5, 0.6, 0.6), (-0.3, -0.85, 0.45), (0.35, -0.6, 0.75), (0.2, 0.85, 0.5), (-0.9, -0.1, 0.35)):
            dd = R @ (f32(d) / np.linalg.norm(d))
            p, n = stick(cap, top + dd * 3, top, embed=0.0)
            if p is not None:
                spots.append(placed(sdf.ellipsoid((0, 0, 0), (0.1 * s, 0.1 * s, 0.035 * s)), p, R=frame(n)))
    stem = part(flat_bottom(U(*stems, k=0.02)), 0.015, 220, tone("#F3E7D2", "#FFFFFF", "#C8B69A", lift=0.3, sink=0.3, bottom=(0, 0.4, 0.2), var=0))
    cap_paint = mix_paint(tone("#E4463A", "#FF8468", "#A42A22", lift=0.55, sink=0.2, var=0), "#EAD7BA",
                          lambda P, N: sst(-0.1, -0.45, N[:, 2]))
    cap = part(U(*caps), 0.015, 600, cap_paint)
    sp = part(U(*spots), 0.012, 250, flat("#FFF8EC"))
    return finish("Mushroom_Red", [stem, cap, sp], ao=(0.35, 0.45))


@asset("Reeds")
def reeds():
    rng = np.random.default_rng(41)
    green, heads = [], []
    for i, a in enumerate(ground_ring(1, 9, 41, jitter=0.4)):
        r0 = rng.uniform(0.1, 0.45)
        base = (math.cos(a) * r0, math.sin(a) * r0, -0.05)
        if i % 3 == 0:  # cattail
            h = rng.uniform(2.7, 3.4)
            top = (base[0] * 1.3, base[1] * 1.3, h)
            green.append(chain(arc(base, top, (base[0] * 0.2, base[1] * 0.2, 0), 4), [0.07, 0.06, 0.055, 0.05], k=0.01))
            hc = f32(top) - f32((0, 0, 0.35))
            heads.append(sdf.capsule(tuple(hc - f32((0, 0, 0.3))), tuple(hc + f32((0, 0, 0.18))), 0.15))
            green.append(sdf.round_cone(tuple(f32(top) - f32((0, 0, 0.1))), tuple(f32(top) + f32((0, 0, 0.3))), 0.045, 0.02))
        else:
            h = rng.uniform(1.9, 3.0)
            out = rng.uniform(0.5, 1.0)
            tip = (math.cos(a) * out, math.sin(a) * out, h)
            green.append(chain(arc(base, tip, (-math.cos(a) * out * 0.4, -math.sin(a) * out * 0.4, 0.2), 5), [0.1, 0.085, 0.065, 0.045, 0.02], k=0.02))
    green.append(sdf.ellipsoid((0, 0, 0.05), (0.5, 0.5, 0.2)))
    g = part(flat_bottom(U(*green, k=0.06)), 0.022, 1000, tone("#62A93E", "#B6DC66", "#356E2F", lift=0.3, sink=0.3, top=(0.2, 2.8, 0.55), var=0))
    h = part(U(*heads), 0.02, 350, tone("#84502D", "#B07A4C", "#55321C", lift=0.4, sink=0.4, var=0))
    return finish("Reeds", [g, h], ao=(0.6, 0.45))


@asset("LilyPad")
def lilypad():
    pad = sdf.cylinder((0, 0, 0.08), 1.15, 0.08, rounding=0.07)
    notch = U(sdf.round_box((0.62, -0.05, 0.08), (0.6, 0.06, 0.3), 0.0, rot=(0, 0, -12)),
              sdf.round_box((0.62, 0.05, 0.08), (0.6, 0.06, 0.3), 0.0, rot=(0, 0, 12)))
    pad = sdf.smooth_subtract(pad, notch, k=0.04)

    def curl(P):
        Q = P.copy()
        r = np.sqrt(Q[:, 0] ** 2 + Q[:, 1] ** 2)
        Q[:, 2] -= 0.1 * (r / 1.15) ** 3
        return Q
    pad = sdf.warp(pad, curl, pad=0.15)
    pp = part(pad, 0.02, 420, tone("#5DAE45", "#A3D767", "#3A7A34", lift=0.55, sink=0.5, var=0.07, freq=3.0))
    fc = f32((-0.25, -0.2, 0.15))
    petals = []
    for i in range(8):
        a = i * 45
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        petals.append(sdf.ellipsoid(tuple(fc + f32((ca * 0.19, sa * 0.19, 0.06))), (0.21, 0.085, 0.05), rot=(0, -32, a)))
    for i in range(6):
        a = i * 60 + 20
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        petals.append(sdf.ellipsoid(tuple(fc + f32((ca * 0.09, sa * 0.09, 0.14))), (0.15, 0.07, 0.045), rot=(0, -60, a)))
    fl = part(U(*petals, k=0.02), 0.016, 520, tone("#FF8DBA", "#FFD6E7", "#D65E8E", lift=0.5, sink=0.3, var=0))
    ce = part(sdf.sphere(tuple(fc + f32((0, 0, 0.15))), 0.08), 0.016, 120, flat("#FFCF3F"))
    return finish("LilyPad", [pp, fl, ce], ao=(0.35, 0.4))


# ── Rocks and ground bits ────────────────────────────────────────────────────

def stone_paint(seed=0, pal=STONE):
    return tone(*pal, lift=0.6, sink=0.55, bottom=(0.0, 0.5, 0.2), var=0.07, freq=1.6, seed=seed)


def mossy(shape, blobs, seed, voxel, tris, thick=0.05):
    return part(moss_patch(shape, blobs, thick=thick), voxel, tris, tone(*MOSS, lift=0.55, sink=0.5, var=0.06, freq=2.0, seed=seed))


def facet_rock(center, radii, cuts, k=0.15, amp=0.03, freq=2.0, seed=1, rot=(0, 0, 0)):
    """Soft pebble with a few planar facets: ellipsoid smooth-intersected with half-spaces.
    cuts: (normal, distance from center along that normal)."""
    c = f32(center)
    s = sdf.ellipsoid(tuple(c), radii, rot=rot)
    for n, d in cuts:
        nn = f32(n) / np.linalg.norm(n)
        s = sdf.smooth_intersect(s, ((lambda P, nn=nn, d=d: (P - c) @ nn - d), s[1]), k=k)
    s = sdf.noise_bumps(s, amplitude=amp, frequency=freq, seed=seed)
    return s


@asset("Rock_Small_A")
def rock_small_a():
    s = flat_bottom(facet_rock((0, 0, 0.3), (0.72, 0.6, 0.62),
                               [((0.15, -0.1, 1), 0.36), ((-0.35, -1, 0.25), 0.44), ((1, 0.25, 0.3), 0.5), ((-0.8, 0.6, 0.45), 0.48)],
                               k=0.06, amp=0.02, freq=2.5, seed=1, rot=(0, 0, 20)))
    return finish("Rock_Small_A", [part(s, 0.022, 500, stone_paint(1))], ao=(0.4, 0.45))


@asset("Rock_Small_B")
def rock_small_b():
    a = facet_rock((0, 0, 0.45), (0.78, 0.64, 0.85), [((0.2, -0.15, 1), 0.62), ((-0.2, -1, 0.1), 0.5), ((1, -0.3, 0.2), 0.58), ((-1, 0.4, 0.5), 0.55)],
                   k=0.07, amp=0.02, freq=2.3, seed=2)
    b = facet_rock((0.62, -0.32, 0.18), (0.42, 0.36, 0.34), [((0.1, 0, 1), 0.2), ((0.3, -1, 0.2), 0.27)], k=0.05, amp=0.015, seed=3)
    s = flat_bottom(U(a, b, k=0.08))
    return finish("Rock_Small_B", [part(s, 0.025, 750, stone_paint(2)),
                                   mossy(s, [((-0.05, 0.15, 1.12), (0.5, 0.42, 0.12))], 2, 0.02, 280, thick=0.03)], ao=(0.5, 0.45))


@asset("Rock_Medium_A")
def rock_medium_a():
    big = facet_rock((0, 0, 1.0), (2.0, 1.65, 1.75), [((0.12, -0.1, 1), 1.3), ((-0.3, -1, 0.3), 1.2), ((1, -0.2, 0.35), 1.4), ((-1, 0.3, 0.25), 1.45),
                                                     ((0.4, 1, 0.4), 1.25), ((-0.6, -0.5, 1), 1.35)], k=0.14, amp=0.04, freq=1.2, seed=3, rot=(0, 0, 15))
    small = facet_rock((1.95, -1.2, 0.35), (0.75, 0.62, 0.62), [((0.1, 0, 1), 0.32), ((0.5, -1, 0.2), 0.45), ((1, 0.3, 0.3), 0.5)], k=0.06, amp=0.02, seed=4)
    return finish("Rock_Medium_A", [part(flat_bottom(big), 0.045, 1600, stone_paint(3)), part(flat_bottom(small), 0.03, 500, stone_paint(4))], ao=(1.0, 0.5))


@asset("Rock_Medium_B")
def rock_medium_b():
    s = facet_rock((0, 0, 0.55), (2.2, 1.75, 1.35), [((0.05, 0.08, 1), 1.0), ((-0.2, -1, 0.35), 1.35), ((1, 0.2, 0.3), 1.8), ((-1, -0.3, 0.3), 1.75),
                                                     ((0.3, 1, 0.3), 1.35)], k=0.16, amp=0.04, freq=1.2, seed=5, rot=(0, 0, -10))
    s = flat_bottom(s)
    return finish("Rock_Medium_B", [part(s, 0.045, 1600, stone_paint(5, pal=("#A39E97", "#D3CFC6", "#69655F"))),
                                    mossy(s, [((-0.7, 0.4, 1.5), (1.1, 0.85, 0.3)), ((0.5, 0.0, 1.5), (0.65, 0.55, 0.28))], 5, 0.035, 600, thick=0.04)], ao=(1.0, 0.5))


@asset("Log_A")
def log_a():
    cz = 0.66
    body = sdf.cylinder((0, 0, cz), 0.68, 3.0, rot=(0, 90, 0), rounding=0.2)
    body = ridges(body, 0.03, 10, axis="x", center=(0.0, cz), twist=0.4)
    stub = sdf.round_cone((0.9, -0.1, 1.0), (1.3, -0.45, 1.7), 0.25, 0.18)
    stub2 = sdf.round_cone((-1.5, 0.2, 1.05), (-1.8, 0.7, 1.45), 0.2, 0.14)
    wood = U(body, stub, stub2, k=0.2)
    hollow = sdf.cylinder((-3.0, 0, cz), 0.45, 1.3, rot=(0, 90, 0), rounding=0.1)
    wood = flat_bottom(sdf.smooth_subtract(wood, hollow, k=0.08), 0.0)

    bark = tone(*BARK, lift=0.55, sink=0.5, var=0.06, freq=1.2)
    rings = rings_paint("#E8B97E", "#C68E57", lambda P: np.sqrt(P[:, 1] ** 2 + (P[:, 2] - cz) ** 2), freq=22)

    def paint(P, N):
        c = bark(P, N)
        end = sst(0.55, 0.85, np.abs(N[:, 0])) * sst(2.6, 2.9, np.abs(P[:, 0]))
        c = lerp(c, rings(P, N), end)
        r = np.sqrt(P[:, 1] ** 2 + (P[:, 2] - cz) ** 2)
        inside = sst(0.5, 0.4, r) * sst(-1.6, -2.2, P[:, 0])
        c = lerp(c, C("#3A2618"), inside * (0.6 + 0.4 * sst(-2.9, -2.0, P[:, 0])))
        return c
    w = part(wood, 0.035, 2000, paint)
    moss = mossy(body, [((-1.0, -0.1, 1.35), (1.1, 0.55, 0.35)), ((1.9, 0.15, 1.3), (0.6, 0.5, 0.3))], 4, 0.03, 400, thick=0.04)
    return finish("Log_A", [w, moss], ao=(0.8, 0.5))


@asset("Stump_A")
def stump_a():
    body = sdf.cylinder((0, 0, 0.62), 0.95, 0.62, rounding=0.12)
    rs = []
    for a in ground_ring(1, 5, 51, jitter=0.35):
        rs.append(sdf.round_cone((math.cos(a) * 0.5, math.sin(a) * 0.5, 0.55), (math.cos(a) * 1.55, math.sin(a) * 1.55, 0.0), 0.36, 0.14))
    wood = flat_bottom(ridges(U(body, *rs, k=0.3), 0.03, 11, twist=0.3))
    bark = tone(*BARK, lift=0.35, sink=0.5, bottom=(0, 0.6, 0.2), var=0.05, freq=1.5)
    rings = rings_paint("#EDC08A", "#C9925A", lambda P: np.sqrt(P[:, 0] ** 2 + P[:, 1] ** 2), freq=18)

    def paint(P, N):
        return lerp(bark(P, N), rings(P, N), sst(0.6, 0.85, N[:, 2]) * sst(1.05, 1.15, P[:, 2]))
    return finish("Stump_A", [part(wood, 0.03, 1300, paint)], ao=(0.8, 0.5))


@asset("PondRim_Stone")
def pond_stone():
    s = facet_rock((0, 0, 0.0), (1.1, 0.92, 0.62), [((0, 0, 1), 0.4), ((-0.3, -1, 0.1), 0.78), ((1, 0.35, 0.1), 0.92)],
                   k=0.06, amp=0.02, freq=2.2, seed=61, rot=(0, 0, 12))
    return finish("PondRim_Stone", [part(flat_bottom(s), 0.022, 450, stone_paint(6, pal=("#A8A39B", "#DAD5CA", "#6C6760")))], ao=(0.4, 0.4))


# ── Home backyard ────────────────────────────────────────────────────────────

def picket(x, h, w=0.62, t=0.2, tilt=0.0, y=0.0, z0=0.0):
    """Board with a soft pointed top, base at z0, top at z0+h."""
    body_h = h - w * 0.5
    body = sdf.round_box((0, 0, body_h * 0.5), (w * 0.5, t * 0.5, body_h * 0.5), 0.08)
    tip = sdf.round_box((0, 0, body_h), (w * 0.35, t * 0.5, w * 0.35), 0.08, rot=(0, 45, 0))
    return placed(U(body, tip, k=0.03), (x, y, z0), rot=(0, tilt, 0))


def cream_paint(seed=0):
    return tone(*CREAM, lift=0.45, sink=0.5, bottom=(0.0, 1.0, 0.25), var=0.04, freq=1.1, seed=seed)


@asset("Fence_Straight")
def fence_straight():
    rng = np.random.default_rng(71)
    n = 7
    boards = [picket(-4 + (i + 0.5) * 8 / n, 3.35 + rng.uniform(-0.1, 0.1), tilt=rng.uniform(-2.5, 2.5)) for i in range(n)]
    rails = [sdf.round_box((0, 0.2, z), (4.0, 0.09, 0.17), 0.07) for z in (0.95, 2.35)]
    s = flat_bottom(U(*boards, *rails, k=0.03))
    return finish("Fence_Straight", [part(s, 0.03, 2200, cream_paint(1))], ao=(0.7, 0.5), x_extent=4.0)


@asset("Fence_Post")
def fence_post():
    post = sdf.round_box((0, 0, 1.95), (0.34, 0.34, 1.95), 0.1)
    collar = sdf.round_box((0, 0, 3.86), (0.42, 0.42, 0.1), 0.06)
    ball = sdf.sphere((0, 0, 4.18), 0.3)
    s = flat_bottom(U(post, collar, ball, k=0.05))
    return finish("Fence_Post", [part(s, 0.025, 700, cream_paint(2))], ao=(0.5, 0.45))


@asset("Gate_Picket")
def gate_picket():
    boards, wood, metal = [], [], []
    for side in (-1, 1):
        for i in range(4):
            x = side * (0.55 + i * 0.97)
            h = 3.0 + 0.55 * math.cos(math.pi * abs(x) / 8.4) - 0.1
            boards.append(picket(x, h, w=0.66, z0=0.15))
        cx = side * 2.0
        wood.append(sdf.round_box((cx, 0.2, 0.95), (1.95, 0.09, 0.17), 0.07))
        wood.append(sdf.round_box((cx, 0.2, 2.45), (1.95, 0.09, 0.17), 0.07))
        ang = math.degrees(math.atan2(1.5, 3.4)) * side
        wood.append(sdf.round_box((cx, 0.22, 1.7), (1.85, 0.08, 0.14), 0.06, rot=(0, ang, 0)))
        for z in (0.95, 2.45):
            metal.append(sdf.round_box((side * 3.92, 0.24, z), (0.1, 0.13, 0.22), 0.05))
    metal.append(torus((0.25, -0.12, 1.75), 0.16, 0.05, rot=(90, 0, 0)))
    metal.append(sdf.round_box((-0.1, -0.1, 1.75), (0.3, 0.06, 0.08), 0.03))
    s = flat_bottom(U(*boards, *wood, k=0.03))
    return finish("Gate_Picket", [part(s, 0.03, 2600, cream_paint(3)), part(U(*metal), 0.02, 400, tone(*METAL, lift=0.4, sink=0.4, var=0))],
                  ao=(0.7, 0.5), x_extent=4.0)


@asset("Shack")
def shack():
    W, D, WALL = 3.2, 2.8, 3.8
    rng = np.random.default_rng(81)
    planks = []
    n = 6
    ph = WALL / n
    for i in range(n):
        j = rng.uniform(-0.03, 0.03, 2)
        planks.append(sdf.round_box((0, 0, ph * (i + 0.5)), (W + j[0], D + j[1], ph * 0.5 + 0.03), 0.12))
    gable = sdf.smooth_intersect(sdf.round_box((0, 0, 4.9), (W - 0.1, D - 0.12, 1.3), 0.06),
                                 (lambda P: (P[:, 2] - 6.25 + 0.8125 * np.abs(P[:, 0])) / 1.2866, (f32((-W, -D, 3.5)), f32((W, D, 6.4)))), k=0.05)
    hollow = sdf.round_box((0, 0, 2.3), (W - 0.36, D - 0.36, 2.15), 0.15)
    door = U(sdf.cylinder((0, -D, 1.7), 1.25, 0.7, rot=(90, 0, 0)), sdf.round_box((0, -D, 0.75), (1.25, 0.7, 0.95), 0.0))
    walls = sdf.smooth_subtract(sdf.smooth_subtract(U(*planks, k=0.0), hollow, k=0.05), door, k=0.06)
    gable = sdf.smooth_subtract(gable, hollow, k=0.05)

    def wall_paint(P, N):
        c = tone(*WOOD, lift=0.4, sink=0.5, var=0.05, freq=0.9)(P, N)
        band = np.floor(P[:, 2] / ph)
        c = c * (1.0 + 0.07 * np.sin(band * 2.4 + 0.5))[:, None]
        inside = (np.abs(P[:, 0]) < W - 0.22) & (np.abs(P[:, 1]) < D - 0.22)
        depth = sst(-D, 0.5, P[:, 1])
        return lerp(c, C("#2E2119"), inside.astype(np.float32) * (0.75 + 0.25 * depth))
    wall_o = part(walls, 0.04, 2600, wall_paint)
    gable_o = part(gable, 0.04, 500, tone("#DCA86C", "#F2C792", "#9E7046", lift=0.4, sink=0.4, var=0.04))
    posts = U(*[sdf.round_box((sx * W, sy * D, 1.95), (0.3, 0.3, 1.98), 0.12) for sx in (-1, 1) for sy in (-1, 1)])
    frame_s = U(sdf.smooth_intersect(torus((0, -D - 0.12, 1.7), 1.42, 0.18, rot=(90, 0, 0)), (lambda P: 1.65 - P[:, 2], torus((0, -D - 0.12, 1.7), 1.42, 0.18, rot=(90, 0, 0))[1]), k=0.02),
                sdf.round_box((-1.42, -D - 0.12, 0.85), (0.18, 0.18, 0.86), 0.07), sdf.round_box((1.42, -D - 0.12, 0.85), (0.18, 0.18, 0.86), 0.07),
                sdf.round_box((0, -D - 0.1, 4.45), (0.85, 0.08, 0.32), 0.06), k=0.03)
    trim = part(flat_bottom(U(posts, frame_s)), 0.035, 1100, tone(*CREAM, lift=0.4, sink=0.5, var=0.03))

    # roof: three overlapping board rows per side, sloping toward +-X
    theta = math.degrees(math.atan2(2.6, 3.2))
    u = f32((math.cos(math.radians(theta)), 0, -math.sin(math.radians(theta))))
    nrm = f32((math.sin(math.radians(theta)), 0, math.cos(math.radians(theta))))
    ridge = f32((0, 0, 6.3))
    boards, patches, nails = [], [], []
    for side in (-1, 1):
        m = f32((side, 1, 1))
        rot = (0, theta * side, 0)
        for row, s in enumerate((0.72, 2.35, 3.98)):
            c = (ridge + u * s + nrm * (0.22 + row * 0.07)) * m
            boards.append(sdf.round_box(tuple(c), (0.95, D + 0.65, 0.17), 0.1, rot=rot))
    for side, s, y, gam, size, col in ((1, 2.2, -1.0, 12, (0.55, 0.5), 0), (-1, 3.2, 1.3, -9, (0.5, 0.45), 1), (1, 3.9, 1.7, 5, (0.38, 0.4), 0)):
        m = f32((side, 1, 1))
        row_off = 0.22 + (0 if s < 1.5 else 1 if s < 3.1 else 2) * 0.07
        c = (ridge + u * s + nrm * (row_off + 0.2)) * m
        c[1] = y
        R = rotm((0, theta * side, 0)) @ rotm((0, 0, gam))
        patches.append((placed(sdf.round_box((0, 0, 0), (size[0], size[1], 0.06), 0.04), c, R=R), col))
        for px in (-1, 1):
            for py in (-1, 1):
                nails.append(placed(sdf.sphere((px * (size[0] - 0.12), py * (size[1] - 0.12), 0.07), 0.06), c, R=R))
    roof = U(*boards, k=0.02)
    ridge_cap = sdf.capsule((0, -D - 0.6, 6.72), (0, D + 0.6, 6.72), 0.26)

    def roof_paint(P, N):
        c = tone(*ROOF, lift=0.45, sink=0.55, var=0.05, freq=0.8)(P, N)
        return c
    roof_o = part(roof, 0.04, 1500, roof_paint)
    cap_o = part(ridge_cap, 0.04, 200, tone(*WOOD_D, lift=0.4, sink=0.4, var=0))
    patch_y = part(U(*[p for p, c in patches if c == 0]), 0.025, 250, tone("#E7B75E", "#FAD890", "#A87C35", lift=0.4, sink=0.3, var=0))
    patch_b = part(U(*[p for p, c in patches if c == 1]), 0.025, 150, tone("#6FA2DA", "#A9CCF2", "#4670A8", lift=0.4, sink=0.3, var=0))
    nails_o = part(U(*nails), 0.02, 250, flat("#5B5E63"))
    # crooked stovepipe
    px, py = -1.9, 1.3
    base_z = 6.3 - 0.8125 * abs(px) + 0.3
    pipe = U(chain([(px, py, base_z - 0.3), (px, py, base_z + 0.7), (px - 0.15, py, base_z + 1.3)], [0.27, 0.27, 0.27], k=0.02),
             sdf.cylinder((px - 0.2, py, base_z + 1.45), 0.4, 0.14, rounding=0.06))
    pipe_o = part(pipe, 0.03, 400, mix_paint(tone(*METAL, lift=0.4, sink=0.4, var=0), "#B0633A", lambda P, N: sst(base_z + 1.2, base_z + 1.35, P[:, 2])))
    return finish("Shack", [wall_o, gable_o, trim, roof_o, cap_o, patch_y, patch_b, nails_o, pipe_o], ao=(1.4, 0.55), samples=24)


@asset("Signpost")
def signpost():
    post = sdf.round_box((0, 0.12, 2.5), (0.23, 0.23, 2.5), 0.1)
    board = sdf.round_box((0, -0.2, 3.75), (1.6, 0.13, 0.78), 0.14, rot=(0, -4, 0))
    wood = part(flat_bottom(post), 0.03, 400, tone(*WOOD_D, lift=0.4, sink=0.4, bottom=(0, 1, 0.2), var=0.05))
    face = part(board, 0.03, 600, mix_paint(tone("#DDAE72", "#F3CD98", "#A8773F", lift=0.3, sink=0.4, var=0.04, freq=1.5), "#B98450",
                                            lambda P, N: sst(0.5, 0.9, np.abs(N[:, 0])) + sst(0.5, 0.9, np.abs(N[:, 2]))))
    nails = part(U(sdf.sphere((-1.3, -0.35, 3.82), 0.07), sdf.sphere((1.3, -0.35, 3.64), 0.07)), 0.02, 120, flat("#5B5E63"))
    return finish("Signpost", [wood, face, nails], ao=(0.6, 0.45))


@asset("Lantern_Post")
def lantern_post():
    post = U(sdf.round_box((0, 0, 3.2), (0.25, 0.25, 3.2), 0.09), sdf.round_box((0, 0, 0.22), (0.42, 0.42, 0.22), 0.08),
             sdf.sphere((0, 0, 6.5), 0.3), k=0.05)
    wood = part(flat_bottom(post), 0.03, 500, tone(*WOOD_D, lift=0.4, sink=0.4, bottom=(0, 1, 0.2), var=0.04))
    lx = 1.45
    arm = chain([(0, 0, 5.7), (0.8, 0, 6.35), (lx, 0, 6.25), (lx, 0, 5.95)], [0.1, 0.1, 0.09, 0.07], k=0.03)
    cap = sdf.round_cone((lx, 0, 5.52), (lx, 0, 5.82), 0.46, 0.12)
    base = sdf.round_box((lx, 0, 4.45), (0.42, 0.42, 0.08), 0.05)
    bars = [sdf.round_box((lx + sx * 0.33, sy * 0.33, 4.97), (0.05, 0.05, 0.47), 0.03) for sx in (-1, 1) for sy in (-1, 1)]
    metal = part(U(arm, cap, base, *bars, sdf.sphere((lx, 0, 4.3), 0.1), k=0.03), 0.02, 900, tone(*METAL, lift=0.45, sink=0.4, var=0))
    glass = part(sdf.round_box((lx, 0, 4.97), (0.32, 0.32, 0.46), 0.14), 0.025, 300,
                 lambda P, N: lerp(np.tile(C("#FFD463"), (len(P), 1)), C("#FFF5CC"), sst(4.6, 5.3, P[:, 2]) * 0.8), glow=True)
    return finish("Lantern_Post", [wood, metal, glass], ao=(0.6, 0.45))


@asset("Mailbox")
def mailbox():
    post = U(sdf.round_box((0, 0.15, 1.45), (0.17, 0.17, 1.45), 0.06), sdf.round_box((0, 0.15, 2.85), (0.42, 0.55, 0.08), 0.04), k=0.04)
    wood = part(flat_bottom(post), 0.025, 350, tone(*WOOD_D, lift=0.4, sink=0.4, bottom=(0, 1, 0.2), var=0.04))
    body = U(sdf.round_box((0, 0.05, 3.2), (0.46, 0.8, 0.3), 0.1), sdf.cylinder((0, 0.05, 3.5), 0.46, 0.8, rot=(90, 0, 0), rounding=0.1), k=0.02)
    lip = sdf.round_box((0, -0.77, 3.35), (0.5, 0.06, 0.52), 0.05)
    lip = sdf.smooth_intersect(lip, sdf.offset(U(sdf.round_box((0, -0.77, 3.2), (0.5, 0.2, 0.34), 0.1), sdf.cylinder((0, -0.77, 3.5), 0.5, 0.2, rot=(90, 0, 0), rounding=0.1)), 0.0), k=0.02)
    box = part(U(body, lip, k=0.01), 0.025, 900, tone("#5C9EDB", "#A3CDF4", "#3A6BA5", lift=0.5, sink=0.45, var=0))
    flag = U(sdf.round_box((0.52, 0.35, 3.62), (0.045, 0.07, 0.42), 0.03), sdf.round_box((0.52, 0.52, 3.92), (0.045, 0.24, 0.14), 0.03))
    fl = part(flag, 0.018, 250, tone("#E5473C", "#FF8C73", "#A32A22", lift=0.4, sink=0.4, var=0))
    knob = part(sdf.sphere((0, -0.86, 3.5), 0.07), 0.015, 80, flat("#E8C35A"))
    return finish("Mailbox", [wood, box, fl, knob], ao=(0.5, 0.45))


@asset("Hay_Bale")
def hay_bale():
    body = sdf.round_box((0, 0, 0.8), (1.45, 0.9, 0.8), 0.32)
    grooves = U(*[band_x(x, (0.9, 0.8), 0.32, 0.07, 0.045, 0.8) for x in (-0.98, 0.0, 0.98)])
    body = sdf.smooth_subtract(body, grooves, k=0.06)
    body = sdf.noise_bumps(body, amplitude=0.018, frequency=6.0, seed=91)
    straw = part(flat_bottom(body), 0.03, 1100, tone(*HAY, lift=0.5, sink=0.5, bottom=(0, 0.6, 0.25), var=0.08, freq=3.0))
    bands = U(*[band_x(x, (0.9, 0.8), 0.32, 0.05, 0.07, 0.8) for x in (-0.5, 0.5)])
    bd = part(flat_bottom(bands), 0.02, 500, tone("#9A5A2A", "#C4834C", "#643818", lift=0.4, sink=0.4, var=0))
    return finish("Hay_Bale", [straw, bd], ao=(0.6, 0.45))


@asset("Bench_Wood")
def bench_wood():
    planks = []
    rng = np.random.default_rng(101)
    for y in (-0.36, 0.0, 0.36):
        planks.append(sdf.round_box((0, y, 1.45), (2.15 + rng.uniform(-0.04, 0.04), 0.16, 0.1), 0.06))
    for z in (2.2, 2.78):
        planks.append(sdf.round_box((0, 0.62 + (z - 1.5) * 0.12, z), (2.15, 0.09, 0.22), 0.07, rot=(-7, 0, 0)))
    legs = []
    for x in (-1.65, 1.65):
        legs.append(sdf.round_box((x, -0.34, 0.68), (0.15, 0.15, 0.7), 0.06))
        legs.append(sdf.round_box((x, 0.5, 1.4), (0.14, 0.14, 1.42), 0.06, rot=(-7, 0, 0)))
        legs.append(sdf.round_box((x, 0.08, 1.28), (0.12, 0.5, 0.09), 0.05))
        legs.append(sdf.round_box((x, -0.02, 2.02), (0.11, 0.42, 0.08), 0.04))
    seat = part(U(*planks, k=0.01), 0.025, 1300, tone(*WOOD, lift=0.45, sink=0.5, var=0.05, freq=1.2))
    lg = part(flat_bottom(U(*legs, k=0.03)), 0.025, 900, tone(*WOOD_D, lift=0.4, sink=0.45, bottom=(0, 0.8, 0.2), var=0.04))
    return finish("Bench_Wood", [seat, lg], ao=(0.7, 0.5))


@asset("Well")
def well():
    rng = np.random.default_rng(111)
    ring = sdf.smooth_subtract(sdf.cylinder((0, 0, 0.95), 1.85, 0.95, rounding=0.25), sdf.cylinder((0, 0, 1.4), 1.3, 1.0, rounding=0.1), k=0.1)
    stones = []
    for row, z in enumerate((0.45, 1.25)):
        for i in range(11):
            a = (i + 0.5 * row) * 2 * math.pi / 11 + rng.uniform(-0.05, 0.05)
            stones.append(sdf.ellipsoid((math.cos(a) * 1.75, math.sin(a) * 1.75, z), (0.36, 0.52, 0.36), rot=(0, 0, math.degrees(a))))
    body = flat_bottom(U(U(ring, *stones, k=0.12), sdf.torus((0, 0, 1.9), 1.58, 0.3), k=0.1))
    body = sdf.smooth_subtract(body, sdf.cylinder((0, 0, 1.6), 1.3, 0.9), k=0.05)
    st = part(body, 0.03, 2400, tone(*STONE, lift=0.55, sink=0.5, bottom=(0, 0.6, 0.2), var=0.08, freq=2.2))
    water = part(sdf.cylinder((0, 0, 1.2), 1.36, 0.08), 0.03, 200, lambda P, N: np.tile(C("#3C7FB8"), (len(P), 1)))
    wood = U(sdf.round_box((-1.75, 0, 3.0), (0.2, 0.2, 2.0), 0.08), sdf.round_box((1.75, 0, 3.0), (0.2, 0.2, 2.0), 0.08),
             sdf.cylinder((0, 0, 4.0), 0.14, 1.95, rot=(0, 90, 0), rounding=0.05), sdf.cylinder((0, 0, 4.0), 0.3, 0.25, rot=(0, 90, 0), rounding=0.1),
             sdf.round_box((2.05, 0, 3.8), (0.08, 0.08, 0.26), 0.04), sdf.cylinder((2.2, 0, 3.58), 0.08, 0.2, rot=(0, 90, 0), rounding=0.03), k=0.03)
    wd = part(wood, 0.03, 900, tone(*WOOD_D, lift=0.45, sink=0.45, var=0.04))
    rope = part(sdf.capsule((0, 0, 3.75), (0, 0, 2.95), 0.05), 0.02, 80, flat("#D8C18E"))
    bucket = U(sdf.smooth_subtract(sdf.round_cone((0, 0, 2.3), (0, 0, 2.8), 0.28, 0.33), sdf.cylinder((0, 0, 2.85), 0.25, 0.3), k=0.03),
               torus((0, 0, 2.95), 0.33, 0.045, rot=(90, 0, 0)))
    bk = part(bucket, 0.018, 450, tone(*WOOD, lift=0.4, sink=0.4, var=0))
    phi = 40.0
    roof_l = [sdf.round_box((0, side * 0.92, 5.6), (2.4, 1.4, 0.15), 0.08, rot=(-phi * side, 0, 0)) for side in (-1, 1)]
    rf = part(U(*roof_l, k=0.02), 0.035, 700, tone(*ROOF, lift=0.45, sink=0.55, var=0.05))
    ridge = part(sdf.capsule((-2.5, 0, 6.52), (2.5, 0, 6.52), 0.22), 0.03, 150, tone(*WOOD_D, lift=0.4, sink=0.4, var=0))
    return finish("Well", [st, water, wd, rope, bk, rf, ridge], ao=(1.2, 0.5))


@asset("Bridge_Wood")
def bridge_wood():
    L, H, base = 6.0, 1.45, 0.3

    def ztop(y):
        return base + H * (1 - (y / L) ** 2)

    def slope(y):
        return -2 * H * y / (L * L)
    rng = np.random.default_rng(121)
    planks_a, planks_b = [], []
    n = 15
    for i in range(n):
        y = -5.62 + i * (11.24 / (n - 1))
        ang = math.degrees(math.atan(slope(y)))
        pl = sdf.round_box((0, y, ztop(y) - 0.13), (2.1 + rng.uniform(-0.06, 0.06), 0.36, 0.13), 0.06, rot=(ang + rng.uniform(-1.5, 1.5), 0, rng.uniform(-1.5, 1.5)))
        (planks_a if i % 2 == 0 else planks_b).append(pl)
    ys = np.linspace(-6.0, 6.0, 9)
    stringers = [chain([(sx * 1.55, float(y), ztop(float(y)) - 0.45) for y in ys], [0.24] * 9, k=0.05) for sx in (-1, 1)]
    posts, rails = [], []
    for sx in (-1, 1):
        for y in (-5.3, -2.65, 0.0, 2.65, 5.3):
            zt = ztop(y)
            posts.append(sdf.round_box((sx * 2.05, y, (zt - 0.5 + zt + 1.45) * 0.5), (0.15, 0.15, (1.95) * 0.5), 0.06))
            posts.append(sdf.sphere((sx * 2.05, y, zt + 1.5), 0.17))
        rails.append(chain([(sx * 2.05, float(y), ztop(float(y)) + 1.25) for y in np.linspace(-5.3, 5.3, 9)], [0.12] * 9, k=0.02))
        rails.append(chain([(sx * 2.05, float(y), ztop(float(y)) + 0.55) for y in np.linspace(-5.3, 5.3, 9)], [0.09] * 9, k=0.02))
    deck_a = part(U(*planks_a, k=0.01), 0.035, 1400, tone(*WOOD, lift=0.45, sink=0.5, var=0.05, freq=1.0))
    deck_b = part(U(*planks_b, k=0.01), 0.035, 1400, tone("#BD8049", "#E0AC74", "#80532F", lift=0.45, sink=0.5, var=0.05, freq=1.0, seed=2))
    frame_o = part(flat_bottom(U(*stringers, *posts, *rails, k=0.05)), 0.035, 2800, tone(*WOOD_D, lift=0.45, sink=0.5, bottom=(0, 0.8, 0.2), var=0.04))
    return finish("Bridge_Wood", [deck_a, deck_b, frame_o], ao=(1.0, 0.5), y_extent=6.0)


@asset("Birdhouse_Post")
def birdhouse_post():
    post = U(sdf.round_box((0, 0, 2.45), (0.17, 0.17, 2.45), 0.06), sdf.round_box((0, 0, 0.18), (0.36, 0.36, 0.18), 0.06), k=0.04)
    wood = part(flat_bottom(post), 0.025, 350, tone(*WOOD_D, lift=0.4, sink=0.4, bottom=(0, 1, 0.2), var=0.04))
    body = sdf.round_box((0, 0, 5.35), (0.56, 0.5, 0.62), 0.12)
    gab = sdf.smooth_intersect(sdf.round_box((0, 0, 6.05), (0.54, 0.48, 0.45), 0.05),
                               (lambda P: (P[:, 2] - 6.45 + 0.84 * np.abs(P[:, 0])) / 1.306, (f32((-0.6, -0.6, 5.6)), f32((0.6, 0.6, 6.5)))), k=0.03)
    house = sdf.smooth_subtract(U(body, gab, k=0.02), sdf.cylinder((0, -0.5, 5.5), 0.19, 0.25, rot=(90, 0, 0)), k=0.03)

    def house_paint(P, N):
        c = tone("#F4D27A", "#FFEBB2", "#B8913F", lift=0.4, sink=0.45, var=0)(P, N)
        hole = sst(0.26, 0.15, np.sqrt(P[:, 0] ** 2 + (P[:, 2] - 5.5) ** 2)) * sst(-0.55, -0.35, P[:, 1])
        return lerp(c, C("#2A1F18"), hole)
    ho = part(house, 0.02, 900, house_paint)
    theta = math.degrees(math.atan2(0.84, 1.0))
    roof = U(*[sdf.round_box((side * 0.36, 0, 6.2), (0.52, 0.66, 0.07), 0.05, rot=(0, theta * side, 0)) for side in (-1, 1)], k=0.02)
    rf = part(roof, 0.02, 400, tone("#5B92D8", "#9CC2F2", "#3A64A6", lift=0.45, sink=0.5, var=0))
    perch = part(sdf.capsule((0, -0.5, 5.12), (0, -0.82, 5.12), 0.06), 0.015, 100, tone(*WOOD_D, lift=0.3, sink=0.3, var=0))
    return finish("Birdhouse_Post", [wood, ho, rf, perch], ao=(0.6, 0.45))


# ── Ability gates ────────────────────────────────────────────────────────────

@asset("Boulder_Big")
def boulder_big():
    rock = rock_shape([((0, 0, 4.3), (4.5, 4.3, 4.5), (0, 0, 15)), ((1.5, -0.8, 5.6), (2.6, 2.6, 2.6), (0, 0, 0)),
                       ((-1.6, 0.9, 5.4), (2.7, 2.7, 2.6), (0, 0, 0))],
                      amp=0.12, freq=0.5, seed=131, k=1.2)
    # a big paw print pressed into the front face: "something huge pushes this"
    cut = []
    for px, pz, rr in ((0.0, 3.75, (0.95, 0.75, 0.62)), (-0.62, 3.35, (0.62, 0.7, 0.5)), (0.62, 3.35, (0.62, 0.7, 0.5))):
        p, _ = stick(rock, (px, -12, pz), (px, 0, pz))
        cut.append(sdf.ellipsoid(tuple(p + f32((0, 0.48, 0))), rr))
    for tx, tz, r in ((-1.45, 4.55, 0.4), (-0.55, 5.2, 0.43), (0.55, 5.2, 0.43), (1.45, 4.55, 0.4)):
        p, _ = stick(rock, (tx, -12, tz), (tx, 0, tz))
        cut.append(sdf.sphere(tuple(p + f32((0, r - 0.2, 0))), r))
    cutter = U(*cut)
    body = sdf.smooth_subtract(rock, cutter, k=0.12)
    base = stone_paint(13, pal=("#A7A095", "#D5CEC0", "#6A655E"))

    def paint(P, N):
        c = base(P, N)
        m = sst(0.12, 0.0, cutter[0](P))
        return lerp(c, C("#6E675F"), m * 0.8)
    rk = part(body, 0.07, 4200, paint)
    moss = part(moss_cap(rock, 7.0, wave=0.45, thick=0.1, seed=13), 0.07, 1600, tone(*MOSS, lift=0.6, sink=0.55, var=0.06, freq=1.0))
    return finish("Boulder_Big", [rk, moss], ao=(2.2, 0.55))


@asset("RootTunnel")
def root_tunnel():
    rx, ry, rz = 4.4, 3.6, 3.4

    def surf_z(x, y):
        return 0.1 + rz * math.sqrt(max(0.0, 1 - (x / rx) ** 2 - (y / ry) ** 2))
    mound = flat_bottom(sdf.noise_bumps(U(sdf.ellipsoid((0, 0, 0.1), (rx, ry, rz)), sdf.ellipsoid((0.8, 1.0, 1.5), (2.6, 2.2, 2.6)), k=0.5), 0.1, 0.9, seed=141))
    rng = np.random.default_rng(141)
    roots = []
    for psi, off, r in ((8, -1.0, 0.6), (-28, 1.1, 0.66), (62, 0.2, 0.55), (112, -1.6, 0.58), (140, 1.4, 0.52), (172, 0.3, 0.6), (32, 2.3, 0.5)):
        p = math.radians(psi)
        pts, rad = [], []
        for sv in np.linspace(-1.02, 1.02, 9):
            x = sv * rx * math.cos(p) - off * math.sin(p)
            y = sv * rx * math.sin(p) * (ry / rx) + off * math.cos(p) * 0.8
            z = surf_z(x, y) * 0.9 + r * 0.3 + rng.uniform(-0.12, 0.12)
            pts.append((x, y, max(z, r * 0.5)))
            rad.append(r * (1.3 - 0.5 * (1 - abs(sv) / 1.02)) * rng.uniform(0.85, 1.12))
        roots.append(chain(pts, rad, k=0.3))
    # a thick root arch framing the tiny door
    arch = chain([(-1.9, -3.2, 0.0), (-1.55, -3.55, 1.35), (-0.8, -3.8, 2.15), (0.0, -3.9, 2.35), (0.8, -3.8, 2.15), (1.55, -3.55, 1.35), (1.9, -3.2, 0.0)],
                 [0.7, 0.55, 0.5, 0.5, 0.5, 0.55, 0.7], k=0.2)
    stump = sdf.cylinder((0.5, 0.7, 4.0), 1.35, 1.25, rounding=0.3)
    jag = U(*[sdf.round_box((0.5 + 1.45 * math.cos(a), 0.7 + 1.45 * math.sin(a), 5.5), (0.7, 0.7, 0.6), 0.1, rot=(25, 0, math.degrees(a)))
              for a in (0.3, 1.9, 3.5, 5.0)])
    stump = sdf.smooth_subtract(stump, U(jag, sdf.cylinder((0.5, 0.7, 5.4), 0.8, 0.3)), k=0.15)

    def gnarl(P):
        Q = P.copy()
        Q[:, 0] += 0.14 * np.sin(P[:, 1] * 1.7 + P[:, 2] * 0.9)
        Q[:, 1] += 0.14 * np.sin(P[:, 2] * 1.5 + P[:, 0] * 1.1)
        Q[:, 2] += 0.1 * np.sin(P[:, 0] * 1.3 + P[:, 1] * 0.7)
        return Q
    wood = ridges(sdf.warp(U(*roots, stump, k=0.35), gnarl, pad=0.3), 0.05, 9, twist=0.35)
    wood = U(wood, ridges(arch, 0.04, 8, twist=0.5), k=0.3)
    tunnel = U(sdf.capsule((0, -7, 0.72), (0, 7, 0.72), 0.66), sdf.round_box((0, 0, 0.2), (0.66, 7, 0.52), 0.0))
    wood = flat_bottom(sdf.smooth_subtract(wood, tunnel, k=0.08))
    mound = sdf.smooth_subtract(mound, tunnel, k=0.08)

    def dark_hole(c, P):
        near = sst(0.95, 0.6, np.abs(P[:, 0])) * sst(1.6, 1.25, P[:, 2])
        deep = sst(3.7, 2.6, np.abs(P[:, 1]))
        return lerp(c, C(BLACK), near * (0.75 + 0.25 * deep))

    def wood_paint(P, N):
        return dark_hole(tone(*BARK, lift=0.6, sink=0.5, var=0.07, freq=0.9)(P, N), P)

    def mound_paint(P, N):
        c = lerp(tone(*DIRT, lift=0.3, sink=0.5, var=0.06)(P, N), tone(*MOSS, lift=0.5, sink=0.3, var=0.06)(P, N), sst(0.35, 0.7, N[:, 2]))
        return dark_hole(c, P)
    wd = part(wood, 0.06, 4200, wood_paint)
    md = part(mound, 0.07, 1300, mound_paint)
    shrooms_cap, shrooms_stem = [], []
    both = U(wood, mound)
    for x, y in ((2.3, -2.0), (-2.7, -1.4), (-1.2, 2.5), (2.9, 1.2)):
        p, n = stick(both, (x, y, 12), (x, y, 0))
        if p is None:
            continue
        shrooms_stem.append(sdf.round_cone(tuple(p - f32((0, 0, 0.1))), tuple(p + f32((0, 0, 0.4))), 0.14, 0.1))
        shrooms_cap.append(sdf.smooth_subtract(sdf.ellipsoid(tuple(p + f32((0, 0, 0.5))), (0.42, 0.42, 0.28)), sdf.ellipsoid(tuple(p + f32((0, 0, 0.32))), (0.37, 0.37, 0.16)), k=0.03))
    caps = part(U(*shrooms_cap), 0.02, 500, tone("#F08A3C", "#FFC07A", "#B45A20", lift=0.5, sink=0.2, var=0))
    stems = part(U(*shrooms_stem), 0.02, 200, flat("#F3E7D2"))
    return finish("RootTunnel", [wd, md, caps, stems], ao=(2.0, 0.55))


@asset("DarkHollow")
def dark_hollow():
    hill = U(sdf.ellipsoid((0, 1.2, 0), (6.6, 5.8, 6.6)), sdf.sphere((-3.5, 2.2, 1.8), 3.6), sdf.sphere((3.6, 2.4, 1.5), 3.4),
             sdf.sphere((1.2, 3.5, 4.0), 3.0), k=1.0)
    hill = flat_bottom(sdf.noise_bumps(hill, 0.16, 0.5, seed=151))
    cave = sdf.smooth_intersect(sdf.ellipsoid((0, -3.8, 1.2), (2.55, 6.0, 3.35)), (lambda P: 0.12 - P[:, 2], sdf.ellipsoid((0, -3.8, 1.2), (2.55, 6.0, 3.35))[1]), k=0.1)
    stones = []
    rng = np.random.default_rng(151)
    for a_deg, sz in ((0, 1.45), (32, 1.25), (62, 1.3), (90, 1.5), (118, 1.3), (148, 1.25), (180, 1.45)):
        a = math.radians(a_deg)
        x, z = 3.25 * math.cos(a), 0.6 + 3.9 * math.sin(a)
        p, _ = stick(hill, (x, -15, z), (x, 5, z))
        y = (p[1] if p is not None else -5.5) + 0.35
        stones.append(sdf.ellipsoid((x, y, z), (sz * rng.uniform(0.9, 1.1), sz * 0.85, sz * rng.uniform(0.8, 1.0)), rot=(0, a_deg + rng.uniform(-15, 15), 0)))
    rocks = flat_bottom(sdf.noise_bumps(U(*stones, k=0.25), 0.06, 1.5, seed=152))
    hill_c = sdf.smooth_subtract(hill, cave, k=0.3)
    rocks_c = sdf.smooth_subtract(rocks, cave, k=0.15)

    def darken(c, P):
        near = sst(0.5, -0.1, cave[0](P))
        deep = sst(-6.3, -3.8, P[:, 1])
        return lerp(c, C(BLACK), near * (0.35 + 0.65 * deep))

    def hill_paint(P, N):
        c = lerp(tone(*DIRT, lift=0.3, sink=0.5, var=0.07, freq=0.7)(P, N), tone(*GRASS, lift=0.6, sink=0.3, var=0.06, freq=0.6)(P, N),
                 sst(0.3, 0.65, N[:, 2]) * sst(0.6, 1.4, P[:, 2]))
        return darken(c, P)

    def rock_paint(P, N):
        return darken(stone_paint(15)(P, N), P)
    h = part(hill_c, 0.08, 4000, hill_paint)
    r = part(rocks_c, 0.05, 2000, rock_paint)
    tufts = []
    for bx, by, br in ((-4.2, 1.8, 1.2), (3.6, 3.2, 1.0), (-1.2, 4.6, 0.9)):
        p, _ = stick(hill, (bx, by, 14), (bx, by, 0))
        if p is not None:
            c0 = p + f32((0, 0, br * 0.35))
            tufts += [sdf.sphere(tuple(c0), br), sdf.sphere(tuple(c0 + f32((br * 0.7, 0.2, -br * 0.25))), br * 0.7),
                      sdf.sphere(tuple(c0 + f32((-br * 0.65, -0.2, -br * 0.3))), br * 0.65)]
    bushes = part(sdf.noise_bumps(U(*tufts, k=0.3), 0.04, 2.0, seed=153), 0.05, 900, tone(*BUSH, lift=0.55, sink=0.6, var=0.05, freq=1.2))
    eyes = part(U(sdf.ellipsoid((-0.42, 2.02, 1.5), (0.16, 0.12, 0.24)), sdf.ellipsoid((0.42, 2.02, 1.5), (0.16, 0.12, 0.24))), 0.02, 160,
                flat("#FFE98A"), glow=True)
    return finish("DarkHollow", [h, r, bushes, eyes], ao=(2.4, 0.6), samples=24)


@asset("VineWall")
def vine_wall():
    slabs = U(sdf.round_box((0, 0, 2.25), (3.2, 2.6, 2.3), 1.1, rot=(0, 0, 5)),
              sdf.round_box((0.3, 0.2, 6.3), (2.8, 2.3, 2.1), 1.0, rot=(0, 0, -8)),
              sdf.round_box((-0.2, 0.1, 10.0), (2.5, 2.1, 2.0), 0.95, rot=(0, 0, 12)),
              sdf.round_box((0.2, 0.0, 12.9), (2.05, 1.8, 1.2), 0.8, rot=(0, 0, -4)), k=0.3)
    pillar = flat_bottom(sdf.noise_bumps(sdf.noise_bumps(slabs, 0.1, 0.7, seed=161), 0.05, 1.6, seed=162))
    rk = part(pillar, 0.07, 3200, tone("#A09A91", "#D2CCBF", "#65605A", lift=0.55, sink=0.55, bottom=(0, 2, 0.15), var=0.08, freq=0.8, seed=16))
    grass = part(moss_cap(pillar, 13.3, wave=0.25, thick=0.1, seed=16), 0.06, 900, tone(*GRASS, lift=0.6, sink=0.5, var=0.05))

    def on_face(x, z, out=0.05):
        p, _ = stick(pillar, (x, -12, z), (x, 5, z))
        return None if p is None else (float(p[0]), float(p[1]) - out, float(p[2]))
    vines, leaves = [], []
    rails = {}
    for side, ph in ((-1, 0.0), (1, 2.0)):
        pts = [on_face(side * 1.35 + 0.35 * math.sin(z * 0.9 + ph), z, out=0.02) for z in np.linspace(0.0, 13.2, 15)]
        pts = [p for p in pts if p]
        rails[side] = pts
        vines.append(chain(pts, [0.24] + [0.2] * (len(pts) - 2) + [0.14], k=0.08))
    for zr in (1.9, 4.3, 6.7, 9.1, 11.5):
        pts = []
        for t in np.linspace(0, 1, 5):
            x = -1.35 + 2.7 * t
            z = zr - 0.3 * math.sin(math.pi * t)
            q = on_face(x, z, out=0.0)
            if q:
                pts.append(q)
        vines.append(chain(pts, [0.15] * len(pts), k=0.06))
    leaf_local = U(sdf.ellipsoid((0, 0.55, 0), (0.48, 0.62, 0.07)), sdf.ellipsoid((0, 0.95, 0), (0.25, 0.35, 0.065)), k=0.2)

    def cup(P):
        Q = P.copy()
        Q[:, 2] -= 0.18 * (Q[:, 0] / 0.5) ** 2
        return Q
    leaf_local = sdf.warp(leaf_local, cup, pad=0.3)
    rng = np.random.default_rng(163)
    for side in (-1, 1):
        for i, p in enumerate(rails[side][1:-1]):
            if i % 1:
                continue
            lat = side if i % 2 == 0 else -side
            n = f32((lat * 0.35, -1.0, 0.25))
            n /= np.linalg.norm(n)
            up = f32((lat * 0.9, 0.0, 0.45))
            ydir = up - n * float(up @ n)
            ydir /= np.linalg.norm(ydir)
            xdir = np.cross(ydir, n)
            R = np.stack([xdir, ydir, n], axis=1)
            s = rng.uniform(0.9, 1.25)
            leaves.append(_scaled(leaf_local, f32(p) + f32((0, -0.12, 0)), R, s))
    vn = part(U(*vines, k=0.05), 0.04, 1600, tone("#4E9A3A", "#8CC45C", "#2F6A2C", lift=0.45, sink=0.45, var=0.05, freq=1.2))
    lv = part(U(*leaves, k=0.02), 0.03, 2000, tone("#62BC45", "#B4E36C", "#347A34", lift=0.55, sink=0.5, var=0.05, freq=1.0, seed=3))
    return finish("VineWall", [rk, grass, vn, lv], ao=(1.8, 0.55), samples=24)


# ═══ BUDGETS ══════════════════════════════════════════════════════════════════

LARGE = {"Tree_Puffy_A", "Tree_Puffy_B", "Tree_Puffy_C", "Tree_Pine_A", "Tree_Pine_B", "Tree_Fruit", "Shack", "Well", "Bridge_Wood",
         "Boulder_Big", "RootTunnel", "DarkHollow", "VineWall"}
MEDIUM = {"Rock_Medium_A", "Rock_Medium_B", "Log_A", "Stump_A", "Fence_Straight", "Gate_Picket", "Bench_Wood", "Lantern_Post",
          "Bush_A", "Bush_B", "Bush_C", "Signpost", "Mailbox", "Hay_Bale", "Birdhouse_Post"}


def budget(name):
    return 8000 if name in LARGE else 3500 if name in MEDIUM else 1500


# ═══ PREVIEW RENDERING ════════════════════════════════════════════════════════

def _render_settings(samples=24):
    fk.preview_studio()
    sc = bpy.context.scene
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    # famkit's studio is tuned for white creature bodies and blows out real colours;
    # -1 EV puts a fully lit surface back at roughly its painted albedo.
    sc.view_settings.exposure = -1.0
    return sc


def _label(cam):
    cu = bpy.data.curves.new("_label", "FONT")
    cu.align_x = "CENTER"
    cu.size = 0.042
    ob = bpy.data.objects.new("_label", cu)
    fk.link(ob)
    ob.parent = cam
    ob.location = (0, -0.335, -1.0)
    mat = bpy.data.materials.new("_labelmat")
    mat.use_nodes = True
    nt = mat.node_tree
    for nd in list(nt.nodes):
        if nd.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(nd)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (0.03, 0.035, 0.05, 1)
    out = next(nd for nd in nt.nodes if nd.type == "OUTPUT_MATERIAL")
    nt.links.new(em.outputs[0], out.inputs[0])
    cu.materials.append(mat)
    try:
        ob.visible_shadow = False
    except Exception:
        pass
    return ob


def _capsule():
    o = bpy.data.objects.get("_Capsule5")
    if o:
        return o
    o = sdf.to_mesh("_Capsule5", sdf.capsule((0, 0, 1.0), (0, 0, 4.0), 1.0), voxel=0.08)
    o = fk.decimate_to(o, 800)
    vpaint(o, tone("#8FA6C9", "#C9D6EA", "#5A6E8F", var=0))
    fk.preview_tint(o, (1, 1, 1))
    o.name = "_Capsule5"
    return o


def _load_px(path, w, h):
    img = bpy.data.images.load(path, check_existing=False)
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)


def _save_px(arr, path):
    h, w = arr.shape[:2]
    out = bpy.data.images.new("_sheet", width=w, height=h, alpha=True)
    out.pixels.foreach_set(arr.astype(np.float32).ravel())
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)


def render_tiles(objs, cols, tile, yaw=-32, pitch=16, capsule=False, labels=None):
    sc = _render_settings()
    cam = fk.look_setup((0, 0, 1), 10)
    lbl = _label(cam)
    cap = _capsule() if capsule else None
    for o in objs:
        fk.preview_tint(o, (1, 1, 1))
        o.hide_render = True
    if cap:
        cap.hide_render = True
    rows = (len(objs) + cols - 1) // cols
    sheet = np.ones((rows * tile, cols * tile, 4), np.float32)
    tmp = os.path.join(SCRATCH, "_meadow_tile.png")
    for i, o in enumerate(objs):
        o.hide_render = False
        bb = np.array([list(v) for v in o.bound_box], np.float32)
        lo, hi = bb.min(0), bb.max(0)
        if cap:
            off = hi[0] + 1.3
            cap.location = (off, 0, 0)
            cap.hide_render = False
            hi = np.maximum(hi, f32((off + 1.0, 1.0, 5.0)))
            lo = np.minimum(lo, f32((off - 1.0, -1.0, 0.0)))
        c = (lo + hi) * 0.5
        rad = float(np.linalg.norm(hi - lo)) * 0.5
        c[2] -= rad * 0.06
        fk.look_setup(tuple(c), max(rad * 2.95, 2.0), yaw=yaw, pitch=pitch, lens=50)
        cam.data.clip_start = 0.05
        lbl.data.body = (labels or {}).get(o.name) or f"{o.name}  {fk.triangle_count(o)}"
        fk.render_png(tmp, res=(tile, tile))
        px = _load_px(tmp, tile, tile)
        r, cidx = divmod(i, cols)
        y0 = (rows - 1 - r) * tile
        sheet[y0:y0 + tile, cidx * tile:(cidx + 1) * tile] = px
        o.hide_render = True
        if cap:
            cap.hide_render = True
    for o in objs:
        o.hide_render = False
    bpy.data.objects.remove(lbl, do_unlink=True)
    if os.path.exists(tmp):
        os.remove(tmp)
    return sheet


# Backyard vignette: (asset, x, y, rot_z)
LAYOUT = [
    ("Shack", 0, 5, 0), ("Tree_Fruit", 9.5, 9, 20), ("Tree_Puffy_A", -24, 14, 0), ("Tree_Pine_A", 20, 18, 0),
    ("Tree_Puffy_B", -27, -2, 40), ("Tree_Pine_B", 28, 6, 0), ("Tree_Puffy_C", -38, 30, 0), ("Tree_Pine_A", 40, 30, 60),
    ("Fence_Post", -16, 13, 0), ("Fence_Straight", -12, 13, 0), ("Fence_Post", -8, 13, 0), ("Fence_Straight", -4, 13, 0),
    ("Fence_Post", 0, 13, 0), ("Gate_Picket", 4, 13, 0), ("Fence_Post", 8, 13, 0), ("Fence_Straight", 12, 13, 0), ("Fence_Post", 16, 13, 0),
    ("Fence_Straight", -16, 9, 90), ("Fence_Post", -16, 5, 0), ("Fence_Straight", -16, 1, 90), ("Fence_Post", -16, -3, 0),
    ("Bush_A", -5.5, 3.5, 0), ("Bush_B", 5.8, 3.2, 0), ("Bush_C", -12, 9, 10), ("Bush_A", 13, 8, 70),
    ("FlowerPatch_Yellow", -3.2, -1.5, 0), ("FlowerPatch_Pink", 3.6, -1.2, 40), ("FlowerPatch_Blue", -8, -0.5, 0),
    ("FlowerPatch_White", 7.5, -3.5, 0), ("FlowerPatch_Yellow", -12.5, -4, 80), ("FlowerPatch_Pink", 11, 3, 0),
    ("GrassTuft_A", -1.5, -4, 0), ("GrassTuft_B", 2, -5, 30), ("GrassTuft_A", -6, -6, 50), ("GrassTuft_B", 5.5, -0.5, 0),
    ("GrassTuft_A", 9.5, -7, 0), ("GrassTuft_B", -10, 3, 0), ("GrassTuft_A", 0.5, 1.2, 0), ("GrassTuft_B", -14, -8, 0),
    ("Mushroom_Red", -4.5, -7.5, 0), ("Mushroom_Red", 12.5, 4.5, 60),
    ("Mailbox", -7.5, -8, 0), ("Signpost", 5.5, -9, -10), ("Lantern_Post", -3.8, 1.5, 0), ("Hay_Bale", 9, 1, 25),
    ("Well", -10.5, 4, 0), ("Bench_Wood", 13, -2, -20), ("Birdhouse_Post", 14, 9, 0), ("Stump_A", 3.2, -12, 0),
    ("Log_A", -12, -12, 15), ("Rock_Small_A", -1, -10, 0), ("Rock_Small_B", 8, -11, 0), ("Rock_Medium_A", 18, -4, 0),
    ("Rock_Medium_B", -19, -2, 30),
    ("Bridge_Wood", 21, -16, 90), ("Reeds", 16, -13, 0), ("LilyPad", 22, -10, 0), ("LilyPad", 19.5, -19, 50),
    ("PondRim_Stone", 14, -17, 0), ("PondRim_Stone", 17, -21, 30),
    ("Boulder_Big", -24, 34, 0), ("RootTunnel", -8, 38, 0), ("DarkHollow", 9, 40, 0), ("VineWall", 26, 36, -10),
]


def render_vignette(objs, path_or_none, w=1400, h=620, capsule=True):
    sc = _render_settings(samples=32)
    by = {o.name: o for o in objs}
    temp = []
    for o in objs:
        fk.preview_tint(o, (1, 1, 1))
        o.hide_render = True
    for name, x, y, rz in LAYOUT:
        src = by.get(name)
        if not src:
            continue
        d = bpy.data.objects.new("_v_" + name, src.data)
        fk.link(d)
        d.location = (x, y, 0)
        d.rotation_euler = (0, 0, math.radians(rz))
        temp.append(d)
    if capsule:
        cap = _capsule()
        cap.location = (1.2, -4.5, 0)
        cap.hide_render = False
    # pond + grass ground
    floor = bpy.data.objects["PreviewFloor"]
    floor.scale = (4, 4, 1)
    fm = floor.data.materials[0]
    bsdf = next(n for n in fm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    old = tuple(bsdf.inputs["Base Color"].default_value)
    bsdf.inputs["Base Color"].default_value = (0.22, 0.5, 0.1, 1)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=7.5)
    pond = fk.mesh_object("_pond", bm)
    pond.location = (19.5, -15.5, 0.03)
    pond.scale = (1.0, 0.8, 1)
    pm = bpy.data.materials.new("_pondmat")
    pm.use_nodes = True
    pb = next(n for n in pm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    pb.inputs["Base Color"].default_value = (0.1, 0.36, 0.62, 1)
    pb.inputs["Roughness"].default_value = 0.15
    pond.data.materials.append(pm)
    temp.append(pond)
    cam = fk.look_setup((1.0, 13.0, 3.0), 70.0, yaw=-8, pitch=24, lens=30)
    cam.data.clip_end = 400
    tmp = os.path.join(SCRATCH, "_meadow_vig.png")
    fk.render_png(tmp, res=(w, h))
    px = _load_px(tmp, w, h)
    os.remove(tmp)
    for d in temp:
        bpy.data.objects.remove(d, do_unlink=True)
    if capsule:
        cap.hide_render = True
    floor.scale = (1, 1, 1)
    bsdf.inputs["Base Color"].default_value = old
    for o in objs:
        o.hide_render = False
    if path_or_none:
        _save_px(px, path_or_none)
    return px


# ═══ MAIN ═════════════════════════════════════════════════════════════════════

def build(names):
    objs = []
    for n in names:
        t = time.time()
        o = ASSETS[n]()
        assert o.name == n, (o.name, n)
        tris = fk.triangle_count(o)
        flag = "" if tris <= budget(n) else f"  OVER BUDGET ({budget(n)})"
        lo = np.array([list(v) for v in o.bound_box]).min(0)
        hi = np.array([list(v) for v in o.bound_box]).max(0)
        dims = hi - lo
        print(f"[meadow] {n:20s} tris={tris:5d} size=({dims[0]:.2f},{dims[1]:.2f},{dims[2]:.2f}) minz={lo[2]:.3f} {time.time() - t:.1f}s{flag}", flush=True)
        objs.append(o)
    return objs


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--sheet", default="")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--tile", type=int, default=340)
    ap.add_argument("--capsule", action="store_true")
    ap.add_argument("--vignette", default="")
    ap.add_argument("--yaw", type=float, default=-32)
    ap.add_argument("--pitch", type=float, default=16)
    args = ap.parse_args(argv)

    names = [n.strip() for n in args.only.split(",") if n.strip() and n.strip() != "ALL"] or list(ASSETS)
    objs = build(names)

    if args.sheet:
        _save_px(render_tiles(objs, args.cols, args.tile, yaw=args.yaw, pitch=args.pitch, capsule=args.capsule), args.sheet)
        print("[meadow] sheet", args.sheet)
    if args.vignette:
        render_vignette(objs, args.vignette)
        print("[meadow] vignette", args.vignette)

    if not args.only:
        cols, tile = 7, 200
        ref = _capsule()
        grid = render_tiles(objs + [ref], cols, tile, labels={"_Capsule5": "scale: 5-stud avatar"})
        ref.hide_render = True
        vig = render_vignette(objs, None, w=cols * tile, h=640)
        sheet = np.concatenate([grid, vig], axis=0)  # row 0 is the bottom: grid below the vignette
        os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
        _save_px(sheet, PREVIEW)
        for o in objs:
            o.data.materials.clear()
        for o in list(bpy.data.objects):
            if o not in objs and o.type == "MESH":
                bpy.data.objects.remove(o, do_unlink=True)
        path = fk.export_fbx(objs, FBX_NAME)
        total = sum(fk.triangle_count(o) for o in objs)
        print(f"[meadow] exported {path} ({len(objs)} objects, {total} tris); preview {PREVIEW}")


main()
