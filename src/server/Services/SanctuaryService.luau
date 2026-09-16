--!strict
-- SanctuaryService — SPEC §16 (Sanctuary as autobiography), §29 (sinks), §15 (parents stay
-- forever), §53 (friends visit).
--
-- Each player gets a plot for the session. Upgrading a tier BUILDS things you can see; decor
-- fills slots; garden beds grow ingredients; retired lineage parents wander the lawn.
-- Plots are laid out by the world builder as Workspace.World.Plots.Plot_<n>, each with a
-- `Center` part whose CFrame's -Z faces the hub path.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local CollectionService = game:GetService("CollectionService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Kit = require(Shared:WaitForChild("Kit"))
local Sanctuary = require(Shared.Config:WaitForChild("Sanctuary"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local Ingredients = require(Shared.Config:WaitForChild("Ingredients"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local CreatureService = require(script.Parent.CreatureService)
local GameEvents = require(script.Parent.GameEvents)

local SanctuaryService = {}

local plotOf: { [number]: number } = {}          -- userId -> plot index
local ownerOf: { [number]: Player } = {}         -- plot index -> player
local builtFolder: { [number]: Folder } = {}     -- plot index -> runtime folder
local wanderers: { [number]: { any } } = {}

local function plotsRoot(): Instance?
	local world = workspace:FindFirstChild("World")
	return world and world:FindFirstChild("Plots")
end

local function plotCenter(index: number): CFrame
	local root = plotsRoot()
	local plot = root and root:FindFirstChild("Plot_" .. index)
	local center = plot and plot:FindFirstChild("Center") :: BasePart?
	if center then
		local p = center.Position
		return CFrame.new(p.X, p.Y - center.Size.Y * 0.5, p.Z) * center.CFrame.Rotation
	end
	-- fallback ring, so the game still runs before the world is built
	local a = (index - 1) / Sanctuary.MAX_PLOTS * math.pi * 2
	local pos = Vector3.new(math.cos(a) * 200, 0, math.sin(a) * 200)
	return CFrame.lookAt(pos, Vector3.new(0, 0, 0)) * CFrame.Angles(0, math.pi, 0)
end

function SanctuaryService.plotCF(player: Player): CFrame?
	local i = plotOf[player.UserId]
	return i and plotCenter(i) or nil
end

-- plot-local {x,y,z,yaw} -> world CFrame
local function toWorld(index: number, p): CFrame
	local base = plotCenter(index)
	-- plot-local -Z faces the hub; the Center part's LookVector points at the hub
	return base * CFrame.new(p[1], p[2], p[3]) * CFrame.Angles(0, math.rad(p[4] or 0), 0)
end

function SanctuaryService.spawnCF(player: Player): CFrame?
	local i = plotOf[player.UserId]
	if not i then
		return nil
	end
	local s = Sanctuary.spawn
	return toWorld(i, { s[1], s[2], s[3], 180 })
end

function SanctuaryService.eggCF(player: Player): CFrame?
	local i = plotOf[player.UserId]
	if not i then
		return nil
	end
	local s = Sanctuary.eggSpot
	return toWorld(i, { s[1], s[2], s[3], 0 })
end

-- ═══ BUILDING ════════════════════════════════════════════════════════════════

local function pop(model: Model)
	-- construction "pop": grow from 0.2 to full size with overshoot
	local final = model:GetScale()
	model:ScaleTo(final * 0.2)
	local v = Instance.new("NumberValue")
	v.Value = 0.2
	v.Changed:Connect(function(x)
		if model.Parent then
			model:ScaleTo(final * math.max(0.05, x))
		end
	end)
	local tw = TweenService:Create(v, TweenInfo.new(0.55, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Value = 1 })
	tw:Play()
	tw.Completed:Connect(function()
		v:Destroy()
	end)
end

local function placeBuild(index: number, buildName: string, animate: boolean)
	local folder = builtFolder[index]
	local spec = Sanctuary.builds[buildName]
	local assetName = Sanctuary.assetFor[buildName] or buildName
	if spec == "perimeter" then
		local half = Sanctuary.PLOT_SIZE / 2
		local seg = 8
		for side = 0, 3 do
			for k = 0, 7 do
				local along = -half + seg * (k + 0.5)
				local p
				if side == 0 then
					p = { along, 0, -half, 0 } -- front (entrance side)
				elseif side == 1 then
					p = { half, 0, along, 90 }
				elseif side == 2 then
					p = { -along, 0, half, 180 }
				else
					p = { -half, 0, -along, 270 }
				end
				local name = (side == 0 and (k == 3 or k == 4)) and ((k == 3) and "Gate_Picket" or "") or assetName
				if name ~= "" then
					local cf = toWorld(index, p)
					if name == "Gate_Picket" then
						cf = toWorld(index, { 0, 0, -half, 0 })
					end
					local m = Kit.place(name, cf, folder)
					if m and animate then
						pop(m)
					end
				end
			end
		end
		return
	end
	if spec == "path" then
		for k = 0, 6 do
			local z = -28 + k * 4.2
			local m = Kit.place(assetName, toWorld(index, { (k % 2 == 0) and 0.6 or -0.6, 0, z, k * 37 }), folder, { collide = false })
			if m and animate then
				task.delay(k * 0.08, pop, m)
			end
		end
		return
	end
	for _, p in ipairs(spec :: any) do
		local m = Kit.place(assetName, toWorld(index, p), folder, { scale = p[5] })
		if m then
			m:SetAttribute("Build", buildName)
			if buildName == "Windmill" then
				local sails = Kit.place("Windmill_Sails", m:GetPivot() * CFrame.new(0, 11, -3.6), folder, { collide = false })
				if sails then
					sails.Name = "WindmillSails"
					CollectionService:AddTag(sails, "Spin")
				end
			end
			if buildName == "Sanctuary_Sign" then
				local owner = ownerOf[index]
				local part = m.PrimaryPart :: BasePart
				local gui = Instance.new("SurfaceGui")
				gui.Face = Enum.NormalId.Front
				gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
				gui.PixelsPerStud = 40
				gui.LightInfluence = 0.3
				gui.Parent = part
				local label = Instance.new("TextLabel")
				label.BackgroundTransparency = 1
				label.Size = UDim2.fromScale(1, 0.5)
				label.Position = UDim2.fromScale(0, 0.25)
				label.Font = Enum.Font.FredokaOne
				label.TextScaled = true
				label.TextColor3 = Color3.fromRGB(92, 58, 30)
				label.Text = owner and (owner.DisplayName .. "'s Sanctuary") or "Sanctuary"
				label.Parent = gui
			end
			if animate then
				pop(m)
			end
		end
	end
end

local function buildUpTo(index: number, tier: number, animateTier: number?)
	for _, t in ipairs(Economy.sanctuaryTiers) do
		if t.tier <= tier then
			for _, b in ipairs(t.builds) do
				placeBuild(index, b, animateTier == t.tier)
			end
		end
	end
end

-- ═══ DECOR ═══════════════════════════════════════════════════════════════════

local function placeDecor(index: number, decorId: string, slot: number, animate: boolean)
	local s = Sanctuary.decorSlots[slot]
	if not s then
		return
	end
	local m = Kit.place(decorId, toWorld(index, { s[1], s[2], s[3], (slot * 53) % 360 }), builtFolder[index])
	if m then
		m:SetAttribute("DecorSlot", slot)
		if animate then
			pop(m)
		end
	end
end

function SanctuaryService.buyDecor(player: Player, decorId: string)
	local profile = PlayerDataService.get(player)
	local def = Sanctuary.decor[decorId]
	local index = plotOf[player.UserId]
	if not profile or not def or not index then
		return { ok = false, reason = "can't place that" }
	end
	local used = {}
	for _, d in ipairs(profile.sanctuary.decor) do
		used[d.slot] = true
	end
	local slot
	for i = 1, Sanctuary.slotsFor(profile.sanctuary.tier) do
		if not used[i] then
			slot = i
			break
		end
	end
	if not slot then
		return { ok = false, reason = "no free spots — upgrade your Sanctuary for more room" }
	end
	if not PlayerDataService.spend(player, { Coins = def.price, Essence = def.essence }) then
		return { ok = false, reason = "not enough coins" }
	end
	table.insert(profile.sanctuary.decor, { id = decorId, slot = slot })
	placeDecor(index, decorId, slot, true)
	GameEvents.fire(player, "sanctuary_decor", { decor = decorId })
	PlayerDataService.sync(player)
	return { ok = true, slot = slot }
end

function SanctuaryService.removeDecor(player: Player, slot: number)
	local profile = PlayerDataService.get(player)
	local index = plotOf[player.UserId]
	if not profile or not index then
		return { ok = false }
	end
	for i, d in ipairs(profile.sanctuary.decor) do
		if d.slot == slot then
			table.remove(profile.sanctuary.decor, i)
			for _, m in ipairs(builtFolder[index]:GetChildren()) do
				if m:GetAttribute("DecorSlot") == slot then
					m:Destroy()
				end
			end
			PlayerDataService.sync(player)
			return { ok = true }
		end
	end
	return { ok = false }
end

-- ═══ UPGRADES ════════════════════════════════════════════════════════════════

function SanctuaryService.upgrade(player: Player)
	local profile = PlayerDataService.get(player)
	local index = plotOf[player.UserId]
	if not profile or not index then
		return { ok = false, reason = "no sanctuary" }
	end
	local nextTier = Economy.sanctuaryTiers[profile.sanctuary.tier + 1]
	if not nextTier then
		return { ok = false, reason = "fully built!" }
	end
	if not PlayerDataService.spend(player, nextTier.cost) then
		return { ok = false, reason = "not enough" }
	end
	profile.sanctuary.tier = nextTier.tier
	for _, b in ipairs(nextTier.builds) do
		placeBuild(index, b, true)
	end
	if nextTier.builds[1] == "Garden_Bed" then
		SanctuaryService.refreshGarden(player)
	end
	GameEvents.fire(player, "sanctuary_upgrade", { tier = nextTier.tier })
	local ok, Analytics = pcall(require, script.Parent.AnalyticsService)
	if ok then
		Analytics.track("sanctuary_upgrade", player, { tier = nextTier.tier })
	end
	Net.event("Toast"):FireClient(player, { kind = "sanctuary", title = "SANCTUARY UPGRADED", label = "🏡 " .. nextTier.name, color = 0x5FD98C })
	PlayerDataService.sync(player)
	return { ok = true, tier = nextTier.tier }
end

-- ═══ GARDEN (SPEC §29 food cultivation) ══════════════════════════════════════

local function bedCF(index: number, bed: number, slot: number): CFrame?
	local beds = Sanctuary.builds.Garden_Bed
	local b = beds[bed]
	if not b then
		return nil
	end
	-- beds are ~8 long; three plants along the bed's long axis
	local base = toWorld(index, b)
	return base * CFrame.new((slot - 2) * 2.4, 1.1, 0)
end

function SanctuaryService.refreshGarden(player: Player)
	local profile = PlayerDataService.get(player)
	local index = plotOf[player.UserId]
	if not profile or not index or profile.sanctuary.tier < 6 then
		return
	end
	local folder = builtFolder[index]
	for _, c in ipairs(folder:GetChildren()) do
		if c:GetAttribute("GardenKey") then
			c:Destroy()
		end
	end
	for key, plant in pairs(profile.sanctuary.garden) do
		local bed, slot = string.match(key, "^(%d+):(%d+)$")
		local cf = bedCF(index, tonumber(bed) or 1, tonumber(slot) or 1)
		local def = Ingredients.get(plant.id)
		if cf and def then
			local grow = Economy.garden.growSeconds[def.rarity] or 300
			local progress = math.clamp((os.time() - plant.at) / grow, 0, 1)
			local model = PropBuilder.build(plant.id)
			if model then
				model:SetAttribute("GardenKey", key)
				local ext = model:GetExtentsSize()
				local s = 0.25 + 0.75 * progress
				model:ScaleTo(math.clamp(1.2 / math.max(ext.X, ext.Y, ext.Z), 0.2, 1) * s)
				model:PivotTo(cf)
				model.Parent = folder
				local prompt = Instance.new("ProximityPrompt")
				prompt.RequiresLineOfSight = false
				prompt.MaxActivationDistance = 8
				prompt.ActionText = progress >= 1 and "Harvest" or string.format("Growing %d%%", math.floor(progress * 100))
				prompt.ObjectText = def.display
				prompt.Enabled = true
				prompt.Parent = model.PrimaryPart
				prompt.Triggered:Connect(function(who)
					if who == player then
						SanctuaryService.harvest(player, key)
					end
				end)
			end
		end
	end
end

function SanctuaryService.plant(player: Player, ingredientId: string)
	local profile = PlayerDataService.get(player)
	if not profile or profile.sanctuary.tier < 6 then
		return { ok = false, reason = "build Garden Beds first" }
	end
	local def = Ingredients.get(ingredientId)
	if not def or (profile.inventory[ingredientId] or 0) <= 0 then
		return { ok = false, reason = "you don't have that" }
	end
	local key
	for bed = 1, #Sanctuary.builds.Garden_Bed do
		for slot = 1, Economy.garden.plotsPerBed do
			local k = bed .. ":" .. slot
			if not profile.sanctuary.garden[k] then
				key = k
				break
			end
		end
		if key then
			break
		end
	end
	if not key then
		return { ok = false, reason = "garden is full" }
	end
	profile.inventory[ingredientId] -= 1
	if profile.inventory[ingredientId] <= 0 then
		profile.inventory[ingredientId] = nil
	end
	profile.sanctuary.garden[key] = { id = ingredientId, at = os.time() }
	SanctuaryService.refreshGarden(player)
	PlayerDataService.sync(player)
	return { ok = true }
end

function SanctuaryService.harvest(player: Player, key: string)
	local profile = PlayerDataService.get(player)
	local plant = profile and profile.sanctuary.garden[key]
	if not plant then
		return { ok = false }
	end
	local def = Ingredients.get(plant.id)
	local grow = Economy.garden.growSeconds[def.rarity] or 300
	if os.time() - plant.at < grow then
		return { ok = false, reason = "still growing" }
	end
	local n = Economy.garden.yield[def.rarity] or 1
	PlayerDataService.give(player, plant.id, n)
	profile.sanctuary.garden[key] = nil
	Net.event("Toast"):FireClient(player, { kind = "pickup", title = "HARVESTED", label = def.emoji .. " " .. def.display .. " x" .. n, color = 0x5FD98C })
	SanctuaryService.refreshGarden(player)
	PlayerDataService.sync(player)
	return { ok = true }
end

-- ═══ RETIRED PARENTS WANDER (SPEC §15, §16) ══════════════════════════════════

local function spawnWanderers(player: Player, index: number)
	local profile = PlayerDataService.get(player)
	if not profile then
		return
	end
	local list = {}
	for i, genome in ipairs(profile.creatures) do
		if genome.retired and i ~= profile.activeCreature and #list < 6 then
			local ok, model = pcall(CreatureBuilder.build, genome, 2)
			if ok and model then
				model.Name = (genome.name or "Elder") .. "_home"
				model:SetAttribute("HomeOf", player.UserId)
				local home = toWorld(index, { math.random(-14, 14), 0, math.random(-10, 14), math.random(0, 359) })
				local go = model:GetAttribute("GroundOffset") or 0
				model:PivotTo(home + Vector3.new(0, CreatureService.groundAt(home.Position.X, home.Position.Z, home.Position.Y) - home.Position.Y + go, 0))
				model.Parent = builtFolder[index]
				CollectionService:AddTag(model, "FAMCreature")
				table.insert(list, { model = model, target = model:GetPivot().Position, nextAt = os.clock() + math.random(2, 6), go = go })
			end
		end
	end
	wanderers[index] = list
end

local function wanderStep(dt: number)
	local now = os.clock()
	for index, list in pairs(wanderers) do
		for _, w in ipairs(list) do
			local root = w.model.PrimaryPart
			if not root or not w.model.Parent then
				continue
			end
			if now > w.nextAt then
				local r = Sanctuary.wanderRadius
				local t = toWorld(index, { math.random(-r, r), 0, math.random(-r, r), 0 })
				w.target = t.Position
				w.nextAt = now + math.random(4, 10)
				if math.random() < 0.3 then
					w.model:SetAttribute("Mood", math.random() < 0.5 and "sit" or "sleep")
					w.nextAt = now + math.random(8, 16)
				else
					w.model:SetAttribute("Mood", nil)
				end
			end
			if w.model:GetAttribute("Mood") then
				continue
			end
			local pos = root.Position
			local to = Vector3.new(w.target.X - pos.X, 0, w.target.Z - pos.Z)
			if to.Magnitude > 0.8 then
				local step = to.Unit * math.min(to.Magnitude, 6 * dt)
				local nx, nz = pos.X + step.X, pos.Z + step.Z
				local y = CreatureService.groundAt(nx, nz, pos.Y) + w.go
				root.CFrame = CFrame.lookAt(Vector3.new(nx, y, nz), Vector3.new(nx + to.Unit.X, y, nz + to.Unit.Z))
			end
		end
	end
end

-- ═══ PLOT LIFECYCLE ══════════════════════════════════════════════════════════

local function assign(player: Player, profile)
	for i = 1, Sanctuary.MAX_PLOTS do
		if not ownerOf[i] then
			ownerOf[i] = player
			plotOf[player.UserId] = i
			local folder = Instance.new("Folder")
			folder.Name = "Sanctuary_" .. player.Name
			folder:SetAttribute("Owner", player.UserId)
			folder:SetAttribute("Plot", i)
			folder.Parent = workspace
			builtFolder[i] = folder
			player:SetAttribute("Plot", i)
			buildUpTo(i, profile.sanctuary.tier, nil)
			for _, d in ipairs(profile.sanctuary.decor) do
				placeDecor(i, d.id, d.slot, false)
			end
			SanctuaryService.refreshGarden(player)
			spawnWanderers(player, i)
			return i
		end
	end
	return nil
end

local function release(player: Player)
	local i = plotOf[player.UserId]
	if not i then
		return
	end
	if builtFolder[i] then
		builtFolder[i]:Destroy()
	end
	builtFolder[i] = nil
	wanderers[i] = nil
	ownerOf[i] = nil
	plotOf[player.UserId] = nil
end

-- Visiting: when a friend walks onto your plot (SPEC §53).
local visitCooldown: { [string]: number } = {}
local function visitCheck()
	for _, visitor in ipairs(Players:GetPlayers()) do
		local hrp = visitor.Character and visitor.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		if hrp then
			for i, owner in pairs(ownerOf) do
				if owner ~= visitor then
					local local_ = plotCenter(i):PointToObjectSpace(hrp.Position)
					if math.abs(local_.X) < 32 and math.abs(local_.Z) < 32 then
						local key = visitor.UserId .. ":" .. owner.UserId
						if (visitCooldown[key] or 0) < os.clock() then
							visitCooldown[key] = os.clock() + 600
							local ok, isFriend = pcall(visitor.IsFriendsWith, visitor, owner.UserId)
							local okA, Analytics = pcall(require, script.Parent.AnalyticsService)
							if okA and ok and isFriend then
								Analytics.track("friend_sanctuary_visit", visitor, { owner = owner.UserId })
							end
							Net.event("Toast"):FireClient(owner, { kind = "visit", title = "VISITOR", label = "👋 " .. visitor.DisplayName .. " is visiting your Sanctuary", color = 0x6FA8FF })
						end
					end
				end
			end
		end
	end
end

function SanctuaryService.start()
	PlayerDataService.onLoaded(function(player, profile)
		assign(player, profile)
		local function toPlot(char: Model)
			task.defer(function()
				local cf = SanctuaryService.spawnCF(player)
				local TrialService = script.Parent:FindFirstChild("TrialService") and require(script.Parent.TrialService)
				if cf and char.Parent and not (TrialService and TrialService.inTrial(player)) then
					char:PivotTo(cf)
				end
			end)
		end
		if player.Character then
			toPlot(player.Character)
		end
		player.CharacterAdded:Connect(toPlot)
	end)
	Players.PlayerRemoving:Connect(release)

	Net.func("SanctuaryUpgrade").OnServerInvoke = function(player)
		return SanctuaryService.upgrade(player)
	end
	Net.func("SanctuaryDecor").OnServerInvoke = function(player, action, arg)
		if action == "buy" and type(arg) == "string" then
			return SanctuaryService.buyDecor(player, arg)
		elseif action == "remove" and type(arg) == "number" then
			return SanctuaryService.removeDecor(player, arg)
		end
		return { ok = false }
	end
	Net.func("GardenPlant").OnServerInvoke = function(player, ingredientId)
		if type(ingredientId) ~= "string" then
			return { ok = false }
		end
		return SanctuaryService.plant(player, ingredientId)
	end

	RunService.Heartbeat:Connect(wanderStep)
	task.spawn(function()
		while true do
			task.wait(15)
			for _, p in ipairs(Players:GetPlayers()) do
				local profile = PlayerDataService.get(p)
				if profile and next(profile.sanctuary.garden) then
					SanctuaryService.refreshGarden(p)
				end
			end
		end
	end)
	task.spawn(function()
		while true do
			task.wait(3)
			visitCheck()
		end
	end)
	print("[Sanctuary] ready")
end

return SanctuaryService
