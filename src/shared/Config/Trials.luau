--!strict
-- Shared.Config.Trials — SPEC §21 Creature Trials, §22 "different builds must be valid".
--
-- Short (60–150 s), no 30-minute commitment. Enough skill that players care, enough
-- creature-construction that builds matter. Each trial favours DIFFERENT traits, so there
-- is no objectively correct monster.
--
-- A trial happens in an arena under Workspace.World.Trials.<id>, laid out by markers the
-- world builder places (tools/studio/build_trials.luau). The avatar runs the course; the
-- creature's traits and abilities change the avatar while inside.

local Trials = {}

Trials.all = {
	Race = {
		display = "Monster Dash", emoji = "🏁", order = 1,
		blurb = "Two laps. Fast legs win, but gliders take the shortcut.",
		duration = 120, minStage = 2, maxPlayers = 8,
		favours = { "Energy", "Flexible", "Air" },
		scoring = "time", laps = 2,
	},
	Smash = {
		display = "Smash Party", emoji = "💥", order = 2,
		blurb = "90 seconds. Break everything. Heavy monsters hit harder.",
		duration = 90, minStage = 2, maxPlayers = 8,
		favours = { "Heavy", "Stone", "Metal" },
		scoring = "points",
	},
	Treasure = {
		display = "Treasure Sniff", emoji = "🧭", order = 3,
		blurb = "Find the buried chests. Mysterious monsters sense them from further away.",
		duration = 90, minStage = 2, maxPlayers = 8,
		favours = { "Mystic", "Night", "Crystal" },
		scoring = "points", chests = 10,
	},
	Obstacle = {
		display = "Obstacle Chaos", emoji = "🤸", order = 4,
		blurb = "Hurdles, bumpers, beams. Tiny, Sticky and Glide monsters find secret routes.",
		duration = 150, minStage = 3, maxPlayers = 8,
		favours = { "Flexible", "Slimy", "Air" },
		scoring = "time",
	},
	Swim = {
		display = "Reef Swim", emoji = "🌊", order = 5,
		blurb = "Through the rings, under the reef. Aquatic monsters fly through water.",
		duration = 120, minStage = 2, maxPlayers = 8,
		favours = { "Water", "Flexible" },
		scoring = "time", update = 1,
	},
}

Trials.order = { "Race", "Smash", "Treasure", "Obstacle", "Swim" }

Trials.QUEUE_SECONDS = 20       -- lobby countdown once the first player joins
Trials.RESULTS_SECONDS = 8

-- Avatar stats inside a trial, from the creature's effective traits. Clamped so a build
-- helps a lot without making anyone unable to play (SPEC §12: never punish a choice).
function Trials.stats(traits: { [string]: number }, abilities: { [string]: boolean }, stage: number)
	local function t(name)
		return math.max(0, traits[name] or 0)
	end
	local speed = 18 + t("Energy") * 0.07 + t("Flexible") * 0.05 + t("Air") * 0.03 - t("Heavy") * 0.03 + stage * 0.6
	local jump = 50 + t("Air") * 0.25 + t("Flexible") * 0.1 - t("Heavy") * 0.08
	local strength = 1 + t("Heavy") * 0.025 + t("Stone") * 0.015 + t("Metal") * 0.012 + (abilities.Giant and 1.5 or 0)
	local senses = 30 + t("Mystic") * 0.6 + t("Night") * 0.4 + t("Crystal") * 0.4 + (abilities.Light and 20 or 0)
	local swim = 16 + t("Water") * 0.1 + (abilities.Aquatic and 12 or 0)
	return {
		speed = math.clamp(speed, 16, 30),
		jump = math.clamp(jump, 44, 72),
		strength = math.clamp(strength, 1, 6),
		senses = math.clamp(senses, 30, 120),
		swim = math.clamp(swim, 14, 34),
		glide = abilities.Glide == true,
		sticky = abilities.Sticky == true,
		tiny = abilities.Tiny == true,
	}
end

function Trials.get(id: string)
	return Trials.all[id]
end

return Trials
