--!strict
-- Shared.Kit — clone Blender kit meshes by name. One way to get world art, everywhere.
--
-- Kit meshes live in ReplicatedStorage.Assets.Kits.<KitName> as MeshParts whose pivot has
-- been set to BOTTOM-CENTRE at install time (tools/studio/install_kit.luau), matching the
-- Blender convention "base at Z = 0" (docs/ART_KIT_SPEC.md). So placing an asset at a
-- ground point is just `Kit.place(name, CFrame.new(groundPoint))`.
--
-- Missing assets return nil rather than erroring: a world with a missing bench is fine,
-- a server that crashes because of it is not.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Kit = {}

local index: { [string]: BasePart } = {}
local indexed = false

local function build()
	local assets = ReplicatedStorage:FindFirstChild("Assets")
	local kits = assets and assets:FindFirstChild("Kits")
	if not kits then
		return
	end
	for _, d in ipairs(kits:GetDescendants()) do
		if d:IsA("MeshPart") and not index[d.Name] then
			index[d.Name] = d
		end
	end
	indexed = true
end

function Kit.has(name: string): boolean
	if not indexed then
		build()
	end
	return index[name] ~= nil
end

function Kit.names(): { string }
	if not indexed then
		build()
	end
	local out = {}
	for n in pairs(index) do
		table.insert(out, n)
	end
	table.sort(out)
	return out
end

-- Returns a Model containing one anchored MeshPart (PrimaryPart), pivot at its base.
function Kit.clone(name: string): Model?
	if not indexed then
		build()
	end
	local src = index[name]
	if not src then
		return nil
	end
	local model = Instance.new("Model")
	model.Name = name
	local part = src:Clone()
	part.Anchored = true
	part.Parent = model
	model.PrimaryPart = part
	return model
end

export type PlaceOpts = {
	scale: number?,
	collide: boolean?,
	query: boolean?,
	castShadow: boolean?,
	name: string?,
}

function Kit.place(name: string, cf: CFrame, parent: Instance?, opts: PlaceOpts?): Model?
	local model = Kit.clone(name)
	if not model then
		return nil
	end
	local o = opts or {}
	if o.scale and math.abs(o.scale - 1) > 1e-3 then
		model:ScaleTo(o.scale)
	end
	model:PivotTo(cf)
	local part = model.PrimaryPart :: BasePart
	if o.collide ~= nil then
		part.CanCollide = o.collide
	end
	if o.query ~= nil then
		part.CanQuery = o.query
	end
	if o.castShadow ~= nil then
		part.CastShadow = o.castShadow
	end
	if o.name then
		model.Name = o.name
	end
	model.Parent = parent
	return model
end

return Kit
