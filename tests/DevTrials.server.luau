-- DevTrials — plays every launch trial end to end on the real TrialService with short
-- timers: queue -> countdown -> running -> scoring -> results -> rewards -> home.
--
-- Race + Obstacle: the avatar is walked through every checkpoint (both laps).
-- Smash: breaks real smashables through TrialService.smash with the rate limit respected.
-- Treasure: checks the chests were buried.
--
-- Enable (Disabled = false) and press Play. Asserts on STATE.

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services.PlayerDataService)
local FtueService = require(Services.FtueService)
local TrialService = require(Services.TrialService)

local Trials = require(ReplicatedStorage.Shared.Config.Trials)

local TAG = "[TTEST]"
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

local function markers(id: string, prefix: string): { BasePart }
	local arena = workspace.World.Trials:FindFirstChild(id)
	local out = {}
	local m = arena and arena:FindFirstChild("Markers")
	if m then
		for _, c in ipairs(m:GetChildren()) do
			if c:IsA("BasePart") and string.sub(c.Name, 1, #prefix) == prefix then
				table.insert(out, c)
			end
		end
	end
	table.sort(out, function(a, b)
		return (tonumber(string.match(a.Name, "%d+$")) or 0) < (tonumber(string.match(b.Name, "%d+$")) or 0)
	end)
	return out
end

local function waitRunning(player: Player, id: string): boolean
	local arena = workspace.World.Trials:FindFirstChild(id)
	for _ = 1, 200 do
		local runtime = arena and arena:FindFirstChild("Runtime")
		if TrialService.inTrial(player) == id and runtime then
			task.wait(3.8) -- countdown
			return true
		end
		task.wait(0.1)
	end
	return false
end

local function hrp(player: Player): BasePart?
	return player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
end

local function waitHome(player: Player): boolean
	for _ = 1, 400 do
		local h = hrp(player)
		if TrialService.inTrial(player) == nil and h and h.Position.X < 1500 then
			return true
		end
		task.wait(0.1)
	end
	return false
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
	genome.stage = math.max(genome.stage, 3)

	Trials.QUEUE_SECONDS = 2
	Trials.RESULTS_SECONDS = 2
	for _, id in ipairs({ "Race", "Smash", "Treasure", "Obstacle" }) do
		Trials.all[id].duration = 20
	end

	-- ── checkpoint courses ─────────────────────────────────────────────────────
	for _, id in ipairs({ "Race", "Obstacle" }) do
		local cps = markers(id, "Checkpoint_")
		check(id .. ": checkpoints exist", #cps >= 2, #cps)
		local joined = TrialService.join(player, id)
		check(id .. ": join", joined.ok == true, joined.reason)
		check(id .. ": running", waitRunning(player, id))
		local startAt = hrp(player) and hrp(player).Position
		check(id .. ": spawned in arena", startAt and startAt.X > 1900, startAt)
		local laps = Trials.all[id].laps or 1
		for _ = 1, laps do
			for _, cp in ipairs(cps) do
				player.Character:PivotTo(cp.CFrame)
				task.wait(0.25)
			end
		end
		task.wait(0.5)
		local best = profile.trials.best[id]
		check(id .. ": finished + time recorded", best ~= nil and best > 0, best)
		check(id .. ": returned home after results", waitHome(player))
		task.wait(1)
	end

	-- ── smash ──────────────────────────────────────────────────────────────────
	do
		local joined = TrialService.join(player, "Smash")
		check("Smash: join", joined.ok == true, joined.reason)
		check("Smash: running", waitRunning(player, "Smash"))
		local runtime = workspace.World.Trials.Smash:FindFirstChild("Runtime")
		local targets = {}
		for _, m in ipairs(runtime and runtime:GetChildren() or {}) do
			if m.Name == "Smashable" then
				table.insert(targets, m)
			end
		end
		check("Smash: smashables spawned", #targets >= 6, #targets)
		local broken = 0
		for i = 1, math.min(3, #targets) do
			local m = targets[i]
			local p = m.PrimaryPart
			if p then
				player.Character:PivotTo(CFrame.new(p.Position + Vector3.new(0, 3, 5)))
				task.wait(0.2)
				for _ = 1, 30 do
					if not m.Parent then
						break
					end
					TrialService.smash(player, m)
					task.wait(0.25)
				end
				if not m.Parent then
					broken += 1
				end
			end
		end
		check("Smash: broke targets", broken == math.min(3, #targets), broken)
		check("Smash: returned home after results", waitHome(player))
		check("Smash: score recorded", (profile.trials.best.Smash or 0) > 0, profile.trials.best.Smash)
		task.wait(1)
	end

	-- ── treasure ───────────────────────────────────────────────────────────────
	do
		local joined = TrialService.join(player, "Treasure")
		check("Treasure: join", joined.ok == true, joined.reason)
		check("Treasure: running", waitRunning(player, "Treasure"))
		local runtime = workspace.World.Trials.Treasure:FindFirstChild("Runtime")
		local chests = 0
		for _, m in ipairs(runtime and runtime:GetChildren() or {}) do
			if m.Name == "BuriedChest" then
				chests += 1
			end
		end
		check("Treasure: chests buried", chests >= 6, chests)
		check("Treasure: round ends + home", waitHome(player))
	end

	print(string.format("%s trials completed stat = %s", TAG, tostring(profile.trials.played or profile.stats.trials)))
	print(string.format("%s RESULT: %d passed, %d failed", TAG, pass, fail))
end

Players.PlayerAdded:Connect(function(player)
	task.spawn(run, player)
end)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(run, player)
end
