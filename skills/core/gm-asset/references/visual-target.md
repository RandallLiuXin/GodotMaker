# Visual Target - Per-Scene Reference Generation

Use this guide when generating `references/scene_{name}.png`.

## CLI

```bash
python tools/asset_source_generate.py \
  --spec .godotmaker/asset-generation/specs/scene_{name}.json

python tools/asset_image_finalize.py \
  --source .godotmaker/asset-generation/sources/scene_{name}_source.png \
  --out references/scene_{name}.png \
  --label scene_{name}
```

Use the aspect ratio that matches the scene viewport.

## Prompt Rules

The output must look like an in-game screenshot.

- Enumerate every gameplay-visible object.
- Name player characters, enemies, obstacles, collectibles, projectiles, platforms, props, and UI elements.
- Include each object's screen position and approximate screen size.
- Show the scene camera, playfield, boundaries, background layers, and foreground layers.
- Reflect tiling, layer separation, and sprite boundaries when the scene uses them.
- Use the exact visual style language from `STYLE.md`.
- Avoid style labels not present in `STYLE.md`.
- Show the most representative playable moment for the scene.
- Exclude effects the game will not implement.
- Include HUD/UI elements described in `SCENES.md`.

## Prompt Template

```text
Screenshot of a 2D video game. {Camera: angle, distance, perspective}.
Game objects: {player: appearance, position, size vs screen}. {enemies/NPCs: each type, position}. {obstacles}. {collectibles/pickups}. {projectiles if any}.
Environment: {background layers: sky, distant, mid}. {playfield surface: material, tiling}. {foreground elements}. {boundaries/edges}.
HUD: {each UI element: type and screen position}.
Visual style: {STYLE.md Style Anchor + Prompt Suffix}. Apply STYLE.md UI / Asset Rules. Avoid: {relevant STYLE.md Avoid entries}. Clean sharp digital rendering, game engine output.
```

## Inputs

For each scene, gather:

- Asset bindings from `SCENES.md`.
- Matching `ASSETS.md` Visual Asset Contract rows.
- Elements and mood from `SCENES.md`.
- Style Anchor, Prompt Suffix, UI / Asset Rules, and Avoid entries from `STYLE.md`.
- Existing user-art style summaries from `assets/manifest.json` when present.

## Output

Write the finalized scene reference to:

```text
references/scene_{name}.png
```

If the user rejects a generated reference, regenerate with a tightened prompt.
