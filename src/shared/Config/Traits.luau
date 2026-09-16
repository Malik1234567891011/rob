--!strict
-- Shared.Config.Traits — the 26 axes of the trait vector.  SPEC §75 (~25 categories).
--
-- DESIGN RULE (SPEC §90): predictable locally, surprising globally.
-- A battery must RELIABLY push Electric. What Electric + Fungal + Flying eventually
-- becomes is allowed to surprise you. So each trait declares its own visual
-- consequence, and Mutations.luau owns the surprising part.

local Traits = {}

-- tintWeight: how strongly this trait drags body colour when dominant (0..1)
-- bias:       which anatomy slot this trait tends to express through
Traits.all = {
	-- ── Elements ────────────────────────────────────────────────────────────
	Fire      = { display = "Fiery",     emoji = "🔥", category = "Element",  color = 0xFF5A1F, tintWeight = 0.85, bias = "Back",  skin = "Ember",   blurb = "Runs hot. Leaves scorch marks." },
	Electric  = { display = "Electric",  emoji = "⚡", category = "Element",  color = 0xFFD52E, tintWeight = 0.80, bias = "Tail",  skin = "Charged", blurb = "Pupils flicker like bad wiring." },
	Water     = { display = "Aquatic",   emoji = "💧", category = "Element",  color = 0x3FA9F5, tintWeight = 0.70, bias = "Tail",  skin = "Wet",     blurb = "Never fully dries off." },
	Air       = { display = "Airy",      emoji = "🌬️", category = "Element",  color = 0xCFEAFF, tintWeight = 0.45, bias = "Back",  skin = "Soft",    blurb = "Weighs less than it looks." },
	Nature    = { display = "Leafy",     emoji = "🌿", category = "Element",  color = 0x5FBF52, tintWeight = 0.75, bias = "Head",  skin = "Mossy",   blurb = "Small things grow on it." },
	Crystal   = { display = "Crystal",   emoji = "💎", category = "Element",  color = 0x9BE8FF, tintWeight = 0.65, bias = "Horn",  skin = "Faceted", blurb = "Clinks when it walks." },
	Fungal    = { display = "Fungal",    emoji = "🍄", category = "Element",  color = 0xC96FA8, tintWeight = 0.70, bias = "Back",  skin = "Spongy",  blurb = "Prefers the dark. Spreads." },
	Cold      = { display = "Frozen",    emoji = "❄️", category = "Element",  color = 0xBFE9FF, tintWeight = 0.60, bias = "Horn",  skin = "Frosted", blurb = "The air around it goes quiet." },
	Stone     = { display = "Stony",     emoji = "🪨", category = "Element",  color = 0x8C8478, tintWeight = 0.70, bias = "Legs",  skin = "Rough",   blurb = "Heavy footsteps. Cracks pavement." },
	Celestial = { display = "Celestial", emoji = "✨", category = "Element",  color = 0xFFF0A8, tintWeight = 0.55, bias = "Horn",  skin = "Starlit", blurb = "Something about it is far away." },
	Dark      = { display = "Shadowed",  emoji = "🌑", category = "Element",  color = 0x4A4260, tintWeight = 0.80, bias = "Eyes",  skin = "Void",    blurb = "Light gets a little confused near it." },
	Mystic    = { display = "Mystic",    emoji = "🔮", category = "Element",  color = 0xA77BFF, tintWeight = 0.60, bias = "Eyes",  skin = "Arcane",  blurb = "Knows something you don't." },

	-- ── Materials ───────────────────────────────────────────────────────────
	Metal      = { display = "Metallic",   emoji = "🔩", category = "Material", color = 0xA8B0BA, tintWeight = 0.70, bias = "Legs", skin = "Plated",  blurb = "Parts of it are definitely not organic." },
	Artificial = { display = "Artificial", emoji = "📺", category = "Material", color = 0xE0E0E0, tintWeight = 0.40, bias = "Head", skin = "Plastic", blurb = "Somebody manufactured part of this creature." },
	Toy        = { display = "Toylike",    emoji = "🦆", category = "Material", color = 0xFFD93D, tintWeight = 0.75, bias = "Head", skin = "Rubber",  blurb = "Squeaks. Nobody knows why." },
	Shiny      = { display = "Shiny",      emoji = "🪞", category = "Material", color = 0xFFF4C2, tintWeight = 0.35, bias = "Back", skin = "Polished",blurb = "Catches every light in the room." },
	Slimy      = { display = "Slimy",      emoji = "🫧", category = "Material", color = 0x7FE3A8, tintWeight = 0.65, bias = "Tail", skin = "Gooey",   blurb = "Leaves a trail. Sorry." },

	-- ── Qualities ───────────────────────────────────────────────────────────
	Sweet    = { display = "Sweet",     emoji = "🍓", category = "Quality", color = 0xFF8FB0, tintWeight = 0.70, bias = "Ears", skin = "Soft",    blurb = "Smells faintly of dessert." },
	Toxic    = { display = "Toxic",     emoji = "☣️", category = "Quality", color = 0xA6E22E, tintWeight = 0.75, bias = "Back", skin = "Acrid",   blurb = "Do not lick. It will lick you." },
	Energy   = { display = "Energetic", emoji = "💥", category = "Quality", color = 0xFFA63D, tintWeight = 0.30, bias = "Legs", skin = "Soft",    blurb = "Cannot sit still." },
	Silly    = { display = "Silly",     emoji = "🤪", category = "Quality", color = 0xFF7BD5, tintWeight = 0.40, bias = "Eyes", skin = "Soft",    blurb = "Something has gone wrong, delightfully." },
	Night    = { display = "Nocturnal", emoji = "🌙", category = "Quality", color = 0x5C6BC0, tintWeight = 0.55, bias = "Eyes", skin = "Dusky",   blurb = "Wakes up when you log off." },
	Ancient  = { display = "Ancient",   emoji = "🦴", category = "Quality", color = 0xD6C9A8, tintWeight = 0.50, bias = "Horn", skin = "Weathered",blurb = "Older than it has any right to be." },
	Heavy    = { display = "Heavy",     emoji = "🏋️", category = "Quality", color = 0x7A7268, tintWeight = 0.45, bias = "Legs", skin = "Rough",   blurb = "The ground notices." },
	Flexible = { display = "Flexible",  emoji = "🪱", category = "Quality", color = 0xC2E86B, tintWeight = 0.30, bias = "Tail", skin = "Soft",    blurb = "Goes through gaps it should not." },
	Round    = { display = "Round",     emoji = "⚪", category = "Quality", color = 0xFFE8C2, tintWeight = 0.25, bias = "Head", skin = "Soft",    blurb = "Structurally, a ball." },
}

-- Stable display order (pairs() order is not deterministic and this drives UI).
Traits.order = {
	"Fire", "Electric", "Water", "Air", "Nature", "Crystal", "Fungal", "Cold",
	"Stone", "Celestial", "Dark", "Mystic",
	"Metal", "Artificial", "Toy", "Shiny", "Slimy",
	"Sweet", "Toxic", "Energy", "Silly", "Night", "Ancient", "Heavy", "Flexible", "Round",
}

-- Threshold at which a trait becomes VISIBLE and gets announced to the player.
-- Deliberately low so the very first apple produces "NEW TRAIT DISCOVERED" (SPEC §8, 0:16).
Traits.VISIBLE_AT = 3

function Traits.get(id: string)
	return Traits.all[id]
end

function Traits.exists(id: string): boolean
	return Traits.all[id] ~= nil
end

function Traits.display(id: string): string
	local t = Traits.all[id]
	return t and (t.emoji .. " " .. t.display) or id
end

return Traits
