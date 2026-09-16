--!strict
-- OfflineService — SPEC §17 "WHILE YOU WERE GONE..."
--
-- The hard rule: NEVER complete a major evolution offline. The emotionally important
-- reveal waits for the player. What they come back to is curiosity, not a number:
--   "Mochi found something strange near the cave..."
-- not
--   "+$87,294 offline income."

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local Rng = require(Shared.Util:WaitForChild("Rng"))

local PlayerDataService = require(script.Parent.PlayerDataService)

local OfflineService = {}

local MIN_AWAY = 120          -- under two minutes is not "away"
local MAX_CREDITED_HOURS = 14 -- generous cap; this is a hook, not an idle game

-- Each line is a question the player wants answered by walking over and looking.
local FINDS = {
	{ kind = "object",  text = "%s dug something up near the fence. It is sitting beside their bed." },
	{ kind = "object",  text = "%s came back from the treeline carrying this. Nobody knows what it is." },
	{ kind = "skill",   text = "%s has been practising something. It will not show you yet." },
	{ kind = "social",  text = "%s spent the whole time following the big one around." },
	{ kind = "trace",   text = "There are footprints behind the shack. They are not %s's." },
	{ kind = "object",  text = "%s found something strange near the cave..." },
	{ kind = "mood",    text = "%s slept the entire time. Not sorry about it." },
	{ kind = "object",  text = "%s left a present for you. It is slightly damp." },
}

function OfflineService.report(player: Player, profile)
	local away = os.time() - (profile.lastSeen or os.time())
	if away < MIN_AWAY or profile.activeCreature == 0 then
		return nil
	end

	local genome = profile.creatures[profile.activeCreature]
	if not genome then
		return nil
	end

	local hours = math.min(away / 3600, MAX_CREDITED_HOURS)
	local rng = Rng.new(os.time() % 100000 + player.UserId)
	local name = genome.name or "Your monster"

	-- it forages while you are gone; it does NOT evolve
	local gathered = {}
	local picks = math.clamp(math.floor(hours * 1.6) + 1, 1, 8)
	local pool = Ingredients.byBiome("Meadow")
	for _ = 1, picks do
		local id = rng:pick(pool)
		gathered[id] = (gathered[id] or 0) + 1
		profile.inventory[id] = (profile.inventory[id] or 0) + 1
	end

	local find = rng:pick(FINDS)
	local coins = math.floor(hours * 18)
	profile.coins += coins

	local lines = {}
	for id, n in pairs(gathered) do
		local def = Ingredients.get(id)
		if def then
			table.insert(lines, string.format("%s %s x%d", def.emoji, def.display, n))
		end
	end
	table.sort(lines)

	return {
		awaySeconds = away,
		headline = string.format(find.text, name),
		kind = find.kind,
		gathered = lines,
		coins = coins,
		-- explicit, so nobody "optimises" this into an idle game later
		evolvedOffline = false,
	}
end

function OfflineService.start()
	PlayerDataService.onLoaded(function(player, profile)
		local report = OfflineService.report(player, profile)
		if report then
			task.delay(2.5, function()
				if player.Parent then
					Net.event("OfflineReport"):FireClient(player, report)
					PlayerDataService.sync(player)
				end
			end)
		end
	end)
	print("[Offline] ready")
end

return OfflineService
