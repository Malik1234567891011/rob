-- DevUpdate1 — SPEC §76 "Have Update 1 ready before launch". Flips WorldState.UpdateLevel
-- to 1 on a running server (what Config/Release's schedule does) and checks the Ocean
-- actually opens LIVE: lock gone, reef gate buildable + openable, ocean foods spawning,
-- Swim trial joinable, and ocean food really grows Gills (Aquatic).
--
-- Enable (Disabled = false) and press Play. Asserts on STATE.

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services.PlayerDataService)
local FtueService = require(Services.FtueService)
local FeedingService = require(Services.FeedingService)
local WorldService = require(Services.WorldService)
local TrialService = require(Services.TrialService)

local TAG = "[UTEST]"
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

local function run(player: Player)
	for _ = 1, 100 do
		if PlayerDataService.get(player) and player.Character then
			break
		end
		task.wait(0.1)
	end
	task.wait(2)
	local profile = PlayerDataService.get(player)
	if profile.activeCreature == 0 then
		FtueService.pickEgg(player, 1)
	end
	local genome = PlayerDataService.activeCreature(player)
	local ws = ReplicatedStorage:WaitForChild("WorldState")
	local world = workspace:WaitForChild("World")

	-- before
	check("launch build: update level 0", (ws:GetAttribute("UpdateLevel") or 0) == 0)
	check("ocean lock present", world:FindFirstChild("OceanLock", true) ~= nil)
	check("reef gate refuses", WorldService.tryGate(player, "OceanReef").reason == "not yet released")
	check("swim trial refuses", TrialService.join(player, "Swim").ok == false)

	-- flip
	ws:SetAttribute("UpdateLevel", 1)
	task.wait(1.5)
	check("ocean lock removed live", world:FindFirstChild("OceanLock", true) == nil)
	local marker = world.Markers:FindFirstChild("Gate_OceanReef")
	check("reef gate prompt built", marker and marker:FindFirstChild("GatePrompt") ~= nil)

	local oceanProps = 0
	for _, m in ipairs(workspace:GetDescendants()) do
		if m:IsA("Model") and m:GetAttribute("Biome") == "Ocean" then
			oceanProps += 1
		end
	end
	check("ocean foods spawned", oceanProps > 0, oceanProps)

	-- the ocean changes the monster: Water + Flexible -> Gills -> Aquatic
	genome.stage = math.max(genome.stage, 2)
	for _, id in ipairs({ "Fish", "Jellyfish", "Kelp", "Fish", "Jellyfish", "Kelp", "Fish", "Jellyfish" }) do
		PlayerDataService.give(player, id, 1)
		local r = FeedingService.feed(player, id)
		if not r.ok then
			warn(TAG .. " feed " .. id .. ": " .. tostring(r.reason))
		end
		task.wait(0.6)
	end
	check("ocean diet grows Gills", genome.mutations.Gills == true)
	check("Aquatic ability granted", (genome.abilities or {}).Aquatic == true)

	local reef = WorldService.tryGate(player, "OceanReef")
	check("reef gate opens with Aquatic", reef.ok == true and reef.opened == true, reef.reason)

	local swim = TrialService.join(player, "Swim")
	check("swim trial joinable", swim.ok == true, swim.reason)
	TrialService.leave(player)

	print(string.format("%s RESULT: %d passed, %d failed", TAG, pass, fail))
end

Players.PlayerAdded:Connect(function(player)
	task.spawn(run, player)
end)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(run, player)
end
