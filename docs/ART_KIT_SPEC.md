# Art Kit Spec — static world meshes (environment, structures, ingredient props)

Creatures are done (tools/blender/creatures.py). This spec is for everything that does NOT
animate: world kits and ingredient pickups. Every kit must look like ONE game.

## Pipeline (headless, reproducible)

```
tools/blender/kit_<name>.py   -- the generator. Re-running it rebuilds the kit exactly.
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P tools/blender/kit_<name>.py
  -> art/build/kit_<name>.fbx          (all meshes of the kit, one FBX)
  -> art/previews/kit_<name>.png       (contact sheet you LOOKED at and are happy with)
```

Start every script with:

```python
import sys; sys.path.insert(0, "/Users/malik/rob/tools/blender")
import bpy, bmesh, math, numpy as np
from mathutils import Vector
import famkit as fk, sdf
fk.reset_scene()
```

Use the helpers, do not edit them (other work depends on them). If you need a helper, put it
in your own kit script.

- `sdf.py` — signed-distance modelling: `sphere ellipsoid round_cone capsule round_box torus
  cylinder`, `smooth_union(*shapes, k=)`, `smooth_subtract`, `smooth_intersect`, `warp`,
  `mirror_x`, `noise_bumps`, then `sdf.to_mesh(name, shape, voxel=)`. This is how the
  creatures got their soft sculpted look. Voxel 0.02–0.06 depending on size.
- `famkit.py` — `decimate_to(obj, tris)`, `paint(obj, fn(co, normal)->rgb)`, `solid_color`,
  `bake_ao(obj, floor_z=0, samples, distance, strength)`, `box_uv(obj, 2.0)`, `uv_sphere`,
  `tube(points, radii)`, `join(objs, name)`, `transform(obj, loc, rot, scale)`,
  `shade_flat/shade_smooth`, `export_fbx(objs, "kit_<name>.fbx")`,
  `preview_tint(obj, (1,1,1))` (shows vertex colours in renders), `preview_studio()`,
  `render_views(path, target, distance, views=((yaw,pitch),...), res, lens)`.

## Hard rules (the Roblox importer and world builder depend on these)

1. **One object per asset, named exactly as listed** in your kit list. No suffixes (`.001`).
2. **Origin convention:** build each asset centred on X/Y with its **base at Z = 0**, standing
   upright (Z up). Leave every object at location (0,0,0) with no rotation/scale — bake
   transforms into the mesh. Overlapping at the origin in the FBX is expected.
3. **Units:** 1 Blender unit = 1 Roblox stud. Z up. "Front" of an asset faces −Y.
   Scale anchors: a Roblox avatar is ~5 studs tall; a baby creature ~1.5; a grown ~3;
   a door ~7. Trees 10–18. Ingredient pickups 0.8–2.5.
4. **Colour lives in vertex colours**, real final sRGB colours (the part is tinted white).
   Paint with `fk.paint` / `fk.solid_color`, then `fk.bake_ao` for soft contact shading.
   No materials/textures in the FBX (strip them: `obj.data.materials.clear()`).
5. **Triangle budgets** (hard caps): pickup ≤ 900 · small prop ≤ 1,500 · medium ≤ 3,500 ·
   large/landmark ≤ 8,000. Roblox mobile matters. Use `fk.decimate_to`.
6. Run `fk.box_uv(obj, 2.0)` on every mesh (lets Roblox materials tile later).
7. Do **not** upload, do **not** touch Roblox Studio, do **not** modify files outside your kit
   script / FBX / preview. The disk is nearly full: delete scratch files you create; keep
   previews ≤ 1400 px wide.

## Style — this is the part that matters

- **Soft, chunky, stylized, readable.** Rounded forms from SDF smooth unions, generous
  bevels, no thin fiddly detail, no noise soup. Pikmin / Animal Crossing / Kirby's world, not
  realism, not blocky voxels, not flat-shaded low-poly facets (except crystals/metal edges).
- **Saturated natural palette, NOT neon vomit** (SPEC §40). Greens lean yellow-green, woods
  warm, stones warm-grey or blue-grey, metal desaturated with rust accents. Glow only where
  the object glows (crystals, glowworms, star fragments).
- **Two-to-three tone paint jobs:** base colour, a lighter top/highlight gradient (fake sky
  light: lerp toward lighter as normal.z rises), a darker underside, then AO. Small accents
  (a stripe, spots, a label) for charm.
- **Silhouette first.** Every asset must read at thumbnail size from 60 studs away.
- **Funny before cool** (SPEC §41): a slightly squashed, cheerful proportion beats accuracy.
- Food and objects should look *delicious / tactile* — the whole game is "can I feed THAT?"

## Process

1. Build a few assets, render a contact sheet, **look at it** (Read the PNG), fix what looks
   wrong, repeat. Check scale against a 5-stud reference capsule in at least one render.
2. When the whole kit is done, render a final contact sheet to `art/previews/kit_<name>.png`
   showing every asset labelled or in list order, export the FBX, and report back:
   the FBX path, the exact list of object names, triangle counts, and anything you are
   unsure about.
