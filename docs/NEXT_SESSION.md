# Handoff: resume here

## Latest (2026-09-16 evening)
- **Place is PUBLISHED:** "Feed a Monster", placeId 89616734304159, private, Team Create on
  (cloud autosave). Studio API access is on, so DataStore works in playtests.
  `PlayerDataService.wipe` via DevHooks (`run`, "$me") resets your save to a true new player.
- **Seeing play mode:** `screen_capture` is magenta during Play. Use macOS
  `screencapture -l <windowId>` on the Studio window (see memory roblox-studio-mcp-limits).
  Studio must be the active app, or frames are stale.
- **FTUE was play-tested as a new player 6 times and fixed.** Egg V in view, camera turned
  to eggs, menus hidden until first meal, one-tap first feed, camera push-in, pet prompt
  after first feed, emoji that Roblox can't draw replaced.
- **Void Fang** (from Malik's character sheet) is installed as `Assets.Creatures.Forms.VoidFang`.
  It is a secret mutation form (Dark/Ancient/Heavy, Mythic), and a legend paces the north canyon.
  Malik loved it.
- **Next:**
  - Panel UI pass at phone size (Feed/Monster/Book/Home/Shop).
  - The baby's first visible change is still subtle.
  - Re-run the test suites after today's changes.

**Updated 2026-09-16 (afternoon).** The plan is `docs/COMPLETION_PLAN.md`: the whole game, not an MVP.
Malik explicitly rejected both the MVP scope and `generate_mesh`. Blender is the art pipeline.

## State
- **Art.**
  - Creatures: 3 families × 4 heads plus every part variant (Tier 3, skinned, one shared skeleton).
  - Kits: meadow, junk/caves, hub, plus 80 props (all 75 ingredients, eggs, shells).
  - `kit_events` (UFO, picnic, meteor, rock seal) is being built.
  - All art lives in `ReplicatedStorage.Assets` in the open Studio place.
- **World.** `src/server/WorldTerrain.luau` is the island as one height function, written to voxels in bands. `src/server/WorldBuilder.luau` dresses it.
  - Run with the shim, as two calls:
    1. `WB.clear(); WB.terrain()`
    2. `WB.clearProps()` then hub, plots, meadow, countryside, junkyard, caves, ocean, strange, trials, spawn
  - They must be separate calls: freshly written voxels are not raycastable until the engine steps.
  - `WB.rejects` explains empty scatter areas.
  - The build is deterministic. The world is saved in the place, not in git, so REBUILD it after changes.
  - **Offline review:**
    1. `tools/studio/export_world.luau`
    2. Fetch the chunks (see the file header).
    3. `tools/join_export.py`
    4. `tools/blender/world_preview.py` renders to `art/previews/world/_sheet.jpg`.
- **Systems.** Every launch system is in and asserted by the test suites below. Update 1 (Ocean) ships dark.
  - Switch it on with `Config/Release.updateLevel`, or schedule it with `Config/Release.unlockAt[1]` (live flip, no restart).
- **Tests** (`tests/`, all disabled Scripts; enable ONE, then Play):

  | Suite | What it covers | Result |
  |---|---|---|
  | DevIntegration | core loop | 32/32 |
  | DevSystems | quests, merchant, gates, sanctuary, eggs, monetization guard, passes/cosmetics, parade, events, trials | 51/51 |
  | DevTrials | all 4 trials end to end | 22/22 |
  | DevEvents | all 8 world events | 51/51 |
  | DevUpdate1 | the Ocean opens live | 11/11 |
  | DevTiming | FTUE ≤ 15 s | |

## Code sync (zero-token)
1. Upload with `python3 tools/sync_rbxmx.py <files…>`.
2. Insert the asset with `insert_asset`.
3. Run the apply snippet (`tools/studio/apply_sync.luau`) plus a loadstring compile check.
4. A NEW script needs a `multi_edit` placeholder first. Play must be stopped to apply.

## Blocked / needs Malik
- **Visual review.** `screen_capture` hangs whenever the Studio window isn't visible, because Studio stops rendering.
  - Workaround: `tools/blender/world_preview.py` rebuilds the exported world layout (`art/build/world_export/`) in Blender and renders review shots.
  - Real Studio screenshots of the UI at phone size are still owed.
- **Publish the place** (File → Publish, private). Needed for DataStore, persistence, the global board and real world-firsts.
  - In Studio, world-first bonuses fire on every play because the board is memory-only.
- **Game pass and product ids** go into `Config/Monetization` after publishing.

## Where to look
- `docs/COMPLETION_PLAN.md`: phases A–E with status boxes
- `docs/DECISIONS.md`: constraints that bit
- `docs/ART_DIRECTION.md`: the Tier 3 target
- `docs/ART_KIT_SPEC.md`: kit rules for Blender agents
- `tests/README.md`: what each suite proves
