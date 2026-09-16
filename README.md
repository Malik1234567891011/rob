# Feed a Monster!

> **Feed it anything. See what it becomes.**

A Roblox experience built from the design spec in [`docs/SPEC.md`](docs/SPEC.md).
You start with one tiny creature. Almost everything in the world can be fed to it,
and what you feed it changes what it physically becomes.

**The one sentence:** *Every player raises something nobody else has.*

---

## Status

Playable end to end in Roblox Studio. Verified by running it, not by reading it:

| Check | Result |
|---|---|
| Integration suite (`tests/DevIntegration`) | **33 / 33 pass** |
| Time to first feed (slow simulated player) | **7.2 s** — spec demands ≤ 15 s |
| Eggs on screen after join | **0.56 s** — no menu, no lore |
| Server + client boot | clean, zero errors |
| Config cross-reference validator | clean |
| Distinct creature silhouettes | **1,451,520** before colour/pattern/size |

## The numbers behind the creature system

- **26 traits** — the axes every ingredient pushes on
- **50 ingredients** — each with a hidden influence vector and a procedural prop
- **26 mutations**, 9 of them secret, including Stormwing / Lava Snail / TV Head / Moon Beast
- **11 abilities**, 5 wired to real world gates that change where you can go
- **3 body families × 8 anatomy slots** = 1.45M silhouettes
- **4 biomes**, 92 live ingredient pickups, 5 ability gates
- **2 currencies.** Exactly two. (SPEC §28)

Nothing above is hardcoded per-creature. Adding watermelon is a table entry.

## Layout

```
docs/SPEC.md        the full design spec — source of truth, never deleted
docs/TASKS.md       build plan,each task cites the spec section it satisfies
docs/DECISIONS.md   architecture decisions + the constraints that actually bit
src/shared/         Config (data-driven everything), CreatureBuilder, Net, Util
src/server/         Services: PlayerData Feeding Creature World Ftue Offline
                    Lineage Discovery Analytics
src/client/         ClientMain + Controllers (UI, Effects)
tools/              validate_config.py, gen_thumbnails.py
tests/              integration + timing harnesses
art/thumbnails/     the five SPEC §58 concepts, 1920×1080 ready for Roblox
```

## Running it

The code lives in the Studio place. `src/` is the canonical copy in git.

```bash
python3 tools/validate_config.py     # cross-check every config reference
python3 tools/gen_thumbnails.py      # regenerate thumbnails (needs OpenAI key)
```

To verify in Studio: open the place, press **Play**, read the output window.
`[ITEST]` lines report the integration suite; `[TIMING]` reports time-to-first-feed.
**Delete `DevIntegration` and `DevTiming` from `ServerScriptService` before publishing.**

## Before you publish

- [ ] Remove `DevIntegration` + `DevTiming` from `ServerScriptService`
- [ ] Publish the place so DataStore works — until then it runs **memory-only** and
      says so loudly in the log. Progress does not persist in an unpublished place.
- [ ] Re-check the exact title is still free (SPEC §59)
- [ ] Upload the five thumbnails from `art/thumbnails/roblox_1920x1080/` and let
      Roblox personalize between them rather than picking one by taste (SPEC §58)

## What is deliberately NOT here

Per the spec, not by omission:

- **No shop, no products, no Robux prompts.** SPEC §31: *"don't build the shop before
  players care."* The player must love the creature first.
- **No trading.** SPEC §51 is explicit that this must not ship at launch.
- **No permadeath, ever.** SPEC §52.
- **Ocean / Volcano / Sky Islands** are config-ready but unpopulated — SPEC §76 wants
  them held back as Update 1 (*"SOMETHING IS IN THE OCEAN"*).
