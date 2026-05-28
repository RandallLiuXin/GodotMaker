# Visual Target — Per-Scene Reference Generation

How to write prompts for `tools/asset_gen.py` when generating `references/scene_{name}.png`. These reference images are the visual ground truth for `gm-evaluate`'s VQA cross-check, so every spatial and stylistic choice baked in here becomes an enforceable requirement downstream.

## CLI

```bash
python tools/asset_gen.py image \
  --model gemini --prompt "{prompt}" \
  --size 1K --aspect-ratio 16:9 -o references/scene_{name}.png
```

(Use the aspect ratio that matches `project.godot`'s viewport for that scene.)

## Prompt rules

The output must look like an **in-game screenshot, not concept art**. A clean screenshot showing every game object at correct scale and position is what drives the rest of the pipeline. A beautiful atmospheric scene wastes budget when later steps can't reproduce its effects.

- **Enumerate every game object.** Player character, each enemy type, obstacles, collectibles, projectiles, platforms, props — name each with position and approximate size relative to screen. Objects absent from the reference get forgotten downstream.
- **Reflect real technical constraints.** If you plan tiling backgrounds, prompt a tiling-friendly composition. If sprites are separate layers, show them as distinct objects against the background, not composited photorealism.
- **Don't prompt downgraded quality.** Avoid "lowpoly", "pixel art", "retro" unless the GDD explicitly requires it — these don't help and the generator produces worse output. Prompt clean, sharp rendering with the actual composition you need.
- **Focus on the most important moment of the scene.** The frame that best shows spatial layout, core mechanic, and the camera perspective the player will see most.
- **Exclude what you won't build.** Volumetric lighting, motion blur, depth of field, atmospheric fog, complex reflections, lens flares, detailed cast shadows — skip unless the game actually implements them. They create asset requirements nobody can fulfill.
- **Show HUD/UI elements.** Health bar, score counter, minimap, inventory slots — include every UI element described in `SCENES.md` for this scene with its screen position.

## Prompt template

```
Screenshot of a {2D/3D} video game. {Camera: angle, distance, perspective}.
Game objects: {player — appearance, position, size vs screen}. {enemies/NPCs — each type, position}. {obstacles}. {collectibles/pickups}. {projectiles if any}.
Environment: {background layers — sky, distant, mid}. {playfield surface — material, tiling}. {foreground elements}. {boundaries/edges}.
HUD: {each UI element — type and screen position}.
Visual style: {STYLE.md Style Anchor + Prompt Suffix}. Apply STYLE.md UI / Asset Rules. Avoid: {relevant STYLE.md Avoid entries}. Clean sharp digital rendering, game engine output.
```

## Inputs

For each scene, gather from the planning docs:
- **Asset bindings**: the scene's `Asset bindings` rows plus matching
  `ASSETS.md` Visual Asset Contract rows
- **Elements + Mood** → `SCENES.md` (the per-scene section)
- **Visual style** → `STYLE.md` Style Anchor, Prompt Suffix, UI / Asset Rules, Avoid, and `GDD.md` §4
- **Style anchors** → if the user supplied art in `assets/`, reference those files explicitly via the analyst's `assets/manifest.json` style summary

## Output

`references/scene_{name}.png` — the file `gm-evaluate` will VQA-compare against the running game's screenshot of the same scene.

If the user rejects a generated reference, regenerate with a tightened prompt. Reference images that ship into the tag become the contract for what the implementation must visually match.
