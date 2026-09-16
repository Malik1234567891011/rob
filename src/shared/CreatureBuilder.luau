--!strict
-- Shared.CreatureBuilder — genome -> assembled creature Model.  SPEC §71.
--
-- The genome is the only thing stored or sent. Assembly clones Blender-authored skinned
-- meshes from ReplicatedStorage.Assets.Creatures.<Family>:
--
--   Bodies.<Head>   RootPart (holds the whole Bone tree) + Body__<Head>__Main/__Belly
--   Parts           every part variant, named <Slot>__<Variant>__<Piece>
--
-- A part mesh deforms with the body's skeleton as soon as it is WELDED to the RootPart:
-- Roblox resolves skinned-mesh bones by name inside the part's assembly (verified, see
-- docs/DECISIONS.md). So a mutation swapping a tail is: destroy old pieces, weld new ones.
--
-- Output contract other systems rely on:
--   model.PrimaryPart = RootPart (anchored, invisible, sits AT GROUND LEVEL under the feet)
--   attributes: CreatureId Stage Generation Dominant Scale Family Head Height GroundOffset

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
local PropBuilder = require(Shared:WaitForChild("PropBuilder"))

local CreatureBuilder = {}

local WHITE = Color3.new(1, 1, 1)
local BLACK = Color3.new(0, 0, 0)

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
		for _, v in pairs(a.def.requirements) do
			sa += v
		end
		for _, v in pairs(b.def.requirements) do
			sb += v
		end
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
		if def.tintPrimary then
			primary = TableUtil.unpackColor(def.tintPrimary)
		end
		if def.tintSecondary then
			secondary = TableUtil.unpackColor(def.tintSecondary)
		end
		if def.glow then
			glow = math.max(glow, def.glow)
		end
		if def.sizeMul then
			sizeMul *= def.sizeMul
		end
		if def.ability then
			abilities[def.ability] = true
		end
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

-- ═══ ASSETS ══════════════════════════════════════════════════════════════════

local warned: { [string]: boolean } = {}
local function warnOnce(key: string, msg: string)
	if not warned[key] then
		warned[key] = true
		warn("[CreatureBuilder] " .. msg)
	end
end

local function familyFolder(family: string): Instance?
	local assets = ReplicatedStorage:FindFirstChild("Assets")
	local creatures = assets and assets:FindFirstChild("Creatures")
	if not creatures then
		return nil
	end
	local f = creatures:FindFirstChild(family)
	if f and f:FindFirstChild("Bodies") and f:FindFirstChild("Parts") then
		return f
	end
	local fallback = creatures:FindFirstChild("Cute")
	if fallback then
		warnOnce("family:" .. family, "no assets for family " .. family .. ", using Cute")
	end
	return fallback
end

-- Index a family's Parts model once: "Slot__Variant" -> { MeshPart }
local partIndex: { [Instance]: { [string]: { MeshPart } } } = {}
local function indexParts(partsModel: Instance): { [string]: { MeshPart } }
	local cached = partIndex[partsModel]
	if cached then
		return cached
	end
	local idx: { [string]: { MeshPart } } = {}
	for _, child in ipairs(partsModel:GetChildren()) do
		if child:IsA("MeshPart") then
			local slot, variant = string.match(child.Name, "^(%w+)__(%w+)__")
			if slot and variant then
				local key = slot .. "__" .. variant
				idx[key] = idx[key] or {}
				table.insert(idx[key], child)
			end
		end
	end
	partIndex[partsModel] = idx
	return idx
end

-- ═══ STYLE ═══════════════════════════════════════════════════════════════════

local function materialEnum(name: string?): Enum.Material?
	if not name then
		return nil
	end
	local ok, mat = pcall(function()
		return (Enum.Material :: any)[name]
	end)
	return ok and mat or nil
end

local function colorFor(mode, ctx): Color3
	if type(mode) == "number" then
		return TableUtil.unpackColor(mode)
	elseif mode == "secondary" then
		return ctx.secondary
	elseif mode == "belly" then
		return ctx.belly
	elseif mode == "trait" then
		return ctx.traitColor
	elseif mode == "dark" then
		return ctx.primary:Lerp(BLACK, 0.35)
	end
	return ctx.primary
end

local function applyStyle(part: MeshPart, slot: string, variant: string, piece: string, ctx)
	local style = Anatomy.styleFor(slot, variant, piece)
	local skinDef = Anatomy.skins[ctx.skin or "Soft"] or Anatomy.skins.Soft
	local color = colorFor(style.color, ctx)
	local material = materialEnum(style.material) or Enum.Material.SmoothPlastic
	local transparency = style.transparency or 0
	local reflect = 0

	if style.skin ~= false and not style.material then
		material = materialEnum(skinDef.material) or material
		reflect = skinDef.reflect or 0
		transparency = math.max(transparency, skinDef.transparency or 0)
		if skinDef.darken then
			color = color:Lerp(BLACK, skinDef.darken)
		end
	end

	part.Color = color
	part.Material = material
	part.Reflectance = reflect
	part.Transparency = transparency
	part.TextureID = ""
end

-- ═══ MAIN BUILD ══════════════════════════════════════════════════════════════

local function stripJoints(p: Instance)
	for _, c in ipairs(p:GetChildren()) do
		if c:IsA("JointInstance") or c:IsA("WeldConstraint") or c:IsA("Motor6D") then
			c:Destroy()
		end
	end
end

local function attach(model: Model, root: BasePart, templateRoot: BasePart, src: MeshPart): MeshPart
	local p = src:Clone()
	stripJoints(p)
	p.Anchored = false
	p.CanCollide = false
	p.CanTouch = false
	p.CanQuery = true -- clicking any visible piece inspects the creature (SPEC §24)
	p.Massless = true
	p.CastShadow = true
	p.CFrame = root.CFrame * templateRoot.CFrame:ToObjectSpace(src.CFrame)
	local weld = Instance.new("WeldConstraint")
	weld.Part0 = root
	weld.Part1 = p
	weld.Parent = p
	p.Parent = model
	return p
end

local function droppedAt(level: number, piece: string): boolean
	local drop = Anatomy.lodDrop[level]
	if not drop then
		return false
	end
	for prefix in pairs(drop) do
		if string.sub(piece, 1, #prefix) == prefix then
			return true
		end
	end
	return false
end

--[[
	Assembles `genome` into a Model.
	`lod` 1 = full, 2 = drops tiny interior pieces, 3 = silhouette + eyes.
	SPEC §72: never ship every full monster at max fidelity to mobile.
]]
function CreatureBuilder.build(genome, lod: number?): Model
	local level = lod or 1
	local ctx = CreatureBuilder.resolve(genome)
	local body = Anatomy.bodies[genome.bodyFamily] or Anatomy.bodies.Cute
	ctx.belly = ctx.primary:Lerp(WHITE, 0.45 + (body.bellyLift or 0.15))

	local model = Instance.new("Model")
	model.Name = genome.name or "Creature"

	local fam = familyFolder(genome.bodyFamily or "Cute")
	if not fam then
		error("[CreatureBuilder] ReplicatedStorage.Assets.Creatures is missing — install creature assets")
	end
	local bodies = fam:FindFirstChild("Bodies") :: Instance
	local head = ctx.parts.Head or "Round"
	local bodyT = bodies:FindFirstChild(head) or bodies:FindFirstChild("Round") or bodies:FindFirstChildWhichIsA("Model")
	if not bodies:FindFirstChild(head) then
		warnOnce("head:" .. fam.Name .. head, "no " .. head .. " body for " .. fam.Name .. ", using " .. (bodyT and bodyT.Name or "?"))
	end
	assert(bodyT, "no bodies installed")
	local bodyRoot = bodyT:FindFirstChild("RootPart") :: BasePart
	local partsModel = fam:FindFirstChild("Parts") :: Instance
	local partsRoot = partsModel:FindFirstChild("RootPart") :: BasePart

	-- the root carries every bone; it is the creature's physical anchor
	local root = bodyRoot:Clone()
	stripJoints(root)
	for _, c in ipairs(root:GetChildren()) do
		if not c:IsA("Bone") then
			c:Destroy()
		end
	end
	root.Name = "RootPart"
	root.Anchored = true
	root.CanCollide = false
	root.CanTouch = false
	root.CanQuery = false
	root.Transparency = 1
	root.CFrame = CFrame.identity
	root.Parent = model
	model.PrimaryPart = root

	-- body pieces (the sculpted head is part of the body)
	for _, src in ipairs(bodyT:GetChildren()) do
		if src:IsA("MeshPart") and src.Name ~= "Rig__Sockets" then
			local piece = string.match(src.Name, "__([%w]+)$") or "Main"
			local p = attach(model, root, bodyRoot, src)
			applyStyle(p, "Body", head, piece, ctx)
		end
	end

	-- every other slot
	local idx = indexParts(partsModel)
	for _, slot in ipairs(Anatomy.slotOrder) do
		if slot ~= "Head" then
			local variant = ctx.parts[slot]
			if variant and variant ~= "None" then
				local list = idx[slot .. "__" .. variant]
				if not list then
					warnOnce("part:" .. fam.Name .. slot .. variant, "missing part " .. slot .. "/" .. variant .. " for " .. fam.Name)
				else
					for _, src in ipairs(list) do
						local piece = string.match(src.Name, "__([%w]+)$") or ""
						if not droppedAt(level, piece) then
							local p = attach(model, root, partsRoot, src)
							applyStyle(p, slot, variant, piece, ctx)
						end
					end
				end
			end
		end
	end

	-- glow (SPEC §43: rare mutations should be recognisable across a server)
	local skinDef = Anatomy.skins[ctx.skin or "Soft"]
	local glow = math.max(ctx.glow or 0, skinDef and skinDef.glow or 0)
	if glow > 0.05 and level <= 2 then
		local light = Instance.new("PointLight")
		light.Name = "Glow"
		light.Color = ctx.traitColor
		light.Brightness = 1.2 * glow
		light.Range = 8 + 10 * glow
		light.Parent = root
	end

	if math.abs(ctx.scale - 1) > 1e-3 then
		model:ScaleTo(ctx.scale)
	end

	-- measure: lowest and highest point relative to the root, from the rest-pose parts
	local lowest, highest = math.huge, -math.huge
	for _, d in ipairs(model:GetChildren()) do
		if d:IsA("MeshPart") then
			local half = d.Size.Y * 0.5
			lowest = math.min(lowest, d.Position.Y - half)
			highest = math.max(highest, d.Position.Y + half)
		end
	end
	if lowest == math.huge then
		lowest, highest = 0, 2
	end
	local rootY = root.Position.Y
	model:SetAttribute("GroundOffset", rootY - lowest)
	model:SetAttribute("Height", highest - lowest)
	model:SetAttribute("CreatureId", genome.id)
	model:SetAttribute("Stage", genome.stage or 1)
	model:SetAttribute("Generation", genome.generation or 1)
	model:SetAttribute("Dominant", ctx.dominant or "")
	model:SetAttribute("Scale", ctx.scale)
	model:SetAttribute("Family", fam.Name)
	model:SetAttribute("Head", bodyT.Name)
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
	chosen.Head = opts.plainStart and "Round" or randomVariant("Head", rng, chosen)
	chosen.Eyes = (opts.plainStart or rng:chance(0.7)) and "Big" or randomVariant("Eyes", rng, chosen)
	chosen.Mouth = "Smile"
	chosen.Ears = opts.plainStart and "Round" or randomVariant("Ears", rng, chosen)
	chosen.Horn = "None"
	chosen.Back = "None"
	chosen.Tail = opts.plainStart and "Stub" or randomVariant("Tail", rng, chosen)
	chosen.Legs = opts.plainStart and "Stubby" or randomVariant("Legs", rng, chosen)

	local base = TableUtil.unpackColor(opts.baseColor or body.baseColor)
	local hue = rng:num(-0.05, 0.05)
	local h, s, v = Color3.toHSV(base)
	local primary = Color3.fromHSV((h + hue) % 1, math.clamp(s * rng:num(0.9, 1.15), 0, 1), math.clamp(v * rng:num(0.94, 1.04), 0, 1))
	local secondary = Color3.fromHSV((h + hue + 0.08) % 1, math.clamp(s * 0.85, 0, 1), math.clamp(v * 0.85, 0, 1))

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

-- Ingredient props moved to PropBuilder; kept here so existing callers keep working.
function CreatureBuilder.buildProp(ingredientId: string): Model?
	return PropBuilder.build(ingredientId)
end

return CreatureBuilder
