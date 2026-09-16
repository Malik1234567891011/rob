-- install_asset.luau — run via MCP execute_luau (Edit) right after insert_asset.
-- Moves an inserted model from Workspace into ReplicatedStorage.Assets.<dest>, strips the
-- Package plumbing Studio adds (PackageLink -> "Modifying packages" popups), the importer's
-- InitialPoses/AnimationController, and Blender's ".003" name suffixes.
-- Fill SRC / DEST / NAME / ASSET_ID before running.
local SRC, DEST, NAME, ASSET_ID = "%SRC%", "%DEST%", "%NAME%", "%ASSET_ID%"

local RS = game:GetService("ReplicatedStorage")
local function folder(parent, name)
	local f = parent:FindFirstChild(name)
	if not f then
		f = Instance.new("Folder")
		f.Name = name
		f.Parent = parent
	end
	return f
end

local m = workspace:FindFirstChild(SRC)
assert(m, SRC .. " not found in Workspace")
for _, d in ipairs(m:GetDescendants()) do
	if d:IsA("PackageLink") or d:IsA("AnimationController") or (d:IsA("Folder") and d.Name == "InitialPoses") then
		d:Destroy()
	end
end
for _, d in ipairs(m:GetDescendants()) do
	if d:IsA("BasePart") or d:IsA("Bone") then
		d.Name = string.gsub(d.Name, "%.%d+$", "")
	end
end
local parent = RS
for seg in string.gmatch("Assets." .. DEST, "[^%.]+") do
	parent = folder(parent, seg)
end
local old = parent:FindFirstChild(NAME)
if old then
	old:Destroy()
end
m.Name = NAME
m:SetAttribute("AssetId", ASSET_ID)
m:PivotTo(CFrame.new())
m.Parent = parent
local bones = 0
for _, d in ipairs(m:GetDescendants()) do
	if d:IsA("Bone") then
		bones += 1
	end
end
return string.format("%s -> %s.%s  children=%d bones=%d", SRC, DEST, NAME, #m:GetChildren(), bones)
