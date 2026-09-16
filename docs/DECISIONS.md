# Architecture decisions & hard-won constraints

Written from what actually happened building this, not from what should work in theory.
If you are picking this up later, read this before fighting the same walls.

---

## The Roblox Studio MCP sandbox: what it can and cannot do

Verified empirically on 2026-09-16, not assumed:

| Capability | Result |
|---|---|
| `execute_luau` create/destroy Parts in `Workspace` | ✅ works |
| `execute_luau` read/write instance properties | ✅ works |
| `execute_luau` **network** (`HttpService:GetAsync`, even to localhost) | ❌ `lacking capability Network` |
| `execute_luau` **`require()`** any ModuleScript | ❌ `has additional values for the Capabilities property: LoadUnownedAsset` |
| `execute_luau` parent a script into any container | ❌ same capability wall |
| Clearing `Instance.Capabilities` to work around it | ❌ needs a `SecurityCapabilities` value; assigning one from a fresh instance silently no-ops |
| `multi_edit` create nested ModuleScripts/Scripts | ✅ **this is the only write path for code** |
| `screen_capture` | ✅ edit mode only — returns solid magenta during Play |

**Consequences that shaped the build:**

1. **A localhost file-sync server is impossible.** The obvious design (serve `src/` over
   HTTP, have a Studio bootstrap fetch a manifest) cannot work — the sandbox has no
   network capability at all. Code goes in via `multi_edit`, one file per call.

2. **You cannot unit-test a module from the MCP.** `require` is blocked. So verification
   happens by *playtesting and reading the console*, which is a better test anyway —
   it exercises the real runtime, not a mock.

3. **Visual verification needs a workaround.** `screen_capture` only works in edit mode,
   but scripts only run in Play mode. The approach used here: have the real builder emit
   a compact geometry dump during Play, then replay those exact parts in edit mode and
   capture. **One implementation, no preview-renderer to drift out of sync.**

4. **`multi_edit` creates intermediate path segments as Folders.** So
   `...StarterPlayerScripts.Main.Controllers.UIController` makes `Main` a *Folder*, and you
   can then never make `Main` a LocalScript. Put sibling folders beside the script instead:
   `StarterPlayerScripts.ClientMain` + `StarterPlayerScripts.Controllers.*`.

---

## Engine-bundled sounds: verified, not guessed

`rbxasset://sounds/*` files ship with every client — no uploads, nothing to break.
But not every plausible filename exists. Probed live (`ContentProvider:PreloadAsync`):

**Present:** `electronicpingshort.wav` · `switch3.wav` · `switch.wav` · `bass.wav` ·
`clickfast.wav` · `snap.mp3` · `metal.ogg` · `impact_water.mp3` · `action_jump.mp3` ·
`action_falling.mp3` · `action_get_up.mp3` · `action_footsteps_plastic.mp3` ·
`action_swim.mp3` · `hit.wav` · `splat.wav` · `uuhhh.mp3` · `button.wav`

**NOT present** (fail with `Temp read failed`): `pop_mid_up.wav` · `pageturn.wav`

`EffectsController` gets ~28 distinct reaction sounds out of 10 bundled files by
treating each as (file, pitch, volume). A metal clang and a juicy crunch are different
files; a pop and a squeak are the same file at different pitches.

---

## Bugs the build process caught (and how)

These are all cases where "it compiles" or "no errors" would have been wrong:

1. **Runaway creature scale.** `sizeMul` stacked multiplicatively — Gigantism × Monarch ×
   Everything = 3.1×, on top of stage 1.95× and feed drift 1.45× = **8.7× base**. Caught by
   printing the scale in the smoke test. Fixed with `Progression.MAX_SCALE` per stage.

2. **Detached heads on the Heavy body.** Head position was a raw fraction of torso depth
   (`headForward = 1.95`), which put the head 2 studs off the body. Caught by *reading the
   geometry dump numbers*, before ever rendering it. Fixed by computing the attach distance
   from the head's own radius so it always overlaps the torso slightly.

3. **Limbs flying off tall/narrow bodies.** All offsets used one scalar unit
   (`torso.Size.Y`). On the Weird body (tall, narrow) that pushed legs to x=±11 on a body
   only 13 wide. Fixed with **per-axis half-extent offsets**; part *sizes* still use a
   balanced mean of the torso axes so narrow bodies don't get oversized limbs.

4. **Creatures sinking through the floor.** Models had no notion of where their feet were.
   Added a `GroundOffset` attribute measured from the assembled bounding box.

5. **`TextButton.Text` shadows a child named `Text`.** Naming the button's label child
   `"Text"` meant `btn.Text.ZIndex` indexed the *string property* and threw at runtime.
   Renamed to `"Label"`. This only surfaced in a real playtest.

6. **A test that passed for the wrong reason.** `"cannot feed unowned item"` returned
   `"too fast"` — the rate limiter fired before the ownership check, so the assertion never
   tested ownership at all. Now asserts on the *specific reason string*, and a second case
   covers the rate limiter with items actually in the bag.

---

## Deliberate deviations from the spec, and why

- **Server-built creature models, not client-assembled.** SPEC §71–72 describes clients
  assembling from a replicated genome with LOD. This build keeps the genome authoritative
  and compact as specified, but the server builds the model so it replicates automatically.
  `CreatureBuilder.build(genome, lod)` **already takes an LOD parameter** (1/2/3) and drops
  cosmetic slots accordingly — moving assembly client-side is a swap of the call site, not
  a rewrite. Do this before scaling past ~20 concurrent creatures per server.

- **No shop, no products, no currency purchases.** SPEC §31 is explicit: *"don't build the
  shop before players care."* The economy config defines Coins/Essence and sinks; no
  monetization surface exists. That is the spec being followed, not a gap.

- **Side HUD button is the Discovery Book, not Quests/Friends.** SPEC §44 lists
  "Side: Quests, Friends". Those systems are not built, and a button that does nothing is
  worse than no button. The Book is built and is core to §25.

- **The aspiration creature is an NPC.** SPEC §8 (0:50) wants "a massive player monster"
  walking past. On an empty server there is no such player, so `WorldService` stages one
  that patrols the horizon. No popup, no text — exactly as specified.
