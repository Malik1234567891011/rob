# Handoff: resume here

**Updated 2026-09-16 (afternoon).** The plan is `docs/COMPLETION_PLAN.md`: the whole game, not an MVP.
Malik explicitly rejected both the MVP scope and `generate_mesh`. Blender is the art pipeline.

## State
- **Art.**
  - Creatures: 3 families × 4 heads plus every part variant (Tier 3, skinned, one shared skeleton).
  - Kits: meadow, junk/caves, hub, plus 80 props (all 75 ingredients, eggs, shells).
  - `kit_events` (UFO, picnic, meteor, rock seal) is being built.
  - All art lives in `ReplicatedStorage.Assets` in the open Studio place.
- **World.** `src/server/WorldBuilder.luau` builds everything in edit mode. Run it with the shim: `WB.clear() … WB.all()`.
  - The build is deterministic.
  - The world must be REBUILT after WorldBuilder changes. It is saved in the place, not in git.
- **Systems.** Every launch system is in and asserted by the test suites below. Update 1 (Ocean) ships dark.
  - Switch it on with `Config/Release.updateLevel`, or schedule it with `Config/Release.unlockAt[1]` (live flip, no restart).
- **Tests** (`tests/`, all disabled Scripts; enable ONE, then Play):

  | Suite | What it covers | Result |
  |---|---|---|
  | DevIntegration | core loop | 32/32 |
  | DevSystems | quests, merchant, gates, sanctuary, eggs, monetization guard, parade, events, trials | 43/43 |
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
