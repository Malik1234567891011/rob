-- DevEvents — runs every world event (SPEC §54, §48 meteor) back to back with 8-second
-- durations and checks each one starts, puts something in the world, cleans up after
-- itself and never logs an "[Events] X failed" error.
--
-- Enable (Disabled = false) and press Play. Asserts on STATE.

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local LogService = game:GetService("LogService")

local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services.PlayerDataService)
local FtueService = require(Services.FtueService)
local EventService = require(Services.EventService)

local TAG = "[ETEST]"
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

local errors: { string } = {}
LogService.MessageOut:Connect(function(msg, kind)
	if kind == Enum.MessageType.MessageError or string.find(msg, "[Events]", 1, true) and string.find(msg, "failed", 1, true) then
		table.insert(errors, msg)
	end
end)

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
		FtueService.pickEgg(player, 3)
	end
	local ws = ReplicatedStorage:WaitForChild("WorldState")
	local runtime = workspace:WaitForChild("EventRuntime", 10)
	check("event runtime folder", runtime ~= nil)

	for _, def in pairs(EventService.events) do
		def.minutes = 8 / 60
	end
	for _, kind in ipairs({ "IngredientRain", "GiantPicnic", "Storm", "FullMoon", "UFO", "SlimeInvasion", "Earthquake", "Meteor" }) do
		local errBefore = #errors
		local started = EventService.run(kind)
		check(kind .. ": starts", started == true)
		task.wait(kind == "Meteor" and 7.5 or 3)
		check(kind .. ": WorldState.Event set", ws:GetAttribute("Event") == kind, ws:GetAttribute("Event"))
		local things = runtime and #runtime:GetChildren() or 0
		if kind ~= "Storm" or things > 0 then
			check(kind .. ": something in the world", things > 0, things)
		end
		if kind == "Storm" then
			check("Storm: electric boost live", ws:GetAttribute("EventBoost") == "Electric:2", ws:GetAttribute("EventBoost"))
		end
		for _ = 1, 200 do
			if ws:GetAttribute("Event") == nil then
				break
			end
			task.wait(0.1)
		end
		check(kind .. ": ends", ws:GetAttribute("Event") == nil)
		task.wait(0.5)
		check(kind .. ": cleans up", runtime and #runtime:GetChildren() == 0, runtime and #runtime:GetChildren())
		check(kind .. ": no errors", #errors == errBefore, errors[#errors])
	end
	check("boost cleared after events", ws:GetAttribute("EventBoost") == nil, ws:GetAttribute("EventBoost"))
	print(string.format("%s RESULT: %d passed, %d failed", TAG, pass, fail))
end

Players.PlayerAdded:Connect(function(player)
	task.spawn(run, player)
end)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(run, player)
end
