--!strict
-- MonsterPanel — who your monster is. SPEC §14 stages, §12 traits, §11 abilities, §15 the
-- Nest, §19 names, §18 temperament. A kid reads "Leafy, Electric, can Glide"; an optimiser
-- toggles numbers. Evolve and Nest live here because they are about THIS creature.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Mutations = require(Shared.Config:WaitForChild("Mutations"))
local Progression = require(Shared.Config:WaitForChild("Progression"))
local Anatomy = require(Shared.Config:WaitForChild("Anatomy"))
local CreatureBuilder = require(Shared:WaitForChild("CreatureBuilder"))
local TableUtil = require(Shared.Util:WaitForChild("TableUtil"))

local MonsterPanel = {}
MonsterPanel.title = "Monster"
MonsterPanel.emoji = "🐾"
MonsterPanel.height = 0.7

local TEMPERAMENT = {
	curious = "🧐 Curious", lazy = "😴 Lazy", greedy = "🤤 Greedy", brave = "🦁 Brave",
	nervous = "😰 Nervous", silly = "🤪 Silly", affectionate = "🥰 Affectionate", mischievous = "😈 Mischievous",
}

function MonsterPanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local scroll = Theme.scroll(body)
	Theme.list(scroll, Enum.FillDirection.Vertical, 10)
	Theme.pad(scroll, 2, 4)

	local function section(title: string, order: number): Frame
		local f = Instance.new("Frame")
		f.BackgroundTransparency = 1
		f.Size = UDim2.new(1, -8, 0, 0)
		f.AutomaticSize = Enum.AutomaticSize.Y
		f.LayoutOrder = order
		f.Parent = scroll
		Theme.list(f, Enum.FillDirection.Vertical, 6)
		Theme.text({ text = title, font = Theme.BOLD, textSize = 13, color = Theme.MUTED, parent = f, order = 0 })
		return f
	end

	local function chipsRow(parent: Instance, order: number): Frame
		local row = Instance.new("Frame")
		row.BackgroundTransparency = 1
		row.Size = UDim2.new(1, 0, 0, 0)
		row.AutomaticSize = Enum.AutomaticSize.Y
		row.LayoutOrder = order
		row.Parent = parent
		local l = Instance.new("UIGridLayout")
		l.CellSize = UDim2.fromOffset(150, 30)
		l.CellPadding = UDim2.fromOffset(6, 6)
		l.SortOrder = Enum.SortOrder.LayoutOrder
		l.Parent = row
		return row
	end

	local function refresh()
		Theme.clear(scroll)
		local profile = ctx.profile
		local g = ctx.genome
		if not profile or not g then
			Theme.text({ text = "No monster yet. Pick an egg in your backyard! 🥚", font = Theme.DISPLAY, textSize = 22, parent = scroll, auto = true })
			return
		end
		local stage = Progression.stage(g.stage or 1)
		local family = Anatomy.bodies[g.bodyFamily] or Anatomy.bodies.Cute

		-- ── headline ─────────────────────────────────────────────────────────
		local top = Theme.card(scroll, Theme.lighter(ctx.Theme.accent.monster, 0.72), 20)
		top.Size = UDim2.new(1, -8, 0, 118)
		top.LayoutOrder = 1
		Theme.pad(top, 16, 10)
		Theme.text({ text = (g.name or "Your Monster"), font = Theme.DISPLAY, textSize = 32, parent = top, size = UDim2.new(1, -130, 0, 40) })
		Theme.text({ text = string.format("%s <b>%s</b>  ·  Gen %d  ·  %s", stage.emoji, stage.name, g.generation or 1, family.display),
			textSize = 16, pos = UDim2.fromOffset(0, 42), size = UDim2.new(1, -130, 0, 22), parent = top })
		local tmp = TableUtil.topN(g.temperament or {}, 1)
		Theme.text({ text = tmp[1] and (TEMPERAMENT[tmp[1].key] or tmp[1].key) or "", textSize = 15, color = Theme.MUTED,
			pos = UDim2.fromOffset(0, 66), size = UDim2.new(1, -130, 0, 20), parent = top })

		local need = stage.feedsToNext
		if need then
			local barHolder = Instance.new("Frame")
			barHolder.BackgroundTransparency = 1
			barHolder.Position = UDim2.new(1, -120, 0, 8)
			barHolder.Size = UDim2.fromOffset(120, 80)
			barHolder.Parent = top
			Theme.text({ text = "GROWING", font = Theme.BOLD, textSize = 12, color = Theme.MUTED, parent = barHolder })
			local bar, set = Theme.progress(barHolder, Theme.accent.monster, 14)
			bar.Position = UDim2.fromOffset(0, 24)
			set((g.fedCount or 0) / need)
			Theme.text({ text = string.format("%d / %d meals", math.min(g.fedCount or 0, need), need), textSize = 13,
				pos = UDim2.fromOffset(0, 44), parent = barHolder })
		end

		-- ── evolve / nest ────────────────────────────────────────────────────
		if Progression.readyToEvolve(g.stage or 1, g.fedCount or 0) and (g.stage or 1) < Progression.maxStage() then
			Theme.button({ emoji = "✨", label = "IT'S READY TO EVOLVE", size = UDim2.new(1, -8, 0, 64), color = Theme.accent.shop,
				textSize = 24, parent = scroll, order = 2, onClick = function()
					local r = ctx.Net.func("Evolve"):InvokeServer()
					if r and r.ok then
						ctx.close()
					end
				end })
		elseif (g.stage or 1) >= Progression.maxStage() then
			Theme.button({ emoji = "🥚", label = "THE NEST — RAISE THE NEXT ONE", size = UDim2.new(1, -8, 0, 60), color = Theme.accent.book,
				textColor = Theme.WHITE, textSize = 20, parent = scroll, order = 2, onClick = function()
					ctx.Net.func("CreateLineage"):InvokeServer()
					ctx.close()
				end })
			Theme.text({ text = "Your Mythic monster stays in your Sanctuary forever. Its egg inherits a gene.", textSize = 13,
				color = Theme.MUTED, parent = scroll, order = 3, auto = true })
		end

		-- ── traits (what it is made of) ──────────────────────────────────────
		local traitsSec = section("MADE OF", 10)
		local eff = CreatureBuilder.effectiveTraits(g)
		local ranked = TableUtil.topN(eff, 6)
		local maxV = ranked[1] and math.max(ranked[1].value, 10) or 10
		for i, entry in ipairs(ranked) do
			local t = Traits.get(entry.key)
			if t and entry.value >= 1 then
				local row = Instance.new("Frame")
				row.BackgroundTransparency = 1
				row.Size = UDim2.new(1, 0, 0, 26)
				row.LayoutOrder = i
				row.Parent = traitsSec
				Theme.text({ text = t.emoji .. " " .. t.display, font = Theme.BOLD, textSize = 15, size = UDim2.new(0.36, 0, 1, 0), parent = row })
				local bar, set = Theme.progress(row, Theme.hex(t.color), 14)
				bar.Position = UDim2.new(0.37, 0, 0.5, -7)
				bar.Size = UDim2.new(0.5, 0, 0, 14)
				set(entry.value / maxV)
				Theme.text({ text = string.format("%d", entry.value), textSize = 13, color = Theme.MUTED,
					size = UDim2.new(0.12, 0, 1, 0), pos = UDim2.new(0.88, 0, 0, 0), parent = row, align = Enum.TextXAlignment.Right })
			end
		end
		if #ranked == 0 then
			Theme.text({ text = "Nothing yet — feed it something!", textSize = 14, color = Theme.MUTED, parent = traitsSec, order = 1 })
		end

		-- ── mutations + abilities ────────────────────────────────────────────
		local mutSec = section("MUTATIONS", 20)
		local mutRow = chipsRow(mutSec, 1)
		local count = 0
		for _, id in ipairs(Mutations.order) do
			if (g.mutations or {})[id] then
				local def = Mutations.get(id)
				count += 1
				Theme.chip(mutRow, def.emoji .. " " .. def.display, def.secret and Theme.accent.book or Theme.accent.quest, count)
			end
		end
		if count == 0 then
			Theme.text({ text = "None yet. Keep feeding it the same kind of thing and watch.", textSize = 14, color = Theme.MUTED, parent = mutSec, order = 2 })
		end
		local abSec = section("CAN DO", 30)
		local abRow = chipsRow(abSec, 1)
		local an = 0
		for ability, on in pairs(g.abilities or {}) do
			local def = Mutations.abilities[ability]
			if on and def then
				an += 1
				Theme.chip(abRow, def.emoji .. " " .. def.display, Theme.accent.trials, an)
			end
		end
		if an == 0 then
			Theme.text({ text = "No special abilities yet. Mutations unlock them — and they open new places.", textSize = 14,
				color = Theme.MUTED, parent = abSec, order = 2 })
		end

		-- ── roster (swap / new egg) ──────────────────────────────────────────
		local rosterSec = section("YOUR MONSTERS", 40)
		local row = Instance.new("Frame")
		row.BackgroundTransparency = 1
		row.Size = UDim2.new(1, 0, 0, 64)
		row.LayoutOrder = 1
		row.Parent = rosterSec
		Theme.list(row, Enum.FillDirection.Horizontal, 8)
		local slots = 0
		for i, c in ipairs(profile.creatures) do
			if not c.retired then
				slots += 1
				local st = Progression.stage(c.stage or 1)
				Theme.button({ emoji = st.emoji, label = c.name or ("#" .. i), size = UDim2.fromOffset(150, 58), textSize = 16,
					color = i == profile.activeCreature and Theme.accent.monster or Theme.PAPER2, parent = row, order = i,
					onClick = function()
						ctx.Net.func("SwitchCreature"):InvokeServer(i)
					end })
			end
		end
		Theme.button({ emoji = "🥚", label = "New Egg", sub = "25 🔮", size = UDim2.fromOffset(120, 58), color = Theme.PAPER2, textSize = 16,
			parent = row, order = 99, onClick = function()
				local r = ctx.Net.func("NewEgg"):InvokeServer(nil)
				if r and not r.ok then
					ctx.toast({ title = "NOT YET", label = tostring(r.reason), color = 0xEC6060 })
				end
			end })

		-- ── elders (retired parents live forever) ────────────────────────────
		local elders = {}
		for _, c in ipairs(profile.creatures) do
			if c.retired then
				table.insert(elders, (c.name or "Elder") .. " (Gen " .. (c.generation or 1) .. ")")
			end
		end
		if #elders > 0 then
			local e = section("LIVING IN YOUR SANCTUARY", 50)
			Theme.text({ text = table.concat(elders, "  ·  "), textSize = 14, parent = e, order = 1, auto = true })
		end

		-- ── settings ─────────────────────────────────────────────────────────
		local set = section("SETTINGS", 90)
		local srow = Instance.new("Frame")
		srow.BackgroundTransparency = 1
		srow.Size = UDim2.new(1, 0, 0, 50)
		srow.LayoutOrder = 1
		srow.Parent = set
		Theme.list(srow, Enum.FillDirection.Horizontal, 8)
		for i, key in ipairs({ "music", "sfx" }) do
			local on = profile.settings == nil or profile.settings[key] ~= false
			Theme.button({ emoji = key == "music" and "🎵" or "🔊", label = (key == "music" and "Music " or "Sounds ") .. (on and "On" or "Off"),
				size = UDim2.fromOffset(150, 46), textSize = 16, color = on and Theme.accent.quest or Theme.PAPER2, parent = srow, order = i,
				onClick = function()
					ctx.Net.func("SetSetting"):InvokeServer(key, not on)
					if profile.settings then
						profile.settings[key] = not on
					end
					ctx.effects.setEnabled(key, not on)
					refresh()
				end })
		end
	end

	return { refresh = refresh }
end

return MonsterPanel
