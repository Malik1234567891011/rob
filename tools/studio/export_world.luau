-- export_world.luau — run via MCP execute_luau (Edit). Serialises Workspace.World parts and a
-- terrain height/material grid into ServerStorage.__ExportP / __ExportT (90 KB StringValues).
-- Fetch each chunk with:  return "@@P1@@" .. game.ServerStorage.__ExportP["1"].Value .. "@@END@@" .. string.rep("~", 95000)
-- (the padding forces the MCP to save the result to a file), then:
--   python3 tools/join_export.py <tool-results dir> P <n> art/build/world_export/parts.txt
--   python3 tools/join_export.py <tool-results dir> T <n> art/build/world_export/terrain.txt
-- and render with tools/blender/world_preview.py.
local RS = game:GetService("ReplicatedStorage")
local SS = game:GetService("ServerStorage")
local map = {}
for _, d in ipairs(RS.Assets.Kits:GetDescendants()) do if d:IsA("MeshPart") then map[d.MeshId] = d.Parent.Name .. "/" .. d.Name end end
for _, d in ipairs(RS.Assets.Props:GetDescendants()) do if d:IsA("MeshPart") then map[d.MeshId] = "Props/" .. d.Parent.Name end end
local lines = {}
local function f(v) return string.format("%.2f", v) end
local function r(v) return string.format("%.3f", v) end
for _, d in ipairs(workspace.World:GetDescendants()) do
  if d:IsA("BasePart") and d.Transparency < 0.99 then
    local c = { d.CFrame:GetComponents() }
    local kind
    if d:IsA("MeshPart") then kind = map[d.MeshId] or ("?" .. d.Name)
    elseif d:IsA("Part") then kind = "#" .. d.Shape.Name
    elseif d:IsA("WedgePart") then kind = "#Wedge"
    else kind = "#" .. d.ClassName end
    local col = d.Color
    table.insert(lines, table.concat({ kind, f(c[1]), f(c[2]), f(c[3]), r(c[4]), r(c[5]), r(c[6]), r(c[7]), r(c[8]), r(c[9]), r(c[10]), r(c[11]), r(c[12]),
      f(d.Size.X), f(d.Size.Y), f(d.Size.Z), string.format("%02x%02x%02x", col.R*255, col.G*255, col.B*255), d.Material.Name, string.format("%.2f", d.Transparency) }, " "))
  end
end
local parts = table.concat(lines, "\n")
local T = workspace.Terrain
local p1 = RaycastParams.new(); p1.FilterType = Enum.RaycastFilterType.Include; p1.FilterDescendantsInstances = { T }; p1.IgnoreWater = true
local p2 = RaycastParams.new(); p2.FilterType = Enum.RaycastFilterType.Include; p2.FilterDescendantsInstances = { T }; p2.IgnoreWater = false
local mats, matList = {}, {}
local function mi(m) if not mats[m] then table.insert(matList, m.Name); mats[m] = #matList end return mats[m] end
local out = {}
local function region(name, x0, x1, z0, z1, step)
  table.insert(out, string.format("R %s %d %d %d %d %d", name, x0, x1, z0, z1, step))
  for z = z0, z1, step do
    local row = {}
    for x = x0, x1, step do
      local g = workspace:Raycast(Vector3.new(x, 400, z), Vector3.new(0, -500, 0), p1)
      local w = workspace:Raycast(Vector3.new(x, 400, z), Vector3.new(0, -500, 0), p2)
      if not g then table.insert(row, w and ("_ 0 " .. math.floor(w.Position.Y*2+0.5)) or "_")
      else
        local cell = math.floor(g.Position.Y*2+0.5) .. " " .. mi(g.Material)
        if w and w.Material == Enum.Material.Water and w.Position.Y > g.Position.Y + 0.2 then cell ..= " " .. math.floor(w.Position.Y*2+0.5) end
        table.insert(row, cell)
      end
    end
    table.insert(out, table.concat(row, ","))
  end
end
region("main", -904, 904, -1000, 624, 8)
region("trials", 5840, 6264, -240, 2464, 8)
local terrain = "M " .. table.concat(matList, " ") .. "\n" .. table.concat(out, "\n")
for _, name in ipairs({"__ExportP", "__ExportT"}) do local o = SS:FindFirstChild(name); if o then o:Destroy() end end
local function store(name, s)
  local folder = Instance.new("Folder"); folder.Name = name; folder.Parent = SS
  local i, n = 1, 0
  while i <= #s do n += 1; local v = Instance.new("StringValue"); v.Name = tostring(n); v.Value = string.sub(s, i, i + 89999); v.Parent = folder; i += 90000 end
  return n
end
return "parts " .. #lines .. " P chunks " .. store("__ExportP", parts) .. "; T chunks " .. store("__ExportT", terrain)
