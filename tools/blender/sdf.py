"""sdf — signed-distance modelling for soft, sculpted-looking creature forms.

Why not metaballs: metaball blends are not controllable (head + body came out as a
snowman). Here every primitive's radius is its real surface, and each union declares its
own blend width `k`, so "cheeks melt into the face" is a number.

Pipeline: numpy SDF on a voxel grid -> OpenVDB grid (bundled with Blender) -> Volume to
Mesh -> clean mesh object.

    import sdf
    s = sdf.Scene()
    body = s.ellipsoid((0,0,1), (1,1.1,0.8))
    head = s.sphere((0,-0.7,1.7), 0.95)
    shape = sdf.smooth_union(body, head, k=0.5)
    obj = sdf.to_mesh("Body", shape, voxel=0.03)
"""

import math
import os
import tempfile

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector


# A shape is (fn, bounds): fn(P: (N,3) float32) -> (N,) distances; bounds = (min xyz, max xyz)

def _rot_matrix(rot_deg):
    if not rot_deg or all(a == 0 for a in rot_deg):
        return None
    m = Euler([math.radians(a) for a in rot_deg]).to_matrix()
    return np.array(m, dtype=np.float32)


def _local(P, center, rot):
    Q = P - np.asarray(center, dtype=np.float32)
    if rot is not None:
        Q = Q @ rot  # row vectors: multiply by R to apply R^T (world -> local)
    return Q


def _bounds_box(center, half):
    c = np.asarray(center, dtype=np.float32)
    h = np.asarray(half, dtype=np.float32)
    return (c - h, c + h)


def sphere(center, r):
    c = np.asarray(center, dtype=np.float32)
    return (lambda P: np.linalg.norm(P - c, axis=1) - r, _bounds_box(center, (r, r, r)))


def ellipsoid(center, radii, rot=None):
    R = _rot_matrix(rot)
    rad = np.asarray(radii, dtype=np.float32)

    def fn(P):
        Q = _local(P, center, R)
        k0 = np.linalg.norm(Q / rad, axis=1)
        k1 = np.linalg.norm(Q / (rad * rad), axis=1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)

    m = float(max(radii))
    return (fn, _bounds_box(center, (m, m, m)))


def round_cone(a, b, ra, rb):
    """Capsule with different radii at each end. Limbs, necks, horns, tails."""
    A = np.asarray(a, dtype=np.float32)
    B = np.asarray(b, dtype=np.float32)
    ba = B - A
    l2 = float(ba @ ba)
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2

    def fn(P):
        pa = P - A
        y = pa @ ba
        z = y - l2
        xv = pa * l2 - np.outer(y, ba)
        x2 = np.sum(xv * xv, axis=1)
        y2 = y * y * l2
        z2 = z * z * l2
        k = math.copysign(1.0, rr) * rr * rr * x2
        out = np.empty(len(P), dtype=np.float32)
        c1 = np.sign(z) * a2 * z2 > k
        c2 = np.sign(y) * a2 * y2 < k
        c3 = ~(c1 | c2)
        out[c1] = np.sqrt(x2[c1] + z2[c1]) * il2 - rb
        out[c2 & ~c1] = np.sqrt(x2[c2 & ~c1] + y2[c2 & ~c1]) * il2 - ra
        out[c3] = (np.sqrt(x2[c3] * a2 * il2) + y[c3] * rr) * il2 - ra
        return out

    lo = np.minimum(A - ra, B - rb)
    hi = np.maximum(A + ra, B + rb)
    return (fn, (lo, hi))


def capsule(a, b, r):
    return round_cone(a, b, r, r)


def round_box(center, half, radius, rot=None):
    R = _rot_matrix(rot)
    h = np.asarray(half, dtype=np.float32) - radius

    def fn(P):
        Q = np.abs(_local(P, center, R)) - h
        outside = np.linalg.norm(np.maximum(Q, 0.0), axis=1)
        inside = np.minimum(np.max(Q, axis=1), 0.0)
        return outside + inside - radius

    m = float(np.linalg.norm(half))
    return (fn, _bounds_box(center, (m, m, m)))


def torus(center, major, minor, rot=None):
    R = _rot_matrix(rot)

    def fn(P):
        Q = _local(P, center, R)
        qx = np.linalg.norm(Q[:, [0, 1]], axis=1) - major
        return np.sqrt(qx * qx + Q[:, 2] ** 2) - minor

    m = major + minor
    return (fn, _bounds_box(center, (m, m, minor)))


def cylinder(center, radius, half_height, rot=None, rounding=0.0):
    R = _rot_matrix(rot)

    def fn(P):
        Q = _local(P, center, R)
        d0 = np.linalg.norm(Q[:, [0, 1]], axis=1) - (radius - rounding)
        d1 = np.abs(Q[:, 2]) - (half_height - rounding)
        outside = np.sqrt(np.maximum(d0, 0) ** 2 + np.maximum(d1, 0) ** 2)
        inside = np.minimum(np.maximum(d0, d1), 0.0)
        return outside + inside - rounding

    m = max(radius, half_height)
    return (fn, _bounds_box(center, (m, m, m)))


# ── combinators ──────────────────────────────────────────────────────────────

def _merge_bounds(*bs):
    lo = np.min(np.stack([b[0] for b in bs]), axis=0)
    hi = np.max(np.stack([b[1] for b in bs]), axis=0)
    return (lo, hi)


def smooth_union(*shapes, k=0.3):
    def fn(P):
        d = shapes[0][0](P)
        for s in shapes[1:]:
            e = s[0](P)
            if k <= 0:
                d = np.minimum(d, e)
            else:
                h = np.maximum(k - np.abs(d - e), 0.0) / k
                d = np.minimum(d, e) - h * h * k * 0.25
        return d

    return (fn, _merge_bounds(*[s[1] for s in shapes]))


def union(*shapes):
    return smooth_union(*shapes, k=0.0)


def smooth_subtract(base, cutter, k=0.1):
    def fn(P):
        a = base[0](P)
        b = -cutter[0](P)
        if k <= 0:
            return np.maximum(a, b)
        h = np.maximum(k - np.abs(a - b), 0.0) / k
        return np.maximum(a, b) + h * h * k * 0.25

    return (fn, base[1])


def smooth_intersect(a, b, k=0.1):
    def fn(P):
        x = a[0](P)
        y = b[0](P)
        if k <= 0:
            return np.maximum(x, y)
        h = np.maximum(k - np.abs(x - y), 0.0) / k
        return np.maximum(x, y) + h * h * k * 0.25

    return (fn, _merge_bounds(a[1], b[1]))


def offset(shape, amount):
    return (lambda P: shape[0](P) - amount, (shape[1][0] - amount, shape[1][1] + amount))


def warp(shape, fn_points, pad=0.3):
    """Domain warp: evaluate `shape` at fn_points(P). Bends, twists, lumps."""
    return (lambda P: shape[0](fn_points(P)), (shape[1][0] - pad, shape[1][1] + pad))


def mirror_x(shape):
    def fn(P):
        Q = P.copy()
        Q[:, 0] = np.abs(Q[:, 0])
        return shape[0](Q)

    lo, hi = shape[1]
    m = max(abs(lo[0]), abs(hi[0]))
    return (fn, (np.array([-m, lo[1], lo[2]], dtype=np.float32), np.array([m, hi[1], hi[2]], dtype=np.float32)))


def noise_bumps(shape, amplitude=0.02, frequency=6.0, seed=1):
    rng = np.random.default_rng(seed)
    phases = rng.uniform(0, 6.28, size=9).astype(np.float32)

    def fn(P):
        n = (np.sin(P[:, 0] * frequency + phases[0]) * np.sin(P[:, 1] * frequency * 1.13 + phases[1])
             * np.sin(P[:, 2] * frequency * 0.91 + phases[2]))
        return shape[0](P) + n * amplitude

    return (fn, shape[1])


# ── meshing ──────────────────────────────────────────────────────────────────

def evaluate(shape, voxel, pad=2):
    lo, hi = shape[1]
    lo = np.floor(lo / voxel - pad).astype(int)
    hi = np.ceil(hi / voxel + pad).astype(int)
    dims = hi - lo + 1
    ii, jj, kk = np.meshgrid(np.arange(dims[0]), np.arange(dims[1]), np.arange(dims[2]), indexing="ij")
    P = (np.stack([ii, jj, kk], axis=-1).reshape(-1, 3) + lo) * voxel
    P = P.astype(np.float32)
    D = np.empty(len(P), dtype=np.float32)
    chunk = 400_000
    for s in range(0, len(P), chunk):
        D[s:s + chunk] = shape[0](P[s:s + chunk])
    return D.reshape(tuple(dims)), lo


def to_mesh(name, shape, voxel=0.03, adaptivity=0.0):
    import openvdb as vdb

    D, lo = evaluate(shape, voxel)
    # Volume to Mesh keeps the region ABOVE the threshold, so store "inside-ness".
    grid = vdb.FloatGrid(background=-voxel * 3)
    grid.copyFromArray((-D).astype(np.float32), ijk=(int(lo[0]), int(lo[1]), int(lo[2])))
    grid.transform = vdb.createLinearTransform(voxelSize=voxel)
    grid.name = "density"
    grid.gridClass = vdb.GridClass.FOG_VOLUME
    # UNIQUE path per call: Blender caches volume grids by file path, so reusing a name
    # (Body__Blocky for two families) silently loads the previous family's geometry.
    import uuid
    path = os.path.join(tempfile.gettempdir(), f"fam_sdf_{uuid.uuid4().hex}.vdb")
    vdb.write(path, grids=[grid])

    vol = bpy.data.volumes.new(name + "_vol")
    vol.filepath = path
    vobj = bpy.data.objects.new(name + "_vobj", vol)
    bpy.context.scene.collection.objects.link(vobj)
    # Volume to Mesh lives on a MESH object and points at the volume object.
    carrier = bpy.data.objects.new(name + "_carrier", bpy.data.meshes.new(name + "_carrier"))
    bpy.context.scene.collection.objects.link(carrier)
    mod = carrier.modifiers.new("V2M", "VOLUME_TO_MESH")
    mod.object = vobj
    mod.grid_name = "density"
    mod.threshold = 0.0
    mod.adaptivity = adaptivity
    mod.resolution_mode = "GRID"
    mod.use_smooth_shade = True
    bpy.context.view_layer.update()

    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(carrier.evaluated_get(dg), depsgraph=dg)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    carrier_mesh = carrier.data
    bpy.data.objects.remove(carrier, do_unlink=True)
    bpy.data.meshes.remove(carrier_mesh)
    bpy.data.objects.remove(vobj, do_unlink=True)
    bpy.data.volumes.remove(vol)
    try:
        os.remove(path)
    except OSError:
        pass
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj
