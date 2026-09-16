--!strict
-- Shared.Config.Anatomy — SPEC §4 (combinatorial creature system), §73 (modular kits).
--
-- We are NOT making 300 monsters. We make parts that recombine.
-- 3 bodies x 4 heads x 6 eyes x 4 mouths x 5 ears x 6 horns x 7 backs x 6 tails x 4 legs
--   = ~1.45M silhouettes before colour, pattern, size and mutation overlays.
--
-- A part variant is a list of PIECES the builder instantiates from primitives:
--   shape     : Ball | Block | Cylinder | Wedge
--   size      : {x,y,z} in body-relative units (scaled by creature size)
--   offset    : {x,y,z} from the attachment point
--   rot       : {rx,ry,rz} degrees
--   colorMode : "primary" | "secondary" | "trait" | <hex number>
--   material  : Roblox material name (default SmoothPlastic)
--   mirror    : duplicate the whole variant mirrored across X
--
-- SPEC §91 guard: `banned` lists variants that must never coexist, so the
-- generator produces "deliberately ridiculous", never "broken generator".

local Anatomy = {}

-- ═══ BODY FAMILIES (SPEC §60: Cute / Heavy / Weird) ══════════════════════════
Anatomy.bodies = {
	Cute = {
		display = "Cute",
		torso = { shape = "Ball", size = { 2.3, 2.1, 2.7 } },
		headScale = 1.20, headForward = 1.45, headLift = 0.75,
		legLength = 0.85, legSpread = 0.62,
		baseColor = 0xFFC9D6,
		-- biases fed into temperament generation (SPEC §18)
		temperament = { affectionate = 0.35, curious = 0.25, silly = 0.15 },
		affinity = { Sweet = 1.2, Nature = 1.1, Toy = 1.1 },
	},
	Heavy = {
		display = "Heavy",
		torso = { shape = "Block", size = { 3.1, 2.4, 3.6 } },
		headScale = 0.92, headForward = 1.95, headLift = 0.45,
		legLength = 1.15, legSpread = 0.86,
		baseColor = 0x8C8478,
		temperament = { lazy = 0.3, brave = 0.3, greedy = 0.2 },
		affinity = { Stone = 1.25, Metal = 1.2, Heavy = 1.3 },
	},
	Weird = {
		display = "Weird",
		torso = { shape = "Ball", size = { 2.0, 2.8, 2.2 } },
		headScale = 1.05, headForward = 1.25, headLift = 1.35,
		legLength = 1.45, legSpread = 0.48,
		baseColor = 0xA77BFF,
		temperament = { mischievous = 0.3, curious = 0.3, nervous = 0.2 },
		affinity = { Mystic = 1.3, Fungal = 1.2, Dark = 1.2 },
	},
}
Anatomy.bodyOrder = { "Cute", "Heavy", "Weird" }

-- ═══ PARTS ═══════════════════════════════════════════════════════════════════
Anatomy.parts = {

	Head = {
		Round   = { display = "Round Head",  pieces = { { shape = "Ball",     size = {1.0,1.0,1.0},   offset = {0,0,0}, colorMode = "primary" } } },
		Blocky  = { display = "Blocky Head", pieces = { { shape = "Block",    size = {0.95,0.95,1.0}, offset = {0,0,0}, colorMode = "primary" } } },
		Snouted = { display = "Snouted",     pieces = {
			{ shape = "Ball",  size = {1.0,1.0,1.0},    offset = {0,0,0},          colorMode = "primary" },
			{ shape = "Ball",  size = {0.55,0.45,0.6},  offset = {0,-0.18,-0.62},  colorMode = "secondary" } } },
		Bulb    = { display = "Bulbous",     pieces = {
			{ shape = "Ball",  size = {1.15,0.9,1.05},  offset = {0,0.05,0},       colorMode = "primary" },
			{ shape = "Ball",  size = {0.5,0.5,0.5},    offset = {0,0.62,0},       colorMode = "secondary" } } },
	},

	Eyes = {
		Dot     = { display = "Dot Eyes",    mirror = true, pieces = {
			{ shape = "Ball", size = {0.22,0.22,0.16}, offset = {0.28,0.12,-0.46}, colorMode = 0x1A1A1A } } },
		Big     = { display = "Big Eyes",    mirror = true, pieces = {
			{ shape = "Ball", size = {0.46,0.5,0.3},   offset = {0.27,0.12,-0.42}, colorMode = 0xFFFFFF },
			{ shape = "Ball", size = {0.24,0.26,0.2},  offset = {0.27,0.10,-0.52}, colorMode = 0x1A1A1A } } },
		Sleepy  = { display = "Sleepy Eyes", mirror = true, pieces = {
			{ shape = "Block", size = {0.36,0.07,0.16}, offset = {0.27,0.14,-0.47}, colorMode = 0x1A1A1A } } },
		Glow    = { display = "Glowing Eyes", mirror = true, pieces = {
			{ shape = "Ball", size = {0.3,0.34,0.22}, offset = {0.27,0.13,-0.45}, colorMode = "trait", material = "Neon" } } },
		Many    = { display = "Too Many Eyes", pieces = {
			{ shape = "Ball", size = {0.3,0.32,0.2},  offset = {0.28,0.16,-0.44}, colorMode = 0xFFFFFF },
			{ shape = "Ball", size = {0.3,0.32,0.2},  offset = {-0.28,0.16,-0.44},colorMode = 0xFFFFFF },
			{ shape = "Ball", size = {0.22,0.24,0.16},offset = {0,0.44,-0.42},    colorMode = 0xFFFFFF },
			{ shape = "Ball", size = {0.2,0.2,0.14},  offset = {0.44,-0.14,-0.36},colorMode = 0xFFFFFF },
			{ shape = "Ball", size = {0.2,0.2,0.14},  offset = {-0.44,-0.14,-0.36},colorMode = 0xFFFFFF } } },
		Screen  = { display = "Screen Face", pieces = {
			{ shape = "Block", size = {0.78,0.6,0.1}, offset = {0,0.1,-0.5},  colorMode = 0x8FD6FF, material = "Neon" },
			{ shape = "Block", size = {0.84,0.66,0.08},offset = {0,0.1,-0.46},colorMode = 0x3A3A3A } } },
	},

	Mouth = {
		Smile  = { display = "Smile",     pieces = { { shape = "Block", size = {0.42,0.08,0.1}, offset = {0,-0.28,-0.48}, colorMode = 0x2A1A1A } } },
		Fangs  = { display = "Fangs",     pieces = {
			{ shape = "Block", size = {0.46,0.1,0.1},  offset = {0,-0.28,-0.48}, colorMode = 0x2A1A1A },
			{ shape = "Wedge", size = {0.1,0.18,0.1},  offset = {0.14,-0.36,-0.5}, colorMode = 0xFFFFFF },
			{ shape = "Wedge", size = {0.1,0.18,0.1},  offset = {-0.14,-0.36,-0.5},colorMode = 0xFFFFFF } } },
		Beak   = { display = "Beak",      pieces = { { shape = "Wedge", size = {0.3,0.26,0.5}, offset = {0,-0.22,-0.66}, rot = {0,180,0}, colorMode = 0xE8A81F } } },
		Gaping = { display = "Gaping Maw", pieces = {
			{ shape = "Ball",  size = {0.6,0.4,0.28}, offset = {0,-0.26,-0.46}, colorMode = 0x1A0E12 },
			{ shape = "Wedge", size = {0.08,0.2,0.08},offset = {0.2,-0.14,-0.56}, colorMode = 0xFFFFFF },
			{ shape = "Wedge", size = {0.08,0.2,0.08},offset = {-0.2,-0.14,-0.56},colorMode = 0xFFFFFF } } },
	},

	Ears = {
		None    = { display = "No Ears", pieces = {} },
		Round   = { display = "Round Ears",  mirror = true, pieces = {
			{ shape = "Ball", size = {0.42,0.44,0.22}, offset = {0.46,0.42,0.02}, colorMode = "primary" } } },
		Floppy  = { display = "Floppy Ears", mirror = true, pieces = {
			{ shape = "Block", size = {0.2,0.62,0.34}, offset = {0.5,0.18,0.02}, rot = {0,0,18}, colorMode = "secondary" } } },
		Pointy  = { display = "Pointy Ears", mirror = true, pieces = {
			{ shape = "Wedge", size = {0.2,0.6,0.26}, offset = {0.42,0.6,0.05}, rot = {0,0,-12}, colorMode = "primary" } } },
		Antenna = { display = "Antennae",    mirror = true, pieces = {
			{ shape = "Cylinder", size = {0.07,0.7,0.07}, offset = {0.22,0.72,0}, rot = {0,0,-16}, colorMode = "secondary" },
			{ shape = "Ball",     size = {0.2,0.2,0.2},   offset = {0.32,1.06,0}, colorMode = "trait", material = "Neon" } } },
	},

	Horn = {
		None     = { display = "No Horns", pieces = {} },
		Nub      = { display = "Little Nubs", mirror = true, pieces = {
			{ shape = "Ball", size = {0.22,0.26,0.22}, offset = {0.24,0.62,-0.1}, colorMode = "secondary" } } },
		Curved   = { display = "Curved Horns", mirror = true, pieces = {
			{ shape = "Cylinder", size = {0.16,0.5,0.16}, offset = {0.28,0.7,-0.05}, rot = {0,0,-22}, colorMode = "secondary" },
			{ shape = "Cylinder", size = {0.12,0.4,0.12}, offset = {0.46,1.0,-0.05}, rot = {0,0,-52}, colorMode = "secondary" } } },
		Crystal  = { display = "Crystal Antlers", mirror = true, pieces = {
			{ shape = "Wedge", size = {0.14,0.62,0.14}, offset = {0.26,0.78,-0.06}, rot = {0,0,-14}, colorMode = "trait", material = "Glass" },
			{ shape = "Wedge", size = {0.1,0.42,0.1},   offset = {0.44,1.12,-0.12}, rot = {0,0,-40}, colorMode = "trait", material = "Glass" },
			{ shape = "Wedge", size = {0.1,0.38,0.1},   offset = {0.16,1.14,0.1},   rot = {0,0,12},  colorMode = "trait", material = "Glass" } } },
		Single   = { display = "Unicorn Horn", pieces = {
			{ shape = "Wedge", size = {0.18,0.86,0.18}, offset = {0,0.74,-0.2}, colorMode = "trait", material = "Glass" } } },
		Crown    = { display = "Tiny Crown", pieces = {
			{ shape = "Cylinder", size = {0.52,0.14,0.52}, offset = {0,0.66,0}, colorMode = 0xFFD52E, material = "Metal" },
			{ shape = "Wedge", size = {0.1,0.22,0.1}, offset = {0.2,0.8,0},  colorMode = 0xFFD52E, material = "Metal" },
			{ shape = "Wedge", size = {0.1,0.22,0.1}, offset = {-0.2,0.8,0}, colorMode = 0xFFD52E, material = "Metal" },
			{ shape = "Wedge", size = {0.1,0.26,0.1}, offset = {0,0.82,-0.2},colorMode = 0xFFD52E, material = "Metal" } } },
	},

	Back = {
		None     = { display = "Bare Back", pieces = {} },
		Spikes   = { display = "Spines", pieces = {
			{ shape = "Wedge", size = {0.18,0.46,0.3}, offset = {0,0.62,0.34},  colorMode = "secondary" },
			{ shape = "Wedge", size = {0.2,0.56,0.32}, offset = {0,0.66,-0.04}, colorMode = "secondary" },
			{ shape = "Wedge", size = {0.16,0.4,0.28}, offset = {0,0.58,-0.42}, colorMode = "secondary" } } },
		Shell    = { display = "Shell", pieces = {
			{ shape = "Ball", size = {1.5,0.9,1.7}, offset = {0,0.5,0}, colorMode = "secondary" } } },
		Wings    = { display = "Butterfly Wings", mirror = true, pieces = {
			{ shape = "Block", size = {0.08,1.5,1.7}, offset = {0.72,0.75,0.2},  rot = {0,-22,16}, colorMode = "trait" },
			{ shape = "Block", size = {0.07,1.0,1.1}, offset = {0.82,0.2,-0.55}, rot = {0,-26,10}, colorMode = "secondary" } } },
		Fins     = { display = "Back Fin", pieces = {
			{ shape = "Wedge", size = {0.12,0.85,1.5}, offset = {0,0.72,0.1}, colorMode = "trait" } } },
		Mushroom = { display = "Mushroom Cluster", pieces = {
			{ shape = "Cylinder", size = {0.14,0.34,0.14}, offset = {0.3,0.62,0.2},   colorMode = 0xF0E6D2 },
			{ shape = "Ball",     size = {0.6,0.34,0.6},   offset = {0.3,0.82,0.2},   colorMode = "trait" },
			{ shape = "Cylinder", size = {0.11,0.26,0.11}, offset = {-0.24,0.6,-0.3}, colorMode = 0xF0E6D2 },
			{ shape = "Ball",     size = {0.46,0.26,0.46}, offset = {-0.24,0.75,-0.3},colorMode = "trait" } } },
		Screen   = { display = "Belly Screen", pieces = {
			{ shape = "Block", size = {1.15,0.95,0.12}, offset = {0,0.0,-0.82}, colorMode = 0x2E2E2E },
			{ shape = "Block", size = {0.95,0.75,0.08}, offset = {0,0.0,-0.9},  colorMode = 0x8FD6FF, material = "Neon" } } },
	},

	Tail = {
		None    = { display = "No Tail", pieces = {} },
		Stub    = { display = "Stubby Tail", pieces = {
			{ shape = "Ball", size = {0.42,0.42,0.5}, offset = {0,0.1,0.95}, colorMode = "primary" } } },
		Long    = { display = "Long Tail", pieces = {
			{ shape = "Cylinder", size = {0.26,0.8,0.26}, offset = {0,0.2,1.0},  rot = {70,0,0}, colorMode = "primary" },
			{ shape = "Cylinder", size = {0.2,0.7,0.2},   offset = {0,0.52,1.5}, rot = {48,0,0}, colorMode = "primary" },
			{ shape = "Ball",     size = {0.26,0.26,0.26},offset = {0,0.8,1.8},  colorMode = "secondary" } } },
		Fluffy  = { display = "Fluffy Tail", pieces = {
			{ shape = "Ball", size = {0.75,0.8,0.75}, offset = {0,0.45,1.05}, colorMode = "secondary" },
			{ shape = "Ball", size = {0.5,0.55,0.5},  offset = {0,0.85,1.2},  colorMode = "secondary" } } },
		Bolt    = { display = "Lightning Tail", pieces = {
			{ shape = "Wedge", size = {0.16,0.6,0.3}, offset = {0,0.3,1.0},  rot = {0,0,22},  colorMode = "trait", material = "Neon" },
			{ shape = "Wedge", size = {0.14,0.5,0.26},offset = {0,0.72,1.25},rot = {0,0,-30}, colorMode = "trait", material = "Neon" } } },
		FishTail= { display = "Fish Tail", pieces = {
			{ shape = "Wedge", size = {0.12,0.9,0.8},  offset = {0,0.3,1.15}, rot = {0,0,0},   colorMode = "trait" },
			{ shape = "Wedge", size = {0.12,0.7,0.6},  offset = {0,0.2,1.35}, rot = {0,180,0}, colorMode = "trait" } } },
	},

	Legs = {
		Stubby = { display = "Stubby Legs", mirror = true, pieces = {
			{ shape = "Cylinder", size = {0.4,0.5,0.4}, offset = {0.5,-0.45,-0.55}, colorMode = "secondary" },
			{ shape = "Cylinder", size = {0.4,0.5,0.4}, offset = {0.5,-0.45,0.6},   colorMode = "secondary" } } },
		Long   = { display = "Long Legs", mirror = true, pieces = {
			{ shape = "Cylinder", size = {0.26,1.3,0.26}, offset = {0.46,-0.85,-0.5}, colorMode = "secondary" },
			{ shape = "Cylinder", size = {0.26,1.3,0.26}, offset = {0.46,-0.85,0.55}, colorMode = "secondary" } } },
		Chunky = { display = "Chunky Legs", mirror = true, pieces = {
			{ shape = "Block", size = {0.62,0.7,0.62}, offset = {0.62,-0.6,-0.7}, colorMode = "secondary" },
			{ shape = "Block", size = {0.62,0.7,0.62}, offset = {0.62,-0.6,0.75}, colorMode = "secondary" } } },
		Noodle = { display = "Noodle Legs", mirror = true, pieces = {
			{ shape = "Cylinder", size = {0.16,1.5,0.16}, offset = {0.4,-0.95,-0.4}, rot = {0,0,8},  colorMode = "secondary" },
			{ shape = "Cylinder", size = {0.16,1.5,0.16}, offset = {0.44,-0.95,0.5}, rot = {0,0,-8}, colorMode = "secondary" } } },
	},
}

Anatomy.slotOrder = { "Head", "Eyes", "Mouth", "Ears", "Horn", "Back", "Tail", "Legs" }

-- ═══ SKINS & PATTERNS ════════════════════════════════════════════════════════
Anatomy.skins = {
	Soft      = { material = "SmoothPlastic", reflect = 0.0,  transparency = 0 },
	Mossy     = { material = "Grass",         reflect = 0.0,  transparency = 0 },
	Rough     = { material = "Slate",         reflect = 0.0,  transparency = 0 },
	Plated    = { material = "Metal",         reflect = 0.35, transparency = 0 },
	Polished  = { material = "Metal",         reflect = 0.6,  transparency = 0 },
	Faceted   = { material = "Glass",         reflect = 0.4,  transparency = 0.25 },
	Frosted   = { material = "Glacier",       reflect = 0.2,  transparency = 0.1 },
	Ember     = { material = "Neon",          reflect = 0.0,  transparency = 0 },
	Charged   = { material = "Neon",          reflect = 0.0,  transparency = 0 },
	Gooey     = { material = "Glass",         reflect = 0.15, transparency = 0.3 },
	Spongy    = { material = "Fabric",        reflect = 0.0,  transparency = 0 },
	Wet       = { material = "Glass",         reflect = 0.3,  transparency = 0.15 },
	Rubber    = { material = "SmoothPlastic", reflect = 0.1,  transparency = 0 },
	Plastic   = { material = "Plastic",       reflect = 0.05, transparency = 0 },
	Void      = { material = "Neon",          reflect = 0.0,  transparency = 0 },
	Starlit   = { material = "Neon",          reflect = 0.0,  transparency = 0 },
	Arcane    = { material = "ForceField",    reflect = 0.2,  transparency = 0.15 },
	Weathered = { material = "Concrete",      reflect = 0.0,  transparency = 0 },
	Dusky     = { material = "Fabric",        reflect = 0.0,  transparency = 0 },
	Acrid     = { material = "Neon",          reflect = 0.0,  transparency = 0 },
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

return Anatomy
