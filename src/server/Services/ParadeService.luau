--!strict
-- ParadeService — SPEC §23 CREATURE PARADE. Our Dress-to-Impress DNA.
--
-- Every ~15 minutes, opt-in players send their monster down the runway in the hub, one at
-- a time. Everyone on the server reacts: 😂 Weirdest · 😍 Cutest · 😱 Scariest ·
-- 🤯 Most Unexpected. There is deliberately NO "best" — nobody should chase one aesthetic.
-- Rewards are tiny; the real reward is the whole server looking at your creature.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Economy = require(Shared.Config:WaitForChild("Economy"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local CreatureService = require(script.Parent.CreatureService)
local GameEvents = require(script.Parent.GameEvents)

local ParadeService = {}

ParadeService.INTERVAL = 15 * 60
ParadeService.SIGNUP_SECONDS = 60
ParadeService.WALK_SECONDS = 14
ParadeService.MAX_ENTRANTS = 8
ParadeService.CATEGORIES = {
	{ id = "Weirdest", emoji = "😂" },
	{ id = "Cutest", emoji = "😍" },
	{ id = "Scariest", emoji = "😱" },
	{ id = "Unexpected", emoji = "🤯" },
}

local state = {
	phase = "idle", -- idle | signup | walking | results
	nextAt = 0,
	entrants = {} :: { Player },
	current = nil :: Player?,
	votes = {} :: { [number]: { [string]: number } },   -- entrant userId -> category -> count
	voted = {} :: { [string]: boolean },                 -- "voter:entrant" -> true
}

local worldState: Folder

local function publish()
	worldState:SetAttribute("ParadePhase", state.phase)
	worldState:SetAttribute("ParadeNextAt", state.nextAt)
	worldState:SetAttribute("ParadeCurrent", state.current and state.current.UserId or 0)
	worldState:SetAttribute("ParadeEntrants", #state.entrants)
end

local function markers()
	local world = workspace:FindFirstChild("World")
	local hub = world and world:FindFirstChild("Hub")
	local m = hub and hub:FindFirstChild("Markers")
	local a = m and m:FindFirstChild("ParadeStart") :: BasePart?
	local b = m and m:FindFirstChild("ParadeEnd") :: BasePart?
	return a, b
end

function ParadeService.join(player: Player)
	if state.phase ~= "signup" then
		return { ok = false, reason = "the parade isn't signing up right now" }
	end
	for _, p in ipairs(state.entrants) do
		if p == player then
			return { ok = true, already = true }
		end
	end
	if #state.entrants >= ParadeService.MAX_ENTRANTS then
		return { ok = false, reason = "the runway is full this time" }
	end
	local genome = PlayerDataService.activeCreature(player)
	if not genome or (genome.stage or 1) < 2 then
		return { ok = false, reason = "your monster needs to grow a little first" }
	end
	table.insert(state.entrants, player)
	publish()
	return { ok = true }
end

function ParadeService.vote(voter: Player, category: string)
	if state.phase ~= "walking" or not state.current then
		return { ok = false, reason = "nothing on the runway" }
	end
	if voter == state.current then
		return { ok = false, reason = "no voting for yourself" }
	end
	local valid = false
	for _, c in ipairs(ParadeService.CATEGORIES) do
		if c.id == category then
			valid = true
		end
	end
	if not valid then
		return { ok = false, reason = "bad category" }
	end
	local key = voter.UserId .. ":" .. state.current.UserId
	if state.voted[key] then
		return { ok = false, reason = "already reacted" }
	end
	state.voted[key] = true
	local id = state.current.UserId
	state.votes[id] = state.votes[id] or {}
	state.votes[id][category] = (state.votes[id][category] or 0) + 1
	Net.event("ParadeReaction"):FireAllClients({ category = category, entrant = id })
	GameEvents.fire(voter, "parade_vote", { category = category })
	return { ok = true }
end

local function walk(player: Player)
	local a, b = markers()
	local model = CreatureService.get(player)
	if not a or not b or not model then
		return
	end
	state.current = player
	publish()
	Net.event("WorldNotice"):FireAllClients({
		kind = "parade_walk", owner = player.DisplayName, userId = player.UserId,
		creature = model:GetAttribute("CreatureId"), name = model.Name,
	})
	CreatureService.setOverride(player, {
		from = a.Position, to = b.Position, duration = ParadeService.WALK_SECONDS,
		startedAt = os.clock(), pauseAt = 0.55, pauseFor = 2.5, action = "celebrate",
	})
	local profile = PlayerDataService.get(player)
	if profile then
		profile.parade.entered += 1
		PlayerDataService.addCurrency(player, Economy.rewards.paradeEntered)
		GameEvents.fire(player, "parade_entered", {})
	end
	task.wait(ParadeService.WALK_SECONDS + 1)
	CreatureService.setOverride(player, nil)
	state.current = nil
	publish()
end

local function results()
	state.phase = "results"
	publish()
	local winners = {}
	for _, cat in ipairs(ParadeService.CATEGORIES) do
		local bestId, bestN = nil, 0
		for userId, t in pairs(state.votes) do
			if (t[cat.id] or 0) > bestN then
				bestId, bestN = userId, t[cat.id]
			end
		end
		if bestId then
			local p = Players:GetPlayerByUserId(bestId)
			if p then
				PlayerDataService.addCurrency(p, Economy.rewards.paradeCategoryWin)
				local profile = PlayerDataService.get(p)
				if profile then
					profile.parade.votes[cat.id] = (profile.parade.votes[cat.id] or 0) + 1
					PlayerDataService.sync(p)
				end
				local model = CreatureService.get(p)
				if model then
					model:SetAttribute("ParadeTitle", cat.emoji .. " " .. cat.id)
					model:SetAttribute("ParadeTitleUntil", workspace:GetServerTimeNow() + 1800)
				end
				table.insert(winners, { category = cat.id, emoji = cat.emoji, owner = p.DisplayName, votes = bestN })
			end
		end
	end
	Net.event("WorldNotice"):FireAllClients({ kind = "parade_results", winners = winners })
	task.wait(10)
end

local function runParade()
	state.phase = "signup"
	state.entrants = {}
	state.votes = {}
	state.voted = {}
	state.nextAt = workspace:GetServerTimeNow() + ParadeService.SIGNUP_SECONDS
	publish()
	Net.event("WorldNotice"):FireAllClients({ kind = "parade_signup", closesAt = state.nextAt })
	task.wait(ParadeService.SIGNUP_SECONDS)
	if #state.entrants == 0 then
		state.phase = "idle"
		state.nextAt = workspace:GetServerTimeNow() + ParadeService.INTERVAL
		publish()
		return
	end
	state.phase = "walking"
	publish()
	for _, p in ipairs(state.entrants) do
		if p.Parent then
			walk(p)
		end
	end
	results()
	state.phase = "idle"
	state.nextAt = workspace:GetServerTimeNow() + ParadeService.INTERVAL
	publish()
end

-- For DevHooks / live-ops: start the signup now.
function ParadeService.startNow()
	if state.phase == "idle" then
		task.spawn(runParade)
		return true
	end
	return false
end

function ParadeService.start()
	worldState = ReplicatedStorage:WaitForChild("WorldState") :: Folder
	Net.func("ParadeJoin").OnServerInvoke = function(player)
		return ParadeService.join(player)
	end
	Net.func("ParadeVote").OnServerInvoke = function(player, category)
		if type(category) ~= "string" then
			return { ok = false }
		end
		return ParadeService.vote(player, category)
	end
	state.nextAt = workspace:GetServerTimeNow() + ParadeService.INTERVAL * 0.5
	publish()
	task.spawn(function()
		while true do
			task.wait(2)
			if state.phase == "idle" and workspace:GetServerTimeNow() >= state.nextAt - ParadeService.SIGNUP_SECONDS then
				runParade()
			end
		end
	end)
	print("[Parade] ready")
end

return ParadeService
