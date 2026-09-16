-- install_kit.luau — run via MCP execute_luau (Edit) after insert_asset of a kit FBX
-- (docs/ART_KIT_SPEC.md). Moves every MeshPart into ReplicatedStorage.Assets.Kits.<KIT>,
-- sets the pivot to BOTTOM-CENTRE (the Blender "base at Z=0" convention Shared.Kit relies
-- on), tints white so vertex colours show true, and turns off collision for small decor.
-- Set SRC and KIT before running.
local SRC, KIT = "%SRC%", "%KIT%"
local NO_COLLIDE = { "Flower", "GrassTuft", "Reeds", "LilyPad", "Mushroom", "Bunting", "Lantern_String", "Balloon", "Portal_Disc", "Sails" }
local RS = game:GetService("ReplicatedStorage")
local m = workspace:FindFirstChild(SRC)
assert(m, SRC .. " missing")
local assets = RS:FindFirstChild("Assets") or Instance.new("Folder")
assets.Name = "Assets"
assets.Parent = RS
local kits = assets:FindFirstChild("Kits") or Instance.new("Folder")
kits.Name = "Kits"
kits.Parent = assets
local old = kits:FindFirstChild(KIT)
if old then old:Destroy() end
local folder = Instance.new("Folder")
folder.Name = KIT
folder.Parent = kits
local report = {}
for _, d in ipairs(m:GetDescendants()) do
	if d:IsA("MeshPart") then
		d.Name = string.gsub(d.Name, "%.%d+$", "")
		for _, c in ipairs(d:GetChildren()) do
			if c:IsA("JointInstance") or c:IsA("WeldConstraint") then c:Destroy() end
		end
		d.Anchored = true
		d.Color = Color3.new(1, 1, 1)
		d.Material = Enum.Material.SmoothPlastic
		d.TextureID = ""
		local collide = true
		for _, k in ipairs(NO_COLLIDE) do
			if string.find(d.Name, k, 1, true) then collide = false end
		end
		d.CanCollide = collide
		d.CanTouch = false
		d.CollisionFidelity = collide and Enum.CollisionFidelity.Hull or Enum.CollisionFidelity.Box
		d.PivotOffset = CFrame.new(0, -d.Size.Y * 0.5, 0)
		d.CFrame = CFrame.new(0, d.Size.Y * 0.5, 0)
		d.Parent = folder
		table.insert(report, string.format("%s %.1fx%.1fx%.1f", d.Name, d.Size.X, d.Size.Y, d.Size.Z))
	end
end
m:Destroy()
table.sort(report)
return KIT .. ": " .. #report .. " meshes\n" .. table.concat(report, " | ")
