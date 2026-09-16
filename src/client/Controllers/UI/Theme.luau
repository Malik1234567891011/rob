--!strict
-- UI.Theme — one visual language for every panel. SPEC §44: mobile first, chunky targets,
-- "the creature is the UI" (so the HUD stays small and soft).
--
-- Everything is built from code (no image uploads to break): rounded cards, lip buttons that
-- press down, soft drop shadows made from offset frames.

local TweenService = game:GetService("TweenService")

local Theme = {}

Theme.PAPER = Color3.fromRGB(253, 250, 244)
Theme.PAPER2 = Color3.fromRGB(243, 238, 228)
Theme.INK = Color3.fromRGB(38, 32, 48)
Theme.MUTED = Color3.fromRGB(126, 118, 138)
Theme.LINE = Color3.fromRGB(226, 218, 204)
Theme.SHADOW = Color3.fromRGB(20, 14, 30)
Theme.WHITE = Color3.new(1, 1, 1)

Theme.accent = {
	feed = Color3.fromRGB(255, 208, 84),
	monster = Color3.fromRGB(255, 150, 188),
	book = Color3.fromRGB(167, 128, 255),
	quest = Color3.fromRGB(96, 214, 140),
	home = Color3.fromRGB(88, 196, 196),
	trials = Color3.fromRGB(255, 146, 72),
	shop = Color3.fromRGB(255, 196, 64),
	party = Color3.fromRGB(110, 168, 255),
	parade = Color3.fromRGB(244, 108, 196),
	danger = Color3.fromRGB(236, 96, 96),
}

Theme.DISPLAY = Enum.Font.FredokaOne
Theme.BODY = Enum.Font.GothamMedium
Theme.BOLD = Enum.Font.GothamBold

function Theme.darker(c: Color3, k: number?): Color3
	return c:Lerp(Color3.new(0, 0, 0), k or 0.22)
end

function Theme.lighter(c: Color3, k: number?): Color3
	return c:Lerp(Color3.new(1, 1, 1), k or 0.5)
end

function Theme.hex(n: number): Color3
	return Color3.fromRGB(math.floor(n / 65536) % 256, math.floor(n / 256) % 256, n % 256)
end

function Theme.corner(parent: Instance, r: number?)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, r or 16)
	c.Parent = parent
	return c
end

function Theme.stroke(parent: Instance, thickness: number?, color: Color3?, transparency: number?)
	local s = Instance.new("UIStroke")
	s.Thickness = thickness or 2
	s.Color = color or Theme.LINE
	s.Transparency = transparency or 0
	s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	s.Parent = parent
	return s
end

function Theme.pad(parent: Instance, px: number?, py: number?)
	local p = Instance.new("UIPadding")
	local x, y = px or 12, py or px or 12
	p.PaddingLeft, p.PaddingRight = UDim.new(0, x), UDim.new(0, x)
	p.PaddingTop, p.PaddingBottom = UDim.new(0, y), UDim.new(0, y)
	p.Parent = parent
	return p
end

function Theme.list(parent: Instance, dir: Enum.FillDirection?, gap: number?, align: Enum.HorizontalAlignment?)
	local l = Instance.new("UIListLayout")
	l.FillDirection = dir or Enum.FillDirection.Vertical
	l.Padding = UDim.new(0, gap or 8)
	l.SortOrder = Enum.SortOrder.LayoutOrder
	if align then
		l.HorizontalAlignment = align
	end
	l.Parent = parent
	return l
end

function Theme.grid(parent: Instance, cell: Vector2, gap: number?)
	local g = Instance.new("UIGridLayout")
	g.CellSize = UDim2.fromOffset(cell.X, cell.Y)
	g.CellPadding = UDim2.fromOffset(gap or 8, gap or 8)
	g.SortOrder = Enum.SortOrder.LayoutOrder
	g.HorizontalAlignment = Enum.HorizontalAlignment.Center
	g.Parent = parent
	return g
end

export type TextProps = {
	text: string?, font: Enum.Font?, color: Color3?, size: UDim2?, pos: UDim2?, textSize: number?,
	align: Enum.TextXAlignment?, valign: Enum.TextYAlignment?, wrap: boolean?, name: string?,
	parent: Instance?, order: number?, auto: boolean?, stroke: number?, scaled: boolean?,
}

function Theme.text(p: TextProps): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Font = p.font or Theme.BODY
	t.TextColor3 = p.color or Theme.INK
	t.Text = p.text or ""
	t.Size = p.size or UDim2.new(1, 0, 0, (p.textSize or 16) + 6)
	t.Position = p.pos or UDim2.new()
	t.TextXAlignment = p.align or Enum.TextXAlignment.Left
	t.TextYAlignment = p.valign or Enum.TextYAlignment.Center
	t.TextWrapped = p.wrap ~= false
	t.RichText = true
	if p.scaled then
		t.TextScaled = true
		local c = Instance.new("UITextSizeConstraint")
		c.MaxTextSize = p.textSize or 28
		c.Parent = t
	else
		t.TextSize = p.textSize or 16
	end
	if p.auto then
		t.AutomaticSize = Enum.AutomaticSize.Y
	end
	if p.stroke then
		t.TextStrokeTransparency = p.stroke
		t.TextStrokeColor3 = Theme.SHADOW
	end
	t.Name = p.name or "Text"
	t.LayoutOrder = p.order or 0
	if p.parent then
		t.Parent = p.parent
	end
	return t
end

-- A soft shadow behind any frame.
function Theme.shadow(frame: GuiObject, offset: number?, transparency: number?)
	local s = Instance.new("Frame")
	s.Name = "Shadow"
	s.BackgroundColor3 = Theme.SHADOW
	s.BackgroundTransparency = transparency or 0.82
	s.BorderSizePixel = 0
	s.Size = UDim2.new(1, 0, 1, 0)
	s.Position = UDim2.fromOffset(0, offset or 5)
	s.ZIndex = math.max(0, frame.ZIndex - 1)
	local r = frame:FindFirstChildOfClass("UICorner")
	Theme.corner(s, r and r.CornerRadius.Offset or 16)
	s.Parent = frame.Parent
	-- follow the frame
	local function sync()
		s.AnchorPoint = frame.AnchorPoint
		s.Size = frame.Size
		s.Position = frame.Position + UDim2.fromOffset(0, offset or 5)
		s.Visible = frame.Visible
		s.LayoutOrder = frame.LayoutOrder
	end
	sync()
	frame:GetPropertyChangedSignal("Position"):Connect(sync)
	frame:GetPropertyChangedSignal("Size"):Connect(sync)
	frame:GetPropertyChangedSignal("Visible"):Connect(sync)
	return s
end

export type ButtonProps = {
	label: string?, emoji: string?, size: UDim2, pos: UDim2?, anchor: Vector2?, color: Color3?,
	textColor: Color3?, parent: Instance?, radius: number?, textSize: number?, order: number?,
	name: string?, onClick: (() -> ())?, badge: boolean?, sub: string?,
}

-- Chunky "lip" button: a darker base under a face that presses down on click.
function Theme.button(p: ButtonProps): TextButton
	local color = p.color or Theme.PAPER
	local holder = Instance.new("TextButton")
	holder.Name = p.name or "Button"
	holder.Text = ""
	holder.AutoButtonColor = false
	holder.BackgroundTransparency = 1
	holder.Size = p.size
	holder.Position = p.pos or UDim2.new()
	holder.AnchorPoint = p.anchor or Vector2.new()
	holder.LayoutOrder = p.order or 0

	local lip = Instance.new("Frame")
	lip.Name = "Lip"
	lip.BackgroundColor3 = Theme.darker(color, 0.28)
	lip.BorderSizePixel = 0
	lip.Size = UDim2.new(1, 0, 1, -2)
	lip.Position = UDim2.fromOffset(0, 5)
	lip.Parent = holder
	Theme.corner(lip, p.radius or 16)

	local face = Instance.new("Frame")
	face.Name = "Face"
	face.BackgroundColor3 = color
	face.BorderSizePixel = 0
	face.Size = UDim2.new(1, 0, 1, -5)
	face.Parent = holder
	Theme.corner(face, p.radius or 16)
	Theme.stroke(face, 2, Theme.darker(color, 0.12), 0.3)

	local label = Theme.text({
		text = (p.emoji and (p.emoji .. (p.label and "  " or "")) or "") .. (p.label or ""),
		font = Theme.DISPLAY, color = p.textColor or Theme.INK, textSize = p.textSize or 20,
		align = Enum.TextXAlignment.Center, size = p.sub and UDim2.new(1, -8, 0.62, 0) or UDim2.new(1, -8, 1, 0),
		pos = UDim2.fromOffset(4, 0), parent = face, name = "Label", scaled = true,
	})
	label.TextWrapped = false
	if p.sub then
		Theme.text({
			text = p.sub, font = Theme.BOLD, color = p.textColor or Theme.INK, textSize = 12,
			align = Enum.TextXAlignment.Center, size = UDim2.new(1, -8, 0.34, 0), pos = UDim2.new(0, 4, 0.6, 0),
			parent = face, name = "Sub", scaled = true,
		}).TextTransparency = 0.2
	end

	if p.badge then
		local dot = Instance.new("Frame")
		dot.Name = "Badge"
		dot.Size = UDim2.fromOffset(16, 16)
		dot.AnchorPoint = Vector2.new(0.5, 0.5)
		dot.Position = UDim2.new(1, -6, 0, 6)
		dot.BackgroundColor3 = Theme.accent.danger
		dot.Visible = false
		dot.Parent = holder
		Theme.corner(dot, 8)
		Theme.stroke(dot, 2, Theme.WHITE)
	end

	local down = false
	holder.MouseButton1Down:Connect(function()
		down = true
		TweenService:Create(face, TweenInfo.new(0.06), { Position = UDim2.fromOffset(0, 4) }):Play()
	end)
	local function up()
		if down then
			down = false
			TweenService:Create(face, TweenInfo.new(0.12, Enum.EasingStyle.Back), { Position = UDim2.fromOffset(0, 0) }):Play()
		end
	end
	holder.MouseButton1Up:Connect(up)
	holder.MouseLeave:Connect(up)
	if p.onClick then
		holder.MouseButton1Click:Connect(p.onClick)
	end
	if p.parent then
		holder.Parent = p.parent
	end
	return holder
end

function Theme.setButton(btn: TextButton, label: string?, color: Color3?)
	local face = btn:FindFirstChild("Face") :: Frame?
	if not face then
		return
	end
	if label then
		(face:FindFirstChild("Label") :: TextLabel).Text = label
	end
	if color then
		face.BackgroundColor3 = color;
		(btn:FindFirstChild("Lip") :: Frame).BackgroundColor3 = Theme.darker(color, 0.28)
	end
end

function Theme.card(parent: Instance?, color: Color3?, radius: number?): Frame
	local f = Instance.new("Frame")
	f.BackgroundColor3 = color or Theme.PAPER
	f.BorderSizePixel = 0
	Theme.corner(f, radius or 18)
	if parent then
		f.Parent = parent
	end
	return f
end

function Theme.progress(parent: Instance, color: Color3, height: number?): (Frame, (number) -> ())
	local bar = Instance.new("Frame")
	bar.Name = "Progress"
	bar.BackgroundColor3 = Theme.PAPER2
	bar.BorderSizePixel = 0
	bar.Size = UDim2.new(1, 0, 0, height or 10)
	Theme.corner(bar, (height or 10) // 2)
	local fill = Instance.new("Frame")
	fill.Name = "Fill"
	fill.BackgroundColor3 = color
	fill.BorderSizePixel = 0
	fill.Size = UDim2.fromScale(0, 1)
	fill.Parent = bar
	Theme.corner(fill, (height or 10) // 2)
	bar.Parent = parent
	return bar, function(v: number)
		TweenService:Create(fill, TweenInfo.new(0.35, Enum.EasingStyle.Quint), { Size = UDim2.fromScale(math.clamp(v, 0, 1), 1) }):Play()
	end
end

function Theme.chip(parent: Instance, text: string, color: Color3?, order: number?): TextLabel
	local t = Theme.text({ text = text, font = Theme.BOLD, textSize = 14, color = Theme.INK, parent = parent, order = order,
		align = Enum.TextXAlignment.Center, wrap = false })
	t.AutomaticSize = Enum.AutomaticSize.X
	t.Size = UDim2.fromOffset(0, 28)
	t.BackgroundTransparency = 0
	t.BackgroundColor3 = color and Theme.lighter(color, 0.62) or Theme.PAPER2
	Theme.corner(t, 14)
	Theme.pad(t, 10, 0)
	return t
end

function Theme.scroll(parent: Instance, size: UDim2?, pos: UDim2?): ScrollingFrame
	local s = Instance.new("ScrollingFrame")
	s.BackgroundTransparency = 1
	s.BorderSizePixel = 0
	s.Size = size or UDim2.fromScale(1, 1)
	s.Position = pos or UDim2.new()
	s.ScrollBarThickness = 5
	s.ScrollBarImageColor3 = Theme.MUTED
	s.CanvasSize = UDim2.new()
	s.AutomaticCanvasSize = Enum.AutomaticSize.Y
	s.ScrollingDirection = Enum.ScrollingDirection.Y
	s.Parent = parent
	return s
end

function Theme.clear(container: Instance)
	for _, c in ipairs(container:GetChildren()) do
		if c:IsA("GuiObject") then
			c:Destroy()
		end
	end
end

function Theme.fmt(n: number): string
	if n >= 1e9 then
		return string.format("%.1fB", n / 1e9)
	elseif n >= 1e6 then
		return string.format("%.1fM", n / 1e6)
	elseif n >= 1e4 then
		return string.format("%.1fK", n / 1e3)
	end
	local s = tostring(math.floor(n))
	return (s:reverse():gsub("(%d%d%d)", "%1,"):reverse():gsub("^,", ""))
end

function Theme.countdown(seconds: number): string
	seconds = math.max(0, math.floor(seconds))
	if seconds >= 3600 * 24 then
		return string.format("%dd %dh", seconds // 86400, (seconds % 86400) // 3600)
	elseif seconds >= 3600 then
		return string.format("%dh %02dm", seconds // 3600, (seconds % 3600) // 60)
	end
	return string.format("%d:%02d", seconds // 60, seconds % 60)
end

function Theme.pop(gui: GuiObject)
	local scale = gui:FindFirstChildOfClass("UIScale") or Instance.new("UIScale")
	scale.Parent = gui
	scale.Scale = 0.6
	TweenService:Create(scale, TweenInfo.new(0.35, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = 1 }):Play()
end

return Theme
