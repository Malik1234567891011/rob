--!strict
-- TrialService — SPEC §21 Creature Trials. 60–150 s contests where the creature you built
-- changes how you play. Server-authoritative: positions, hits, chest finds and times are
-- all checked here; the client only draws the HUD and applies glide/climb feel.
--
-- Flow: join from the Trials portal -> lobby countdown (others can join) -> teleport to the
-- arena spawns -> 3,2,1 -> run -> results -> rewards -> back to the hub.
--
-- Arenas live at Workspace.World.Trials.<TrialId> and expose a `Markers` folder:
--   Spawn_1..8, Return (in the hub)            all trials
--   Checkpoint_1..N                            Race, Obstacle, Swim (in order; last = finish)
--   SmashSpot_1..N                             Smash
--   ChestSpot_1..N                             Treasure
--   anything named Void                        falling below = respawn at last checkpoint

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Trials = require(Shared.Config:WaitForChild("Trials"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local GameEvents = require(script.Parent.GameEvents)

local TrialService = {}

type Entrant = {
	score: number,
	finishedAt: number?,
	checkpoint: number,
	lap: number,
	stats: any,
	lastSafe: CFrame,
	returnCF: CFrame?,
}

local sessions: { [string]: any } = {}

local function arenaFor(id: string): Instance?
	local world = workspace:FindFirstChild("World")
	local trials = world and world:FindFirstChild("Trials")
	return trials and trials:FindFirstChild(id)
end

local function marker(arena: Instance, name: string): BasePart?
	local m = arena:FindFirstChild("Markers")
	return m and m:FindFirstChild(name) :: BasePart?
end

local function markersPrefixed(arena: Instance, prefix: string): { BasePart }
	local out = {}
	local m = arena:FindFirstChild("Markers")
	if not m then
		return out
	end
	for _, c in ipairs(m:GetChildren()) do
		if c:IsA("BasePart") and string.sub(c.Name, 1, #prefix) == prefix then
			table.insert(out, c)
		end
	end
	table.sort(out, function(a, b)
		return (tonumber(string.match(a.Name, "%d+$")) or 0) < (tonumber(string.match(b.Name, "%d+$")) or 0)
	end)
	return out
end

local function hrpOf(player: Player): BasePart?
	local char = player.Character
	return char and char:FindFirstChild("HumanoidRootPart") :: BasePart?
end

local function humanoidOf(player: Player): Humanoid?
	local char = player.Character
	return char and char:FindFirstChildOfClass("Humanoid")
end

local function broadcast(id: string)
	local s = sessions[id]
	if not s then
		return
	end
	local board = {}
	for p, e in pairs(s.players) do
		table.insert(board, { name = p.DisplayName, userId = p.UserId, score = e.score, finished = e.finishedAt ~= nil,
			lap = e.lap, checkpoint = e.checkpoint })
	end
	local def = Trials.get(id)
	table.sort(board, function(a, b)
		if def.scoring == "time" then
			if a.finished ~= b.finished then
				return a.finished
			end
			if a.finished then
				return a.score < b.score
			end
			return (a.lap * 1000 + a.checkpoint) > (b.lap * 1000 + b.checkpoint)
		end
		return a.score > b.score
	end)
	local payload = {
		trial = id, state = s.state, startsAt = s.startsAt, endsAt = s.endsAt,
		board = board, checkpoints = s.checkpointCount, laps = def.laps or 1,
	}
	for p, e in pairs(s.players) do
		payload.me = { score = e.score, lap = e.lap, checkpoint = e.checkpoint, stats = e.stats }
		Net.event("TrialState"):FireClient(p, payload)
	end
end

local function applyStats(player: Player, stats)
	local hum = humanoidOf(player)
	if hum then
		hum.UseJumpPower = true
		hum.WalkSpeed = stats.speed
		hum.JumpPower = stats.jump
	end
	local char = player.Character
	if char then
		char:SetAttribute("TrialGlide", stats.glide)
		char:SetAttribute("TrialSticky", stats.sticky)
		char:SetAttribute("TrialTiny", stats.tiny)
		char:SetAttribute("TrialSwim", stats.swim)
	end
end

local function restoreStats(player: Player)
	local hum = humanoidOf(player)
	if hum then
		hum.WalkSpeed = 16
		hum.JumpPower = 50
	end
	local char = player.Character
	if char then
		char:SetAttribute("TrialGlide", nil)
		char:SetAttribute("TrialSticky", nil)
		char:SetAttribute("TrialTiny", nil)
		char:SetAttribute("TrialSwim", nil)
	end
end

local function statsFor(player: Player)
	local genome = PlayerDataService.activeCreature(player)
	if not genome then
		return Trials.stats({}, {}, 1)
	end
	return Trials.stats(CreatureBuilder.effectiveTraits(genome), genome.abilities or {}, genome.stage or 1)
end

-- ═══ SMASH / TREASURE OBJECTS ════════════════════════════════════════════════

local function assetModel(name: string): Model?
	local assets = ReplicatedStorage:FindFirstChild("Assets")
	local kit = assets and assets:FindFirstChild("Kits")
	local src = kit and kit:FindFirstChild(name, true)
	if src then
		if src:IsA("MeshPart") then
			local m = Instance.new("Model")
			local c = src:Clone()
			c.Anchored = true
			c.Parent = m
			m.PrimaryPart = c
			return m
		elseif src:IsA("Model") then
			return src:Clone()
		end
	end
	return nil
end

local function fallbackBlock(size: Vector3, color: Color3): Model
	local m = Instance.new("Model")
	local p = Instance.new("Part")
	p.Size = size
	p.Color = color
	p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.Parent = m
	m.PrimaryPart = p
	return m
end

local function spawnSmashables(id: string, s)
	local arena = s.arena
	for i, spot in ipairs(markersPrefixed(arena, "SmashSpot_")) do
		local big = i % 4 == 0
		local model = assetModel(big and "Smash_Pillar" or "Smash_Crate") or fallbackBlock(big and Vector3.new(4, 8, 4) or Vector3.new(4, 4, 4), big and Color3.fromRGB(150, 140, 130) or Color3.fromRGB(190, 140, 80))
		model.Name = "Smashable"
		local hp = big and 10 or 3
		model:SetAttribute("HP", hp)
		model:SetAttribute("MaxHP", hp)
		model:SetAttribute("Points", big and 60 or 15)
		model:PivotTo(CFrame.new(spot.Position.X, spot.Position.Y - spot.Size.Y * 0.5, spot.Position.Z) * CFrame.Angles(0, math.random() * 6.28, 0))
		model.Parent = s.objects
		local prompt = Instance.new("ProximityPrompt")
		prompt.ActionText = "Smash!"
		prompt.ObjectText = big and "Pillar" or "Crate"
		prompt.HoldDuration = 0
		prompt.MaxActivationDistance = 12
		prompt.RequiresLineOfSight = false
		prompt.KeyboardKeyCode = Enum.KeyCode.E
		prompt.Parent = model.PrimaryPart
		prompt.Triggered:Connect(function(player)
			TrialService.smash(player, model)
		end)
	end
end

function TrialService.smash(player: Player, model: Model)
	local s = sessions.Smash
	if not s or s.state ~= "running" or not model.Parent then
		return
	end
	local e = s.players[player]
	local hrp = hrpOf(player)
	if not e or not hrp or not model.PrimaryPart then
		return
	end
	if (hrp.Position - model.PrimaryPart.Position).Magnitude > 16 then
		return
	end
	local now = os.clock()
	if now - (e.lastSmash or 0) < 0.22 then
		return
	end
	e.lastSmash = now
	local hp = (model:GetAttribute("HP") or 1) - e.stats.strength
	model:SetAttribute("HP", hp)
	Net.event("TrialFx"):FireAllClients({ kind = "hit", at = model.PrimaryPart.Position, by = player.UserId })
	if hp <= 0 then
		e.score += model:GetAttribute("Points") or 10
		Net.event("TrialFx"):FireAllClients({ kind = "break", at = model.PrimaryPart.Position, by = player.UserId })
		model:Destroy()
		broadcast("Smash")
	end
end

local function spawnChests(s, count: number)
	local spots = markersPrefixed(s.arena, "ChestSpot_")
	for i = #spots, 2, -1 do
		local j = math.random(1, i)
		spots[i], spots[j] = spots[j], spots[i]
	end
	for i = 1, math.min(count, #spots) do
		local spot = spots[i]
		local model = assetModel("Treasure_Chest") or fallbackBlock(Vector3.new(3, 2, 2), Color3.fromRGB(200, 150, 60))
		model.Name = "BuriedChest"
		-- buried: only the lid pokes out of the ground
		model:PivotTo(CFrame.new(spot.Position.X, spot.Position.Y - spot.Size.Y * 0.5 - 1.2, spot.Position.Z) * CFrame.Angles(0, math.random() * 6.28, 0))
		model.Parent = s.objects
		for _, d in ipairs(model:GetDescendants()) do
			if d:IsA("BasePart") then
				d.CanCollide = false
			end
		end
		local prompt = Instance.new("ProximityPrompt")
		prompt.ActionText = "Dig"
		prompt.ObjectText = "Something buried"
		prompt.HoldDuration = 0.6
		prompt.MaxActivationDistance = 9
		prompt.RequiresLineOfSight = false
		prompt.Parent = model.PrimaryPart
		prompt.Triggered:Connect(function(player)
			local e = s.players[player]
			if not e or s.state ~= "running" or not model.Parent then
				return
			end
			e.score += 100
			Net.event("TrialFx"):FireAllClients({ kind = "chest", at = model.PrimaryPart.Position, by = player.UserId })
			model:Destroy()
			broadcast("Treasure")
		end)
	end
end

-- ═══ SESSION LIFECYCLE ═══════════════════════════════════════════════════════

local function endSession(id: string)
	local s = sessions[id]
	if not s or s.state == "results" then
		return
	end
	local def = Trials.get(id)
	s.state = "results"
	s.endsAt = workspace:GetServerTimeNow() + Trials.RESULTS_SECONDS

	-- rank
	local ranked = {}
	for p, e in pairs(s.players) do
		if p.Parent then
			if def.scoring == "time" and not e.finishedAt then
				e.score = math.huge
			end
			table.insert(ranked, { p = p, e = e })
		end
	end
	table.sort(ranked, function(a, b)
		if def.scoring == "time" then
			return a.e.score < b.e.score
		end
		return a.e.score > b.e.score
	end)
	local participants = {}
	for _, r in ipairs(ranked) do
		table.insert(participants, r.p)
	end
	for rank, r in ipairs(ranked) do
		local p, e = r.p, r.e
		local profile = PlayerDataService.get(p)
		local completed = def.scoring ~= "time" or e.finishedAt ~= nil
		local withFriend = false
		for _, other in ipairs(participants) do
			if other ~= p then
				local ok, isFriend = pcall(p.IsFriendsWith, p, other.UserId)
				if ok and isFriend then
					withFriend = true
				end
			end
		end
		if profile and completed then
			profile.trials.played += 1
			PlayerDataService.stat(p, "trials")
			PlayerDataService.addCurrency(p, Economy.rewards.trialCompleted)
			local best = profile.trials.best[id]
			local better = best == nil or (def.scoring == "time" and e.score < best) or (def.scoring ~= "time" and e.score > best)
			if better then
				profile.trials.best[id] = e.score
			end
			if rank == 1 and #ranked > 1 then
				profile.trials.wins += 1
				PlayerDataService.addCurrency(p, Economy.rewards.trialWin)
			end
			GameEvents.fire(p, "trial_done", { trial = id, rank = rank, withFriend = withFriend, score = e.score, personalBest = better })
			PlayerDataService.sync(p)
		end
	end
	broadcast(id)

	task.delay(Trials.RESULTS_SECONDS, function()
		for p, e in pairs(s.players) do
			restoreStats(p)
			if p.Parent and p.Character then
				local ret = marker(s.arena, "Return")
				p.Character:PivotTo(e.returnCF or (ret and ret.CFrame + Vector3.new(0, 4, 0)) or CFrame.new(0, 10, 0))
			end
			Net.event("TrialState"):FireClient(p, { trial = id, state = "closed" })
		end
		if s.objects then
			s.objects:Destroy()
		end
		sessions[id] = nil
	end)
end

local function startRunning(id: string)
	local s = sessions[id]
	local def = Trials.get(id)
	local spawns = markersPrefixed(s.arena, "Spawn_")
	local i = 0
	for p, e in pairs(s.players) do
		i += 1
		local spawn = spawns[((i - 1) % math.max(1, #spawns)) + 1]
		local hrp = hrpOf(p)
		e.returnCF = hrp and hrp.CFrame or nil
		e.stats = statsFor(p)
		if p.Character and spawn then
			local cf = spawn.CFrame + Vector3.new(0, 4, 0)
			p.Character:PivotTo(cf)
			e.lastSafe = cf
		end
		applyStats(p, e.stats)
		local ok, Analytics = pcall(require, script.Parent.AnalyticsService)
		if ok then
			Analytics.track("trial_enter", p, { trial = id, players = s.count })
		end
	end
	s.objects = Instance.new("Folder")
	s.objects.Name = "Runtime"
	s.objects.Parent = s.arena
	s.checkpoints = markersPrefixed(s.arena, "Checkpoint_")
	s.checkpointCount = #s.checkpoints
	if id == "Smash" then
		spawnSmashables(id, s)
	elseif id == "Treasure" then
		spawnChests(s, def.chests or 10)
	end
	s.state = "countdown"
	s.startsAt = workspace:GetServerTimeNow() + 3.5
	s.endsAt = s.startsAt + def.duration
	broadcast(id)
	task.delay(3.5, function()
		if sessions[id] ~= s then
			return
		end
		s.state = "running"
		s.runStart = os.clock()
		broadcast(id)
		task.delay(def.duration, function()
			if sessions[id] == s then
				endSession(id)
			end
		end)
	end)
end

function TrialService.join(player: Player, id: string)
	local def = Trials.get(id)
	if not def then
		return { ok = false, reason = "no such trial" }
	end
	if def.update and not TrialService.updateLive(def.update) then
		return { ok = false, reason = "coming soon" }
	end
	local genome = PlayerDataService.activeCreature(player)
	if not genome then
		return { ok = false, reason = "you need a monster" }
	end
	if (genome.stage or 1) < def.minStage then
		return { ok = false, reason = "your monster needs to grow first" }
	end
	local arena = arenaFor(id)
	if not arena then
		return { ok = false, reason = "arena not built" }
	end
	for otherId, s in pairs(sessions) do
		if s.players[player] then
			return { ok = false, reason = "already in " .. otherId }
		end
	end
	local s = sessions[id]
	if s and s.state ~= "queue" then
		return { ok = false, reason = "a round is running — try again in a moment" }
	end
	if not s then
		s = { state = "queue", players = {}, count = 0, arena = arena,
			startsAt = workspace:GetServerTimeNow() + Trials.QUEUE_SECONDS }
		sessions[id] = s
		task.delay(Trials.QUEUE_SECONDS, function()
			if sessions[id] == s and s.state == "queue" then
				if s.count > 0 then
					startRunning(id)
				else
					sessions[id] = nil
				end
			end
		end)
	end
	if s.count >= def.maxPlayers then
		return { ok = false, reason = "full" }
	end
	s.players[player] = { score = 0, checkpoint = 0, lap = 1, stats = statsFor(player), lastSafe = CFrame.new() }
	s.count += 1
	broadcast(id)
	return { ok = true, startsAt = s.startsAt }
end

function TrialService.leave(player: Player)
	for id, s in pairs(sessions) do
		if s.players[player] then
			s.players[player] = nil
			s.count -= 1
			restoreStats(player)
			Net.event("TrialState"):FireClient(player, { trial = id, state = "closed" })
			if s.count <= 0 and s.state ~= "results" then
				if s.objects then
					s.objects:Destroy()
				end
				sessions[id] = nil
			else
				broadcast(id)
			end
		end
	end
	return { ok = true }
end

function TrialService.inTrial(player: Player): string?
	for id, s in pairs(sessions) do
		if s.players[player] then
			return id
		end
	end
	return nil
end

-- Set by the world/update config; Update 1 content (Swim) waits behind this.
TrialService.updateLive = function(_n: number): boolean
	local ws = ReplicatedStorage:FindFirstChild("WorldState")
	return ws ~= nil and (ws:GetAttribute("UpdateLevel") or 0) >= _n
end

-- ═══ PER-FRAME: checkpoints, finish, void ════════════════════════════════════

local function insidePart(part: BasePart, pos: Vector3, pad: number): boolean
	local rel = part.CFrame:PointToObjectSpace(pos)
	local h = part.Size * 0.5 + Vector3.new(pad, pad, pad)
	return math.abs(rel.X) <= h.X and math.abs(rel.Y) <= h.Y and math.abs(rel.Z) <= h.Z
end

local function step()
	for id, s in pairs(sessions) do
		if s.state ~= "running" then
			continue
		end
		local def = Trials.get(id)
		local cps = s.checkpoints or {}
		for p, e in pairs(s.players) do
			local hrp = hrpOf(p)
			if not hrp or e.finishedAt then
				continue
			end
			-- fell off the course
			if hrp.Position.Y < (s.arena:GetAttribute("VoidY") or -40) then
				p.Character:PivotTo(e.lastSafe)
			end
			if #cps > 0 and (def.scoring == "time") then
				local nextIndex = e.checkpoint + 1
				local cp = cps[nextIndex]
				if cp and insidePart(cp, hrp.Position, 2.5) then
					e.checkpoint = nextIndex
					e.lastSafe = cp.CFrame + Vector3.new(0, 3, 0)
					if nextIndex == #cps then
						if e.lap >= (def.laps or 1) then
							e.finishedAt = os.clock()
							e.score = math.floor((e.finishedAt - (s.runStart or e.finishedAt)) * 100) / 100
							Net.event("TrialFx"):FireAllClients({ kind = "finish", by = p.UserId, at = hrp.Position })
						else
							e.lap += 1
							e.checkpoint = 0
						end
					end
					broadcast(id)
				end
			end
		end
		-- everyone finished -> end early
		if def.scoring == "time" then
			local all = true
			for _, e in pairs(s.players) do
				if not e.finishedAt then
					all = false
				end
			end
			if all and s.count > 0 then
				endSession(id)
			end
		end
	end
end

function TrialService.start()
	Net.func("TrialJoin").OnServerInvoke = function(player, id)
		if type(id) ~= "string" then
			return { ok = false, reason = "bad trial" }
		end
		return TrialService.join(player, id)
	end
	Net.func("TrialLeave").OnServerInvoke = function(player)
		return TrialService.leave(player)
	end
	RunService.Heartbeat:Connect(step)
	Players.PlayerRemoving:Connect(function(p)
		TrialService.leave(p)
	end)
	print("[Trials] ready")
end

return TrialService
