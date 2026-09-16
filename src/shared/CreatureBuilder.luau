--!strict
-- Shared.CreatureBuilder — genome -> assembled Model.  SPEC §71.
--
-- Runs identically on server and client. We replicate the COMPACT GENOME and let
-- each side assemble, so we never send models over the wire.
--
-- Coordinate convention:
--   Head-attached slots (Head/Eyes/Mouth/Ears/Horn) use headUnit = head diameter.
--   Body-attached slots (Back/Tail/Legs)            use bodyUnit = torso height.
--   Piece `offset` and `size` are both in those units, so a creature scales cleanly.
--
-- Roblox gotcha handled here: Part.Shape = Cylinder has its axis on X, not Y.
-- Authored sizes are {diameter, height, diameter}, so cylinders get swapped and
-- rotated. Without this every cylinder in the game lies on its side.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = Shared:WaitForChild("Config")

local Anatomy = require(Config:WaitForChild("Anatomy"))
local Traits = require(Config:WaitForChild("Traits"))
local Mutations = require(Config:WaitForChild("Mutations"))
local Progression = require(Config:WaitForChild("Progression"))
local Ingredients = require(Config:WaitForChild("Ingredients"))
local Rng = require(Shared:WaitForChild("Util"):WaitForChild("Rng"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local CreatureBuilder = {}

local HEAD_SLOTS = { Eyes = true, Mouth = true, Ears = true, Horn = true, Head = true }

-- ═══ TRAIT MATH (SPEC §12 three layers) ══════════════════════════════════════

function CreatureBuilder.effectiveTraits(genome): { [string]: number }
	local out = {}
	-- layer 3: permanent lineage genes, weighted heaviest
	for t, v in pairs(genome.genes or {}) do
		out[t] = (out[t] or 0) + v * Progression.GENE_WEIGHT
	end
	-- layer 2: stable traits earned by repetition
	for t, v in pairs(genome.traits or {}) do
		out[t] = (out[t] or 0) + v
	end
	-- layer 1: recent feeds, temporary, decays out of the window
	local now = os.time()
	for _, r in ipairs(genome.recent or {}) do
		local age = now - r.at
		if age < Progression.RECENT_WINDOW then
			local def = Ingredients.get(r.ingredient)
			if def then
				local falloff = 1 - (age / Progression.RECENT_WINDOW)
				for t, v in pairs(def.influences) do
					out[t] = (out[t] or 0) + v * Progression.RECENT_WEIGHT * falloff
				end
			end
		end
	end
	return out
end

function CreatureBuilder.dominantTrait(genome): (string?, number)
	local eff = CreatureBuilder.effectiveTraits(genome)
	local top = TableUtil.topN(eff, 1)
	if #top == 0 or top[1].value < Traits.VISIBLE_AT then
		return nil, 0
	end
	return top[1].key, top[1].value
end

-- Which mutations are currently expressed, strongest last so it wins overrides.
function CreatureBuilder.activeMutations(genome)
	local list = {}
	for _, id in ipairs(Mutations.order) do
		if (genome.mutations or {})[id] then
			table.insert(list, { id = id, def = Mutations.all[id] })
		end
	end
	table.sort(list, function(a, b)
		local sa, sb = 0, 0
		for _, v in pairs(a.def.requirements) do sa += v end
		for _, v in pairs(b.def.requirements) do sb += v end
		return sa < sb
	end)
	return list
end

-- Genome parts + mutation overrides + tints, resolved into what we actually build.
function CreatureBuilder.resolve(genome)
	local parts = TableUtil.deepCopy(genome.parts)
	local primary = TableUtil.unpackColor(genome.material.Primary)
	local secondary = TableUtil.unpackColor(genome.material.Secondary)
	local glow = genome.material.Glow or 0
	local sizeMul = 1
	local abilities = {}

	for _, m in ipairs(CreatureBuilder.activeMutations(genome)) do
		local def = m.def
		if def.parts then
			for slot, variant in pairs(def.parts) do
				parts[slot] = variant
			end
		end
		if def.tintPrimary then primary = TableUtil.unpackColor(def.tintPrimary) end
		if def.tintSecondary then secondary = TableUtil.unpackColor(def.tintSecondary) end
		if def.glow then glow = math.max(glow, def.glow) end
		if def.sizeMul then sizeMul *= def.sizeMul end
		if def.ability then abilities[def.ability] = true end
	end

	local domTrait = CreatureBuilder.dominantTrait(genome)
	local traitColor = domTrait and TableUtil.unpackColor(Traits.all[domTrait].color) or secondary
	local skin = domTrait and Traits.all[domTrait].skin or genome.material.Skin

	local stage = Progression.stage(genome.stage or 1)
	local drift = math.clamp((genome.fedCount or 0) * Progression.GROWTH_PER_FEED, 0, Progression.MAX_SIZE_DRIFT)
	local scale = stage.sizeBase * (genome.size or 1) * sizeMul * (1 + drift)
	scale = math.min(scale, Progression.MAX_SCALE[stage.id] or 6.5)

	return {
		parts = parts,
		primary = primary,
		secondary = secondary,
		traitColor = traitColor,
		glow = glow,
		scale = scale,
		skin = skin,
		abilities = abilities,
		dominant = domTrait,
	}
end

-- ═══ PRIMITIVE CONSTRUCTION ══════════════════════════════════════════════════

local function materialEnum(name: string?): Enum.Material
	if not name then return Enum.Material.SmoothPlastic end
	local ok, mat = pcall(function() return (Enum.Material :: any)[name] end)
	return (ok and mat) or Enum.Material.SmoothPlastic
end

local function resolveColor(mode, ctx): Color3
	if type(mode) == "number" then
		return TableUtil.unpackColor(mode)
	elseif mode == "secondary" then
		return ctx.secondary
	elseif mode == "trait" then
		return ctx.traitColor
	end
	return ctx.primary
end

-- Builds one piece. Returns the Part, unwelded and unparented.
local function makePiece(piece, unit: number, anchorCF: CFrame, ctx, mirrored: boolean, offScale: Vector3?): BasePart
	local shape = piece.shape or "Block"
	local sx, sy, sz = piece.size[1] * unit, piece.size[2] * unit, piece.size[3] * unit
	-- Body slots pass per-axis half-extents so parts stay attached on tall/narrow
	-- bodies; head slots pass nil and fall back to the uniform head unit.
	local os3 = offScale or Vector3.new(unit, unit, unit)

	local part: BasePart
	local extraRot = CFrame.identity

	if shape == "Wedge" then
		part = Instance.new("WedgePart")
		part.Size = Vector3.new(sx, sy, sz)
	elseif shape == "Cylinder" then
		part = Instance.new("Part")
		;(part :: Part).Shape = Enum.PartType.Cylinder
		-- authored as {diameter, height, diameter}; Part cylinders run along X
		part.Size = Vector3.new(sy, sx, sz)
		extraRot = CFrame.Angles(0, 0, math.rad(90))
	elseif shape == "Ball" then
		part = Instance.new("Part")
		;(part :: Part).Shape = Enum.PartType.Ball
		-- Ball ignores non-uniform size visually, so approximate with a Block when
		-- the piece is clearly not spherical. Keeps silhouettes honest.
		local maxD = math.max(sx, sy, sz)
		local minD = math.min(sx, sy, sz)
		if maxD > minD * 1.35 then
			;(part :: Part).Shape = Enum.PartType.Block
		end
		part.Size = Vector3.new(sx, sy, sz)
	else
		part = Instance.new("Part")
		;(part :: Part).Shape = Enum.PartType.Block
		part.Size = Vector3.new(sx, sy, sz)
	end

	local ox, oy, oz = piece.offset[1] * os3.X, piece.offset[2] * os3.Y, piece.offset[3] * os3.Z
	local rx, ry, rz = 0, 0, 0
	if piece.rot then
		rx, ry, rz = math.rad(piece.rot[1] or 0), math.rad(piece.rot[2] or 0), math.rad(piece.rot[3] or 0)
	end
	if mirrored then
		ox = -ox
		ry, rz = -ry, -rz
	end

	part.CFrame = anchorCF * CFrame.new(ox, oy, oz) * CFrame.Angles(rx, ry, rz) * extraRot
	part.Color = resolveColor(piece.colorMode, ctx)
	part.Material = materialEnum(piece.material)
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.Anchored = false
	part.Massless = true
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	return part
end

local function buildVariant(slot: string, variantName: string, unit: number, anchorCF: CFrame, ctx, container: Model, offScale: Vector3?)
	local slotDefs = Anatomy.parts[slot]
	if not slotDefs then return end
	local variant = slotDefs[variantName]
	if not variant then return end

	for _, piece in ipairs(variant.pieces) do
		local p = makePiece(piece, unit, anchorCF, ctx, false, offScale)
		p.Name = slot .. "_" .. variantName
		p.Parent = container
		if variant.mirror then
			local m = makePiece(piece, unit, anchorCF, ctx, true, offScale)
			m.Name = slot .. "_" .. variantName .. "_M"
			m.Parent = container
		end
	end
end

-- ═══ PATTERNS (cheap visual variety — SPEC §91 "no two look identical") ══════
local function applyPattern(pattern: string, torso: BasePart, unit: number, ctx, container: Model, rng)
	if pattern == "Plain" or pattern == "Gradient" then
		return
	end
	local count = pattern == "Spotted" and 4 or (pattern == "Striped" and 3 or 2)
	for i = 1, count do
		local p = Instance.new("Part")
		p.Anchored = false
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.Massless = true
		p.Material = torso.Material
		p.Color = ctx.secondary
		if pattern == "Spotted" then
			p.Shape = Enum.PartType.Ball
			local d = unit * rng:num(0.22, 0.38)
			p.Size = Vector3.new(d, d, d)
			p.CFrame = torso.CFrame * CFrame.Angles(rng:num(0, 6.28), rng:num(0, 6.28), 0)
				* CFrame.new(0, 0, -torso.Size.Z * 0.42)
		elseif pattern == "Striped" then
			p.Size = Vector3.new(torso.Size.X * 1.02, unit * 0.16, torso.Size.Z * 1.02)
			p.CFrame = torso.CFrame * CFrame.new(0, (i - 2) * unit * 0.32, 0)
		else -- Patchy
			p.Shape = Enum.PartType.Ball
			local d = unit * rng:num(0.4, 0.62)
			p.Size = Vector3.new(d, d * 0.5, d)
			p.CFrame = torso.CFrame * CFrame.Angles(rng:num(0, 6.28), rng:num(0, 6.28), 0)
				* CFrame.new(0, 0, -torso.Size.Z * 0.4)
		end
		p.Name = "Pattern"
		p.Parent = container
	end
end

-- ═══ MAIN BUILD ══════════════════════════════════════════════════════════════

--[[
	Assembles `genome` into a Model.
	`lod` 1 = full, 2 = simplified (drops pattern + cosmetic slots), 3 = torso+head only.
	SPEC §72: never replicate every full complex monster at max fidelity to mobile.
]]
function CreatureBuilder.build(genome, lod: number?): Model
	local level = lod or 1
	local ctx = CreatureBuilder.resolve(genome)
	local rng = Rng.fromString(genome.id or "unseeded")
	local body = Anatomy.bodies[genome.bodyFamily] or Anatomy.bodies.Cute
	local skin = Anatomy.skins[ctx.skin] or Anatomy.skins.Soft

	local model = Instance.new("Model")
	model.Name = genome.name or "Creature"

	-- torso
	local torso = Instance.new("Part")
	torso.Name = "Torso"
	local ts = body.torso.size
	torso.Size = Vector3.new(ts[1], ts[2], ts[3]) * ctx.scale
	if body.torso.shape == "Ball" then
		torso.Shape = Enum.PartType.Ball
	end
	torso.Color = ctx.primary
	torso.Material = materialEnum(skin.material)
	torso.Transparency = skin.transparency or 0
	torso.Reflectance = skin.reflect or 0
	torso.CanCollide = true
	torso.Anchored = true -- root is driven directly; children ride along on welds
	torso.TopSurface = Enum.SurfaceType.Smooth
	torso.BottomSurface = Enum.SurfaceType.Smooth
	torso.Parent = model
	model.PrimaryPart = torso

	-- Part SIZES use a balanced unit (mean of the torso axes) so a tall narrow body
	-- does not get oversized limbs. Part OFFSETS use per-axis half-extents.
	local bodyUnit = (torso.Size.X + torso.Size.Y + torso.Size.Z) / 3
	local offScale = torso.Size * 0.5
	local headUnit = bodyUnit * body.headScale * 0.62

	-- Attach the head just past the torso front and let it overlap slightly, rather
	-- than projecting a raw fraction of torso depth (which detached Heavy heads).
	local headZ = -(torso.Size.Z * 0.5 + headUnit * 0.35) * body.headForward
	local headCF = torso.CFrame * CFrame.new(0, torso.Size.Y * 0.5 * body.headLift, headZ)

	-- body-attached slots
	buildVariant("Legs", ctx.parts.Legs, bodyUnit, torso.CFrame, ctx, model, offScale)
	buildVariant("Tail", ctx.parts.Tail, bodyUnit, torso.CFrame, ctx, model, offScale)
	if level <= 2 then
		buildVariant("Back", ctx.parts.Back, bodyUnit, torso.CFrame, ctx, model, offScale)
	end

	-- head-attached slots
	buildVariant("Head", ctx.parts.Head, headUnit, headCF, ctx, model)
	buildVariant("Eyes", ctx.parts.Eyes, headUnit, headCF, ctx, model)
	if level <= 2 then
		buildVariant("Mouth", ctx.parts.Mouth, headUnit, headCF, ctx, model)
		buildVariant("Ears", ctx.parts.Ears, headUnit, headCF, ctx, model)
		buildVariant("Horn", ctx.parts.Horn, headUnit, headCF, ctx, model)
	end

	if level == 1 then
		applyPattern(genome.material.Pattern or "Plain", torso, bodyUnit, ctx, model, rng)
	end

	-- glow (SPEC §43: rare mutations should be recognisable across a server)
	if ctx.glow > 0.05 and level == 1 then
		local light = Instance.new("PointLight")
		light.Color = ctx.traitColor
		light.Brightness = 1.4 * ctx.glow
		light.Range = 10 + 12 * ctx.glow
		light.Parent = torso
	end

	-- weld everything to the root
	for _, child in ipairs(model:GetChildren()) do
		if child:IsA("BasePart") and child ~= torso then
			local weld = Instance.new("WeldConstraint")
			weld.Part0 = torso
			weld.Part1 = child
			weld.Parent = child
		end
	end

	-- metadata other systems read without re-deriving
	-- Distance from pivot to the lowest point, so callers can sit a creature ON the
	-- ground instead of guessing (case 6 sank its legs to y = -4.9 without this).
	local cf, size = model:GetBoundingBox()
	model:SetAttribute("GroundOffset", (torso.Position.Y - (cf.Position.Y - size.Y * 0.5)))

	model:SetAttribute("CreatureId", genome.id)
	model:SetAttribute("Stage", genome.stage or 1)
	model:SetAttribute("Generation", genome.generation or 1)
	model:SetAttribute("Dominant", ctx.dominant or "")
	model:SetAttribute("Scale", ctx.scale)

	return model
end

-- ═══ GENOME CREATION ═════════════════════════════════════════════════════════

local function randomVariant(slot: string, rng, chosen: { [string]: string }): string
	local options = Anatomy.variantsFor(slot)
	for _ = 1, 12 do
		local pick = rng:pick(options)
		if not Anatomy.isBanned(slot, pick, chosen) then
			return pick
		end
	end
	-- fall back to the first legal option rather than emitting a banned combo
	for _, opt in ipairs(options) do
		if not Anatomy.isBanned(slot, opt, chosen) then
			return opt
		end
	end
	return options[1]
end

function CreatureBuilder.newGenome(opts)
	opts = opts or {}
	local id = opts.id or ("c" .. tostring(math.random(1, 1e9)) .. tostring(os.time() % 100000))
	local rng = Rng.fromString(id)
	local family = opts.bodyFamily or rng:pick(Anatomy.bodyOrder)
	local body = Anatomy.bodies[family]

	-- Babies start deliberately plain so the FIRST feed is an obvious change.
	-- SPEC §8 (0:16) and non-negotiable §99 #2.
	local chosen: { [string]: string } = {}
	chosen.Head = randomVariant("Head", rng, chosen)
	chosen.Eyes = rng:chance(0.7) and "Big" or randomVariant("Eyes", rng, chosen)
	chosen.Mouth = "Smile"
	chosen.Ears = opts.plainStart and "None" or randomVariant("Ears", rng, chosen)
	chosen.Horn = "None"
	chosen.Back = "None"
	chosen.Tail = opts.plainStart and "Stub" or randomVariant("Tail", rng, chosen)
	chosen.Legs = randomVariant("Legs", rng, chosen)

	local base = TableUtil.unpackColor(opts.baseColor or body.baseColor)
	local hue = rng:num(-0.06, 0.06)
	local h, s, v = Color3.toHSV(base)
	local primary = Color3.fromHSV((h + hue) % 1, math.clamp(s * rng:num(0.85, 1.15), 0, 1), math.clamp(v * rng:num(0.9, 1.08), 0, 1))
	local secondary = Color3.fromHSV((h + hue + 0.08) % 1, math.clamp(s * 0.8, 0, 1), math.clamp(v * 0.82, 0, 1))

	-- temperament (SPEC §18) — biased by body family, then jittered
	local temperament = {}
	local tempKeys = { "curious", "lazy", "greedy", "brave", "nervous", "silly", "affectionate", "mischievous" }
	local total = 0
	for _, k in ipairs(tempKeys) do
		local v2 = (body.temperament[k] or 0.1) * rng:num(0.5, 1.6)
		temperament[k] = v2
		total += v2
	end
	for k, v2 in pairs(temperament) do
		temperament[k] = math.floor((v2 / total) * 100 + 0.5) / 100
	end

	return {
		id = id,
		bodyFamily = family,
		size = rng:num(0.94, 1.06),
		parts = chosen,
		material = {
			Skin = "Soft",
			Pattern = opts.plainStart and "Plain" or rng:pick(Anatomy.patterns),
			Primary = TableUtil.packColor(primary),
			Secondary = TableUtil.packColor(secondary),
			Glow = 0,
		},
		traits = {},
		genes = opts.genes or {},
		recent = {},
		mutations = {},
		temperament = temperament,
		stage = 1,
		generation = opts.generation or 1,
		parentId = opts.parentId,
		birth = os.time(),
		name = opts.name,
		fedCount = 0,
		abilities = {},
	}
end

-- ═══ INGREDIENT PROPS (same piece vocabulary — SPEC §7 world as cabinet) ═════

function CreatureBuilder.buildProp(ingredientId: string): Model?
	local def = Ingredients.get(ingredientId)
	if not def then return nil end

	local model = Instance.new("Model")
	model.Name = ingredientId

	local ctx = {
		primary = TableUtil.unpackColor(def.model.color),
		secondary = TableUtil.unpackColor(def.model.color),
		traitColor = TableUtil.unpackColor(def.model.color),
	}

	local main = makePiece({
		shape = def.model.shape,
		size = def.model.size,
		offset = { 0, 0, 0 },
		colorMode = def.model.color,
		material = def.model.material,
	}, 1, CFrame.identity, ctx, false)
	main.Name = "Main"
	main.Anchored = true
	main.CanQuery = true
	main.Parent = model
	model.PrimaryPart = main

	if def.model.topper then
		local t = def.model.topper
		local piece = makePiece({
			shape = t.shape,
			size = t.size,
			offset = t.offset,
			colorMode = t.color,
			material = t.material,
		}, 1, main.CFrame, ctx, false)
		piece.Name = "Topper"
		piece.Anchored = true
		piece.Parent = model
	end

	model:SetAttribute("Ingredient", ingredientId)
	return model
end

return CreatureBuilder
