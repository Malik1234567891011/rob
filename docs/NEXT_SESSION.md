# Handoff — resume here

**Written 2026-09-16 before a deliberate session restart** (to load the Blender MCP).
Everything below is committed and pushed to `main`. Nothing is in-flight.

## Where the game stands

Playable end to end, verified by running it:
- **33/33 integration tests pass** (`tests/DevIntegration.server.luau`)
- **First feed at 7.2 s** (spec ceiling is 15 s); eggs on screen at 0.56 s
- Server + client boot clean, no errors, no failed sound loads
- Pushed to `github.com/Malik1234567891011/rob`, branch `main`

Both dev harnesses (`DevIntegration`, `DevTiming`) are **disabled** in
`ServerScriptService`, so pressing Play gives the real first-60-seconds experience.

## The ONE unbuilt MVP item

The social **Trial** (SPEC §21). Everything else on the §60 MVP list is in.

## What to do next, in order

1. **Read `docs/ART_DIRECTION.md` first.** The creature art is Tier 1 (Roblox primitives)
   and is being replaced. Do not polish primitive geometry — it is being thrown away.
2. **Try `generate_mesh` before Blender.** See the Discovery section at the bottom of
   ART_DIRECTION.md. The Roblox MCP can generate segmented, textured meshes in-place,
   which sidesteps the mesh-upload blocker entirely. Prove one creature body round-trips
   through the existing `Anatomy` slot system before authoring anything by hand.
3. **Then** Blender for Tier 3 on the parts that justify it.
4. Finish the remaining game work (Trial, plus polish).

## Blender MCP state (set up this session)

- ✅ `uv`/`uvx` reinstalled **native arm64** (was x86_64 under Rosetta — that is why it
  tried to compile `cryptography` from Rust source and failed)
- ✅ Addon installed: `~/Library/Application Support/Blender/5.2/scripts/addons/blender_mcp.py`
- ✅ Registered: `claude mcp add blender uvx mcp-for-blender` → shows **Connected**
- ⚠️ Package was renamed `blender-mcp` → **`mcp-for-blender`**; the old name is a
  compat wrapper
- ❗ **Blender-side steps still required:** Blender → Preferences → Add-ons → enable
  *"Interface: MCP for Blender"* (or restart Blender), then click **Start MCP Server**.
  Port 9876 was still closed as of writing. If Blender tool calls fail, check that first
  before assuming the MCP is broken.
- ⚠️ Blender is **5.2.2 LTS**, newer than most addon testing. If it misbehaves, suspect
  version incompatibility.

## Hard-won constraints — do not rediscover these

`docs/DECISIONS.md` has the full list. The short version:
- Roblox MCP Luau sandbox has **no network** and **cannot `require()`** — `multi_edit` is
  the only way to write code, and verification happens by playtest + `get_console_output`
- `screen_capture` is **edit-mode only** (solid magenta during Play)
- macOS `screencapture` grabs whatever is **frontmost** — it caught unrelated windows
  twice. Prefer querying game state over capturing pixels.
