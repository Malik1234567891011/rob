--!strict
-- Shared.Config.Anatomy — SPEC §4 (combinatorial creature system), §73 (modular kits).
--
-- We are NOT making 300 monsters. We make parts that recombine.
--
-- Every variant below is a set of Blender-authored skinned meshes living in
-- ReplicatedStorage.Assets.Creatures.<Family>.Parts, named "<Slot>__<Variant>__<Piece>".
-- Head variants are whole bodies (Assets.Creatures.<Family>.Bodies.<Head>) because the head
-- is sculpted INTO the body — no neck seam. See tools/blender/creatures.py.
--
-- Parts bind to the body's bones BY NAME once welded into its assembly
-- (docs/DECISIONS.md), so a part authored once works on every head of its family.
--
-- ART_DIRECTION "morph, don't accumulate": a slot holds exactly one variant. A mutation
-- that goes aquatic REPLACES the tail; it never stacks a fin on top of the old one.
--
-- SPEC §91 guard: `banned` lists variants that must never coexist, so the generator
-- produces "deliberately ridiculous", never "broken generator".

local Anatomy = {}

-- ═══ BODY FAMILIES (SPEC §60: Cute / Heavy / Weird) ══════════════════════════
Anatomy.bodies = {
	Cute = {
		display = "Cute",
		baseColor = 0xFFB3C6,
		bellyLift = 0.16, -- how much lighter the belly reads than the primary colour
		-- biases fed into temperament generation (SPEC §18)
		temperament = { affectionate = 0.35, curious = 0.25, silly = 0.15 },
		affinity = { Sweet = 1.2, Nature = 1.1, Toy = 1.1 },
		followScale = 1.0,
	},
	Heavy = {
		display = "Heavy",
		baseColor = 0x9AA6B2,
		bellyLift = 0.12,
		temperament = { lazy = 0.3, brave = 0.3, greedy = 0.2 },
		affinity = { Stone = 1.25, Metal = 1.2, Heavy = 1.3 },
		followScale = 1.2,
	},
	Weird = {
		display = "Weird",
		baseColor = 0xB597FF,
		bellyLift = 0.14,
		temperament = { mischievous = 0.3, curious = 0.3, nervous = 0.2 },
		affinity = { Mystic = 1.3, Fungal = 1.2, Dark = 1.2 },
		followScale = 1.05,
	},
}
Anatomy.bodyOrder = { "Cute", "Heavy", "Weird" }

-- ═══ PARTS ═══════════════════════════════════════════════════════════════════
-- `style` overrides piece colour/material for this variant only (keys are piece-name
-- prefixes, eg. Pupil matches PupilL and PupilR).
Anatomy.parts = {

	Head = {
		Round   = { display = "Round Head" },
		Blocky  = { display = "Blocky Head" },
		Snouted = { display = "Snouted" },
		Bulb    = { display = "Bulbous" },
	},

	Eyes = {
		Dot     = { display = "Dot Eyes" },
		Big     = { display = "Big Eyes" },
		Sleepy  = { display = "Sleepy Eyes" },
		Glow    = { display = "Glowing Eyes", style = { Pupil = { color = "trait", material = "Neon" } } },
		Many    = { display = "Too Many Eyes" },
		Screen  = { display = "Screen Face", style = { Screen = { color = 0x8FD6FF, material = "Neon" }, Bezel = { color = 0x3A3A40, material = "SmoothPlastic", skin = false } } },
	},

	Mouth = {
		Smile  = { display = "Smile" },
		Fangs  = { display = "Fangs" },
		Beak   = { display = "Beak", style = { Beak = { color = 0xF2A93B, skin = false } } },
		Gaping = { display = "Gaping Maw", restJaw = 14 },
	},

	Ears = {
		None    = { display = "No Ears" },
		Round   = { display = "Round Ears" },
		Floppy  = { display = "Floppy Ears" },
		Pointy  = { display = "Pointy Ears" },
		Antenna = { display = "Antennae", style = { Bulb = { color = "trait", material = "Neon" }, Stalk = { color = "secondary" } } },
	},

	Horn = {
		None     = { display = "No Horns" },
		Nub      = { display = "Leaf Sprout", style = { Leaf = { color = 0x6CC24A, skin = false }, Stem = { color = 0x4E8F38, skin = false } } },
		Curved   = { display = "Curved Horns", style = { Horn = { color = 0xEFE3CC, skin = false } } },
		Crystal  = { display = "Crystal Antlers", style = { Crystal = { color = "trait", material = "Glass", transparency = 0.15 } } },
		Single   = { display = "Unicorn Horn", style = { Horn = { color = "trait", material = "Glass", transparency = 0.1 } } },
		Crown    = { display = "Tiny Crown", style = { Crown = { color = 0xFFCF3A, material = "Foil", skin = false }, Gem = { color = 0xE0305A, material = "Glass", skin = false } } },
	},

	Back = {
		None     = { display = "Bare Back" },
		Spikes   = { display = "Spines", style = { Spike = { color = "secondary" } } },
		Shell    = { display = "Shell", style = { Shell = { color = "secondary" } } },
		Wings    = { display = "Butterfly Wings", style = { Wing = { color = "trait", transparency = 0.08 } } },
		Fins     = { display = "Back Fin", style = { Fin = { color = "trait" } } },
		Mushroom = { display = "Mushroom Cluster", style = { Cap = { color = "trait" }, Stem = { color = 0xF2E8D5, skin = false } } },
		Screen   = { display = "Belly Screen", style = { Screen = { color = 0x8FD6FF, material = "Neon", skin = false }, Bezel = { color = 0x3A3A40, skin = false } } },
	},

	Tail = {
		None    = { display = "No Tail" },
		Stub    = { display = "Stubby Tail" },
		Long    = { display = "Long Tail" },
		Fluffy  = { display = "Fluffy Tail", style = { Tail = { color = "secondary" } } },
		Bolt    = { display = "Lightning Tail", style = { Tail = { color = "trait", material = "Neon", skin = false } } },
		FishTail= { display = "Fish Tail", style = { Fin = { color = "trait" } } },
	},

	Legs = {
		Stubby = { display = "Stubby Legs" },
		Long   = { display = "Long Legs" },
		Chunky = { display = "Chunky Legs" },
		Noodle = { display = "Noodle Legs" },
	},
}

Anatomy.slotOrder = { "Head", "Eyes", "Mouth", "Ears", "Horn", "Back", "Tail", "Legs" }

-- Default look of each PIECE, matched on the piece-name prefix (the part after the last
-- "__"). Variant `style` entries win over these. `skin = false` means the creature's skin
-- material (Metal, Crystal, Gooey...) is NOT applied: eye whites stay eye whites.
--   color: "primary" | "secondary" | "belly" | "trait" | "dark" | hex
Anatomy.pieceStyle = {
	Main    = { color = "primary" },
	Belly   = { color = "belly" },
	White   = { color = 0xFAF8F2, skin = false },
	Pupil   = { color = 0xFFFFFF, skin = false },
	Shine   = { color = 0xFFFFFF, skin = false },
	Lid     = { color = "primary" },
	Inner   = { color = 0xFFFFFF, skin = false },
	Tongue  = { color = 0xFFFFFF, skin = false },
	Fang    = { color = 0xFFFDF5, skin = false },
	Tooth   = { color = 0xFFFDF5, skin = false },
	Ear     = { color = "primary" },
	Tail    = { color = "primary" },
	FL      = { color = "primary" },
	FR      = { color = "primary" },
	BL      = { color = "primary" },
	BR      = { color = "primary" },
}
Anatomy.defaultPieceStyle = { color = "primary" }

-- Pieces dropped at lower detail levels (SPEC §72 LOD is mandatory).
Anatomy.lodDrop = {
	[2] = { Shine2 = true, Tongue = true, Inner = true },
	[3] = { Shine2 = true, Tongue = true, Inner = true, Shine = true, Lid = true, Fang = true, Tooth = true },
}

-- ═══ SKINS: surface RESPONSE, not tint (ART_DIRECTION "materials become material") ══
-- FORMS: whole-body legendary monsters authored as one rigged model (Assets.Creatures.Forms)
-- instead of assembled from parts. A secret mutation with `form = "<Name>"` turns a monster
-- into its form; everything else (stage scale, animation, follow, abilities) still applies.
-- pieces: mesh-name suffix -> look. The rig uses the Heavy (quadruped) bone names.
Anatomy.forms = {
	VoidFang = {
		display = "Void Fang",
		family = "Heavy",
		scaleMul = 0.62, -- authored at player height; a Mythic stage scale brings it back up
		restJaw = 6, -- a permanent low snarl
		light = 0x2F7BFF,
		pieces = {
			Fur = { color = 0x16161C, material = "Fabric" },
			Glow = { color = 0x2F7BFF, material = "Neon" },
			Eyes = { color = 0xFF2A2A, material = "Neon" },
			Gold = { color = 0xC49A3C, material = "Foil" },
			Dark = { color = 0x0B0B0E, material = "SmoothPlastic" },
		},
	},
}

Anatomy.skins = {
	Soft      = { material = "SmoothPlastic", reflect = 0.0,  transparency = 0 },
	Mossy     = { material = "Grass",         reflect = 0.0,  transparency = 0 },
	Rough     = { material = "Slate",         reflect = 0.0,  transparency = 0 },
	Plated    = { material = "Metal",         reflect = 0.2,  transparency = 0 },
	Polished  = { material = "Foil",          reflect = 0.35, transparency = 0 },
	Faceted   = { material = "Glass",         reflect = 0.25, transparency = 0.12 },
	Frosted   = { material = "Ice",           reflect = 0.1,  transparency = 0.05 },
	-- CrackedLava draws its cracks in the part colour: a grey body reads as black marble,
	-- so ember skin is pulled toward a hot orange (tint/tintMix, SPEC ART: skin is a surface)
	Ember     = { material = "CrackedLava",   reflect = 0.0,  transparency = 0, tint = 0xFF6A2A, tintMix = 0.7 },
	Charged   = { material = "SmoothPlastic", reflect = 0.15, transparency = 0, glow = 0.35 },
	Gooey     = { material = "Glass",         reflect = 0.1,  transparency = 0.22 },
	Spongy    = { material = "Fabric",        reflect = 0.0,  transparency = 0 },
	Wet       = { material = "SmoothPlastic", reflect = 0.22, transparency = 0 },
	Rubber    = { material = "SmoothPlastic", reflect = 0.08, transparency = 0 },
	Plastic   = { material = "Plastic",       reflect = 0.05, transparency = 0 },
	Void      = { material = "SmoothPlastic", reflect = 0.0,  transparency = 0, darken = 0.45 },
	Starlit   = { material = "Glass",         reflect = 0.3,  transparency = 0.05, glow = 0.25 },
	Arcane    = { material = "ForceField",    reflect = 0.1,  transparency = 0 },
	Weathered = { material = "Concrete",      reflect = 0.0,  transparency = 0 },
	Dusky     = { material = "Fabric",        reflect = 0.0,  transparency = 0, darken = 0.2 },
	Acrid     = { material = "SmoothPlastic", reflect = 0.12, transparency = 0, glow = 0.15 },
}

Anatomy.patterns = { "Plain", "Spotted", "Striped", "Patchy", "Gradient" }

-- ═══ COMPATIBILITY RULES (SPEC §91 — no broken-generator sludge) ═════════════
-- If key is present, none of the listed variants may be chosen alongside it.
Anatomy.banned = {
	["Eyes:Screen"] = { "Mouth:Beak", "Mouth:Gaping", "Ears:Floppy" },
	["Head:Blocky"] = { "Ears:Floppy" },
	["Back:Shell"]  = { "Back:Wings" },
	["Legs:Noodle"] = { "Back:Shell" },
	["Mouth:Beak"]  = { "Mouth:Fangs" },
}

function Anatomy.isBanned(slot: string, variant: string, chosen: { [string]: string }): boolean
	for cSlot, cVariant in pairs(chosen) do
		local rules = Anatomy.banned[cSlot .. ":" .. cVariant]
		if rules then
			for _, banned in ipairs(rules) do
				if banned == slot .. ":" .. variant then
					return true
				end
			end
		end
	end
	local own = Anatomy.banned[slot .. ":" .. variant]
	if own then
		for _, banned in ipairs(own) do
			local bSlot, bVariant = string.match(banned, "([^:]+):([^:]+)")
			if bSlot and chosen[bSlot] == bVariant then
				return true
			end
		end
	end
	return false
end

function Anatomy.variantsFor(slot: string): { string }
	local out = {}
	for name in pairs(Anatomy.parts[slot] or {}) do
		table.insert(out, name)
	end
	table.sort(out)
	return out
end

function Anatomy.combinationCount(): number
	local n = 1
	for _, slot in ipairs(Anatomy.slotOrder) do
		n *= #Anatomy.variantsFor(slot)
	end
	return n * #Anatomy.bodyOrder
end

-- Resolve how one piece should look: variant style > piece default > global default.
function Anatomy.styleFor(slot: string, variant: string, piece: string)
	local def = (Anatomy.parts[slot] or {})[variant]
	if def and def.style then
		for prefix, style in pairs(def.style) do
			if string.sub(piece, 1, #prefix) == prefix then
				return style
			end
		end
	end
	for prefix, style in pairs(Anatomy.pieceStyle) do
		if string.sub(piece, 1, #prefix) == prefix then
			return style
		end
	end
	return Anatomy.defaultPieceStyle
end

return Anatomy
