#!/usr/bin/env python3
"""Pack src/ into an .rbxmx of scripts and upload it, so Studio can pull code without
pasting it through tool calls. Each script carries a StringValue-free `SyncPath` attribute.

    python3 tools/sync_rbxmx.py [files...]      # default: every .luau under src/ and tests/

Prints the asset id; then in Studio run tools/studio/apply_sync.luau with that id inserted.
Mapping (matches the live place):
  src/shared/X        -> ReplicatedStorage.Shared.X
  src/server/Services -> ServerScriptService.Services
  src/server/Main.server.luau -> ServerScriptService.Main
  src/client/ClientMain.client.luau -> StarterPlayer.StarterPlayerScripts.ClientMain
  src/client/Controllers -> StarterPlayer.StarterPlayerScripts.Controllers
  tests/X.server.luau -> ServerScriptService.X
"""
import os, sys, pathlib, html, subprocess, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent


def target(path: pathlib.Path):
    rel = path.relative_to(ROOT).as_posix()
    name = path.name
    cls = "ModuleScript"
    if name.endswith(".server.luau"):
        cls, name = "Script", name[: -len(".server.luau")]
    elif name.endswith(".client.luau"):
        cls, name = "LocalScript", name[: -len(".client.luau")]
    else:
        name = name[: -len(".luau")]
    parts = rel.split("/")
    if parts[0] == "src" and parts[1] == "shared":
        dest = ["ReplicatedStorage", "Shared"] + parts[2:-1] + [name]
    elif parts[0] == "src" and parts[1] == "server":
        dest = ["ServerScriptService"] + parts[2:-1] + [name]
    elif parts[0] == "src" and parts[1] == "client":
        dest = ["StarterPlayer", "StarterPlayerScripts"] + parts[2:-1] + [name]
    elif parts[0] == "tests":
        dest = ["ServerScriptService", name]
    else:
        return None
    return cls, ".".join(dest)


def item(cls, name, source, sync_path):
    ref = "RBX" + uuid.uuid4().hex
    attrs = sync_path.encode()
    # Attributes are binary-serialized; simpler to encode the path in the Name of a child
    # StringValue would be visible. Use the script Name = full dotted path instead.
    return f'''<Item class="{cls}" referent="{ref}"><Properties><string name="Name">{html.escape(sync_path)}</string><ProtectedString name="Source"><![CDATA[{source}]]></ProtectedString></Properties></Item>'''


def main():
    files = [pathlib.Path(a).resolve() for a in sys.argv[1:]] or sorted(
        list((ROOT / "src").rglob("*.luau")) + list((ROOT / "tests").rglob("*.luau")))
    items = []
    for f in files:
        t = target(f)
        if not t:
            continue
        cls, dotted = t
        src = f.read_text()
        assert "]]>" not in src, f"{f} contains ]]>"
        # every entry ships as a ModuleScript: an inserted Script would RUN during Play
        items.append(item("ModuleScript", dotted, src, dotted))
    xml = ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" version="4">'
           '<Item class="Folder" referent="RBXroot"><Properties><string name="Name">FAM_Sync</string></Properties>'
           + "".join(items) + "</Item></roblox>")
    out = ROOT / "art" / "build" / "sync.rbxmx"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml)
    print(f"packed {len(items)} scripts -> {out} ({out.stat().st_size} bytes)")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "rbx_upload.py"), str(out), "--name", "FAM code sync", "--force"],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


if __name__ == "__main__":
    main()
