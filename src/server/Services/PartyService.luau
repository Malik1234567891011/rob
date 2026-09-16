--!strict
-- PartyService — SPEC §20 Adventure Parties, §53 friend design.
--
-- "Not 'invite friend = +20% money' — that is fake social design. Friends change what's
--  possible." A party is 2–4 players. What it changes:
--   * CO-OP GATES count every nearby party member's abilities together (Giant + Electric
--     opens the broken generator; neither player could alone).
--   * Party members standing near you sometimes find you an extra ingredient on pickup.
--   * Trials queue together; "Social Creature" quests count.
-- Solo play is never worse than before — parties only add.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local GameEvents = require(script.Parent.GameEvents)

local PartyService = {}
PartyService.MAX = 4

local partyOf: { [Player]: { Player } } = {}
local invites: { [Player]: { from: Player, at: number } } = {}
local inviteCooldown: { [Player]: number } = {}

local function members(player: Player): { Player }
	return partyOf[player] or { player }
end
PartyService.members = members

local function publish(party: { Player })
	local names = {}
	for _, p in ipairs(party) do
		table.insert(names, { name = p.DisplayName, userId = p.UserId })
	end
	for _, p in ipairs(party) do
		p:SetAttribute("PartySize", #party)
		Net.event("PartyState"):FireClient(p, { members = names })
	end
end

function PartyService.invite(from: Player, toUserId: number)
	local to = Players:GetPlayerByUserId(toUserId)
	if not to or to == from then
		return { ok = false, reason = "can't invite that player" }
	end
	if #members(from) >= PartyService.MAX then
		return { ok = false, reason = "party is full" }
	end
	local now = os.clock()
	if (inviteCooldown[from] or 0) > now then
		return { ok = false, reason = "slow down" }
	end
	inviteCooldown[from] = now + 2
	invites[to] = { from = from, at = now }
	Net.event("PartyInvite"):FireClient(to, { from = from.DisplayName, userId = from.UserId })
	return { ok = true }
end

function PartyService.accept(player: Player)
	local inv = invites[player]
	invites[player] = nil
	if not inv or os.clock() - inv.at > 60 or not inv.from.Parent then
		return { ok = false, reason = "invite expired" }
	end
	local existing = partyOf[inv.from]
	if existing and #existing >= PartyService.MAX then
		-- check BEFORE leaving your current party, so a full party never strands you
		return { ok = false, reason = "party is full" }
	end
	if existing and table.find(existing, player) then
		return { ok = true }
	end
	PartyService.leave(player)
	local party = partyOf[inv.from]
	if not party then
		party = { inv.from }
		partyOf[inv.from] = party
	end
	table.insert(party, player)
	partyOf[player] = party
	publish(party)
	for _, p in ipairs(party) do
		local ok, isFriend = pcall(p.IsFriendsWith, p, player.UserId)
		if p ~= player and ok and isFriend then
			local okA, Analytics = pcall(require, script.Parent.AnalyticsService)
			if okA then
				Analytics.track("friend_party", p, { size = #party })
			end
		end
	end
	GameEvents.fire(player, "party_joined", { size = #party })
	return { ok = true }
end

function PartyService.leave(player: Player)
	local party = partyOf[player]
	if not party then
		return { ok = true }
	end
	for i, p in ipairs(party) do
		if p == player then
			table.remove(party, i)
			break
		end
	end
	partyOf[player] = nil
	player:SetAttribute("PartySize", nil)
	Net.event("PartyState"):FireClient(player, { members = {} })
	if #party == 1 then
		partyOf[party[1]] = nil
		party[1]:SetAttribute("PartySize", nil)
		Net.event("PartyState"):FireClient(party[1], { members = {} })
	elseif #party > 1 then
		publish(party)
	end
	return { ok = true }
end

-- Abilities available at a spot: your own + every party member within `radius`.
function PartyService.abilitiesNear(player: Player, at: Vector3, radius: number): ({ [string]: boolean }, { Player })
	local union = {}
	local helpers = {}
	for _, p in ipairs(members(player)) do
		local hrp = p.Character and p.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		if p == player or (hrp and (hrp.Position - at).Magnitude <= radius) then
			local g = PlayerDataService.activeCreature(p)
			for ability, on in pairs(g and g.abilities or {}) do
				if on then
					union[ability] = true
				end
			end
			if p ~= player then
				table.insert(helpers, p)
			end
		end
	end
	return union, helpers
end

function PartyService.start()
	Net.func("PartyInviteSend").OnServerInvoke = function(player, userId)
		if type(userId) ~= "number" then
			return { ok = false }
		end
		return PartyService.invite(player, userId)
	end
	Net.func("PartyAccept").OnServerInvoke = function(player)
		return PartyService.accept(player)
	end
	Net.func("PartyLeave").OnServerInvoke = function(player)
		return PartyService.leave(player)
	end
	Players.PlayerRemoving:Connect(function(p)
		PartyService.leave(p)
		invites[p] = nil
		inviteCooldown[p] = nil
	end)
	print("[Party] ready")
end

return PartyService
