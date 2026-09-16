--!strict
-- EventService — SPEC §48 (weekly meteor) and §54 (world events create server culture).
--
-- Rule from the spec: NO EVENT SIMPLY MEANS "Coins x2". Every event changes what players
-- do for a few minutes:
--   Meteor      — genuine countdown; it crashes into a biome; everyone cracks it together;
--                 strange ingredients inside. Saturdays on a schedule + rare surprise falls.
--   IngredientRain — food falls from the sky in the Meadow and hub; scramble for it.
--   GiantPicnic — a picnic blanket of rare treats appears; first come first fed.
--   Storm       — electric creatures go wild; Electric foods are doubly strong; lightning
--                 leaves Batteries and Star Fragments where it strikes.
--   FullMoon    — night traits wake up; Moon Mushrooms sprout; creatures glow.
--   UFO         — a saucer beams random creatures up for a moment and returns them with
--                 weird residue (Alien Goo + a nudge of Mystic).
--   SlimeInvasion — slimes steal pickups and flee; catch them to get it all back.
--   Earthquake  — a sealed crystal pocket in the caves cracks open for a while.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")
local Lighting = game:GetService("Lighting")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Net = require(Shared:WaitForChild("Net"))
local Economy = require(Shared.Config:WaitForChild("Economy"))
local Trials = require(Shared.Config:WaitForChild("Trials"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))

local PlayerDataService = require(script.Parent.PlayerDataService)
local CreatureService = require(script.Parent.CreatureService)
local GameEvents = require(script.Parent.GameEvents)

local EventService = {}

local worldState: Folder
local active: string? = nil
local activeEndsAt = 0
local runtime: Folder

local EVENTS = {
	IngredientRain = { display = "Ingredient Rain", emoji = "🌧️", minutes = 2, weight = 20 },
	GiantPicnic = { display = "Giant Picnic", emoji = "🧺", minutes = 3, weight = 14 },
	Storm = { display = "Storm", emoji = "⛈️", minutes = 3, weight = 14 },
	FullMoon = { display = "Full Moon", emoji = "🌕", minutes = 4, weight = 10, night = true },
	UFO = { display = "UFO Sighting", emoji = "🛸", minutes = 2, weight = 10 },
	SlimeInvasion = { display = "Slime Invasion", emoji = "🟢", minutes = 3, weight = 14 },
	Earthquake = { display = "Earthquake", emoji = "🌋", minutes = 4, weight = 8 },
	Meteor = { display = "Something Fell From The Sky", emoji = "☄️", minutes = 6, weight = 0 },
}
EventService.events = EVENTS

-- ═══ HELPERS ═════════════════════════════════════════════════════════════════

local function markerList(prefix: string): { BasePart }
	local out = {}
	local world = workspace:FindFirstChild("World")
	if not world then
		return out
	end
	for _, d in ipairs(world:GetDescendants()) do
		if d:IsA("BasePart") and string.sub(d.Name, 1, #prefix) == prefix then
			table.insert(out, d)
		end
	end
	return out
end

local function randomSpot(prefix: string, fallback: Vector3): Vector3
	local list = markerList(prefix)
	if #list == 0 then
		return fallback
	end
	return list[math.random(1, #list)].Position
end

local function jitter(p: Vector3, r: number): Vector3
	local a = math.random() * math.pi * 2
	local d = math.sqrt(math.random()) * r
	return p + Vector3.new(math.cos(a) * d, 0, math.sin(a) * d)
end

local function groundAt(p: Vector3): Vector3
	return Vector3.new(p.X, CreatureService.groundAt(p.X, p.Z, p.Y + 40), p.Z)
end

-- A pickup that exists only for the event, then vanishes.
function EventService.spawnPickup(ingredientId: string, at: Vector3, lifetime: number?, fromSky: boolean?)
	local model = PropBuilder.build(ingredientId)
	if not model then
		return nil
	end
	local ground = groundAt(at)
	local extents = model:GetExtentsSize()
	local rest = CFrame.new(ground + Vector3.new(0, extents.Y * 0.5 + 0.1, 0)) * CFrame.Angles(0, math.random() * 6.28, 0)
	model:PivotTo(fromSky and (rest + Vector3.new(0, 60, 0)) or rest)
	model.Parent = runtime
	if fromSky and model.PrimaryPart then
		local root = model.PrimaryPart
		local offset = root.CFrame:ToObjectSpace(model:GetPivot())
		local cv = Instance.new("CFrameValue")
		cv.Value = model:GetPivot()
		cv.Changed:Connect(function(v)
			if model.Parent then
				model:PivotTo(v)
			end
		end)
		TweenService:Create(cv, TweenInfo.new(1.4 + math.random(), Enum.EasingStyle.Bounce), { Value = rest }):Play()
		task.delay(3, function()
			cv:Destroy()
		end)
		local _ = offset
	end
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Take"
	prompt.ObjectText = ingredientId
	prompt.HoldDuration = 0
	prompt.MaxActivationDistance = 11
	prompt.RequiresLineOfSight = false
	prompt.Parent = model.PrimaryPart or model:FindFirstChildWhichIsA("BasePart")
	prompt.Triggered:Connect(function(player)
		if not model.Parent then
			return
		end
		PlayerDataService.give(player, ingredientId, 1)
		GameEvents.fire(player, "pickup", { ingredient = ingredientId, biome = "Event" })
		Net.event("Toast"):FireClient(player, { kind = "pickup", title = "PICKED UP", label = ingredientId, color = 0xFFD52E })
		PlayerDataService.sync(player)
		model:Destroy()
	end)
	task.delay(lifetime or 120, function()
		if model.Parent then
			model:Destroy()
		end
	end)
	return model
end

local function announce(kind: string, extra)
	local def = EVENTS[kind]
	local payload = { kind = "event", event = kind, display = def.display, emoji = def.emoji, endsAt = activeEndsAt }
	for k, v in pairs(extra or {}) do
		payload[k] = v
	end
	Net.event("WorldNotice"):FireAllClients(payload)
end

local function rewardAll(rewards, reason: string)
	for _, p in ipairs(Players:GetPlayers()) do
		PlayerDataService.addCurrency(p, rewards)
		PlayerDataService.stat(p, "eventsJoined")
		GameEvents.fire(p, "event_joined", { event = reason })
		PlayerDataService.sync(p)
	end
end

-- ═══ EVENT IMPLEMENTATIONS ═══════════════════════════════════════════════════

local RAIN_POOL = { "Apple", "Strawberry", "Blueberry", "Cookie", "Carrot", "Honeycomb", "Feather", "Battery", "BouncyBall", "Mushroom", "Cupcake", "CloudBerry" }

local handlers = {}

handlers.IngredientRain = function(duration)
	local centers = { randomSpot("EventSpot_Meadow", Vector3.new(380, 0, 0)), randomSpot("EventSpot_Hub", Vector3.new(0, 0, 0)) }
	local stop = os.clock() + duration
	while os.clock() < stop and active == "IngredientRain" do
		for _, c in ipairs(centers) do
			EventService.spawnPickup(RAIN_POOL[math.random(1, #RAIN_POOL)], jitter(c, 45), 90, true)
		end
		task.wait(1.6)
	end
end

handlers.GiantPicnic = function(duration)
	local at = groundAt(randomSpot("EventSpot_Meadow", Vector3.new(380, 0, 0)))
	local blanket = Instance.new("Part")
	blanket.Name = "PicnicBlanket"
	blanket.Anchored = true
	blanket.Size = Vector3.new(26, 0.2, 18)
	blanket.CFrame = CFrame.new(at + Vector3.new(0, 0.1, 0))
	blanket.Color = Color3.fromRGB(226, 76, 76)
	blanket.Material = Enum.Material.Fabric
	blanket.Parent = runtime
	local treats = { "Watermelon", "Cupcake", "Cookie", "Cheese", "Strawberry", "CloudBerry", "Honeycomb", "Pumpkin", "Clover" }
	for i = 1, 16 do
		EventService.spawnPickup(treats[(i % #treats) + 1], at + Vector3.new(math.random(-11, 11), 0, math.random(-7, 7)), duration + 20)
	end
	task.wait(duration)
end

handlers.Storm = function(duration)
	worldState:SetAttribute("EventBoost", "Electric:2")
	local stop = os.clock() + duration
	while os.clock() < stop and active == "Storm" do
		local c = jitter(randomSpot("EventSpot_", Vector3.new(0, 0, 0)), 60)
		Net.event("WorldNotice"):FireAllClients({ kind = "lightning", at = groundAt(c) })
		EventService.spawnPickup(math.random() < 0.8 and "Battery" or "StarFragment", c, 60)
		-- electric creatures go crazy
		for _, p in ipairs(Players:GetPlayers()) do
			local g = PlayerDataService.activeCreature(p)
			if g and (CreatureBuilder.effectiveTraits(g).Electric or 0) > 10 then
				CreatureService.actionFor(p, math.random() < 0.5 and "hop" or "celebrate")
			end
		end
		task.wait(4 + math.random() * 3)
	end
	worldState:SetAttribute("EventBoost", nil)
end

handlers.FullMoon = function(duration)
	local prevClock = Lighting.ClockTime
	Lighting.ClockTime = 0.5
	worldState:SetAttribute("EventBoost", "Night:2,Celestial:1.5")
	for _ = 1, 10 do
		EventService.spawnPickup("MoonMushroom", jitter(randomSpot("EventSpot_", Vector3.new(0, 0, 0)), 50), duration + 30)
	end
	task.wait(duration)
	worldState:SetAttribute("EventBoost", nil)
	Lighting.ClockTime = prevClock
end

handlers.UFO = function(duration)
	local center = groundAt(randomSpot("EventSpot_Hub", Vector3.new(0, 0, 0)))
	local saucer = Instance.new("Part")
	saucer.Name = "UFO"
	saucer.Shape = Enum.PartType.Cylinder
	saucer.Size = Vector3.new(3, 26, 26)
	saucer.Material = Enum.Material.Metal
	saucer.Color = Color3.fromRGB(170, 180, 195)
	saucer.Anchored = true
	saucer.CanCollide = false
	saucer.CFrame = CFrame.new(center + Vector3.new(0, 70, 0)) * CFrame.Angles(0, 0, math.rad(90))
	saucer.Parent = runtime
	local dome = Instance.new("Part")
	dome.Shape = Enum.PartType.Ball
	dome.Size = Vector3.new(11, 11, 11)
	dome.Material = Enum.Material.Glass
	dome.Transparency = 0.3
	dome.Color = Color3.fromRGB(150, 255, 150)
	dome.Anchored = true
	dome.CanCollide = false
	dome.CFrame = CFrame.new(center + Vector3.new(0, 73, 0))
	dome.Parent = runtime
	local light = Instance.new("SpotLight")
	light.Face = Enum.NormalId.Left
	light.Range = 80
	light.Angle = 40
	light.Brightness = 4
	light.Color = Color3.fromRGB(170, 255, 140)
	light.Parent = saucer
	local stop = os.clock() + duration
	local t = 0
	while os.clock() < stop and active == "UFO" do
		t += 1
		-- drift over the hub
		local p = center + Vector3.new(math.sin(t * 0.3) * 30, 70, math.cos(t * 0.23) * 30)
		saucer.CFrame = CFrame.new(p) * CFrame.Angles(0, t * 0.5, math.rad(90))
		dome.CFrame = CFrame.new(p + Vector3.new(0, 3, 0))
		if t % 6 == 0 then
			local list = Players:GetPlayers()
			local victim = list[math.random(1, #list)]
			if victim then
				CreatureService.actionFor(victim, "evolve") -- floats up and spins
				Net.event("WorldNotice"):FireAllClients({ kind = "abducted", owner = victim.DisplayName })
				task.delay(3.2, function()
					local g = PlayerDataService.activeCreature(victim)
					if g then
						g.traits.Mystic = (g.traits.Mystic or 0) + 2
					end
					PlayerDataService.give(victim, "AlienGoo", 1)
					Net.event("Toast"):FireClient(victim, { kind = "event", title = "RETURNED", label = "🛸 Your monster came back... sticky.", sub = "+ Alien Goo", color = 0xA6FF4D })
					PlayerDataService.sync(victim)
				end)
			end
		end
		task.wait(1)
	end
end

handlers.SlimeInvasion = function(duration)
	local center = groundAt(randomSpot("EventSpot_Meadow", Vector3.new(380, 0, 0)))
	local slimes = {}
	for i = 1, 12 do
		local s = PropBuilder.build("Slime")
		if s then
			s.Name = "InvaderSlime"
			local stolen = RAIN_POOL[math.random(1, #RAIN_POOL)]
			s:SetAttribute("Stolen", stolen)
			s:PivotTo(CFrame.new(jitter(center, 40)))
			s.Parent = runtime
			local prompt = Instance.new("ProximityPrompt")
			prompt.ActionText = "Catch"
			prompt.ObjectText = "Slime (it has a " .. stolen .. "!)"
			prompt.HoldDuration = 0.2
			prompt.MaxActivationDistance = 10
			prompt.RequiresLineOfSight = false
			prompt.Parent = s.PrimaryPart
			prompt.Triggered:Connect(function(player)
				if not s.Parent then
					return
				end
				PlayerDataService.give(player, "Slime", 1)
				PlayerDataService.give(player, stolen, 1)
				Net.event("Toast"):FireClient(player, { kind = "event", title = "CAUGHT ONE", label = "🟢 Slime + " .. stolen, color = 0x5FD98C })
				PlayerDataService.sync(player)
				s:Destroy()
			end)
			table.insert(slimes, s)
		end
	end
	local stop = os.clock() + duration
	while os.clock() < stop and active == "SlimeInvasion" do
		for _, s in ipairs(slimes) do
			if s.Parent then
				-- hop away from the nearest player
				local pos = s:GetPivot().Position
				local nearest, nd = nil, 30
				for _, p in ipairs(Players:GetPlayers()) do
					local hrp = p.Character and p.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
					if hrp and (hrp.Position - pos).Magnitude < nd then
						nearest, nd = hrp, (hrp.Position - pos).Magnitude
					end
				end
				local dir = nearest and (pos - nearest.Position) or Vector3.new(math.random() - 0.5, 0, math.random() - 0.5)
				dir = Vector3.new(dir.X, 0, dir.Z)
				if dir.Magnitude > 0.01 then
					local nextP = groundAt(pos + dir.Unit * (nearest and 7 or 3))
					s:PivotTo(CFrame.new(nextP + Vector3.new(0, 0.6, 0)))
				end
			end
		end
		task.wait(0.9)
	end
	for _, s in ipairs(slimes) do
		if s.Parent then
			s:Destroy()
		end
	end
end

handlers.Earthquake = function(duration)
	Net.event("WorldNotice"):FireAllClients({ kind = "shake", strength = 1 })
	local world = workspace:FindFirstChild("World")
	local seal = world and world:FindFirstChild("QuakeSeal", true) :: BasePart?
	if seal then
		seal.Transparency = 1
		seal.CanCollide = false
	end
	for _ = 1, 8 do
		EventService.spawnPickup(({ "Amethyst", "Geode", "CrystalShard", "Fossil" })[math.random(1, 4)],
			jitter(randomSpot("EventSpot_Quake", randomSpot("EventSpot_Caves", Vector3.new(0, 0, -420))), 14), duration + 10)
	end
	task.wait(duration)
	if seal then
		seal.Transparency = 0
		seal.CanCollide = true
	end
end

-- ═══ THE METEOR (SPEC §48) ═══════════════════════════════════════════════════

local METEOR_LOOT = { "Meteorite", "StarFragment", "CrystalShard", "MoonMushroom", "CloudBerry", "AlienGoo", "Obsidian", "Amethyst" }

handlers.Meteor = function(duration)
	local impact = groundAt(randomSpot("EventSpot_Meteor", randomSpot("EventSpot_Meadow", Vector3.new(380, 0, 0))))
	Net.event("WorldNotice"):FireAllClients({ kind = "meteor_incoming", at = impact })
	task.wait(4)
	local rock = PropBuilder.build("Meteorite")
	local core: BasePart
	if rock then
		rock:ScaleTo(6)
		core = rock.PrimaryPart :: BasePart
	else
		rock = Instance.new("Model")
		local p = Instance.new("Part")
		p.Shape = Enum.PartType.Ball
		p.Size = Vector3.new(12, 12, 12)
		p.Material = Enum.Material.Basalt
		p.Color = Color3.fromRGB(60, 50, 70)
		p.Anchored = true
		p.Parent = rock
		rock.PrimaryPart = p
		core = p
	end
	rock.Name = "Meteor"
	local rest = CFrame.new(impact + Vector3.new(0, 4, 0))
	rock:PivotTo(rest + Vector3.new(80, 260, 40))
	rock.Parent = runtime
	local glow = Instance.new("PointLight")
	glow.Color = Color3.fromRGB(190, 120, 255)
	glow.Range = 40
	glow.Brightness = 3
	glow.Parent = core
	local fall = Instance.new("CFrameValue")
	fall.Value = rock:GetPivot()
	fall.Changed:Connect(function(v)
		rock:PivotTo(v)
	end)
	local tw = TweenService:Create(fall, TweenInfo.new(2.2, Enum.EasingStyle.Quad, Enum.EasingDirection.In), { Value = rest })
	tw:Play()
	tw.Completed:Wait()
	fall:Destroy()
	Net.event("WorldNotice"):FireAllClients({ kind = "meteor_impact", at = impact })
	Net.event("WorldNotice"):FireAllClients({ kind = "shake", strength = 2 })

	local hp = 80 + 25 * #Players:GetPlayers()
	local maxHp = hp
	local contributors: { [Player]: number } = {}
	rock:SetAttribute("HP", hp)
	rock:SetAttribute("MaxHP", maxHp)
	local cracked = false
	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Crack!"
	prompt.ObjectText = "Meteor"
	prompt.HoldDuration = 0
	prompt.MaxActivationDistance = 20
	prompt.RequiresLineOfSight = false
	prompt.Parent = core
	local lastHit: { [Player]: number } = {}
	prompt.Triggered:Connect(function(player)
		if cracked then
			return
		end
		local now = os.clock()
		if now - (lastHit[player] or 0) < 0.25 then
			return
		end
		lastHit[player] = now
		local g = PlayerDataService.activeCreature(player)
		local stats = Trials.stats(g and CreatureBuilder.effectiveTraits(g) or {}, g and g.abilities or {}, g and g.stage or 1)
		hp -= stats.strength
		contributors[player] = (contributors[player] or 0) + stats.strength
		rock:SetAttribute("HP", hp)
		CreatureService.actionFor(player, "hop")
		if hp <= 0 then
			cracked = true
		end
	end)
	local stop = os.clock() + duration
	while os.clock() < stop and not cracked do
		task.wait(0.5)
	end
	if cracked then
		Net.event("WorldNotice"):FireAllClients({ kind = "meteor_cracked", at = impact })
		for player, dmg in pairs(contributors) do
			if player.Parent then
				local share = math.clamp(math.floor(dmg / maxHp * 12) + 3, 3, 8)
				for _ = 1, share do
					PlayerDataService.give(player, METEOR_LOOT[math.random(1, #METEOR_LOOT)], 1)
				end
				PlayerDataService.addCurrency(player, Economy.rewards.meteorCrack)
				GameEvents.fire(player, "event_joined", { event = "Meteor" })
				Net.event("Toast"):FireClient(player, { kind = "event", title = "METEOR CRACKED", label = "☄️ " .. share .. " strange things inside!", color = 0xB07CFF })
				PlayerDataService.sync(player)
			end
		end
	end
	rock:Destroy()
end

-- ═══ SCHEDULING ══════════════════════════════════════════════════════════════

-- Saturdays (UTC) at 14:00, 17:00 and 20:00, so every region gets a real one.
function EventService.nextMeteorAt(now: number): number
	local base = math.floor(now / 3600) * 3600
	for h = 0, 24 * 8 do
		local t = base + h * 3600
		local d = os.date("!*t", t)
		if t > now and d.wday == 7 and (d.hour == 14 or d.hour == 17 or d.hour == 20) then
			return t
		end
	end
	return now + 7 * 86400
end

function EventService.run(kind: string)
	if active or not handlers[kind] then
		return false
	end
	local def = EVENTS[kind]
	active = kind
	local duration = def.minutes * 60
	activeEndsAt = workspace:GetServerTimeNow() + duration
	worldState:SetAttribute("Event", kind)
	worldState:SetAttribute("EventEndsAt", activeEndsAt)
	announce(kind)
	task.spawn(function()
		local ok, err = pcall(handlers[kind], duration)
		if not ok then
			warn("[Events] " .. kind .. " failed: " .. tostring(err))
		end
		rewardAll(Economy.rewards.eventJoined, kind)
		active = nil
		worldState:SetAttribute("Event", nil)
		worldState:SetAttribute("EventEndsAt", nil)
		Net.event("WorldNotice"):FireAllClients({ kind = "event_over", event = kind })
		for _, c in ipairs(runtime:GetChildren()) do
			c:Destroy()
		end
	end)
	return true
end

function EventService.boost(trait: string): number
	local b = worldState and worldState:GetAttribute("EventBoost")
	if type(b) ~= "string" then
		return 1
	end
	for pair in string.gmatch(b, "[^,]+") do
		local t, m = string.match(pair, "(%w+):([%d%.]+)")
		if t == trait then
			return tonumber(m) or 1
		end
	end
	return 1
end

function EventService.start()
	worldState = ReplicatedStorage:WaitForChild("WorldState") :: Folder
	runtime = Instance.new("Folder")
	runtime.Name = "EventRuntime"
	runtime.Parent = workspace

	local nextMeteor = EventService.nextMeteorAt(os.time())
	worldState:SetAttribute("NextMeteorAt", nextMeteor)
	local nextRandom = os.time() + math.random(8, 14) * 60

	task.spawn(function()
		while true do
			task.wait(5)
			local now = os.time()
			if not active and now >= nextMeteor then
				EventService.run("Meteor")
				nextMeteor = EventService.nextMeteorAt(now + 60)
				worldState:SetAttribute("NextMeteorAt", nextMeteor)
			elseif not active and now >= nextRandom and #Players:GetPlayers() > 0 then
				local total = 0
				for _, e in pairs(EVENTS) do
					total += e.weight
				end
				local r = math.random() * total
				for kind, e in pairs(EVENTS) do
					r -= e.weight
					if r <= 0 then
						-- a rare surprise meteor on any day keeps Saturday special but not exclusive
						if math.random() < 0.06 then
							kind = "Meteor"
						end
						EventService.run(kind)
						break
					end
				end
				nextRandom = now + math.random(18, 30) * 60
			end
		end
	end)
	print("[Events] ready — next meteor", os.date("!%a %H:%M UTC", nextMeteor))
end

return EventService
