# FEED A MONSTER! — Master Design Spec

> **Source of truth.** Captured verbatim-in-substance from the founding design document.
> Nothing in this file gets deleted. Amendments append to `## Amendments` at the bottom.

**Working title:** Feed a Monster!
**One-line pitch:** *Feed it anything. See what it becomes.*

**The thumbnail promise:**
A tiny adorable blob on the left. On the right: an absolutely ridiculous 15-foot monster with
crystal antlers, lava feet, butterfly wings, a TV for a stomach and a tiny crown.
Between them: **YOU FED IT WHAT?!**

**The one sentence the team remembers:**
> "Every player raises something nobody else has."

**The marketing proposition:**
> "Feed it anything. See what it becomes."

---

## 1. Product thesis

You begin with one tiny creature. Almost everything in the world can be fed to it.
What you feed it influences: appearance, abilities, movement, personality, elemental traits,
size, useful skills, hidden mutations, and eventually what its descendants can become.

- Strawberries + flowers → soft, pink, fast.
- Scrap metal + batteries → chunky electric cyborg.
- Mushrooms + bones + moonstone → something much stranger.
- Nothing but fish → there is an actual fish evolutionary family.

Players are not collecting premade pets. **They are creating creatures.**
The recurring player thought is *"What happens if I feed it THIS?"* — a far better curiosity
loop than *"Number went from 826 to 1,004."*

Combines five independently-proven Roblox pillars: raising + progression + collection +
discovery + social display.

## 2. Why bet on this

Roblox discovery prioritizes play-through rate, first-play bounce, repeat play days and
playtime, then intentional co-play, qualified sessions and monetization. RDC (Sept 2026)
added: discovery is increasingly age-aware and looks at the first 28 days and beyond.
Younger users → shorter-form; older users → deeper games.

So the ideal Sept-2026 game is **a hypercasual surface with a deep long-term interior.**
- A 9-year-old sees: feed monster → monster changes.
- A 16-year-old discovers: genetic inheritance → synergistic builds → rare mutations →
  competition → breeding → optimization → collection economy.

The same game scales cognitively with the player.

## 3. Psychology we design around (Self-Determination Theory)

| Need | Implementation |
|---|---|
| Autonomy | I decide what it eats, therefore what it becomes |
| Competence | Discover combos, improve creature, master exploration, engineer builds |
| Relatedness | Friends see my monster, help me find things, compete beside me |
| Curiosity | What will this item do? What's behind that combination? |
| Attachment | Not "a Legendary Dragon" — *my* bizarre creature raised since tiny |
| Mastery | Genetics, traits, biomes, food synergies, competition |
| Expression | Appearance is a consequence of decisions, not a cosmetic menu |
| Anticipation | Creature acts while owner is away |
| Collection | Foods, traits, mutations, bloodlines, decorations, species families |
| Social status | Rare creatures are physically visible to everyone |

Flow research: clear goals, feedback, perceived control, challenge matched to skill.
Game begins nearly challenge-free and gradually exposes optimization.

## 4. MOST IMPORTANT DESIGN PRINCIPLE

**We are not making 300 monsters.** That is Adopt Me with worse art resources.
We build a **combinatorial creature system.**

Internal creature representation:

```
BODY      species family, body archetype, scale, proportions
MATERIAL  skin, texture, pattern, glow, transparency
ANATOMY   head, eyes, mouth, ears, horns, back feature, tail, arms, legs, feet
TRAITS    element 1, element 2, movement, temperament, special ability, metabolism
GENETICS  trait strengths, dominance, hidden genes, lineage traits, mutation flags
COSMETICS accessory, name, aura, trail, habitat theme
```

At maturity, even just 12 body families x 12 skins x 20 heads x 20 backs x 16 tails x
20 eyes x 15 patterns x 16 mutations = an enormous appearance space.
**Not every combination needs to be legal** — constraints create recognizable families
while keeping individuals uncommon.

## 5. The magic trick: the body must ACTUALLY change

Not `+3 Fire XP` floating above the monster. Visible transformation.

Feed a battery → BZZT, pupils briefly become lightning bolts.
Feed another → tiny sparks appear.
Eventually → **MUTATION!** An electric tail physically grows.
Player immediately runs off looking for another battery.

Loop: **Find → Feed → React → Change → Discover → Find**
Not: click → sell → upgrade → click.

## 6. Food is not really food

"Food" is the friendly player-facing word. Items carry hidden influence vectors.

| Item | Influences |
|---|---|
| Apple | Nature +3, Sweet +2, Round +1, Energy +1 |
| Battery | Electric +5, Metal +2, Artificial +2, Toxic +1 |
| Mushroom | Fungal +5, Mystic +1, Night +1 |
| Ice cube | Cold +4, Water +1, Crystal +1 |
| Rubber duck | Toy +5, Water +1, Silly +4, Yellow +2 |

Yes, feed your monster a rubber duck. Yes, there are consequences.
That is exactly the kind of thing children tell each other.

## 7. Why "anything" matters

The world must visually answer: *can I feed that to him?* That question **is content.**
Bench? No. Flower beside the bench? Yes. Traffic cone? Rarely, yes. Fish you caught? Yes.
Meteorite? Yes. Enemy slime? Yes. Cursed sandwich behind the gas station? Absolutely.

The world becomes one giant ingredient cabinet. Every update adds ~10 items, 1 biome,
3 hidden interactions — and indirectly creates dozens of creature possibilities.
Extremely efficient LiveOps: build on existing systems, don't build new systems weekly.

## 8. Player's first 60 seconds

*More important than half the rest of this document.* Roblox measures first-play bounce
(<60s, 61–180s) as a major discovery signal, and recommends contextual tutorials over
front-loaded information.

| Time | Beat |
|---|---|
| 0:00 | No menu. No lore. No character creator. No welcome screen. Drop directly into a beautiful tiny backyard. Three tiny eggs wobble. Pick one. Visually different only by color/personality. No stats. 5-second choice. |
| 0:06 | Egg cracks immediately. Tiny monster tumbles out, looks up at the player's avatar. "HUNGRY!" An apple lies 2m away, bouncing slightly. |
| 0:12 | Player grabs apple. Monster runs toward them excitedly. Big contextual prompt: **FEED 🍎** |
| 0:16 | Monster eats. Ridiculous animation. Confetti-ish juice particles. Physically grows ~8%. A tiny green tuft pops out of its head. **NEW TRAIT DISCOVERED — 🌿 Leafy.** Collection book flashes `1 / ???`. We never say 600. Mystery matters. |
| 0:25 | Mushroom, battery, fish now visible nearby. "Try feeding it something weird." No arrow needed after a few seconds. |
| 0:35 | They choose. Whatever they choose produces an obviously different reaction. Battery: ZAP. Mushroom: POOF. Fish: tongue becomes comically long. |
| 0:50 | A massive player monster walks past the plot edge — maybe taller than their house. Their tiny creature looks up at it. Camera subtly frames it. **No popup.** The player understands without words: *I can make THAT.* Aspiration through environment. |

## 9. First five minutes

- 0–1: first physical mutation
- 1–2: discovers different items produce different changes
- 2–3: monster strong enough to break/open something previously inaccessible
- 3–4: sees another player's weird creature
- 4–5: first major evolution

First evolution gets an exaggerated cinematic: baby floats, silhouette expands, three
acquired characteristics combine → **IT EVOLVED!** → **📸 SHOW WHAT YOU MADE**

Roblox Moments creates gameplay→discovery pathways; videos from Experience Detail Pages
are flowing into Moments. Architect around shareable moments from day one.

## 10. Core loop

**Explore → Find → Feed → Evolve → Unlock**
Explore an area → find something useful or strange → feed it → monster visibly stronger/
stranger → new capability opens something previously inaccessible → repeat.

## 11. Abilities change how you play

Mutations cannot be only skins, or the game is an elaborate dress-up simulator.

| Mutation | Gameplay effect |
|---|---|
| Wings | Glide → later fly |
| Burrow | Dig into cracked earth |
| Giant | Move heavy rocks |
| Tiny | Fit through small passages |
| Aquatic | Dive underwater |
| Heatproof | Explore volcanic areas |
| Electric | Power dead machinery |
| Sticky | Climb walls |
| Ghost | Pass certain barriers |
| Light | Explore dark caves |
| Plant | Grow climbable vines |

The creature you create changes your exploration route. **There is no objectively correct creature.**

## 12. Don't lock players permanently

A kid who feeds nothing but rocks must not be punished with "you built the wrong monster."
Three trait layers:

1. **Temporary influence** — recent foods push evolution
2. **Stable traits** — repeated feeding establishes characteristics
3. **Permanent lineage genes** — only major milestones lock genetics

Players eventually unlock controlled ways to shift a creature.
Choices matter without bricking accounts.

## 13. World structure

Hub + biome islands (NOT one seamless MMO continent — mobile performance matters; even
Creatures of Sonaria had to dramatically reduce environment complexity).

| Zone | Ingredients | Traits |
|---|---|---|
| **Home Habitat** | — | Your creature lives here. Customizable. Visible to visitors. Offline activity happens here. |
| **Meadow** (starter) | fruit, flowers, insects, wood, mud, toys | Nature / Sweet / Speed / Cute |
| **Junkyard** | scrap, gears, batteries, magnets, oil, TVs | Metal / Electric / Mechanical / Heavy |
| **Crystal Caves** | crystals, mushrooms, ancient fossils, glowworms, minerals | Crystal / Dark / Mystic / Ancient |
| **Ocean** | fish, coral, pearls, jellyfish, treasure | Water / Flexible / Aquatic / Shiny |
| **Volcano** | coal, obsidian, lava fruit, fire beetles | Fire / Stone / Heat / Strength |
| **Sky Islands** | cloud berries, feathers, star fragments, wind flowers | Air / Light / Flying / Celestial |
| **Strange Zone** (late) | reality behaves improperly | genuinely insane mutations |

Players should glimpse the Strange Zone very early.

## 14. Growth stages

1. **Baby** — cute, fast change, extremely malleable traits
2. **Little** — basic anatomy emerges, first environmental ability
3. **Grown** — build identity obvious, competitions unlock
4. **Giant** — rare combination traits, harder exploration
5. **Mythic** — spectacular; does NOT end progression, unlocks lineage

## 15. Lineages (long-term meta) — NOT "rebirth"

"Rebirth" says: throw away the thing you love so a multiplier grows. Terrible fit.

**The Nest:** at Mythic maturity a monster can create an egg. **The parent stays forever**
and can be displayed in your Sanctuary. Offspring inherits: one body gene, one trait
affinity, one potential mutation, lineage level.

> "My seventh-generation monster has the Ancient Electric gene from my first creature."

## 16. Your Sanctuary

Persistent personal habitat. Starts as a tiny patch of grass + shack; becomes a spectacular
ecosystem of previous creatures. Monsters wander, sleep, play, fight over food, interact,
produce resources, find things. Visitors can enter.

**The Sanctuary is autobiography.** A 200-hour player's home visually tells their account's
story — far more satisfying than `Cash: 93,820,918,772`.

## 17. Offline progression

Grow a Garden's operators cited offline progression as a key reason it worked: players
returned curious about what happened while gone.

**WHILE YOU WERE GONE...** your monster may have found food, dug up an object, practiced an
ability, socialized, produced material, changed slightly, discovered a footprint, or brought
you a weird present.

**Never complete major evolutions offline.** The emotionally important reveal waits for the player.

> *Mochi found something strange near the cave... There is an unidentified object sitting beside its bed.*

That is a return hook. Not `+$87,294 offline income`.

## 18. Personality

Temperament mixture: curious, lazy, greedy, brave, nervous, silly, affectionate, mischievous.
These drive **animations more than stats.**
- Greedy → snatches food
- Nervous → hides behind the player
- Affectionate → runs toward owner
- Lazy → lies down dramatically

A giant terrifying lava creature with Lazy 82% that sleeps constantly is content.

## 19. Name it

After first evolution: *What is its name?* (default suggestion if they don't care).
Names make later messages land: "Mochi found something." / "Mochi learned to fly!" /
"Mochi beat Omar's creature!"

For opted-in 13+, Roblox experience notifications support personalized notifications and
launch data → "Mochi found something strange in your Sanctuary" → join teleports straight
there. Useful, not spammed.

## 20. Social play

Not "invite friend = +20% money" — that is fake social design. Friends change what's *possible*.

**Adventure Parties** (2–4 players): abilities combine. Player A has Giant, Player B has
Electric → Giant moves the broken generator, Electric activates it, door opens, rare food
for everyone. Creature differences become cooperative assets.

## 21. Creature Trials

Short contests, 60–150 seconds. No 30-minute commitment.
Race (movement) · Climb (sticky/flying) · Smash (strength/heavy) · Treasure Hunt (senses/speed)
· Swim (aquatic) · Obstacle Chaos (hybrid).
Enough skill that players care, enough creature-construction that builds matter.

## 22. Don't make combat the whole game

If everything is combat, DPS becomes objectively correct and autonomy collapses — every
optimal player evolves the same monster. Combat may exist alongside races, expeditions,
puzzles, gathering, exploration, shows, photography, hide-and-seek, traversal.
**Different builds must be valid.**

## 23. Social spectacle — CREATURE PARADE

Every ~15 min in the hub. Opt-in players walk their creature down a runway. Server votes with
free reactions: 😂 Weirdest · 😍 Cutest · 😱 Scariest · 🤯 Most Unexpected.
**No "best"** — avoids everyone chasing one aesthetic optimum. Tiny rewards; the real reward
is attention. This is our Dress to Impress DNA.

## 24. Inspection

Click another monster:
```
Noodle
Gen 4
🔥 Fire  🍄 Fungal  🪽 Winged
Owner: Malik
```
And: **HOW DID THEY GET THAT?!** Clicking reveals *known portions* of discovered ancestry —
e.g. `??? + Moon Mushroom + ???`. Envy becomes curiosity rather than commerce.

## 25. The Discovery Book

Not a Pokédex of 300 predefined creatures. Instead:
- **Foods:** Apple ✓ · Battery ✓ · Moon Mushroom ??? · Broken Television ✓
- **Traits:** Leafy ✓ · Electric ✓ · Crystal ✓ · Spectral ???
- **Mutations:** 173 discovered, ??? hidden
- **Weird combinations:** discovered *Static Bloom* (Nature + Electric)

Decades of completionist content without 10,000 separate assets.

## 26. Secret recipes

- **Stormwing** — Electric + Air + high movement
- **Lava Snail** — Fire + Shell + Slow temperament
- **TV Head** — Artificial + Electric + repeated televisions
- **Moon Beast** — Celestial + Night + specific lunar food

Some remain unknown at launch. This manufactures community knowledge:
YouTube "HOW TO GET MOON BEAST", TikTok "nobody knew this mutation existed 💀",
Discord "does anyone know what happens if you feed 10 clocks during meteor weather?"

## 27. Rarity without "open 4,000 eggs"

Interesting randomness emerges from **play**: exploration drops, mutation rolls, meteor
contents. **Robux purchases should be overwhelmingly deterministic.** Roblox requires paid
random-item odds disclosure and eligibility restrictions. This game does not need a casino
to work — that is a strength.

## 28. Economy — exactly two currencies

- **Coins** — from discoveries, activities, expeditions, competitions, excess materials,
  quests. Spent on habitat improvements, tools, travel, ordinary food, sanctuary upgrades.
- **Essence** — rare. From evolutions, discoveries, major achievements, events, lineage
  milestones. Spent on controlled genetic manipulation, lineage systems, high-end Sanctuary.

**No six currencies.** Not Coins/Gems/Crystals/Stars/Tokens/Raid Coins/Diamonds/Event Flowers.
That destroys cognitive simplicity. Temporary event currencies only where necessary.

## 29. Resource sinks (inflation kills persistent economies)

Habitat expansion (escalating coin sink) · Food cultivation · Expedition supplies ·
Cosmetic crafting (materials leave economy) · Trait tuning (late Essence sink) ·
Sanctuary construction (near-infinite prestige sink) · Trading tax (if material trading ships).

## 30. Food has discovery value, not just economic value

A battery is not "worth 800 coins." It is *"WAIT, BATTERY — my monster is close to an
electrical evolution."* Objects become context-dependent, and different players want
different resources. Healthier economy.

## 31–36. Monetization philosophy

**Restrained at launch.** Remember Steal An Egg's lesson: don't build the shop before players
care. The player must first love their creature; only then do products make intuitive sense.

### Launch passes (~5 permanent products, prices are hypotheses)

| Product | ~Robux | What it is |
|---|---|---|
| +2 Active Creature Slots | 249 | Keep multiple creatures accessible. Not required. Huge enthusiast value. |
| Bigger Backpack | 149 | More ingredients per expedition. Convenience. |
| Sanctuary Builder+ | 199 | More decoration capacity + extra cosmetic architecture. Expression, not power. |
| Creature Stylist | 99 | Purely cosmetic: eye colors, name effects, harmless markings, accessory placement. |
| VIP / Researcher | 399 | Nameplate, expanded journal analytics, cosmetic lab, photo features, non-stat accessory line. |

Roblox Managed Pricing can run price experiments but typically needs ~60K transactions / 30
days. **We do not pretend to know perfect pricing beforehand.**

### Developer products (sparingly)

- Trait Cleanser — 49 R$ (reduces a chosen recent influence; useful on direction change)
- Expedition Snack Pack — 39 R$ (also obtainable in-game)
- Habitat Instant Finish — contextual
- Cosmetic effects — **guaranteed, never random** (star footprints, bubbles, leaves, tiny clouds)

**No important creature evolution is paywalled.**

### WHAT WE WILL NOT SELL

- ❌ "100x mutation luck" — cheapens rare creatures instantly
- ❌ Robux-exclusive best genes — pay-to-win
- ❌ Revive monster after death — we are not killing attached monsters
- ❌ Random Robux eggs — legal/design headache, weakens identity
- ❌ **"Buy the rare monster"** — destroys the fundamental fantasy that *you created it*

> We make money because players value what they created. We do not undermine that for a $10 sale.

### Subscription — LATER, only after retention is demonstrated

**Monster Club** (monthly): rotating cosmetic habitat set, expanded sanctuary capacity,
photography tools, extra lineage archive space, cosmetic nameplate. **No essential progression.**
Recurring payment needs recurring genuine value.

### The shop must not scream

Roblox discourages pushy urgency toward minors and misleading countdowns / false scarcity.
No `97% OFF!!!!!!` No `ONLY 3 MINUTES LEFT!!!!` No giant store on first join.
**No purchase prompt before first evolution.** The first five minutes are about
*"I love this little idiot."* Then monetization has leverage.

## 37–39. Content, viral loop, Moments

The game is designed around **shareable questions**:
- "I fed my Roblox monster nothing but batteries for 2 hours"
- "What happens if you feed it 50 mushrooms?"
- "My friend somehow made THIS."
- "Feeding my monster every item commenters tell me to"
- "Rarest mutation anyone has found so far"
- "The devs said nobody has found this evolution yet"
- "Day 12 of trying to make the smallest possible monster"

**The content itself explains the game** — the player never has to.

**Viral loop:** see "I fed my monster 100 TVs" → *WTF happens?* → watch → incredible
transformation → *I want to try another item* → click → play → their creature differs →
they post "I fed mine 100 rubber ducks instead" → repeat.
Far stronger than "LIKE AND FAVORITE FOR CODE 10KLIKES."

**Moment Events** (game prepares perfect camera framing, one tap to share):
evolution · secret mutation · giant transformation · rare item discovery · hilarious creature
failure · race photo finish · first flight · lineage birth.

## 40–43. Art, animation, audio

**Visual identity:** Pixar-ish silhouette readability without photorealism. Soft stylized
low-poly. Chunky shapes. Beautiful lighting. Expressive animation. Saturated natural world,
**not neon vomit.** Silhouettes must be legible at thumbnail resolution.

**Monsters must look FUNNY before they look COOL.** A polished dragon is less shareable than
a fat four-legged toaster with angel wings. The system generates beauty *and* absurdity —
different content vectors. Cool / cursed / adorable are all valid player goals.

**Animation budget:** spend disproportionately on the monster —
eating, looking at owner, running toward owner, sleeping, reacting to food, petting,
evolution, stumbling, celebrating, interacting with other monsters.
**A tree can look mediocre. The creature cannot.**

**Audio:** eating needs ASMR-ish tactile quality — crunch, slurp, metal clang, electric fizz,
monster burp, transformation crescendo, rare mutation signature sting.
Players should recognize the rare mutation sound from across the server. **Sound as status signaling.**

## 44–45. UI principles

**Mobile first.** Main screen has almost nothing:
- Bottom: Feed · Bag · Monster
- Side: Quests · Friends
- Top: Coins

That is about it. Do NOT cover 40% of the viewport with twelve buttons, spin wheels, gifts,
shops, battle pass, codes, daily rewards. **The creature is the UI.**

**Contextual information** — pick up a battery:
```
BATTERY
⚡ Strong Electric influence
🔩 Small Metal influence
```
Advanced players toggle detailed mode: `Electric +5, Metal +2, Artificial +2, Toxic +1`.
Complexity reveals itself as player sophistication increases — supports children *and* optimizers.

## 46–47. Quests and dailies

No "walk 5,000 studs." Quests teach discovery:
- **Try Something New** — feed it something it has never eaten
- **Weird Diet** — feed three different artificial objects
- **Adventure** — discover a hidden ingredient
- **Social Creature** — complete a Trial with a friend
- **Scientist** — trigger a new trait

**Dailies create fresh possibility, not attendance:** world ingredient (one unusual ingredient
more frequent) · creature weather (rain affects certain foods) · expedition conditions (different
traits get bonuses) · wandering merchant (deterministic rotating inventory) · community discovery
(newly discovered mutations playerbase-wide).

Player thinks *"something different is happening today"*, not *"I must claim Day 37."*

## 48. Weekly live event — SOMETHING FELL FROM THE SKY

Every Saturday. Entire server sees the meteor. Genuine countdown. It crashes into a shared
biome. Players break it together. Inside: strange ingredients — some create temporary weekend
mutations, some enter the permanent discovery pool.

Yields co-play, spectacle, content, scarcity, returning users, update ritual.
The scheduled communal event is one of the most important patterns recent Roblox breakouts proved.

## 49. Seasons alter ecology (not just battle passes)

Example **DEEP SEA MONTH**: new Ocean trench, 8 ingredients, 2 creature anatomical families,
5 mutations, 1 world boss/activity, 1 Sanctuary set, 1 lineage gene.
**Nothing disappears mechanically afterward.** Limited cosmetics commemorate participation;
core gameplay content stays accessible.

## 50. Long-term endgame — five infinite pursuits

A game dies when its most dedicated player asks "why am I doing this anymore?"
1. **Discovery** — fill the encyclopedia
2. **Genetics** — engineer unusual trait combinations
3. **Lineages** — develop generations
4. **Sanctuary** — build a visual status monument
5. **Mastery** — trials and challenges

Different archetypes appeal to different people. That matters.

## 51. Trading — NOT at launch

Strong conviction. The moment creatures are fully tradable, optimization shifts from
*"I love my creature"* to *"what's its market value?"*

Launch trading only for: common materials, certain discovered ingredients, crafted cosmetics.
Later perhaps genetic items. Actual creature trading is a months-later update after
understanding behavior and policy. Roblox requires PolicyService handling for paid-item
trading eligibility.

## 52. NO PERMADEATH

Your monster cannot permanently die. Absolutely not. Risk means tired, knocked out,
expedition failed, food lost. **Do not delete someone's six-month digital pet.**

## 53. Friend design

Roblox measures intentional co-play days as a discovery signal. Friends need meaningful
benefits without making solo play miserable: joint expeditions (complementary traits) ·
monster interactions (personalities produce scenes) · sanctuary visits (friend-only
interactions) · co-op secrets (certain objects need two creatures) · trials · ingredient
trading · photos (pose creatures together).

## 54. World events create server culture

UFO (abducts creatures briefly, returns them with weird residue) · Ingredient Rain ·
Giant Picnic (rare foods) · Storm (electric creatures go crazy) · Full Moon (night traits
activate) · Earthquake (cave opens) · Invasion (slimes steal food, players chase them).

**No event should simply mean Coins ×2.** Events alter behavior.

## 55–57. Audience

**Children click** because it is a toy — feed creature, grow creature. No genre literacy, no
anime familiarity, no fantasy lore, no reading requirement. Globally understandable (Grow a
Garden's lesson). Roblox age-checked population as of Feb 2026: ~35% under 13, ~38% 13–17, ~27% adults.

**Teenagers won't dismiss it** because rare creatures genuinely look unbelievable, genetics
have spreadsheet-grade depth, hard Trials require builds, secret combos create prestige, late
zones are beautiful and weird, and players can make horrific/cool creatures — not just
toddler-cute animals. Think *Pokémon + Spore + Tamagotchi + Grow a Garden progression +
Roblox sociality*, cloning none of them.

**Creators play it** because it generates endless prompts automatically. Every ingredient is a
video idea; every update is ten; every hidden mutation is a race; every event is coverage.
Viewer comments generate content directly: "feed it a shoe", "do only purple foods",
"make the fattest possible monster".

## 58–59. Discovery packaging

Roblox thumbnail personalization reports ~+8.5% average qualified play-through improvement,
up to +50%. **Launch 5 thumbnail concepts and let Roblox personalize instead of deciding by taste.**

| # | Concept | Text |
|---|---|---|
| A | Transformation: baby → giant creature | WHAT WILL IT BECOME? |
| B | Weird: player holding battery, monster has giant electrical mouth | DON'T FEED IT THAT |
| C | Cute: baby monster staring at a strawberry | (virtually none) |
| D | Status: three players beside insane mature creatures | — |
| E | Mystery: black silhouetted undiscovered monster | ??? |

**Title candidates:** *Feed a Monster!* (best comprehension — launch this first) ·
*Feed Your Monster!* (more emotional) · *What Did You Feed It?!* (best meme, weaker search) ·
*Raise a Creature* (broader, generic).
Market check found Grow Monster/Dragon and creature-builder concepts, but no prominent
experience owning this exact central fantasy. Re-check exact title availability at publish time.

## 60. MVP — what actually has to exist

99 Nights' creators: keep scope small, work quickly, follow the fun (it was a game-jam idea
built in a three-month sprint).

- One monster base rig with enough modular parts to prove transformation
- Three body branches: **Cute / Heavy / Weird**
- **25 ingredients**
- **~15 visible traits**
- **2 biomes**: Meadow, Junkyard
- **5 environmental abilities**
- One Sanctuary
- One social Trial
- Offline return system
- First lineage
- Excellent onboarding

**NOT in MVP:** giant ocean, 100 genes, clan system, trading economy.

## 61–63. Prototype tests

**Test 1 — is it fun for 20 minutes?** Give testers an ugly block creature + apple, battery,
mushroom, metal, fish, feather, rock. Each visibly transforms it. Don't explain combinations. Watch.
The signal is NOT "yeah, pretty fun." The signal is **"wait, what happens if I give it this?"**

**Test 2 — show 10 players someone else's weird creature.** Ask what they want to know.
Best response: **"How did he get that?"** That is the engine.

**Test 3 — show the thumbnail, don't explain the game.** Ask a child/teen what they think
happens. If they say "you feed the monster and it changes" — packaging is truthful.

## 64. Analytics event schema (instrument from alpha)

```
session_start
ftue_egg_seen · ftue_egg_selected · ftue_first_food_pickup · ftue_first_feed
ftue_first_trait · ftue_first_evolution
ingredient_pickup · ingredient_feed · ingredient_discovered
trait_progress · trait_unlocked · mutation_unlocked
biome_enter · biome_unlock
monster_named · monster_petted
trial_enter · trial_complete
friend_join · friend_party · friend_sanctuary_visit
sanctuary_upgrade
lineage_created
shop_open · product_view · purchase_prompt · purchase_complete
moment_capture · moment_share
session_end
```

**Properties:** player_age_cohort_if_allowed, device, acquisition_source, session_number,
monster_stage, lineage_generation, active_traits, friends_present, time_since_last_session.

**No guessing.**

## 65–67. Funnel, metrics, experiments

**Primary funnel:** Impression → Play → >60s → first feeding → first visible trait → first
evolution → 5 min → 15 min → leaves with unfinished goal → returns D1 → returns D2–7 → creates lineage.
Everything else is subordinate at launch.

**Metrics:** use Roblox's live percentile benchmarks rather than generic internet numbers.
Internal demands: FTUE completion extremely high · first-minute bounce exceptionally low ·
first evolution for the majority of meaningful users · D1 comfortably above comparable median ·
D7 above median before scaling acquisition · intentional co-play growing with account age ·
**organic content: players posting without being paid.** That last metric matters more than people admit.

**Experiments to run:** egg choice vs instant creature · mutation after feed #1 vs #2 · other
player's giant creature at 0:40 vs 3:00 · collection book reveal timing · first world event
timing · naming before vs after first evolution · shop introduction session 1 vs 2 ·
starter creature personalities. **Do not debate endlessly. Measure.**

## 68–72. Technical architecture

Data-driven systems, **not one script per mutation.**

```
ReplicatedStorage/Shared/
  Config/    Ingredients · Traits · Mutations · Biomes · Economy · Progression
  Types/  ·  Networking/  ·  Utilities/

ServerScriptService/Services/
  PlayerDataService · CreatureService · GeneticsService · FeedingService
  EvolutionService · InventoryService · EconomyService · SanctuaryService
  OfflineService · ExpeditionService · TrialService · SocialService
  AnalyticsService · MonetizationService · LiveOpsService

StarterPlayer/Controllers/
  CreatureController · InteractionController · CameraController
  UIController · FeedController · EffectsController

Workspace/  Biomes/ · Hubs/
```

**Every ingredient is configuration. Adding watermelon must not require engineering.**

```lua
Watermelon = {
    rarity = "Common",
    influences = { Water = 3, Sweet = 2, Nature = 1, Round = 2 },
    reactions  = { animation = "BigBite", sfx = "JuicyCrunch" },
    biomes     = { "Meadow" },
}

StormWing = {
    requirements = { Electric = 70, Air = 55, Stage = 3 },
    blockers     = { Heavy = 80 },
    weight       = 1,
    parts        = { Back = "StormWings" },
    ability      = "ChargedGlide",
}
```

**Server authority — never trust the client for:** inventory, genes, currency, feed
consumption, mutation determination, trade outcomes, purchase receipts.
Client asks "I want to feed item X"; server confirms ownership, creature exists, valid state,
no impossible spam, then mutates state. Economy integrity is critical once items have status.

**Creature rendering:** never serialize whole models. Save a compact genome —
CreatureID · BodyFamily · SizeGene · Head/Eye/Ear/Horn/Back/Tail/Leg genes ·
Material/Pattern/PrimaryColor/SecondaryColor genes · TraitVector · MutationFlags ·
TemperamentVector · Generation · Parents · BirthTimestamp.
Client/server renderer assembles the monster. Storage stays manageable.

**Performance:** LOD is mandatory. Nearby monsters full fidelity; far monsters simplified rig/
materials; very distant silhouette/impostor. Sanctuary populations throttle idle animation.
**The creature system is our technical moat and our biggest performance risk.**

## 73–74. Art & LiveOps pipeline

Artists make **modular kits**, not whole creatures. A DEEP SEA update = 3 tails, 2 fins,
3 head features, 2 skin materials, 2 patterns, 2 mutations, 8 food props — which recombine
with the entire historical ecosystem. Incredible content multiplier.

**Weekly update template:** 3–6 ingredients · 1 mutation · 1 world event variation ·
1 cosmetic · 1 small Sanctuary object · 1 balance/QoL fix.
Occasionally: new biome or new system. Roblox's LiveOps guidance distinguishes frequent
content cadence from rarer major system updates for exactly this reason.

## 75–76. Launch content & Update 1

Launch: ~70 ingredients · ~25 trait categories · ~35 major mutations · enough anatomy
components for thousands of recognizable combinations · 5 growth stages · trials ·
world events · ~12 meaningful Sanctuary upgrade tiers · ~15 major secret combinations ·
one late-game lineage system. **That is enough.**

**Have Update 1 ready before launch.** A week after momentum: **SOMETHING IS IN THE OCEAN.**
Ocean opens, new ingredient families, aquatic adaptations, one terrifying/cute secret mutation.
Creators get immediate material; players learn *"oh, this game updates."* Extremely valuable.

## 77–80. Community systems

**Community mystery:** occasionally announce only *"there are 3 undiscovered mutations in this
update."* Nothing else. Players globally experiment. In-game research board:
`WORLD FIRST — StaticFrog22 discovered VOID MOTH` + timestamp + creature portrait.
**Discovery creates permanent status that is not purchasable.**

**Community Research Board** (central hub, global stats): `72.8B items eaten` ·
`Most eaten today: 🍎 Apple` · `Rarest discovered trait: 🌙 Moonborn` ·
`Unsolved: ??? + Battery + Star Fragment` · `Largest creature alive: Chunk — Gen 19`.
Makes the game feel like a world, not a private simulator.

**MONSTER DNA (later):** share a tiny non-tradable "DNA card" — portrait, owner, generation,
traits, date created. Friends display it. Not a clone; a collectible record. Baseball card.

**Creator events:** don't pay a creator to make an ad. Give them a custom mystery ingredient
and don't tell them what it does — they livestream feeding it. Or: one creator gets 24 hours
to discover a hidden creature before everyone else. Content and game become the same thing.

## 81–83. Launch marketing

No giant ad budget immediately. Closed testers → small cohort → **fix first-minute behavior**
→ controlled sponsored traffic. Outside sources (ads, search, social, friends, curation) get an
experience into consideration for organic recommendation; how those cohorts behave determines
whether distribution expands.

> Paid acquisition's job is **ignition**. Roblox's job is **oxygen — if the fire is real.**

**Creator seeding, three tiers:** small Roblox creators (cheap, fast, will experiment) ·
short-form creators (concept fits TikTok/Reels natively — give prompts, not scripts) ·
giant YouTubers (only once the game produces genuinely funny outcomes).

**Do not force influencers to pretend.** The whole brief is: *"Here's the game. Try to make the
weirdest creature possible."* If it needs an eight-paragraph brief to seem interesting, we failed.

## 84–88. Defensibility

Someone will clone it if it works. Guaranteed. The moat:
genetics graph (hundreds of tuned interactions) · creature rendering tech · content library ·
player lineages (switching cost) · sanctuary histories (emotional switching cost) ·
community discovery knowledge · social graph · brand.

A clone ships "Feed A Pet" in two days. **They cannot instantly recreate six months of
biological possibility space.**

**vs. a trend clone:** higher immediate legibility but high competition, weak differentiation,
weak brand, high trend decay. Objective is $1M+, not quick users.
**vs. an RPG:** an RPG needs combat, AI, worldbuilding, quests, levels, weapons, bosses,
balancing, narrative, maps and endgame before you know if anyone cares. This proves its
dopamine loop with **one creature + eight objects.** Enormous startup advantage.
**vs. a pure simulator:** simulators supply only competence (bigger number). This supplies
competence + autonomy + attachment + relatedness + curiosity.
**vs. pure RNG:** RNG asks "did the game give me something rare?" This asks "what did I create?"

## 89–94. Failure modes to design against

1. **It's just a pet simulator** (biggest danger) — if it's feed → bar increases → cosmetic
   change, we lose. The creature must materially modify exploration and interaction.
2. **Combinations feel random** — players must be able to form hypotheses. **Predictable
   locally, surprising globally.** Battery reliably pushes Electric; what Electric + Fungal +
   Flying eventually creates may surprise you.
3. **Every monster looks ugly** — procedural systems produce sludge. Art director needs
   compatibility rules, constrained proportions, harmonized colors, silhouette sanity checks.
   We want *deliberately ridiculous*, not *broken generator*.
4. **Too much complexity too early** — a new player must know none of these words: genome,
   lineage, dominance, affinity, essence. They know: monster hungry, feed monster, it changes.
5. **No real game beyond collection** — hence exploration, abilities, Trials, Sanctuary,
   co-op, secrets, lineages. There must be somewhere to *use* the creature.
6. **Monetization corrupts the fantasy** — money buys convenience, capacity, expression,
   tools. **Gameplay creates monsters.**

## 97. The flywheel

```
easy-to-understand thumbnail → curiosity click → first transformation within seconds
→ "what happens if..." → personal creature → aspiration from other monsters
→ exploration + evolution → attachment → leave with unfinished creature goal
→ offline anticipation → return → friend/social interaction → weird evolution moment
→ TikTok / Moments / YouTube → new users → strong Roblox recommendation cohort
→ more Home distribution → larger community → more secrets discovered → more content
→ stronger reasons to join
```

That is the business.

## 99. NON-NEGOTIABLES

1. Feeding the first object occurs within **~15 seconds**
2. The monster changes **visibly**, almost immediately
3. Players can **form hypotheses** about cause and effect
4. The monster behaves like a **character**, not a walking multiplier
5. No two long-term creatures should routinely look identical
6. Creature abilities **materially change gameplay**
7. A stranger's monster makes me ask **"how the hell did he get that?"**
8. The basic game is **excellent without Robux**
9. Weekly content is **cheap to produce** because systems recombine assets
10. The game constantly creates **moments worth recording**

---

## Amendments

*(append dated amendments below — never edit the sections above)*

### 2026-09-16 — Build amendments

Recorded during the first implementation pass. These are refinements the spec did not
specify, made while building, all traceable to a spec principle:

1. **`Progression.MAX_SCALE` per stage.** Mutation `sizeMul` stacks multiplicatively and
   reached 8.7× base, which is not "spectacular", it is broken. Capped so Mythic lands near
   the 15-foot creature the thumbnail promises.
2. **Follow distance scales with body size.** A Baby at a fixed 7 studs reads as a dot on
   the horizon. The creature is the product (§44 "the creature is the UI"), so it anchors
   *in front of* the owner at a distance proportional to its own torso.
3. **`Traits.VISIBLE_AT = 3` and `Sprout` at `Nature >= 3`.** One apple is Nature+3, so the
   first feed always produces a visible body change. Non-negotiable §99 #2 is encoded as
   data, not as a special case in code.
4. **Name filtering fails CLOSED.** If `TextService` moderation is unavailable (as in an
   unpublished Studio place), the creature is named "Monster" rather than accepting an
   unfiltered player string. This is a children's product.
5. **The aspiration creature (§8, 0:50) is an NPC.** On an empty server there is no
   "massive player monster" to walk past, so one is staged. No popup, no text.
