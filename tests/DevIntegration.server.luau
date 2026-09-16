-- DevIntegration — drives the real server API end to end for the playtest player.
-- We assert on STATE, not on screenshots: query the profile, not the pixels.
--
-- Last run: 33 passed, 0 failed.
--
-- NOTE: two assertions here were once passing for the WRONG reason. Feeding is
-- rate-limited, so an ownership check issued too soon returns "too fast" and never
-- tests ownership at all. Assert on the specific reason string, never just `not ok`.

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services.PlayerDataService)
local FeedingService = require(Services.FeedingService)
local FtueService = require(Services.FtueService)
local CreatureService = require(Services.CreatureService)
local LineageService = require(Services.LineageService)
local AnalyticsService = require(Services.AnalyticsService)
local DiscoveryService = require(Services.DiscoveryService)

local Shared = ReplicatedStorage:WaitForChild("Shared")
local CreatureBuilder = require(Shared.CreatureBuilder)
local Progression = require(Shared.Config.Progression)
local Mutations = require(Shared.Config.Mutations)

local TAG = "[ITEST]"
local pass, fail = 0, 0

local function check(name, condition, detail)
	if condition then
		pass += 1
		print(string.format("%s  PASS  %-42s %s", TAG, name, detail or ""))
	else
		fail += 1
		warn(string.format("%s  FAIL  %-42s %s", TAG, name, detail or ""))
	end
end

local function give(profile, id, n)
	profile.inventory[id] = (profile.inventory[id] or 0) + n
end

local function feedN(player, id, n)
	local ok = 0
	for _ = 1, n do
		local result = FeedingService.feed(player, id)
		if result.ok then ok += 1 end
		task.wait(0.4) -- feeding is rate-limited on purpose; wait like a player
	end
	return ok
end

local function run(player)
	task.wait(4)
	local profile = PlayerDataService.get(player)
	check("profile exists", profile ~= nil)
	if not profile then return end

	local eggResult = FtueService.pickEgg(player, 1)
	check("egg pick succeeds", eggResult.ok == true, eggResult.reason or "")
	local genome = PlayerDataService.activeCreature(player)
	check("creature created", genome ~= nil)
	if not genome then return end
	check("creature starts at Baby", genome.stage == 1, "stage=" .. tostring(genome.stage))
	check("creature model spawned", CreatureService.get(player) ~= nil)
	check("baby starts bare (Horn)", genome.parts.Horn == "None", genome.parts.Horn)

	-- NON-NEGOTIABLE #2: one apple must visibly change the body
	give(profile, "Apple", 1)
	local fedOk = FeedingService.feed(player, "Apple")
	check("first feed accepted", fedOk.ok == true, fedOk.reason or "")
	check("Sprout fired on FIRST apple", genome.mutations.Sprout == true)
	check("Nature trait discovered", profile.discovered.traits.Nature == true)
	check("Apple recorded in book", profile.discovered.ingredients.Apple == true)
	check("coins awarded for discovery", profile.coins > 0, "coins=" .. profile.coins)

	-- server authority: wait past the rate limit or this tests the wrong thing
	task.wait(0.5)
	local cheat = FeedingService.feed(player, "Meteorite")
	check("cannot feed unowned item", cheat.ok == false and cheat.reason == "not owned",
		"reason=" .. tostring(cheat.reason))
	task.wait(0.5)
	give(profile, "Apple", 2) -- must actually OWN them, or this retests ownership
	local spam1 = FeedingService.feed(player, "Apple")
	local spam2 = FeedingService.feed(player, "Apple")
	check("first of the pair is accepted", spam1.ok == true, spam1.reason or "")
	check("feed spam is rate limited", spam2.ok == false and spam2.reason == "too fast",
		"reason=" .. tostring(spam2.reason))

	give(profile, "Apple", 8)
	feedN(player, "Apple", 5)
	check("ready to evolve after 5+ feeds",
		Progression.readyToEvolve(genome.stage, genome.fedCount), "fed=" .. genome.fedCount)
	local evo = FeedingService.evolve(player)
	check("evolve succeeds", evo.ok == true, evo.reason or "")
	check("now stage 2 (Little)", genome.stage == 2, "stage=" .. genome.stage)

	-- SPEC 11: a mutation must grant a real ability
	give(profile, "Battery", 8)
	feedN(player, "Battery", 8)
	check("LiveWire from batteries", genome.mutations.LiveWire == true)
	check("Electric ABILITY granted", (genome.abilities or {}).Electric == true)

	local eff = CreatureBuilder.effectiveTraits(genome)
	check("Electric dominates after batteries", (eff.Electric or 0) > (eff.Nature or 0),
		string.format("Electric=%.1f Nature=%.1f", eff.Electric or 0, eff.Nature or 0))

	local tooEarly = LineageService.create(player)
	check("nest refused before Mythic", tooEarly.ok == false, tooEarly.reason or "")

	genome.stage = Progression.maxStage()
	local parentId = genome.id
	local nested = LineageService.create(player)
	check("nest succeeds at Mythic", nested.ok == true, nested.reason or "")
	check("child is generation 2", nested.generation == 2)
	local parentStill
	for _, c in ipairs(profile.creatures) do
		if c.id == parentId then parentStill = c end
	end
	check("PARENT KEPT FOREVER (not consumed)", parentStill ~= nil)
	check("parent marked retired, not deleted", parentStill and parentStill.retired == true)
	local child = PlayerDataService.activeCreature(player)
	check("child inherited a gene", child and next(child.genes) ~= nil)
	check("child starts at Baby again", child and child.stage == 1)

	local OfflineService = require(Services.OfflineService)
	profile.lastSeen = os.time() - 7200
	local report = OfflineService.report(player, profile)
	check("offline report generated", report ~= nil)
	check("offline NEVER evolves", report and report.evolvedOffline == false)
	check("offline returns a curiosity hook", report and #report.headline > 10)

	local board = DiscoveryService.boardSummary()
	check("board counts items eaten", board.itemsEaten > 0)
	check("world firsts recorded", #board.worldFirsts > 0)

	print(string.rep("-", 62))
	print(AnalyticsService.funnelReport())
	print(string.rep("-", 62))
	print(string.format("%s RESULT: %d passed, %d failed", TAG, pass, fail))
end

Players.PlayerAdded:Connect(function(player) task.spawn(run, player) end)
for _, player in ipairs(Players:GetPlayers()) do task.spawn(run, player) end
