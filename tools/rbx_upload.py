#!/usr/bin/env python3
"""Upload a file to Roblox via the Open Cloud Assets API and print the asset id.

    python3 tools/rbx_upload.py art/build/body_cute.fbx --type Model --name "FAM Body Cute"
    python3 tools/rbx_upload.py art/build/skin.png --type Decal

The key lives in secrets/roblox_api_key.txt (gitignored, created 2026-09-16 on the
malikRania4L account, scopes asset:read + asset:write only). It is never printed.

Every successful upload is appended to art/build/uploads.json so a rebuild can skip
files whose content hash has not changed — uploads go through moderation and are slow.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_PATH = os.path.join(ROOT, "secrets", "roblox_api_key.txt")
LEDGER = os.path.join(ROOT, "art", "build", "uploads.json")
CREATOR_USER_ID = "10958960090"  # malikRania4L — the account Studio is logged into
BASE = "https://apis.roblox.com/assets/v1"

CONTENT_TYPES = {
    ".fbx": "model/fbx",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".rbxm": "model/x-rbxm",
    ".rbxmx": "model/x-rbxm",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


def key():
    with open(KEY_PATH) as f:
        return f.read().strip()


def request(method, url, body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("x-api-key", key())
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:800]
        raise SystemExit(f"HTTP {e.code} {method} {url}\n{detail}")


def multipart(fields, file_field, filename, content, ctype):
    boundary = "----fam" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'
        ).encode()
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def load_ledger():
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            return json.load(f)
    return {}


def save_ledger(ledger):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(ledger, f, indent=2, sort_keys=True)


def upload(path, asset_type, name, description="Feed a Monster! asset", force=False):
    with open(path, "rb") as f:
        content = f.read()
    digest = hashlib.sha256(content).hexdigest()[:16]
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    ledger = load_ledger()
    prior = ledger.get(rel)
    if prior and prior.get("sha") == digest and not force:
        return prior["assetId"], True

    ext = os.path.splitext(path)[1].lower()
    ctype = CONTENT_TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
    meta = {
        "assetType": asset_type,
        "displayName": name[:50],
        "description": description[:1000],
        "creationContext": {"creator": {"userId": CREATOR_USER_ID}},
    }
    body, bctype = multipart({"request": json.dumps(meta)}, "fileContent", os.path.basename(path), content, ctype)
    op = request("POST", f"{BASE}/assets", body, {"Content-Type": bctype})
    op_id = op.get("operationId") or op.get("path", "").split("/")[-1]
    if not op_id:
        raise SystemExit(f"no operation id in response: {op}")

    for attempt in range(90):
        res = request("GET", f"{BASE}/operations/{op_id}")
        if res.get("done"):
            if "error" in res:
                raise SystemExit(f"upload failed: {res['error']}")
            asset_id = res["response"]["assetId"]
            ledger[rel] = {"assetId": asset_id, "sha": digest, "type": asset_type, "name": name, "at": int(time.time())}
            save_ledger(ledger)
            return asset_id, False
        time.sleep(min(2 + attempt, 6))
    raise SystemExit(f"operation {op_id} did not finish")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--type", default="Model", choices=["Model", "Decal", "Audio", "Mesh", "Animation"])
    ap.add_argument("--name")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    for path in args.files:
        name = args.name or "FAM " + os.path.splitext(os.path.basename(path))[0]
        asset_id, cached = upload(path, args.type, name, force=args.force)
        print(f"{path}\t{asset_id}\t{'cached' if cached else 'uploaded'}")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
