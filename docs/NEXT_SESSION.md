# Handoff — resume here

**Updated 2026-09-16.** The plan is `docs/COMPLETION_PLAN.md` — the whole game, not the MVP.
Malik rejected MVP scope and `generate_mesh` explicitly: Blender is the art pipeline.

## Solved this session (do not re-solve)
- Blender MCP works (addon 1.7, Blender 5.2.2).
- **Mesh pipeline:** FBX → `tools/rbx_upload.py` (Open Cloud) → `insert_asset`. Skinning,
  shared skeletons, cross-FBX part binding and vertex colours all verified. DECISIONS.md.
- **Edit-mode runtime:** `loadstring` works in the MCP sandbox, so a require shim runs the
  real modules in edit mode for `screen_capture`. `Script.Source` is writable.

## Where to look
- `docs/COMPLETION_PLAN.md` — phases A–E with status boxes
- `docs/DECISIONS.md` — constraints that bit
- `docs/ART_DIRECTION.md` — Tier 3 target
