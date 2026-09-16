-- DevSystems — end-to-end checks for every system beyond the core feed loop:
-- quests, dailies/merchant, gates (solo, co-op, update-locked), sanctuary tiers + decor +
-- garden, trials (queue -> arena teleport -> leave), parade, world events, extra eggs +
-- switching, monetization guard, world markers.
--
-- Enable this Script in Studio (Disabled = false) and press Play. Asserts on STATE.
-- It is destructive to the playtest profile (memory-only in Studio), so it is disabled
-- by default.

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services.PlayerDataService)
local FeedingService = require(Services.FeedingService)
local FtueService = require(Services.FtueService)
local CreatureService = require(Services.CreatureService)
local LineageService = require(Services.LineageService)
local WorldService = require(Services.WorldService)
local DailyService = require(Services.DailyService)
local SanctuaryService = require(Services.SanctuaryService)
local TrialService = require(Services.TrialService)
local ParadeService = require(Services.ParadeService)
local EventService = require(Services.EventService)
local MonetizationService = require(Services.MonetizationService)

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Quests = require(Shared.Config.Quests)
local Trials = require(Shared.Config.Trials)
local Biomes = require(Shared.Config.Biomes)

local TAG = "[STEST]"
local pass, fail = 0, 0

local function check(name, condition, detail)
	if condition then
		pass += 1
		print(string.format("%s  PASS  %-44s %s", TAG, name, tostring(detail or "")))
	else
		fail += 1
		warn(string.format("%s  FAIL  %-44s %s", TAG, name, tostring(detail or "")))
	end
end

local function section(name)
	print(string.format("%s  ── %s", TAG, name))
end

local function countMeshes(root: Instance?, name: string): number
	local n = 0
	if root then
		for _, d in ipairs(root:GetDescendants()) do
			if d:IsA("MeshPart") and string.gsub(d.Name, "%.%d+$", "") == name then
				n += 1
			end
		end
	end
	return n
end

local function run(player: Player)
	for _ = 1, 100 do
		if PlayerDataService.get(player) and player.Character then
			break
		end
		task.wait(0.1)
	end
	task.wait(2)
	local profile = PlayerDataService.get(player)
	check("profile loaded", profile ~= nil)
	if not profile then
		return
	end
	if profile.activeCreature == 0 then
		FtueService.pickEgg(player, 2)
	end
	local genome = PlayerDataService.activeCreature(player)
	check("have a creature", genome ~= nil)
	if not genome then
		return
	end

	-- ── WORLD MARKERS ──────────────────────────────────────────────────────────
	section("world")
	local world = workspace:FindFirstChild("World")
	local markers = world and world:FindFirstChild("Markers")
	check("World.Markers exists", markers ~= nil)
	local gateCount = 0
	for _, g in ipairs(Biomes.gates) do
		if markers and markers:FindFirstChild("Gate_" .. g.id) then
			gateCount += 1
		end
	end
	check("every gate has a marker", gateCount == #Biomes.gates, gateCount .. "/" .. #Biomes.gates)
	check("plot for player", SanctuaryService.plotCF(player) ~= nil)

	-- ── QUESTS ─────────────────────────────────────────────────────────────────
	section("quests")
	check("active quests filled", #profile.quests.active == Quests.ACTIVE, #profile.quests.active .. "/" .. Quests.ACTIVE)
	-- which 3 quests roll is random; plant a known one so the check is deterministic
	profile.quests.active[1] = { id = "BigBite", progress = 0, seen = {} }
	local doneBefore = profile.quests.completedTotal
	for _, id in ipairs({ "Strawberry", "Carrot", "Pebble" }) do
		PlayerDataService.give(player, id, 1)
		local r = FeedingService.feed(player, id)
		if not r.ok then
			warn(TAG .. " feed " .. id .. " refused: " .. tostring(r.reason))
		end
		task.wait(0.6)
	end
	local big
	for _, q in ipairs(profile.quests.active) do
		if q.id == "BigBite" then
			big = q
		end
	end
	check("feeding advances BigBite", big and big.progress == 3, big and big.progress)
	profile.quests.active[1] = { id = "TrySomethingNew", progress = 0, seen = {} }
	PlayerDataService.give(player, "Honeycomb", 1)
	FeedingService.feed(player, "Honeycomb")
	task.wait(0.3)
	-- other random active quests may complete from the same meals, so "at least one"
	check("new food completes TrySomethingNew", profile.quests.completedTotal >= doneBefore + 1, profile.quests.completedTotal - doneBefore)
	check("quest slots refilled", #profile.quests.active == Quests.ACTIVE, #profile.quests.active)

	-- ── DAILY + MERCHANT ───────────────────────────────────────────────────────
	section("daily")
	local today = DailyService.current()
	check("ingredient of the day", today and today.ingredientOfDay ~= nil, today and today.ingredientOfDay)
	check("weather known", DailyService.weather() ~= nil, DailyService.weather())
	local stock = today and today.merchant or {}
	local first = stock[1]
	local firstId = type(first) == "table" and (first.id or first.ingredient) or first
	profile.coins += 5000
	if firstId then
		local have = profile.inventory[firstId] or 0
		local r = DailyService.buy(player, firstId)
		check("merchant sells today's stock", r.ok == true, r.reason or firstId)
		check("purchase lands in bag", (profile.inventory[firstId] or 0) == have + 1)
	else
		check("merchant has stock", false, "stock shape: " .. typeof(first))
	end
	local bad = DailyService.buy(player, "Meteorite")
	check("merchant refuses unsold item", bad.ok == false and bad.reason == "not sold today", bad.reason)

	-- ── GATES ──────────────────────────────────────────────────────────────────
	section("gates")
	genome.abilities = genome.abilities or {}
	genome.abilities.Giant = nil
	local locked = WorldService.tryGate(player, "MeadowBoulder")
	check("boulder refuses without Giant", locked.ok == false and locked.reason == "missing", locked.reason)
	genome.abilities.Giant = true
	local melonsBefore = profile.inventory.Watermelon or 0
	local coinsBefore = profile.coins
	local opened = WorldService.tryGate(player, "MeadowBoulder")
	check("boulder opens with Giant", opened.ok == true and opened.opened == true, opened.reason)
	check("gate reward given", (profile.inventory.Watermelon or 0) == melonsBefore + 1)
	check("gate coins given", profile.coins > coinsBefore, profile.coins - coinsBefore)
	local again = WorldService.tryGate(player, "MeadowBoulder")
	check("reopening is 'already'", again.ok == true and again.already == true)
	genome.abilities.Electric = true
	local coop = WorldService.tryGate(player, "JunkBigMachine")
	check("co-op gate: own creature counts", coop.ok == true, coop.reason)
	local ocean = WorldService.tryGate(player, "OceanReef")
	check("ocean gate locked until Update 1", ocean.ok == false and ocean.reason == "not yet released", ocean.reason)
	check("unknown gate refused", WorldService.tryGate(player, "Nope").ok == false)

	-- ── SANCTUARY ──────────────────────────────────────────────────────────────
	section("sanctuary")
	profile.coins += 200000
	profile.essence += 100
	local plotFolder: Instance? = nil
	for _, f in ipairs(workspace:GetChildren()) do
		if f:GetAttribute("Owner") == player.UserId and f:GetAttribute("Plot") then
			plotFolder = f
		end
	end
	check("found my sanctuary build folder", plotFolder ~= nil)
	local tier = profile.sanctuary.tier
	local fencesBefore = countMeshes(plotFolder, "Fence_Straight")
	local up = SanctuaryService.upgrade(player)
	check("upgrade to next tier", up.ok == true and up.tier == tier + 1, up.reason or up.tier)
	task.wait(1)
	if tier == 1 then
		check("fence perimeter built at tier 2", countMeshes(plotFolder, "Fence_Straight") > fencesBefore + 20,
			fencesBefore .. " -> " .. countMeshes(plotFolder, "Fence_Straight"))
	end
	for _ = 1, 4 do
		SanctuaryService.upgrade(player)
		task.wait(0.3)
	end
	check("reached tier 6 (garden)", profile.sanctuary.tier >= 6, profile.sanctuary.tier)
	PlayerDataService.give(player, "Strawberry", 2)
	local garden = SanctuaryService.plant(player, "Strawberry")
	check("garden accepts a plant", garden.ok == true, garden.reason)
	local decor = SanctuaryService.buyDecor(player, "Bench_Wood")
	check("decor purchase", decor.ok == true, decor.reason)
	local plotMeshes = 0
	if plotFolder then
		for _, d in ipairs(plotFolder:GetDescendants()) do
			if d:IsA("MeshPart") then
				plotMeshes += 1
			end
		end
	end
	check("sanctuary has built meshes", plotMeshes > 30, plotMeshes)

	-- ── EGGS + SWITCHING ───────────────────────────────────────────────────────
	section("lineage")
	local nCreatures = #profile.creatures
	profile.essence += 30
	local egg = LineageService.newEgg(player, "Heavy")
	check("second egg (25 Essence)", egg.ok == true, egg.reason)
	check("creature count +1", #profile.creatures == nCreatures + 1, #profile.creatures)
	local sw = LineageService.switch(player, 1)
	check("switch back to first", sw.ok == true and profile.activeCreature == 1, sw.reason)
	genome = PlayerDataService.activeCreature(player)

	-- ── MONETIZATION GUARD ─────────────────────────────────────────────────────
	section("monetization")
	local evolutions = profile.stats.evolutions or 0
	profile.stats.evolutions = 0
	local early = MonetizationService.prompt(player, "pass", "ExtraSlots")
	check("no prompt before first evolution", early.ok == false and early.reason == "evolve your monster first", early.reason)
	profile.stats.evolutions = math.max(1, evolutions)
	local later = MonetizationService.prompt(player, "pass", "ExtraSlots")
	check("after evolution: ids pending = coming soon", later.ok == true or later.reason == "coming soon", later.reason)

	-- ── PASSES DO WHAT THEY SAY (cosmetic / QoL only) ─────────────────────────
	section("passes")
	profile.coins += 20000
	profile.essence += 20
	local lockedDecor = SanctuaryService.buyDecor(player, "Lamp_Post")
	check("Builder+ decor refused without pass", lockedDecor.ok == false, lockedDecor.reason)
	profile.passes.SanctuaryPlus = true
	local plusDecor = SanctuaryService.buyDecor(player, "Lamp_Post")
	check("Builder+ decor with pass", plusDecor.ok == true, plusDecor.reason)
	profile.passes.Stylist = true
	profile.passes.Researcher = true
	profile.cosmetics.style = { nameFx = "Gold", eyeShine = "Pink", belly = "Mint" }
	profile.cosmetics.owned.TrailStars = true
	profile.cosmetics.equipped.trail = "TrailStars"
	local styled = CreatureService.refresh(player)
	check("stylist name effect", styled and styled:GetAttribute("NameFx") == "Gold")
	local shineNeon, gradient, badge = false, false, false
	for _, d in ipairs(styled and styled:GetDescendants() or {}) do
		if d:IsA("MeshPart") and string.find(d.Name, "__Shine", 1, true) and d.Material == Enum.Material.Neon then
			shineNeon = true
		elseif d:IsA("UIGradient") and d.Name == "NameFx" then
			gradient = true
		elseif d:IsA("TextLabel") and d.Name == "Sub" and string.find(d.Text, "🔬", 1, true) then
			badge = true
		end
	end
	check("stylist sparkly eyes", shineNeon)
	check("name gradient on nameplate", gradient)
	check("researcher nameplate badge", badge)
	check("trail cosmetic stamped", styled and styled:GetAttribute("Trail") == "TrailStars")
	profile.passes.Stylist, profile.passes.Researcher, profile.passes.SanctuaryPlus = nil, nil, nil
	profile.cosmetics.style = {}
	profile.cosmetics.equipped.trail = nil
	CreatureService.refresh(player)
	genome = PlayerDataService.activeCreature(player)

	-- ── PARADE ─────────────────────────────────────────────────────────────────
	section("parade")
	genome.stage = math.max(genome.stage, 2)
	local started = ParadeService.startNow()
	task.wait(0.5)
	local pj = ParadeService.join(player)
	check("parade signup", started and pj.ok == true, pj.reason)
	local selfVote = ParadeService.vote(player, "Cute")
	check("parade vote guard", selfVote.ok == false, selfVote.reason)

	-- ── WORLD EVENT ────────────────────────────────────────────────────────────
	section("events")
	local ws = ReplicatedStorage:FindFirstChild("WorldState")
	local ranEvent = EventService.run("Earthquake")
	task.wait(1)
	check("earthquake event runs", ranEvent == true and ws and ws:GetAttribute("Event") == "Earthquake")
	local seal = world and world:FindFirstChild("QuakeSeal", true) :: BasePart?
	check("quake opens the crystal pocket", seal and seal.CanCollide == false)

	-- ── TRIALS (last: it teleports the character) ─────────────────────────────
	section("trials")
	genome.stage = math.max(genome.stage, 2)
	local join = TrialService.join(player, "Race")
	check("join Race queue", join.ok == true, join.reason)
	local swim = TrialService.join(player, "Swim")
	check("Swim trial locked until Update 1", swim.ok == false, swim.reason)
	task.wait(Trials.QUEUE_SECONDS + 3)
	check("race is running with me in it", TrialService.inTrial(player) == "Race", TrialService.inTrial(player))
	local hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	check("teleported into the arena", hrp and hrp.Position.X > 1900, hrp and hrp.Position)
	TrialService.leave(player)
	task.wait(1)
	check("left the race", TrialService.inTrial(player) == nil)
	hrp = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	check("leaving mid-race returns you home", hrp and hrp.Position.X < 1500, hrp and hrp.Position)

	CreatureService.refresh(player)
	print(string.format("%s RESULT: %d passed, %d failed", TAG, pass, fail))
end

Players.PlayerAdded:Connect(function(player)
	task.spawn(run, player)
end)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(run, player)
end
