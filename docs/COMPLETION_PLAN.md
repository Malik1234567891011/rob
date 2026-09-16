# Completion Plan — the whole game, not the MVP

**Started 2026-09-16.** Malik's instruction: *"finish everything. the entire game, not an mvp…
make the characters, look at them, test them, iterate, play the game, iterate… until it's
completely done."* Blender is the art pipeline (not `generate_mesh`).

"Done" is measured against SPEC §75 launch content + §76 Update 1 ready, with every
§99 non-negotiable verified by playing, and Tier 3 creature art (ART_DIRECTION.md).

Status: `[ ]` todo · `[~]` in progress · `[x]` done and verified in Studio

---

## How work is verified (read before doing anything)

| Question | How |
|---|---|
| Does a mesh look right? | Blender MCP viewport screenshot, then in Studio `screen_capture` |
| Does the REAL runtime code render right? | edit-mode **require shim** (`tools/studio/shim.luau`): loadstring the actual ModuleScripts, build, `screen_capture`. No preview code. |
| Does gameplay work? | Play mode + `execute_luau` on Server/Client datamodels reading state; `[ITEST]` harness; `user_keyboard_input`/`character_navigation` to actually play |
| Code into Studio | small edit: `multi_edit` with the same old/new strings as the local Edit. whole file: `execute_luau` `X.Source = [====[…]====]`. New script: `multi_edit` create. |
| Assets into Studio | Blender → `art/build/*.fbx` → `tools/rbx_upload.py` → `insert_asset` → strip PackageLink → `ReplicatedStorage.Assets` |

`src/` in git is canonical. Anything done only in Studio is lost if Studio dies.

---

## Phase A — Tooling
- [x] A1 FBX → Open Cloud → Studio round trip, skinning verified (DECISIONS.md)
- [x] A2 `tools/studio/shim.luau` edit-mode require shim + creature preview snippet
- [x] A3 `tools/blender/famkit.py` — shared Blender helpers (organic mesh, skin-modifier limbs,
      remesh/decimate, vertex AO, family skeletons, auto-weights, export, preview render)
- [x] A4 Asset install step: inserted model → `ReplicatedStorage.Assets.<Kind>.<Name>`,
      PackageLink/InitialPoses stripped, ledger id recorded in `Config/AssetIds`

## Phase B — Creatures, Tier 3 (the product)
- [x] B1 Style bible: proportions, eye style, palette, poly budgets (§40–42)
- [x] B2 Family skeleton standard (shared bone names: Root Spine Chest Neck Head Jaw EyeL/R
      EarL/R Horn Back Tail1–4 legs…) so parts bind to any family
- [x] B3 **Cute** body + head variants + every part variant, looked at, iterated
- [x] B4 **Heavy** family
- [x] B5 **Weird** family
- [x] B6 Asset-based `CreatureBuilder` (template clone, part select, weld-to-bind, tint,
      materials, scale, glow, LOD) — same genome, same config keys
- [x] B7 `CreatureAnimator` (client, procedural bones): breathe, blink, look-at-owner,
      eye-track held item, ear perk, tail wag, walk/run, hop, the full feeding beat
      (notice → lean → track → CHOMP → cheek bulge → swallow → wobble), sleep, pet,
      evolution, stumble, celebrate, creature-to-creature
- [x] B8 Skins as surface response, not tint (§ART: Crystal/Metal/Fungal/Stone/Slimy…)
- [~] B9 Eggs + hatch (mesh eggs rock + shell cracks: done; mutation morph pop: done via reveal refresh); mutation morph transition (pop/squash, never "wears hats")
- [~] B10 Temperament-driven behaviour (follow distance + idle actions by temperament) (§18): greedy snatch, nervous hide, lazy flop…

## Phase C — World art
- [x] C1 Environment kit (meadow 40, junk/caves 36, hub 38 meshes) (trees, bushes, flowers, grass, rocks, fences, shack, pond…)
- [x] C2 Ingredient props — all 75 + 3 eggs + 2 shells (kit_props.fbx) — every ingredient a real model (~75)
- [~] C3 Terrain, lighting (built by `src/server/WorldBuilder.luau`; visual pass pending), sky, atmosphere; world built in edit mode by
      `tools/studio/build_*.luau` (reproducible from git)
- [~] C4 Home backyard FTUE spot (§8 "beautiful tiny backyard")
- [~] C5 Hub (parade runway, research board, trial portals, merchant)
- [~] C6 Meadow · Junkyard · Crystal Caves biomes
- [~] C7 Ability gates (models + per-player client reveal animations) with real art (boulder, generator, gap, dark cave, burrow, vines…)
- [~] C8 Strange Zone glimpse
- [~] C9 Ocean (Update 1, flag-gated) — §76

## Phase D — Systems
- [x] D1 PlayerData: session lock, UpdateAsync, schema version, retries
- [x] D2 Multiple creatures + active slots; Sanctuary creatures wander
- [x] D3 Quests (§46) + dailies that create possibility (§47)
- [~] D4 Trials (Race queue→arena→leave verified; other arenas unplayed) (§21): Race, Smash, Treasure Hunt, Climb, Obstacle Chaos (+Swim w/ Ocean)
- [~] D5 Creature Parade (signup verified) every ~15 min, 4 reactions, no "best" (§23)
- [~] D6 World events (Earthquake verified) (§54) + Saturday meteor with real countdown (§48)
- [x] D7 Sanctuary: ~12 tiers, decorations, food cultivation, visitors (§16, §29)
- [~] D8 Adventure parties (needs a 2-player test) + co-op ability gates (§20, §53)
- [x] D9 Lineage / Nest polish, DNA card (§15, §80)
- [~] D10 Moments (capture + share + analytics wired): framed evolution/secret/first-flight shots + capture/share (§39)
- [x] D11 Monetization (ids pending Creator Dashboard) per §31–36: 5 passes + products, deterministic, **no prompt before
      first evolution**, nothing that sells creatures or luck
- [x] D12 Content to launch size (§75): ~70 ingredients, ~35 mutations, ~15 secrets
- [x] D13 Audio: tactile eating, crescendos, recognisable rare sting, music (§43)
- [~] D14 UI overhaul (built; not yet seen at phone size), mobile first (§44–45)
- [x] D15 Analytics — full §64 schema
- [~] D16 Inspection "HOW DID THEY GET THAT?!" + research board + world-first (§24, §77–78)

## Phase E — Play it, break it, fix it
- [~] E1 Adversarial smoke bot (plays badly on purpose) + FTUE timing ≤15 s
- [~] E2 Hands-on playthroughs via input tools, findings logged live to `docs/PLAYTEST.md`
- [ ] E3 Performance: LOD, part counts, many creatures on a server
- [ ] E4 §99 non-negotiables audit, publish checklist

---

## Needs Malik (cannot be done by me)
- Publish the place once (File → Publish to Roblox, keep private) so DataStore, text
  filtering and asset ownership work for real, and Studio work is not one crash from lost.
- After publish: game passes / dev products are created on the Creator Dashboard; their
  ids go in `Config/Monetization`.
