--!strict
-- Shared.PropBuilder — ingredient pickups in the world (SPEC §7 "the world is one giant
-- ingredient cabinet").
--
-- If ReplicatedStorage.Assets.Props.<IngredientId> exists (a Blender-authored model), it is
-- cloned. Otherwise the ingredient's primitive spec in Config/Ingredients is assembled, so
-- a brand-new ingredient is visible the moment its table entry exists.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Ingredients = require(Shared:WaitForChild("Config"):WaitForChild("Ingredients"))
local TableUtil = require(Shared:WaitForChild("Util"):WaitForChild("TableUtil"))

local PropBuilder = {}

local function materialEnum(name: string?): Enum.Material
	if not name then
		return Enum.Material.SmoothPlastic
	end
	local ok, mat = pcall(function()
		return (Enum.Material :: any)[name]
	end)
	return (ok and mat) or Enum.Material.SmoothPlastic
end

local function primitive(spec, color: Color3, anchorCF: CFrame): BasePart
	local shape = spec.shape or "Block"
	local sx, sy, sz = spec.size[1], spec.size[2], spec.size[3]
	local part: BasePart
	local extraRot = CFrame.identity
	if shape == "Wedge" then
		part = Instance.new("WedgePart")
		part.Size = Vector3.new(sx, sy, sz)
	elseif shape == "Cylinder" then
		local p = Instance.new("Part")
		p.Shape = Enum.PartType.Cylinder
		-- authored as {diameter, height, diameter}; Part cylinders run along X
		p.Size = Vector3.new(sy, sx, sz)
		extraRot = CFrame.Angles(0, 0, math.rad(90))
		part = p
	elseif shape == "Ball" then
		local p = Instance.new("Part")
		local maxD, minD = math.max(sx, sy, sz), math.min(sx, sy, sz)
		p.Shape = (maxD > minD * 1.35) and Enum.PartType.Block or Enum.PartType.Ball
		p.Size = Vector3.new(sx, sy, sz)
		part = p
	else
		local p = Instance.new("Part")
		p.Size = Vector3.new(sx, sy, sz)
		part = p
	end
	local off = spec.offset or { 0, 0, 0 }
	part.CFrame = anchorCF * CFrame.new(off[1], off[2], off[3]) * extraRot
	part.Color = color
	part.Material = materialEnum(spec.material)
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.CanCollide = false
	part.Anchored = true
	return part
end

function PropBuilder.build(ingredientId: string): Model?
	local def = Ingredients.get(ingredientId)
	if not def then
		return nil
	end

	local assets = ReplicatedStorage:FindFirstChild("Assets")
	local props = assets and assets:FindFirstChild("Props")
	local template = props and props:FindFirstChild(ingredientId)
	if template and template:IsA("Model") then
		local model = template:Clone()
		for _, d in ipairs(model:GetDescendants()) do
			if d:IsA("BasePart") then
				d.Anchored = true
				d.CanCollide = false
				d.CanQuery = true
			end
		end
		if not model.PrimaryPart then
			model.PrimaryPart = model:FindFirstChildWhichIsA("BasePart")
		end
		-- glowing ingredients (primitive spec says Neon): vertex colours carry the look,
		-- a soft light sells the glow at night and in caves
		local spec = def.model
		local glowSpec = (spec.material == "Neon" and spec) or (spec.topper and spec.topper.material == "Neon" and spec.topper)
		if glowSpec and model.PrimaryPart and not model.PrimaryPart:FindFirstChildOfClass("PointLight") then
			local light = Instance.new("PointLight")
			light.Color = TableUtil.unpackColor(glowSpec.color)
			light.Brightness = 1.6
			light.Range = 9
			light.Shadows = false
			light.Parent = model.PrimaryPart
		end
		model.Name = ingredientId
		model:SetAttribute("Ingredient", ingredientId)
		return model
	end

	local model = Instance.new("Model")
	model.Name = ingredientId
	local main = primitive(def.model, TableUtil.unpackColor(def.model.color), CFrame.identity)
	main.Name = "Main"
	main.CanQuery = true
	main.Parent = model
	model.PrimaryPart = main
	if def.model.topper then
		local t = def.model.topper
		local piece = primitive(t, TableUtil.unpackColor(t.color), main.CFrame)
		piece.Name = "Topper"
		piece.Parent = model
	end
	model:SetAttribute("Ingredient", ingredientId)
	return model
end

return PropBuilder
