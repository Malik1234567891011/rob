--!strict
-- Shared.Net — lazily-created remotes, one name in one place.
-- SPEC §70: the client never asserts state, it only ASKS. Every remote below is
-- a request the server is free to refuse.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Net = {}

-- server -> client pushes
Net.EVENTS = {
	"ProfileSync",     -- full profile after join / after any change
	"CreatureSync",    -- genome changed (fed, mutated, evolved)
	"Toast",           -- transient message: trait found, mutation, reward
	"Evolution",       -- stage-up cinematic cue
	"FtueStep",        -- drives the scripted first 60 seconds
	"Reaction",        -- eat reaction: animation + sfx + colour
	"CreatureAction",  -- (creatureId, action) one-shot animation, broadcast to everyone
	"WorldNotice",     -- gate opened, world event
	"OfflineReport",   -- "WHILE YOU WERE GONE..."
	"TrialState",      -- trial lobby / run / results for participants
	"TrialFx",         -- hits, breaks, chests, finishes (everyone sees)
	"ParadeReaction",  -- a live 😂😍😱🤯 reaction to the monster on the runway
	"PartyState",      -- your party roster
	"PartyInvite",     -- someone invited you
	"Moment",          -- a shareable moment just happened (SPEC §39)
}

-- client -> server requests
Net.FUNCTIONS = {
	"PickEgg",
	"Pickup",
	"Feed",
	"NameCreature",
	"TryGate",
	"Evolve",
	"CreateLineage",
	"Inspect",
	"SetDetailMode",
	"TrialJoin",
	"TrialLeave",
	"ParadeJoin",
	"ParadeVote",
	"SanctuaryUpgrade",
	"SanctuaryDecor",
	"GardenPlant",
	"MerchantBuy",
	"ShopPrompt",
	"PartyInviteSend",
	"PartyAccept",
	"PartyLeave",
	"SwitchCreature",
	"NewEgg",
	"SetSetting",
	"Travel",
}

local folderName = "Net"

local function container(): Folder
	local existing = ReplicatedStorage:FindFirstChild(folderName)
	if existing then
		return existing :: Folder
	end
	if RunService:IsServer() then
		local f = Instance.new("Folder")
		f.Name = folderName
		f.Parent = ReplicatedStorage
		return f
	end
	return ReplicatedStorage:WaitForChild(folderName, 30) :: Folder
end

local function get(name: string, className: string): Instance
	local parent = container()
	local existing = parent:FindFirstChild(name)
	if existing then
		return existing
	end
	if RunService:IsServer() then
		local inst = Instance.new(className)
		inst.Name = name
		inst.Parent = parent
		return inst
	end
	return parent:WaitForChild(name, 30)
end

function Net.event(name: string): RemoteEvent
	return get(name, "RemoteEvent") :: RemoteEvent
end

function Net.func(name: string): RemoteFunction
	return get(name, "RemoteFunction") :: RemoteFunction
end

-- Called once on the server so clients never race a missing remote.
function Net.init()
	for _, name in ipairs(Net.EVENTS) do
		Net.event(name)
	end
	for _, name in ipairs(Net.FUNCTIONS) do
		Net.func(name)
	end
end

return Net
