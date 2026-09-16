#!/usr/bin/env python3
"""Generate the five SPEC §58 thumbnail concepts.

Roblox thumbnail personalization shows different thumbnails to different user
groups (~+8.5% average qualified play-through in Roblox's own tests, up to +50%),
so we ship five and let the platform decide rather than picking by taste.

The prompts deliberately describe what the GAME ACTUALLY RENDERS — chunky low-poly
blobs, crystal antlers, butterfly wings, a CRT head, lightning tails, striped
patterns. SPEC §63's third test is "show the thumbnail, don't explain the game" —
that only works if the art is honest about the product.

Key is read from ~/.config/feedamonster/openai.env and never written to the repo.
"""
import base64, json, os, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "art" / "thumbnails"
OUT.mkdir(parents=True, exist_ok=True)

env = pathlib.Path.home() / ".config/feedamonster/openai.env"
KEY = None
for line in env.read_text().splitlines():
    if line.startswith("OPENAI_API_KEY="):
        KEY = line.split("=", 1)[1].strip()
if not KEY:
    sys.exit("no OPENAI_API_KEY in " + str(env))

STYLE = (
    "Stylized 3D game art in the visual language of a polished Roblox experience. "
    "Soft low-poly forms, chunky rounded shapes, smooth matte plastic surfaces with "
    "a few glossy and neon accents. Warm cinematic key light, soft shadows, shallow "
    "depth of field. Saturated but natural colour — NOT neon overload. "
    "Creature silhouettes must read instantly at small size. Pixar-adjacent charm, "
    "not photorealism. No watermarks, no logos, no real brands, no UI chrome."
)

CREATURE = (
    "The creatures are built from chunky primitive shapes: a big rounded blob torso, "
    "stubby legs, oversized glossy cartoon eyes, and modular add-on parts."
)

CONCEPTS = {
    "A_transformation": (
        "Split composition. On the LEFT, a tiny adorable pale-pink blob creature the size "
        "of a melon, huge shiny black eyes, one small green leaf sprouting from its head, "
        "looking up hopefully. On the RIGHT, towering over it, an absolutely ridiculous "
        "15-foot monster built from the same blob anatomy but enormous: glowing cyan "
        "crystal antlers, translucent butterfly wings, a boxy vintage CRT television for a "
        "face with a glowing blue screen, chunky yellow-and-white striped body, thick blocky "
        "legs, a neon lightning-bolt tail. Bright grassy meadow, blue sky. "
        "Bold chunky white 3D text with a dark outline across the upper area reading exactly: "
        "WHAT WILL IT BECOME?"
    ),
    "B_dont_feed_it_that": (
        "Close, slightly low-angle shot. A blocky cartoon player avatar in the foreground "
        "holds out a single chunky black-and-gold battery toward a creature. The creature is "
        "mid-reaction: its mouth has become an enormous crackling electrical maw, yellow "
        "lightning arcing out, its eyes replaced by glowing yellow bolts, body sparking. "
        "Comedic alarm, not horror. Junkyard setting with scrap piles and old televisions. "
        "Bold chunky yellow 3D text with heavy dark outline reading exactly: DON'T FEED IT THAT"
    ),
    "C_cute": (
        "Extreme close-up, macro. One tiny round pastel-pink blob creature with enormous "
        "glossy black eyes and a tiny smile, sitting in soft grass, staring with total "
        "sincerity at a single bright red strawberry resting just in front of its face. "
        "Golden hour backlight, dreamy bokeh, dew on the grass. Overwhelmingly cute and warm. "
        "NO TEXT ANYWHERE in the image."
    ),
    "D_status": (
        "Wide hero group shot. Three blocky cartoon player avatars stand small in the "
        "foreground, each beside their own enormous and completely different creature: one "
        "made of glowing molten orange stone with a heavy shell, one a sleek electric-blue "
        "creature with huge translucent storm wings and a lightning tail, one a pale lunar "
        "creature with a single spiral crystal horn and drifting motes of light. Dramatic "
        "sunset rim lighting, epic scale contrast, a crowd-gathering moment. NO TEXT."
    ),
    "E_mystery": (
        "A single creature rendered as a pure black silhouette against a swirling deep violet "
        "and midnight-blue void, faint purple rim light tracing its outline. The silhouette is "
        "unmistakably strange: multiple horns, ragged moth wings, far too many small glowing "
        "eyes, a long curling tail. Only the eyes glow. Ominous but playful, not gory. "
        "Enormous bold white 3D question marks reading exactly: ???"
    ),
}


def generate(model, name, prompt, size="1536x1024"):
    body = json.dumps({
        "model": model,
        "prompt": f"{STYLE}\n\n{CREATURE}\n\n{prompt}",
        "size": size,
        "n": 1,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read())
    item = data["data"][0]
    if "b64_json" in item:
        raw = base64.b64decode(item["b64_json"])
    else:
        with urllib.request.urlopen(item["url"], timeout=120) as ir:
            raw = ir.read()
    path = OUT / f"{name}.png"
    path.write_bytes(raw)
    return path, len(raw)


def main():
    models = sys.argv[1:] or ["gpt-image-2.5-sunburst", "gpt-image-2", "gpt-image-1.5"]
    chosen = None
    results = []
    for name, prompt in CONCEPTS.items():
        for model in ([chosen] if chosen else models):
            try:
                t0 = time.time()
                path, size = generate(model, name, prompt)
                chosen = model
                results.append((name, model, path.name, size, time.time() - t0))
                print(f"OK    {name:20s} {model:24s} {size/1024:7.0f} KB  {time.time()-t0:5.1f}s")
                break
            except Exception as e:
                msg = str(e)
                if hasattr(e, "read"):
                    try:
                        msg = e.read().decode()[:300]
                    except Exception:
                        pass
                print(f"FAIL  {name:20s} {model:24s} {msg[:180]}")
    print(f"\n{len(results)}/{len(CONCEPTS)} generated into {OUT}")
    return 0 if len(results) == len(CONCEPTS) else 1


if __name__ == "__main__":
    sys.exit(main())
