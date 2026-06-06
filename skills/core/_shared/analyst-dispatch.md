# Analyst Dispatch Protocol

When the user provides art/audio assets, dispatch an analyst to process them.
The dispatching role MUST NOT read image files in `assets/` directly — always delegate to the analyst.

**Agent definition:** `.claude/agents/analyst.md` — system prompt loaded automatically via `subagent_type: "analyst"`.

## Agent Call

```
Agent({
  subagent_type: "analyst",
  description: "Analyst: process user assets",
  model: "{analyst_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{analyst brief below}"
})
```

## Analyst Brief Template

```
## Analyze: User-provided assets                          [REQUIRED]

### Project Path                                           [REQUIRED]
{Absolute path to the Godot project}

### Assets Directory                                       [REQUIRED]
{Path to assets/ directory}

### GDD Art Direction                                      [REQUIRED]
{Copy GDD §4 art style description here}

### Task                                                   [REQUIRED]
1. List all files in the assets directory (recursively)
2. For each image file (.png, .jpg, .svg, .webp):
   - Identify: type (sprite, tileset, background, ui, icon), role, dimensions
   - If sprite sheet: detect frame count and frame size
   - Assess style characteristics: color palette, line weight, proportions, mood
3. For each audio file (.ogg, .wav, .mp3):
   - Identify: type (bgm, sfx), role, duration
4. Generate `assets/manifest.json` following the schema below
5. Summarize the overall art style in 2-3 sentences (for use as AI generation reference)

### Output Schema: manifest.json                           [REQUIRED]
{See schema below}

### Report Format                                          [REQUIRED]
## Analyst Report:
### Status: DONE | PARTIAL | FAILED
### Asset Summary
- Total files: {count}
- Sprites: {count}, Tilesets: {count}, Backgrounds: {count}, UI: {count}, Audio: {count}
### Art Style Summary
{2-3 sentences describing the visual style}
### Files Generated
- `assets/manifest.json`
```

## manifest.json Schema

```json
{
  "version": 1,
  "art_style": {
    "summary": "Pixel art with warm palette, 1-2px outlines, 16x16 base grid",
    "palette": ["#hex1", "#hex2", "..."],
    "line_weight": "1-2px",
    "proportions": "chibi / realistic / stylized",
    "mood": "bright and cheerful"
  },
  "assets": [
    {
      "file": "sprites/player.png",
      "type": "sprite",
      "role": "Player character idle sprite",
      "dimensions": "64x64",
      "frames": 1,
      "notes": ""
    },
    {
      "file": "sprites/player_run.png",
      "type": "sprite_sheet",
      "role": "Player run animation",
      "dimensions": "256x64",
      "frames": 4,
      "frame_size": "64x64",
      "notes": "4-frame run cycle"
    },
    {
      "file": "audio/bgm_gameplay.ogg",
      "type": "audio_bgm",
      "role": "Gameplay background music",
      "duration": "2:30",
      "notes": "Loops"
    }
  ]
}
```

## Dispatch Rules

1. **One analyst per asset batch.** If user provides assets in multiple rounds, dispatch a new analyst each time (or re-dispatch to update manifest).
2. **Analyst is read-only on game code.** Analyst may only write to `assets/manifest.json`. It must not modify any .gd/.tscn/.tres files.
3. **Use the Agent Call template above.** Read `analyst_model` from `.godotmaker/config.yaml` (default: `sonnet`).
4. **Style summary feeds `/gm-asset`.** Copy the art_style.summary from manifest.json into the asset generation prompts when creating source-generation specs.
