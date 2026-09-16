--!strict
-- Shared.CreatureAnimator — procedural bone animation for skinned creatures.
--
-- ART_DIRECTION: "Animation may actually be more important than geometry." A creature
-- that anticipates, looks at things, blinks, breathes, squashes and settles reads as far
-- more expensive than one with twice the polygons standing still.
--
-- Everything here writes Bone.Transform, which is LOCAL to each client and never
-- replicates. The server only moves the anchored RootPart. So animation costs no network,
-- and each client animates only what is near it (LOD, see CreatureController).
--
-- Rotations are authored in ROOT space (the creature's own frame: +X its right, +Y up,
-- +Z behind it, it faces -Z) and converted into each bone's local frame, so the animation
-- code never cares how Blender rolled a bone.
--
-- Deterministic: every layer is a pure function of (state, time), so a pose can be
-- rendered in edit mode for inspection with `rig:poseAt(action, t)`.

local CreatureAnimator = {}
CreatureAnimator.__index = CreatureAnimator

local RAD = math.pi / 180
local ID = CFrame.identity

local function clamp(x: number, a: number, b: number): number
	return math.max(a, math.min(b, x))
end

local function smoothstep(a: number, b: number, x: number): number
	local t = clamp((x - a) / (b - a), 0, 1)
	return t * t * (3 - 2 * t)
end

-- 0 -> 1 -> 0 bump over [a, b]
local function bump(a: number, b: number, x: number): number
	if x <= a or x >= b then
		return 0
	end
	local t = (x - a) / (b - a)
	return math.sin(t * math.pi)
end

local function damp(current: number, target: number, rate: number, dt: number): number
	return current + (target - current) * (1 - math.exp(-rate * dt))
end

-- ═══ ACTIONS: one-shot timelines ═════════════════════════════════════════════
-- Each returns a partial pose table for time t (seconds since start). Keys:
--   rootPos(Vector3) rootRot(CFrame)  spine neck head jaw (degrees pitch) cheeks(0..1)
--   lids(0 open..1 closed)  tailAmp tailRate  headRoll headYaw  belly(0..1) legsFold(0..1)
--   earPerk(-1..1)  eyeWide(0..1)
local ACTIONS = {}

-- The feeding beat, fully authored (ART_DIRECTION): notice -> lean -> CHOMP -> cheeks
-- bulge -> swallow -> satisfied wobble. ~2.4 s so the mutation reveal lands right after.
ACTIONS.eat = {
	duration = 2.5,
	pose = function(t: number)
		local p = {}
		-- anticipation: pull back, eyes wide, tail goes insane
		local back = bump(0.0, 0.34, t)
		-- lunge + bite
		local lunge = smoothstep(0.22, 0.4, t) * (1 - smoothstep(0.55, 0.8, t))
		local jawOpen = smoothstep(0.2, 0.36, t) * (1 - smoothstep(0.4, 0.47, t))
		-- chewing: three chomps
		local chew = 0
		if t > 0.5 and t < 1.55 then
			chew = (0.5 - 0.5 * math.cos((t - 0.5) * math.pi * 2 * 2.85)) * (1 - smoothstep(1.35, 1.55, t))
		end
		local cheeks = smoothstep(0.42, 0.55, t) * (1 - smoothstep(1.5, 1.75, t))
		-- swallow: gulp down and up
		local gulp = bump(1.55, 1.9, t)
		-- satisfied wobble, decaying
		local wobbleT = t - 1.85
		local wobble = wobbleT > 0 and math.sin(wobbleT * 14) * math.exp(-wobbleT * 3.2) or 0

		p.spine = -14 * lunge + 6 * back
		p.neck = -16 * lunge + 8 * back - 10 * gulp
		p.head = 10 * back - 8 * lunge + 8 * gulp
		p.jaw = 34 * jawOpen + 16 * chew
		p.cheeks = cheeks * (0.75 + 0.25 * chew)
		p.rootPos = Vector3.new(0, 0.02 * chew, -0.14 * lunge + 0.06 * back)
		p.rootRot = CFrame.Angles(0, 0, wobble * 9 * RAD)
		p.belly = gulp * 0.7 + smoothstep(1.7, 1.9, t) * (1 - smoothstep(2.1, 2.5, t)) * 0.4
		p.lids = smoothstep(1.9, 2.05, t) * (1 - smoothstep(2.3, 2.5, t)) * 0.55 -- happy squint
		p.eyeWide = back
		p.tailAmp = 1.0 * (1 - smoothstep(0.4, 0.6, t)) + 0.5 * smoothstep(1.85, 2.0, t)
		p.tailRate = 16
		p.earPerk = back * 0.8 - gulp * 0.3
		return p
	end,
}

ACTIONS.hop = {
	duration = 0.62,
	pose = function(t: number)
		local air = bump(0.1, 0.5, t)
		local squashIn = bump(0.0, 0.14, t)
		local squashOut = bump(0.48, 0.62, t)
		return {
			rootPos = Vector3.new(0, 0.9 * air - 0.08 * (squashIn + squashOut), 0),
			spine = 8 * air - 6 * squashOut,
			legsTuck = air,
			earPerk = -air,
			tailAmp = 0.3,
		}
	end,
}

ACTIONS.celebrate = {
	duration = 1.7,
	pose = function(t: number)
		local h1 = bump(0.05, 0.55, t)
		local h2 = bump(0.7, 1.35, t)
		local spin = smoothstep(0.7, 1.35, t) * 360
		return {
			rootPos = Vector3.new(0, 0.8 * h1 + 1.2 * h2, 0),
			rootRot = CFrame.Angles(0, spin * RAD, 0),
			head = 12 * (h1 + h2),
			jaw = 22 * (h1 + h2),
			lids = 0.5 * bump(1.3, 1.7, t),
			legsTuck = math.max(h1, h2),
			tailAmp = 1.2,
			tailRate = 18,
			earPerk = 1,
		}
	end,
}

ACTIONS.pet = {
	duration = 2.2,
	pose = function(t: number)
		local enjoy = smoothstep(0.0, 0.25, t) * (1 - smoothstep(1.8, 2.2, t))
		return {
			lids = 0.62 * enjoy,
			headRoll = math.sin(t * 3.2) * 11 * enjoy,
			head = 6 * enjoy,
			rootRot = CFrame.Angles(0, 0, math.sin(t * 7) * 4 * RAD * enjoy),
			tailAmp = 1.3 * enjoy,
			tailRate = 20,
			earPerk = -0.6 * enjoy,
			cheeks = 0.35 * enjoy,
		}
	end,
}

ACTIONS.hungry = {
	duration = 1.6,
	pose = function(t: number)
		local a = smoothstep(0, 0.2, t) * (1 - smoothstep(1.3, 1.6, t))
		return {
			jaw = (8 + 10 * (0.5 + 0.5 * math.sin(t * 16))) * a,
			headRoll = 12 * a,
			head = 10 * a,
			eyeWide = a,
			earPerk = a,
			tailAmp = 0.9 * a,
			rootPos = Vector3.new(0, 0.25 * bump(0.2, 0.55, t) + 0.25 * bump(0.75, 1.1, t), 0),
		}
	end,
}

ACTIONS.stumble = {
	duration = 1.2,
	pose = function(t: number)
		local fall = smoothstep(0, 0.25, t) * (1 - smoothstep(0.55, 1.1, t))
		return {
			rootRot = CFrame.Angles(0, 0, 32 * RAD * fall),
			rootPos = Vector3.new(0, -0.12 * fall, 0),
			lids = 0.8 * bump(0.2, 0.7, t),
			jaw = 14 * fall,
			head = -10 * fall,
			earPerk = -fall,
		}
	end,
}

ACTIONS.evolve = {
	duration = 3.2,
	pose = function(t: number)
		local rise = smoothstep(0.2, 1.4, t) * (1 - smoothstep(2.4, 2.75, t))
		local spin = smoothstep(0.4, 2.4, t) * 720
		local land = bump(2.7, 3.2, t)
		return {
			rootPos = Vector3.new(0, 2.2 * rise - 0.15 * land, 0),
			rootRot = CFrame.Angles(0, spin * RAD, 0),
			legsTuck = rise,
			lids = 0.9 * smoothstep(0.3, 0.6, t) * (1 - smoothstep(2.3, 2.5, t)),
			head = 14 * rise,
			earPerk = -rise,
			tailAmp = 0.2,
			eyeWide = land,
			jaw = 26 * land,
		}
	end,
}

ACTIONS.sniff = {
	duration = 1.4,
	pose = function(t: number)
		local lean = smoothstep(0, 0.25, t) * (1 - smoothstep(1.1, 1.4, t))
		return {
			spine = -8 * lean,
			neck = -12 * lean,
			head = -6 * lean + math.sin(t * 22) * 3 * lean,
			earPerk = lean,
			tailAmp = 0.6 * lean,
		}
	end,
}

CreatureAnimator.actions = ACTIONS

-- ═══ MOODS: loops that last until changed ════════════════════════════════════
local MOODS = {}

MOODS.sleep = function(t: number)
	local breath = math.sin(t * 1.6)
	return {
		rootPos = Vector3.new(0, -0.3, 0),
		lids = 1,
		head = -16,
		neck = -8,
		legsFold = 1,
		belly = 0.35 + 0.25 * breath,
		spine = 2 * breath,
		tailAmp = 0.05,
		earPerk = -0.9,
	}
end

MOODS.sit = function(t: number)
	return {
		rootPos = Vector3.new(0, -0.12, 0),
		rootRot = CFrame.Angles(-10 * RAD, 0, 0),
		legsFold = 0.55,
		head = 8,
		tailAmp = 0.25,
	}
end

MOODS.hide = function(t: number) -- nervous (SPEC §18)
	return {
		rootPos = Vector3.new(0, -0.1, 0),
		head = -12,
		neck = -6,
		earPerk = -1,
		lids = 0.25,
		tailAmp = 0.05,
		rootRot = CFrame.Angles(0, 0, math.sin(t * 30) * 1.2 * RAD), -- trembling
	}
end

CreatureAnimator.moods = MOODS

-- ═══ RIG ═════════════════════════════════════════════════════════════════════

type Pose = { [string]: any }

function CreatureAnimator.new(model: Model)
	local root = model.PrimaryPart
	assert(root, "creature has no PrimaryPart")
	local self = setmetatable({}, CreatureAnimator)
	self.model = model
	self.root = root
	self.bones = {}
	self.basis = {}
	for _, d in ipairs(root:GetDescendants()) do
		if d:IsA("Bone") then
			self.bones[d.Name] = d
		end
	end
	-- rest orientation of every bone in ROOT space (Transform must be identity here)
	for name, b in pairs(self.bones) do
		b.Transform = ID
	end
	for name, b in pairs(self.bones) do
		local cf = root.CFrame:ToObjectSpace(b.WorldCFrame)
		self.basis[name] = cf - cf.Position
	end
	self.scale = model:GetScale()
	self.seed = (string.len(model.Name) * 7.31) % 10
	self.t = self.seed
	self.lastPos = root.Position
	self.speed = 0
	self.look = { yaw = 0, pitch = 0, eyeYaw = 0, eyePitch = 0 }
	self.lookTarget = nil :: Vector3?
	self.blinkAt = 1.5 + self.seed % 2
	self.blink = 0
	self.action = nil :: string?
	self.actionT = 0
	self.mood = nil :: string?
	self.moodBlend = 0
	self.excitement = 0.3
	self.gait = 0
	self.restJaw = model:GetAttribute("RestJaw") or 0
	return self
end

-- rotate bone by Q (root space) and translate by v (root space, studs at scale 1)
function CreatureAnimator:set(name: string, q: CFrame?, v: Vector3?)
	local b = self.bones[name]
	if not b then
		return
	end
	local basis = self.basis[name]
	local r = q and (basis:Inverse() * q * basis) or ID
	if v then
		local lv = basis:Inverse() * (v * self.scale)
		r = CFrame.new(lv) * r
	end
	b.Transform = r
end

function CreatureAnimator:play(action: string)
	if ACTIONS[action] then
		self.action = action
		self.actionT = 0
	end
end

function CreatureAnimator:setMood(mood: string?)
	if mood ~= self.mood then
		self.mood = mood
	end
end

function CreatureAnimator:setLookTarget(worldPos: Vector3?)
	self.lookTarget = worldPos
end

local function merge(into: Pose, from: Pose?, weight: number)
	if not from or weight <= 0 then
		return
	end
	for k, v in pairs(from) do
		local cur = into[k]
		if typeof(v) == "number" then
			into[k] = (cur or 0) + v * weight
		elseif typeof(v) == "Vector3" then
			into[k] = (cur or Vector3.zero) + v * weight
		elseif typeof(v) == "CFrame" then
			local blended = weight >= 1 and v or CFrame.identity:Lerp(v, weight)
			into[k] = (cur or CFrame.identity) * blended
		end
	end
end

-- Compute and apply the full pose. `dt` real seconds.
function CreatureAnimator:step(dt: number)
	self.t += dt
	local t = self.t
	local root = self.root

	-- speed from the server-driven root motion (studs/s, smoothed)
	local pos = root.Position
	local flat = Vector3.new(pos.X - self.lastPos.X, 0, pos.Z - self.lastPos.Z)
	self.lastPos = pos
	local instSpeed = dt > 0 and flat.Magnitude / dt or 0
	self.speed = damp(self.speed, math.min(instSpeed, 40), 10, dt)

	local pose: Pose = {}

	-- mood loop
	self.moodBlend = damp(self.moodBlend, self.mood and 1 or 0, 4, dt)
	if self.mood and MOODS[self.mood] then
		merge(pose, MOODS[self.mood](t), self.moodBlend)
	end

	-- one-shot action
	if self.action then
		local def = ACTIONS[self.action]
		self.actionT += dt
		if self.actionT >= def.duration then
			self.action = nil
		else
			merge(pose, def.pose(self.actionT), 1)
		end
	end

	-- blink (suppressed while a pose already controls the lids heavily)
	if t >= self.blinkAt then
		self.blink = 1
		self.blinkAt = t + 1.8 + (math.sin(t * 12.9898) * 0.5 + 0.5) * 3.2
	end
	self.blink = math.max(0, self.blink - dt * 8)
	local blinkLid = math.sin(self.blink * math.pi)

	self:apply(pose, dt, blinkLid)
end

function CreatureAnimator:poseAt(action: string?, t: number, mood: string?, speed: number?)
	local pose: Pose = {}
	if mood and MOODS[mood] then
		merge(pose, MOODS[mood](t), 1)
	end
	if action and ACTIONS[action] then
		merge(pose, ACTIONS[action].pose(t), 1)
	end
	self.t = t
	self.speed = speed or 0
	self:apply(pose, 1 / 60, 0)
end

function CreatureAnimator:apply(pose: Pose, dt: number, blinkLid: number)
	local t = self.t
	local speed = self.speed
	local moving = clamp(speed / 10, 0, 1)
	local sleeping = (pose.lids or 0) >= 0.99

	-- ── locomotion (trot: diagonal pairs) ────────────────────────────────────
	self.gait += dt * (4 + speed * 0.9)
	local g = self.gait
	local swing = 28 * moving
	local legsFold = clamp(pose.legsFold or 0, 0, 1)
	local legsTuck = clamp(pose.legsTuck or 0, 0, 1)
	local legPhase = { FL = 0, BR = 0, FR = math.pi, BL = math.pi }
	for leg, ph in pairs(legPhase) do
		local s = math.sin(g + ph)
		local front = leg:sub(1, 1) == "F"
		local fold = (front and -62 or 62) * legsFold
		local hip = swing * s + fold + (front and -18 or 18) * legsTuck
		local knee = math.max(0, -math.cos(g + ph)) * 34 * moving + 40 * legsTuck + 20 * legsFold
		self:set("Leg" .. leg .. "1", CFrame.Angles(hip * RAD, 0, 0))
		self:set("Leg" .. leg .. "2", CFrame.Angles((front and -knee or knee) * RAD, 0, 0))
	end

	-- ── root: bob, sway, breathing ───────────────────────────────────────────
	local breath = math.sin(t * 2.4)
	local bob = math.abs(math.sin(g)) * 0.09 * moving
	local idleSway = math.sin(t * 0.9) * 2.2 * (1 - moving)
	local rootPos = (pose.rootPos or Vector3.zero) + Vector3.new(0, bob + breath * 0.012 * (1 - moving), 0)
	local rootRot = (pose.rootRot or ID) * CFrame.Angles(-4 * moving * RAD, 0, (idleSway + math.sin(g) * 3 * moving) * RAD)
	self:set("Root", rootRot, rootPos)

	-- ── look-at (neck + head + eyes share the job) ───────────────────────────
	local wantYaw, wantPitch = 0, 0
	if self.lookTarget and not sleeping then
		local head = self.bones.Head
		local from = head and head.TransformedWorldCFrame.Position or self.root.Position
		local rel = self.root.CFrame:VectorToObjectSpace(self.lookTarget - from)
		if rel.Magnitude > 0.1 then
			local d = rel.Unit
			wantYaw = math.deg(math.atan2(-d.X, -d.Z))
			wantPitch = math.deg(math.asin(clamp(d.Y, -1, 1)))
		end
	end
	local L = self.look
	L.yaw = damp(L.yaw, clamp(wantYaw, -75, 75), 6, dt)
	L.pitch = damp(L.pitch, clamp(wantPitch, -28, 32), 6, dt)
	L.eyeYaw = damp(L.eyeYaw, clamp(wantYaw - L.yaw * 0.9, -22, 22), 14, dt)
	L.eyePitch = damp(L.eyePitch, clamp(wantPitch - L.pitch * 0.9, -14, 14), 14, dt)

	local spinePitch = (pose.spine or 0) + breath * 0.8
	self:set("Spine", CFrame.Angles(spinePitch * RAD, L.yaw * 0.15 * RAD, 0))
	local neckPitch = (pose.neck or 0) + L.pitch * 0.35
	self:set("Neck", CFrame.Angles(neckPitch * RAD, L.yaw * 0.35 * RAD, 0))
	local headPitch = (pose.head or 0) + L.pitch * 0.55 + math.sin(t * 1.3) * 1.5
	local headRoll = (pose.headRoll or 0) + math.sin(t * 0.7 + 1) * 2
	self:set("Head", CFrame.Angles(headPitch * RAD, L.yaw * 0.5 * RAD, headRoll * RAD))

	local eyeRot = CFrame.Angles(L.eyePitch * RAD, L.eyeYaw * RAD, 0)
	self:set("EyeL", eyeRot)
	self:set("EyeR", eyeRot)

	-- ── lids: blink, squint, sleep ───────────────────────────────────────────
	local lids = clamp(math.max(pose.lids or 0, blinkLid) - (pose.eyeWide or 0) * 0.2, 0, 1)
	local lidQ = CFrame.Angles(-lids * 165 * RAD, 0, 0)
	self:set("LidL", lidQ)
	self:set("LidR", lidQ)

	-- ── jaw, cheeks, belly ───────────────────────────────────────────────────
	self:set("Jaw", CFrame.Angles(((pose.jaw or 0) + self.restJaw) * RAD, 0, 0))
	local ch = pose.cheeks or 0
	self:set("CheekL", nil, Vector3.new(-0.1 * ch, 0.02 * ch, 0.02 * ch))
	self:set("CheekR", nil, Vector3.new(0.1 * ch, 0.02 * ch, 0.02 * ch))
	local belly = pose.belly or 0
	self:set("Belly", nil, Vector3.new(0, 0.02 * belly, -0.1 * belly))

	-- ── ears: perk / flop, with a little lag-wobble ──────────────────────────
	local perk = clamp(pose.earPerk or 0, -1, 1)
	local earWob = math.sin(t * 3.1) * 3 + math.sin(g * 2) * 6 * moving
	self:set("EarL", CFrame.Angles(0, 0, (-perk * 14 - earWob) * RAD))
	self:set("EarR", CFrame.Angles(0, 0, (perk * 14 + earWob) * RAD))

	-- ── tail: wag, amplitude grows toward the tip ────────────────────────────
	local amp = clamp((pose.tailAmp or 0.35) + moving * 0.3, 0, 1.6)
	local rate = pose.tailRate or 7
	for i = 1, 4 do
		local w = math.sin(t * rate - i * 0.7) * amp * (6 + i * 5)
		local lift = -3 * i * (1 - moving) + 4 * moving
		self:set("Tail" .. i, CFrame.Angles(lift * RAD, w * RAD, 0))
	end

	-- ── wings (if any): slow flutter, faster when moving ─────────────────────
	local flap = math.sin(t * (3 + moving * 10)) * (8 + 22 * moving)
	self:set("WingL", CFrame.Angles(0, 0, flap * RAD))
	self:set("WingR", CFrame.Angles(0, 0, -flap * RAD))
end

function CreatureAnimator:reset()
	for _, b in pairs(self.bones) do
		b.Transform = ID
	end
end

return CreatureAnimator
