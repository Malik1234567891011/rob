--!strict
-- TrialsPanel — SPEC §21 Creature Trials. The list, what each trial favours (so different
-- builds are visibly valid, §22), personal bests, and the in-run HUD.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Shared = ReplicatedStorage:WaitForChild("Shared")
local Trials = require(Shared.Config:WaitForChild("Trials"))
local Traits = require(Shared.Config:WaitForChild("Traits"))
local Net = require(Shared:WaitForChild("Net"))

local TrialsPanel = {}
TrialsPanel.title = "Creature Trials"
TrialsPanel.emoji = "🏁"
TrialsPanel.height = 0.66

function TrialsPanel.build(body: Frame, ctx)
	local Theme = ctx.Theme
	local scroll = Theme.scroll(body)
	Theme.list(scroll, Enum.FillDirection.Vertical, 10)
	Theme.pad(scroll, 2, 4)

	-- ═══ HUD (lives on the main gui, visible only during a trial) ════════════
	local hud = Theme.card(ctx.gui, Theme.PAPER, 20)
	hud.Name = "TrialHud"
	hud.AnchorPoint = Vector2.new(0.5, 0)
	hud.Position = UDim2.new(0.5, 0, 0, 62)
	hud.Size = UDim2.fromOffset(340, 118)
	hud.Visible = false
	hud.ZIndex = 30
	Theme.stroke(hud, 3, Theme.accent.trials)
	local hudTitle = Theme.text({ text = "", font = Theme.DISPLAY, textSize = 20, pos = UDim2.fromOffset(14, 6), size = UDim2.new(1, -110, 0, 26), parent = hud })
	local hudTimer = Theme.text({ text = "", font = Theme.DISPLAY, textSize = 30, align = Enum.TextXAlignment.Right, pos = UDim2.new(1, -110, 0, 4), size = UDim2.fromOffset(96, 34), parent = hud })
	local hudLine = Theme.text({ text = "", font = Theme.BOLD, textSize = 16, pos = UDim2.fromOffset(14, 36), size = UDim2.new(1, -28, 0, 22), parent = hud })
	local hudBoard = Theme.text({ text = "", textSize = 13, color = Theme.MUTED, pos = UDim2.fromOffset(14, 60), size = UDim2.new(1, -120, 0, 52), parent = hud })
	local leave = Theme.button({ label = "Leave", size = UDim2.fromOffset(88, 40), pos = UDim2.new(1, -100, 1, -50), color = Theme.PAPER2, textSize = 16, parent = hud,
		onClick = function()
			Net.func("TrialLeave"):InvokeServer()
		end })
	local _l = leave
	local center = Theme.text({ text = "", font = Theme.DISPLAY, textSize = 96, color = Theme.WHITE, stroke = 0.3, align = Enum.TextXAlignment.Center,
		size = UDim2.new(1, 0, 0, 120), pos = UDim2.new(0, 0, 0.32, 0), parent = ctx.gui, scaled = true })
	center.Visible = false

	local state: any = nil
	RunService.Heartbeat:Connect(function()
		if not state or state.state == "closed" then
			hud.Visible = false
			center.Visible = false
			return
		end
		hud.Visible = true
		local now = workspace:GetServerTimeNow()
		local def = Trials.get(state.trial)
		hudTitle.Text = def and (def.emoji .. " " .. def.display) or ""
		if state.state == "queue" then
			hudTimer.Text = Theme.countdown((state.startsAt or now) - now)
			hudLine.Text = string.format("Waiting for monsters… %d joined", #(state.board or {}))
			center.Visible = false
		elseif state.state == "countdown" then
			local left = math.ceil((state.startsAt or now) - now)
			center.Visible = left > 0
			center.Text = left > 0 and tostring(left) or "GO!"
			hudTimer.Text = Theme.countdown((state.endsAt or now) - (state.startsAt or now))
		elseif state.state == "running" then
			local since = now - (state.startsAt or now)
			center.Visible = since < 0.8
			center.Text = "GO!"
			hudTimer.Text = Theme.countdown((state.endsAt or now) - now)
		elseif state.state == "results" then
			center.Visible = false
			hudTimer.Text = "🏆"
		end
		if state.me then
			if def and def.scoring == "time" then
				hudLine.Text = string.format("Lap %d / %d  ·  Checkpoint %d / %d", state.me.lap or 1, state.laps or 1, state.me.checkpoint or 0, state.checkpoints or 0)
			else
				hudLine.Text = string.format("Score: %d", state.me.score or 0)
			end
		end
		local lines = {}
		for i, e in ipairs(state.board or {}) do
			if i > 3 then
				break
			end
			local s = (def and def.scoring == "time") and (e.finished and string.format("%.2fs", e.score) or "running") or tostring(e.score)
			table.insert(lines, string.format("%d. %s — %s", i, e.name, s))
		end
		hudBoard.Text = table.concat(lines, "\n")
	end)

	Net.event("TrialState").OnClientEvent:Connect(function(payload)
		local prev = state and state.state
		state = payload
		if payload.state == "results" and prev ~= "results" then
			local def = Trials.get(payload.trial)
			local myRank = 0
			for i, e in ipairs(payload.board or {}) do
				if e.userId == ctx.player.UserId then
					myRank = i
				end
			end
			ctx.toast({ kind = "quest", title = "TRIAL COMPLETE", label = (def and def.emoji or "🏁") .. " You placed #" .. myRank, color = 0xFF9248 })
			ctx.effects.play("Evolution")
		elseif payload.state == "running" and prev ~= "running" then
			ctx.effects.play("Impact")
		end
	end)

	local function refresh()
		Theme.clear(scroll)
		local profile = ctx.profile
		local g = ctx.genome
		Theme.text({ text = "Short contests. Your monster's build changes how you play — there is no single best monster.",
			textSize = 15, color = Theme.MUTED, parent = scroll, order = 0, auto = true })
		for i, id in ipairs(Trials.order) do
			local def = Trials.get(id)
			local card = Theme.card(scroll, Theme.lighter(Theme.accent.trials, 0.8), 18)
			card.Size = UDim2.new(1, -8, 0, 112)
			card.LayoutOrder = i
			Theme.pad(card, 14, 10)
			Theme.text({ text = def.emoji .. "  " .. def.display, font = Theme.DISPLAY, textSize = 22, parent = card, size = UDim2.new(0.66, 0, 0, 28) })
			Theme.text({ text = def.blurb, textSize = 14, color = Theme.MUTED, pos = UDim2.fromOffset(0, 28), size = UDim2.new(0.66, 0, 0, 36), parent = card })
			local fav = {}
			for _, t in ipairs(def.favours) do
				local tr = Traits.get(t)
				if tr then
					table.insert(fav, tr.emoji)
				end
			end
			local best = profile and profile.trials and profile.trials.best[id]
			local bestText = best and ((def.scoring == "time") and string.format("Best %.2fs", best) or ("Best " .. best)) or "No best yet"
			Theme.text({ text = "Favours " .. table.concat(fav, " ") .. "   ·   " .. bestText, textSize = 13, font = Theme.BOLD,
				pos = UDim2.fromOffset(0, 66), size = UDim2.new(0.66, 0, 0, 20), parent = card })
			local ws = ctx.world
			local locked = def.update and ((ws and ws:GetAttribute("UpdateLevel") or 0) < def.update)
			local tooYoung = g and (g.stage or 1) < def.minStage
			Theme.button({ label = locked and "Soon" or (tooYoung and ("Stage " .. def.minStage) or "JOIN"), size = UDim2.new(0.3, 0, 0, 56),
				pos = UDim2.new(0.7, 0, 0.5, -28), textSize = 22, parent = card,
				color = (locked or tooYoung) and Theme.PAPER2 or Theme.accent.trials, onClick = function()
					local r = Net.func("TrialJoin"):InvokeServer(id)
					if r and r.ok then
						ctx.close()
					elseif r then
						ctx.toast({ title = "NOT YET", label = tostring(r.reason), color = 0xEC6060 })
					end
				end })
		end
	end

	return { refresh = refresh }
end

return TrialsPanel
