# Build Plan — Feed a Monster!

Status: `[ ]` todo · `[~]` in progress · `[x]` done · `[-]` deliberately staged (config-ready, not wired)

Reference: every task cites the spec section it satisfies (`docs/SPEC.md`).

---

## Phase 0 — Foundation (§68 data-driven architecture)
- [ ] 0.1 `Shared/Types` — Genome, TraitVector, Ingredient, Mutation type definitions
- [ ] 0.2 `Shared/Utilities` — Signal, TableUtil, Rng (seeded), IdGen
- [ ] 0.3 `Shared/Networking` — remote definitions, server-authoritative request/response
- [ ] 0.4 `Config/Traits` — ~25 trait categories (§75)
- [ ] 0.5 `Config/Ingredients` — influence vectors, rarity, biome, reaction (§6, §69)
- [ ] 0.6 `Config/Anatomy` — body families + modular part kits (§4, §73)
- [ ] 0.7 `Config/Mutations` — requirements / blockers / parts / ability (§69)
- [ ] 0.8 `Config/Biomes` — spawn tables, ingress rules (§13)
- [ ] 0.9 `Config/Progression` — 5 growth stages (§14)
- [ ] 0.10 `Config/Economy` — Coins + Essence ONLY (§28)

## Phase 1 — Creature system (the moat, §71)
- [ ] 1.1 Genome encode/decode — compact, never serialize models
- [ ] 1.2 `CreatureBuilder` — genome → assembled Model (shared, client+server)
- [ ] 1.3 Body archetypes: Cute / Heavy / Weird (§60)
- [ ] 1.4 Silhouette/compatibility rules — prevent procedural sludge (§91)
- [ ] 1.5 Procedural animation: idle, walk, eat, look-at-owner, sleep, celebrate (§42)
- [ ] 1.6 Temperament → behaviour mapping (§18)

## Phase 2 — Core loop, server-authoritative (§70)
- [ ] 2.1 `PlayerDataService` — profile, DataStore, session lock
- [ ] 2.2 `InventoryService` — server-owned bag
- [ ] 2.3 `GeneticsService` — trait vector accumulation, 3-layer influence (§12)
- [ ] 2.4 `FeedingService` — validate → consume → mutate state → replicate
- [ ] 2.5 `EvolutionService` — stage advance + mutation evaluation
- [ ] 2.6 `CreatureService` — spawn, follow owner, replicate genome
- [ ] 2.7 `DiscoveryService` — the Discovery Book (§25)
- [ ] 2.8 `EconomyService` — Coins/Essence, sinks (§28, §29)

## Phase 3 — World (§13)
- [ ] 3.1 Procedural Meadow biome
- [ ] 3.2 Procedural Junkyard biome
- [ ] 3.3 Home Habitat / Sanctuary plot (§16)
- [ ] 3.4 Ingredient spawners + respawn
- [ ] 3.5 Ability gates — 5 environmental abilities unlock routes (§11)
- [ ] 3.6 Strange Zone glimpse, visible early (§13)

## Phase 4 — Client (§44 mobile-first, creature IS the UI)
- [ ] 4.1 `CreatureController` — render replicated genomes, LOD (§72)
- [ ] 4.2 `InteractionController` — pickup + FEED prompt
- [ ] 4.3 `UIController` — Feed/Bag/Monster, Quests/Friends, Coins. Nothing else.
- [ ] 4.4 `EffectsController` — feed particles, trait sting, mutation crescendo (§43)
- [ ] 4.5 `CameraController` — FTUE framing + evolution cinematic
- [ ] 4.6 Contextual item info, simple → detailed toggle (§45)

## Phase 5 — FTUE (§8 — most important 60 seconds)
- [ ] 5.1 0:00 three wobbling eggs, no menu
- [ ] 5.2 0:06 hatch + "HUNGRY!"
- [ ] 5.3 0:12 apple + FEED prompt  ← **first feed by ~0:15 is non-negotiable #1**
- [ ] 5.4 0:16 eat → grow 8% → leaf tuft → NEW TRAIT DISCOVERED → book `1/???`
- [ ] 5.5 0:25 mushroom/battery/fish offered
- [ ] 5.6 0:35 divergent reactions per item
- [ ] 5.7 0:50 giant monster walks past — aspiration, no popup
- [ ] 5.8 first evolution cinematic + name prompt (§19)

## Phase 6 — Meta systems
- [ ] 6.1 `OfflineService` — "WHILE YOU WERE GONE", never evolve offline (§17)
- [ ] 6.2 Lineage / The Nest — parent kept forever (§15)
- [ ] 6.3 One social Trial (§21)
- [ ] 6.4 `AnalyticsService` — full §64 event schema
- [ ] 6.5 Inspection — click another monster (§24)
- [ ] 6.6 Community Research Board (§78)

## Phase 7 — Packaging
- [ ] 7.1 Five thumbnails A–E via OpenAI image gen (§58)
- [ ] 7.2 Title/description copy

## Phase 8 — Verification
- [ ] 8.1 Playtest in Studio, read console clean
- [ ] 8.2 Screenshot evidence of transformation
- [ ] 8.3 Non-negotiables §99 checklist audit

---

## Deliberately staged (NOT in this build — §60 says so)
- [-] Ocean / Volcano / Sky Islands biomes — config-ready, content later (§76 = Update 1)
- [-] Trading economy (§51 — explicitly not at launch)
- [-] Clan system
- [-] Monetization products (§31 — "don't build the shop before players care")
- [-] Subscription (§35 — only after retention proven)
