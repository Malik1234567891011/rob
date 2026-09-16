#!/usr/bin/env python3
"""Cross-check the Luau config modules for dangling references.

These files reference each other by string key (an ingredient names traits, a
mutation names anatomy variants, a biome names ingredients). Nothing in Luau
catches a typo there until it silently does nothing at runtime, so we gate it here.

Exit 0 = clean, 1 = broken references.
"""
import re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = ROOT / "src/shared/Config"
errors, warnings = [], []


def read(name):
    return (CFG / name).read_text()


def block(src, header, end):
    """Text between `header` and the next top-level `end` marker."""
    i = src.index(header) + len(header)
    j = src.index(end, i)
    return src[i:j]


# ── Traits ────────────────────────────────────────────────────────────────────
traits_src = read("Traits.luau")
TRAITS = set(re.findall(r'"(\w+)"', block(traits_src, "Traits.order = {", "}")))
trait_defs = set(re.findall(r'^\t(\w+)\s*= \{ display', traits_src, re.M))
if TRAITS != trait_defs:
    errors.append(f"Traits.order vs definitions mismatch: {sorted(TRAITS ^ trait_defs)}")

# ── Anatomy ───────────────────────────────────────────────────────────────────
anat_src = read("Anatomy.luau")
parts_blk = block(anat_src, "Anatomy.parts = {", "\nAnatomy.slotOrder")
SLOTS = {}
for slot_m in re.finditer(r'\n\t(\w+) = \{(.*?)\n\t\},\n', parts_blk, re.S):
    slot, body = slot_m.group(1), slot_m.group(2)
    SLOTS[slot] = set(re.findall(r'\n\t\t(\w+)\s*= \{ display', body))
SLOT_ORDER = re.findall(r'"(\w+)"', block(anat_src, "Anatomy.slotOrder = {", "}"))
for s in SLOT_ORDER:
    if s not in SLOTS:
        errors.append(f"Anatomy.slotOrder lists '{s}' but no such parts block")
SKINS = set(re.findall(r'\n\t(\w+)\s*= \{ material', block(anat_src, "Anatomy.skins = {", "\nAnatomy.patterns")))
BODIES = set(re.findall(r'"(\w+)"', block(anat_src, "Anatomy.bodyOrder = {", "}")))

# skins named by traits must exist
for t, skin in re.findall(r'\n\t(\w+)\s*= \{[^\n]*?skin = "(\w+)"', traits_src):
    if skin not in SKINS:
        errors.append(f"Trait {t}: skin '{skin}' not in Anatomy.skins")

# body affinity keys must be traits
for body_m in re.finditer(r'affinity = \{([^}]*)\}', anat_src):
    for k in re.findall(r'(\w+) =', body_m.group(1)):
        if k not in TRAITS:
            errors.append(f"Anatomy body affinity references unknown trait '{k}'")

# ── Ingredients ───────────────────────────────────────────────────────────────
ing_src = read("Ingredients.luau")
INGREDIENTS = set(re.findall(r'"(\w+)"', block(ing_src, "Ingredients.order = {", "}")))
ing_defs = set(re.findall(r'^\t(\w+) = ing\{', ing_src, re.M))
if INGREDIENTS != ing_defs:
    errors.append(f"Ingredients.order vs definitions mismatch: {sorted(INGREDIENTS ^ ing_defs)}")

RARITIES = set(re.findall(r'(\w+) = [\d.]+', block(ing_src, "Ingredients.rarityPotency = {", "}")))
for m in re.finditer(r'^\t(\w+) = ing\{(.*?)\n\t\},$', ing_src, re.S | re.M):
    name, body = m.group(1), m.group(2)
    infl = re.search(r'influences = \{([^}]*)\}', body)
    if not infl:
        errors.append(f"Ingredient {name}: no influences")
        continue
    keys = re.findall(r'(\w+) =', infl.group(1))
    if not keys:
        errors.append(f"Ingredient {name}: empty influence vector")
    for k in keys:
        if k not in TRAITS:
            errors.append(f"Ingredient {name}: unknown trait '{k}'")
    rar = re.search(r'rarity = "(\w+)"', body)
    if rar and rar.group(1) not in RARITIES:
        errors.append(f"Ingredient {name}: rarity '{rar.group(1)}' has no potency entry")
    shapes = re.findall(r'shape = "(\w+)"', body)
    for sh in shapes:
        if sh not in {"Ball", "Block", "Cylinder", "Wedge"}:
            errors.append(f"Ingredient {name}: unsupported shape '{sh}'")

# ── Mutations ─────────────────────────────────────────────────────────────────
mut_src = read("Mutations.luau")
MUTATIONS = set(re.findall(r'"(\w+)"', block(mut_src, "Mutations.order = {", "}")))
mut_body = block(mut_src, "Mutations.all = {", "\nMutations.order")
mut_defs = set(re.findall(r'\n\t(\w+) = \{\n\t\tdisplay', mut_body))
if MUTATIONS != mut_defs:
    errors.append(f"Mutations.order vs definitions mismatch: {sorted(MUTATIONS ^ mut_defs)}")

ABILITIES = set(re.findall(r'\n\t(\w+)\s+= \{ display', block(mut_src, "Mutations.abilities = {", "\n}")))
for m in re.finditer(r'\n\t(\w+) = \{\n\t\tdisplay.*?\n\t\},', mut_body, re.S):
    name, body = m.group(1), m.group(0)
    for field in ("requirements", "blockers"):
        blk = re.search(field + r' = \{([^}]*)\}', body)
        if blk:
            for k in re.findall(r'(\w+) =', blk.group(1)):
                if k not in TRAITS:
                    errors.append(f"Mutation {name}.{field}: unknown trait '{k}'")
    pblk = re.search(r'parts = \{([^}]*)\}', body)
    if pblk:
        for slot, variant in re.findall(r'(\w+) = "(\w+)"', pblk.group(1)):
            if slot not in SLOTS:
                errors.append(f"Mutation {name}: unknown anatomy slot '{slot}'")
            elif variant not in SLOTS[slot]:
                errors.append(f"Mutation {name}: {slot} has no variant '{variant}'")
    ab = re.search(r'ability = "(\w+)"', body)
    if ab and ab.group(1) not in ABILITIES:
        errors.append(f"Mutation {name}: unknown ability '{ab.group(1)}'")

active = set(re.findall(r'"(\w+)"', block(mut_src, "Mutations.activeAbilities = {", "}")))
for a in active:
    if a not in ABILITIES:
        errors.append(f"activeAbilities lists unknown ability '{a}'")

# Every active ability must be reachable from at least one mutation.
granted = set(re.findall(r'ability = "(\w+)"', mut_body))
for a in active:
    if a not in granted:
        errors.append(f"Ability '{a}' is active but no mutation grants it")

# ── Biomes ────────────────────────────────────────────────────────────────────
bio_src = read("Biomes.luau")
for m in re.finditer(r'spawnTable = \{(.*?)\}', bio_src, re.S):
    for ing in re.findall(r'"(\w+)"', m.group(1)):
        if ing not in INGREDIENTS:
            errors.append(f"Biome spawnTable references unknown ingredient '{ing}'")
BIOME_IDS = set(re.findall(r'"(\w+)"', block(bio_src, "Biomes.order = {", "}")))
gate_blk = block(bio_src, "Biomes.gates = {", "\n}")
gate_count = 0
for m in re.finditer(r'\{ id = "(\w+)", biome = "(\w+)", abilities = \{([^}]*)\}(.*?)\n\t  prompt', gate_blk, re.S):
    gate_count += 1
    gid, biome, abilities, rest = m.groups()
    if biome not in BIOME_IDS:
        errors.append(f"Gate {gid}: unknown biome '{biome}'")
    abil = re.findall(r'"(\w+)"', abilities)
    if not abil:
        errors.append(f"Gate {gid}: no abilities")
    for a in abil:
        if a not in ABILITIES:
            errors.append(f"Gate {gid}: unknown ability '{a}'")
    rw = re.search(r'reward = \{([^}]*)\}', rest)
    for ing in re.findall(r'"(\w+)"', rw.group(1) if rw else ""):
        if ing not in INGREDIENTS:
            errors.append(f"Gate {gid}: reward '{ing}' is not an ingredient")
if gate_count != len(re.findall(r'\{ id = "', gate_blk)):
    errors.append("Biomes.gates: a gate entry did not parse (format drift?)")
# every active ability should open at least one gate (SPEC §11)
gated = set(re.findall(r'"(\w+)"', " ".join(re.findall(r'abilities = \{([^}]*)\}', gate_blk))))
for a in active:
    if a not in gated:
        warnings.append(f"Ability '{a}' opens no gate in the world")

# Biome trait lists
for m in re.finditer(r'\n\t\ttraits = \{([^}]*)\}', bio_src):
    for t in re.findall(r'"(\w+)"', m.group(1)):
        if t not in TRAITS:
            errors.append(f"Biome traits references unknown trait '{t}'")


# ── Quests ────────────────────────────────────────────────────────────────────
KNOWN_EVENTS = {"fed", "pickup", "trait_new", "mutation_new", "evolved", "gate_opened", "pet", "biome_enter",
                "trial_done", "parade_entered", "parade_vote", "lineage", "named", "sanctuary_upgrade",
                "merchant_buy", "event_joined", "party_joined", "quest_done", "sanctuary_decor"}
q_src = read("Quests.luau")
for m in re.finditer(r'\n\t(\w+) = \{\n(.*?)\n\t\},', q_src, re.S):
    qid, body = m.groups()
    ev = re.search(r'event = "(\w+)"', body)
    if not ev or ev.group(1) not in KNOWN_EVENTS:
        errors.append(f"Quest {qid}: unknown event '{ev.group(1) if ev else None}'")
    inf = re.search(r'influence = "(\w+)"', body)
    if inf and inf.group(1) not in TRAITS:
        errors.append(f"Quest {qid}: unknown trait '{inf.group(1)}'")
    bio = re.search(r'biome = "(\w+)"', body)
    if bio and bio.group(1) not in BIOME_IDS:
        errors.append(f"Quest {qid}: unknown biome '{bio.group(1)}'")

# ── Trials ────────────────────────────────────────────────────────────────────
t_src = read("Trials.luau")
for fav in re.findall(r'favours = \{([^}]*)\}', t_src):
    for t in re.findall(r'"(\w+)"', fav):
        if t not in TRAITS:
            errors.append(f"Trial favours unknown trait '{t}'")

# ── Reachability: can every mutation actually be reached by feeding? ──────────
reachable_max = {t: 0 for t in TRAITS}
for m in re.finditer(r'influences = \{([^}]*)\}', ing_src):
    for k, v in re.findall(r'(\w+) = (\d+)', m.group(1)):
        reachable_max[k] = max(reachable_max.get(k, 0), int(v))
for t, v in reachable_max.items():
    if v == 0:
        warnings.append(f"Trait '{t}' is not produced by ANY ingredient — unreachable")

# ── Economy ───────────────────────────────────────────────────────────────────
eco_src = read("Economy.luau")
CURRENCIES = set(re.findall(r'\n\t(\w+)\s+= \{ display', block(eco_src, "Economy.currencies = {", "\n}")))
if CURRENCIES != {"Coins", "Essence"}:
    errors.append(f"SPEC §28 violated: expected exactly Coins+Essence, got {sorted(CURRENCIES)}")
for m in re.finditer(r'= \{ (Coins|Essence) = \d+(?:, (Coins|Essence) = \d+)? \}', eco_src):
    pass
for cur in set(re.findall(r'\{ ((?:Coins|Essence)) = ', eco_src)):
    if cur not in CURRENCIES:
        errors.append(f"Economy reward uses unknown currency '{cur}'")

# ── Report ────────────────────────────────────────────────────────────────────
print(f"traits={len(TRAITS)} ingredients={len(INGREDIENTS)} mutations={len(MUTATIONS)} "
      f"abilities={len(ABILITIES)} bodies={len(BODIES)} skins={len(SKINS)}")
combos = len(BODIES)
for s in SLOT_ORDER:
    combos *= len(SLOTS[s])
print(f"silhouette space = {combos:,}")

for w in warnings:
    print(f"  WARN  {w}")
if errors:
    print(f"\n{len(errors)} ERROR(S):")
    for e in errors:
        print(f"  FAIL  {e}")
    sys.exit(1)
print("config OK")
