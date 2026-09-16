-- apply_sync.luau — run via MCP execute_luau (Edit) after insert_asset of a
-- tools/sync_rbxmx.py bundle. Copies each bundled script's Source into the live script
-- named by its dotted path, then deletes the bundle. Scripts cannot be reparented from
-- the MCP thread, but Source is writable. Missing targets are reported: create them
-- with multi_edit (any placeholder content) and re-run.
local bundle = workspace:FindFirstChild("FAM_Sync")
assert(bundle, "insert the sync bundle first")
local applied, missing, unchanged = {}, {}, 0
for _, src in ipairs(bundle:GetChildren()) do
	if src:IsA("LuaSourceContainer") then
		local segs = string.split(src.Name, ".")
		local node: Instance? = game:GetService(segs[1])
		for i = 2, #segs do
			node = node and node:FindFirstChild(segs[i])
		end
		if node and node:IsA("LuaSourceContainer") then
			if (node :: any).Source ~= (src :: any).Source then
				(node :: any).Source = (src :: any).Source
				table.insert(applied, src.Name)
			else
				unchanged += 1
			end
		else
			table.insert(missing, src.Name)
		end
	end
end
bundle:Destroy()
return string.format("applied %d, unchanged %d\n  %s\nMISSING (%d):\n  %s", #applied, unchanged,
	table.concat(applied, "\n  "), #missing, table.concat(missing, "\n  "))
