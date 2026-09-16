-- DevTiming — measures SPEC §99 non-negotiable #1:
--   "Feeding the first object occurs within ~15 seconds."
--
-- Simulates a plausibly slow player: 3s to look around and pick an egg, then
-- 2s to walk to the apple. If THAT still lands under 15s, a real player will too.
--
-- Last measured: eggs 0.56s · hatch 3.56s · apple 5.21s · FIRST FEED 7.21s — PASS

local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")
local Services = ServerScriptService:WaitForChild("Services")
local PlayerDataService = require(Services.PlayerDataService)
local FtueService = require(Services.FtueService)
local FeedingService = require(Services.FeedingService)

local TAG = "[TIMING]"

local function findAppleProp()
	for _, m in ipairs(workspace:GetChildren()) do
		if m:IsA("Model") and m:GetAttribute("Ingredient") == "Apple" then
			return m
		end
	end
	return nil
end

local function run(player)
	local t0 = os.clock()

	local eggsAt
	for _ = 1, 300 do
		if workspace:FindFirstChild("Eggs_" .. player.Name) then
			eggsAt = os.clock() - t0
			break
		end
		task.wait(0.05)
	end
	print(string.format("%s eggs visible at        %5.2fs", TAG, eggsAt or -1))

	task.wait(3) -- a slow player takes ~3s to choose
	FtueService.pickEgg(player, 2)
	print(string.format("%s creature hatched at     %5.2fs", TAG, os.clock() - t0))

	local appleAt
	for _ = 1, 300 do
		if findAppleProp() then
			appleAt = os.clock() - t0
			break
		end
		task.wait(0.05)
	end
	print(string.format("%s apple available at      %5.2fs", TAG, appleAt or -1))

	task.wait(2) -- ~2s to walk over and grab it
	local profile = PlayerDataService.get(player)
	profile.inventory.Apple = (profile.inventory.Apple or 0) + 1
	local result = FeedingService.feed(player, "Apple")
	local fedAt = os.clock() - t0

	local genome = PlayerDataService.activeCreature(player)
	print(string.format("%s FIRST FEED at           %5.2fs   ok=%s", TAG, fedAt, tostring(result.ok)))
	print(string.format("%s visible change          %s", TAG,
		tostring(genome and next(genome.mutations) ~= nil)))
	print(string.format("%s NON-NEGOTIABLE #1 (<15s): %s", TAG, fedAt <= 15 and "PASS" or "FAIL"))
end

Players.PlayerAdded:Connect(function(p) task.spawn(run, p) end)
for _, p in ipairs(Players:GetPlayers()) do task.spawn(run, p) end
