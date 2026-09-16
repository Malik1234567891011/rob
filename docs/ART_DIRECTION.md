# Art Direction — the Blender pivot

**Status:** DIRECTION SET 2026-09-16, not yet implemented. This supersedes the
primitive-assembly approach in the current `CreatureBuilder`. Read before touching
creature geometry.

---

## The verdict on what currently exists

Current creatures are **Tier 1: Roblox primitives** — spheres, cylinders, wedges welded
together. That was a deliberate choice to prove the loop with zero asset dependencies,
and it did its job (the feeding→mutation→evolution loop is verified, 33/33). It is
**not shippable**, and the spec already said so:

- §42: *"A tree can look mediocre. The creature cannot."*
- §91 (failure mode #3): *"Procedural systems can produce sludge."*
- §40: silhouettes must be legible; Pixar-adjacent readability

So this is not a change of direction. It is the spec being enforced.

## The quality ladder

| Tier | Description | Verdict |
|---|---|---|
| 1 | Roblox primitives, visible seams, default materials/tweens | ❌ unacceptable — *"I'd rather delay the game"* |
| 2 | Custom low-poly meshes, cute proportions, simple bone rig, good silhouette | ⚠️ acceptable while proving the game |
| 3 | Blender meshes, organic topology, proper skinning, custom animation set, PBR, facial reactions, curated mutation modules, mobile-optimized | ✅ **ship target** |

**Target:** high-quality stylized Nintendo / mobile-game creature, rendered in Roblox.
**Not:** photorealistic UE5 fur. **Also not:** sphere + rectangles + horns.

Precedent: Creatures of Sonaria — modeled in Blender, boned, rigged, imported, animated,
modern materials. Roblox showcases this pipeline themselves. Studio is the **runtime
engine, not the sculpting program.**

## Pipeline

```
Blender:  sculpt → retopo → UV → texture → skeleton → weight paint → animation
   ↓ export (skinned mesh + armature)
Roblox:   import → bind to bones → SurfaceAppearance (PBR) → runtime assembly
```

## What Roblox actually supports (and we are not using)

- **Skinned meshes** — geometry deforms continuously around an internal skeleton, up to
  ~4 bone influences per vertex. No visible ball joints. Tails curve, bellies compress,
  necks bend, wing membranes move with bones.
- **SurfaceAppearance PBR** — colour, normal, roughness, metalness, emissive. The same
  mesh reads as skin, scales, metal, crystal.
- Target skeleton shape:

```
SpineRoot
 ├ Spine1 ├ Spine2 ├ Neck └ Head ├ EarL ├ EarR ├ Jaw ├ EyeL └ EyeR
 ├ Tail1 └ Tail2 └ Tail3 └ Tail4
 ├ LegFL / LegFR / LegBL / LegBR
```

## Materials become material, not tint

A mutation must change **surface response**, not `Body.Color`:

| Mutation | Now (wrong) | Target |
|---|---|---|
| Crystal | `Color = cyan` | glossy response, sharp geometry, roughness variation, normal detail, emissive markings |
| Metal | `Color = grey` | metalness ↑, roughness ↓ |
| Fungal | `Color = pink` | matte, bumpy normal map, soft cap geometry |
| Stone | `Color = grey` | rough, cracked normal texture |
| Slimy | `Color = green` | high-gloss response |

## Animation is the product, not decoration

> "Animation may actually be more important than geometry."

The game runs on attachment. A modest mesh that anticipates, shifts weight, looks at
things, blinks, breathes, squashes, overshoots and settles will read as 10× more expensive
than twice the polygons in T-pose.

**The feeding beat, fully authored:**
notices food → head snaps toward it → eyes widen → body leans → tail goes insane →
eyes TRACK the item as the player moves left/right → hops if held overhead →
**CHOMP** → cheeks bulge → swallow → satisfied wobble → *then* mutation.

Required set: idle/breathe, look-at-owner, eye-track-item, ear perk, run-to-owner, eat
(with jaw + cheek deform), sleep, pet reaction, evolution, stumble, celebrate,
creature-to-creature interaction.

## Architecture change: morph, don't accumulate

**The structural fix.** Do not stack accessories — a creature that goes aquatic must not
end up *wearing five hats*:

| | Bad (accumulate) | Good (morph) |
|---|---|---|
| Legs | add fins to existing legs | `BlobLeg_A` → `AquaticLeg_B` |
| Tail | add a tail fin | `RoundTail` → `FishTail` |
| Skin | add scales | `Soft` → `WetScaled` |
| Ears | add gills | `Floppy` → `FinEar` |

**The creature transforms. It does not accumulate hats.** Huge distinction.

## Archetypes + compatibility matrix, not unrestricted Lego

Unrestricted assembly is a procedural character-design problem, not a Roblox limitation:
*giant head + tiny body + mushroom back + antlers + wings + shell + long tail* = everything
clips into everything.

Each body family (Blob / Lizard / Beast) gets its **own** compatible part families.
Every component declares:

- attachment socket
- scale range
- rotation range
- compatible bodies
- exclusion rules
- blend area
- colour channels

`Blob + enormous dinosaur snout` is simply **not legal**. This looks restrictive and
actually *improves* perceived variety, because every generated creature looks
**intentionally designed**.

> The primitive unit becomes professional artwork, not a Roblox Part.

---

## What carries over unchanged (important)

The pivot is **contained to geometry**. These layers do not change at all:

- `Config/Traits`, `Config/Ingredients`, `Config/Mutations`, `Config/Progression`, `Config/Economy`
- `GeneticsService` three-layer influence model, `FeedingService`, `EvolutionService`
- `DiscoveryService`, `LineageService`, `OfflineService`, `AnalyticsService`
- FTUE timing, world, gates, UI, network layer

`Anatomy.parts[slot][variant]` already maps **slot → variant → geometry spec**. Swapping
`pieces = {primitives}` for `mesh = {assetId, socket, scaleRange, exclusions}` is a
contained change to `Anatomy.luau` + `CreatureBuilder.luau`. The compatibility system
(`Anatomy.banned`) already exists and just becomes richer.

**Mutations already declare `parts = { Back = "Wings" }`** — that is already a morph
instruction, not an accumulate instruction. The data model is closer to right than the
rendering is.

## ⚠️ Unsolved blocker — resolve BEFORE authoring meshes

**Getting a Blender mesh into Roblox programmatically.** Same class of problem as the
DataStore one: it will not work in an unpublished place, and it must be solved first or we
author 40 meshes we cannot import.

- The MCP Luau sandbox has **no network** (see `docs/DECISIONS.md`), so it cannot upload.
- Bash **does** have network — the OpenAI thumbnail calls worked from there.
- Therefore the likely path is **Roblox Open Cloud Assets API from Bash**, which needs:
  - a Roblox Open Cloud **API key with asset write scope**
  - the **creator/group ID**
  - confirmation that skinned-mesh upload is supported for that asset type
- Fallback: Studio's 3D Importer, which is GUI-driven and manual.

**Do not author a mesh library until one upload round-trips end to end.**

---

## ⚡ Discovery 2026-09-16: Roblox has native AI mesh generation

While setting up the Blender MCP I found the Roblox Studio MCP already exposes:

- `generate_mesh` — **"Generates a textured mesh from a prompt using AI."** Takes a text
  prompt, a bounding-box size, `maxTriangles` (12–20,000), and **`partNames` +
  `segmentation: "explicit"`** to split the result into up to 8 named parts.
- `segment_mesh` — split an existing MeshPart/Model into up to 5 named sub-parts
- `generate_procedural_model` — parametric model with user-editable attributes
- `generate_material` / `generate_texture` — PBR material and texture generation
- `store_image` / `upload_image` — asset upload path

**Why this matters enormously:** it sidesteps the upload blocker flagged above. These
generate assets *inside the place*, so there is no Open Cloud API key, no manual 3D
Importer, no arm64/Rosetta build chain. The MCP sandbox's lack of network does not apply.

`generate_mesh(partNames = "head, body, tail")` is almost exactly the modular-slot system
this game needs, and `generate_material` maps directly onto the "materials become material,
not tint" requirement.

**This does not replace Blender for Tier 3.** Hand-authored topology, deliberate edge flow,
proper weight painting and a custom animation set will still beat prompt-generated
geometry. But it very plausibly gets us to **solid Tier 2 in hours instead of days**, and —
more importantly — it lets us prove the *whole assembly + morph + material pipeline*
end to end before investing in a hand-authored mesh library.

**Recommended order of attack:**
1. `generate_mesh` one creature body with explicit parts → confirm it imports, rigs, and
   assembles through the existing `Anatomy`/`CreatureBuilder` slot system
2. Prove the morph-don't-accumulate swap works with real meshes
3. Prove `generate_material` gives genuinely different surface response per mutation
4. *Then* decide which parts justify hand-authoring in Blender for Tier 3

Do step 1 before anything else. It is the cheapest possible test of the riskiest assumption.
