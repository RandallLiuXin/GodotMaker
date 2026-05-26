# Asset Generation Reference

This file describes how `/gm-asset` generates, claims, finalizes, and prepares
image/model assets. It does not decide which assets are required for the
current tag; use `asset-planner.md` for that.

## Scope

Use this file for:

1. Choosing the provider path for an already-planned asset.
2. Running API-backed generation tools.
3. Claiming runtime-native image outputs.
4. Finalizing generated images before updating ASSETS.md.
5. Applying asset-type prompt and post-processing recipes.

Do not use this file to modify PLAN.md, GDD.md, STRUCTURE.md, SCENES.md, or
STYLE.md.

## Provider Paths

Project default is controlled by `.godotmaker/config.yaml` `asset_image_model`.

### API-backed providers

API-backed providers are valid `tools/asset_gen.py image --model <selector>`
backends.

| Selector | Backend | Best for |
|----------|---------|----------|
| `gemini:<model>` or `gemini` | Gemini image generation | Precise prompt following: references, characters, backgrounds, 3D refs |
| `openai:<model>` or `openai` | OpenAI image generation/editing | OpenAI Images API projects |
| `grok:<model>` or `grok` | xAI Grok image generation | Textures, simple objects, item kits, simple scenic backgrounds |

Use API-backed providers only when the required API key is configured. Missing
API keys are hard failures.

### Runtime-native providers

Runtime-native providers are not valid `tools/asset_gen.py` backends.

1. `native`: use the active coding-agent runtime's native image-generation
   provider/tool.
2. `codex`: use Codex image generation explicitly. In Claude Code, call Codex
   through `codex exec`. In active Codex, use the active runtime image
   generation path.

Every runtime-native image must be finalized with
`tools/asset_image_finalize.py` before ASSETS.md is updated.

### Codex source claim protocol

For any Codex-generated image, claim the generated source before any project
asset is finalized:

1. Generate the image with `image_gen`.
2. Read that call's `ImageGenerationEnd.saved_path`.
3. Claim the source image:
   ```bash
   python tools/codex_image_claim.py --source "<saved_path>" \
     --out <source_path> \
     --asset-id <asset_id>
   ```
4. Report the JSON printed by `tools/codex_image_claim.py`.
5. If the claim command exits nonzero, report its JSON error for that asset.

Use the `saved_path` from the current `image_gen` call only.

### Finalize claimed or runtime-native source

After a source image has been claimed or returned by a runtime-native provider,
finalize it into the project target path:

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out <target.png> --label <asset_id> [--resize WIDTHxHEIGHT]
```

Put the finalize JSON in the generation group report.

### Claude Code to Codex handoff

When `asset_image_model: codex` is selected in a Claude Code project, use one
non-interactive Codex batch for the current generation group.

1. Write one batch prompt file listing each asset id, prompt, and exact source
   target path.
2. Run one `codex exec` call from the project root.
3. Ask Codex to spawn one subagent per asset, at most 3 concurrent.
4. Require each subagent to follow the Codex source claim protocol.
5. After `codex exec` returns, verify each claimed source exists.
6. Finalize each claimed source into its project target path.

Batch prompt shape:

```text
Use the $imagegen skill and built-in image_gen tool to generate these assets.
Spawn one subagent per asset and run them in parallel, at most 3 at a time.
Wait for all subagents to finish.

For each asset:
1. Follow the Codex source claim protocol.
2. Report the asset id and the claim JSON.

Assets:
- id: <asset_id_1>
  target: .godotmaker/asset-generation/sources/<asset_id_1>_source.png
  prompt: <prompt 1>
- id: <asset_id_2>
  target: .godotmaker/asset-generation/sources/<asset_id_2>_source.png
  prompt: <prompt 2>

If built-in image generation is unavailable, do not create that image file.
Report the failure clearly.
```

Command shape:

```bash
mkdir -p .godotmaker/asset-generation/sources .godotmaker/asset-generation/reports
codex exec --json --dangerously-bypass-approvals-and-sandbox \
  -C "$PWD" --output-last-message .godotmaker/asset-generation/reports/codex_batch.summary.txt \
  - < .godotmaker/asset-generation/reports/codex_batch.prompt.txt
```

Do not silently switch providers when the configured provider is `codex`.

### Active Codex runtime batch

When the active runtime is Codex and `asset_image_model` is `native` or
`codex`, generate up to 3 assets in one batch.

Batch input schema:

```json
{
  "group_id": "assets_001",
  "kind": "art_asset",
  "provider": "<asset_image_model>",
  "items": [
    {
      "asset_id": "<asset_id>",
      "prompt": "<prompt>",
      "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
      "final_path": "assets/img/<asset_id>.png",
      "resize": null
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/assets_001.json"
}
```

1. Use one subagent per asset when Codex subagents are available.
2. Give each subagent exactly one asset's input record.
3. Each subagent generates only its assigned asset and follows the Codex source
   claim protocol.
4. Do not scan global generated-image directories.
5. If isolated generation groups are unavailable, run the batch sequentially.
6. Write the sequential fallback reason in
   `.godotmaker/asset-generation/reports/<group_id>.summary.txt`.
7. Finalize each claimed source into its project target path.
8. Write one flat finalize JSON entry per asset.

Each report uses this shape:

```json
{
  "ok": true,
  "provider": "<asset_image_model>",
  "sequential_fallback_reason": "<reason or null>",
  "assets": [
    {
      "ok": true,
      "source": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
      "path": "<final_path>",
      "asset_id": "<asset_id>",
      "bytes": 12345,
      "width": 64,
      "height": 64,
      "format": "PNG"
    }
  ]
}
```

Each `assets[]` item is the flat JSON printed by
`tools/asset_image_finalize.py`.

### Scene reference batch

Scene references use the same provider paths, claim/finalize steps, and report
entry shape as art assets.

Input schema:

```json
{
  "group_id": "scene_refs_001",
  "kind": "scene_reference",
  "provider": "<asset_image_model>",
  "anchor_item": {
    "asset_id": "scene_main",
    "prompt": "<prompt>",
    "source_path": ".godotmaker/asset-generation/sources/scene_main_source.png",
    "final_path": "references/scene_main.png",
    "resize": null
  },
  "parallel_items": [
    {
      "asset_id": "scene_shop",
      "prompt": "<prompt>",
      "source_path": ".godotmaker/asset-generation/sources/scene_shop_source.png",
      "final_path": "references/scene_shop.png",
      "resize": null
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/scene_refs_001.json"
}
```

If `anchor_item` is present, generate and finalize it first. Then generate
`parallel_items` in batches of up to 3. If no scene needs to anchor style, set
`anchor_item` to `null` and put all missing scene references in
`parallel_items`.

## Tool Reference

Run tools from the project root.

### Generate image with asset_gen.py

Use API-backed providers only.

```bash
python3 tools/asset_gen.py image \
  --model <selector> \
  --prompt "the full prompt" \
  --size 1K \
  --aspect-ratio 1:1 \
  -o assets/img/<asset_name>.png
```

Common options:

1. `--model`: `gemini`, `openai`, `grok`, or provider-prefixed selectors.
2. `--size`: `1K` by default. Gemini also supports `512`, `2K`, and `4K`.
3. `--aspect-ratio`: provider-specific; default is `1:1`.
4. `--image`: reference image input for image-to-image generation/editing.
5. `--resize WIDTHxHEIGHT`: optional resize after generation.
6. `--label`: optional asset id in the JSON result.

`asset_gen.py image` finalizes and validates the output path before returning
JSON.

### Finalize runtime-native images

After runtime-native image generation returns or claims a source image path,
run:

```bash
python3 tools/asset_image_finalize.py \
  --source <generated_image_path> \
  --out assets/img/<asset_name>.png \
  --label <asset_id> \
  [--resize WIDTHxHEIGHT]
```

Use `--resize` only when the target asset requires a fixed size.

### Validate generation reports

Runtime-native generation groups write
`.godotmaker/asset-generation/<group_id>.json`:

```json
{
  "ok": true,
  "provider": "native",
  "assets": [
    {
      "ok": true,
      "source": "<generated_image_path>",
      "path": "assets/img/coin.png",
      "asset_id": "coin",
      "bytes": 12345,
      "width": 64,
      "height": 64,
      "format": "PNG"
    }
  ]
}
```

Validate one or more reports with:

```bash
python3 tools/asset_image_report_check.py .godotmaker/asset-generation/group_1.json
```

### Generate GLB model

```bash
python3 tools/asset_gen.py glb \
  --image assets/img/car.png \
  -o assets/glb/car.glb
```

Use a clean 3D model reference image. Do not remove the solid background before
GLB conversion.

### Generate video

```bash
python3 tools/asset_gen.py video \
  --prompt "walking to the right, smooth walk cycle, solid dark-green background" \
  --image assets/img/knight_walk_pose.png \
  --duration 2 \
  -o assets/video/knight_walk.mp4
```

Use the pose frame, not the character reference, as the starting image.

### Output and logging

Successful image results include:

```json
{
  "ok": true,
  "provider": "xai",
  "path": "assets/img/coin.png",
  "source": "assets/img/coin.png",
  "asset_id": "coin",
  "bytes": 12345,
  "width": 64,
  "height": 64,
  "format": "PNG"
}
```

On failure:

```json
{"ok": false, "error": "..."}
```

Progress and API client output goes to stderr. Redirect stderr to a temp file
and read it only on failure:

```bash
_log=$(mktemp)
result=$(python3 tools/asset_gen.py image --prompt "..." -o path.png 2>"$_log") || tail -20 "$_log"
```

## Asset Recipes

### Scene reference

Use scene references as visual targets for a scene. They are written under
`references/scene_{name}.png` by `/gm-asset` Step 3 and are not gameplay
assets.

Prompt shape:

```text
{description in the art style}. {composition instructions}.
```

Read `visual-target.md` before writing the prompt. Include the scene's player
experience, visible objects, UI, composition, and style language.

### Background

Use backgrounds for title screens, sky panoramas, parallax layers, arenas, and
large scenic images that the game will display.

Prompt shape:

```text
{description in the art style}. {composition instructions}. Intended game display: {viewport or parallax behavior}.
```

Use a precise provider when layout and object placement matter. Use a simpler
provider only for scenic output where exact prompt adherence is not critical.

### Texture

Use for tileable ground, walls, floors, UI panels, and repeated materials.

Prompt shape:

```text
{name}, {description}. Top-down view, uniform lighting, no shadows, seamless tileable texture, suitable for game engine tiling, clean edges.
```

The whole image is the texture. Do not remove the background.

### Single object or sprite

Use for props, items, icons, characters, enemies, and NPCs.

Prompt shape:

```text
{name}, {description}. Centered on a solid {bg_color} background.
```

Use a precise provider for characters or objects that must match the design.
Use a cheaper/simple provider only when exact appearance is flexible.

### Variant from reference

When `--image` is available, feed the existing reference image and prompt only
for the requested change.

Prompt shape:

```text
{what to change: different angle, pose, color, damage state, size variant}
```

Do not re-describe the entire character or object unless the requested change
requires it.

### Item kit

Use one source image for several small objects when they share a style.

Prompt shape:

```text
{item1}, {item2}, {item3}, {item4}. 2x2 grid layout, each item centered in its cell, solid {bg_color} background. {art style}.
```

Slice into individual PNGs:

```bash
python3 tools/grid_slice.py path_grid.png \
  -o .godotmaker/asset-generation/work/items/ --grid 2x2 --names "sword,shield,potion,helm"
```

Then finalize each sliced output into its project target path with
`tools/asset_image_finalize.py`. Remove background from each item first if
transparency is required.

### 3D model reference

Prompt shape:

```text
3D model reference of {name}. {description}. 3/4 front elevated camera angle, solid white background, soft diffused studio lighting, matte material finish, single centered subject, no shadows on background. Any windows or glass should be solid tinted and opaque.
```

Then run `asset_gen.py glb` with the approved reference image.

### Animated sprite

Use one reference image per character and reuse it for all animations.

1. Generate a neutral reference image.
2. Generate pose frames from the reference.
3. Generate videos from pose frames.
4. Extract frames.
5. Trim loops for looping animations.
6. Remove backgrounds in batch.
7. Add additional animations from the same reference.

Reference prompt shape:

```text
{name}, {description}. Neutral standing pose, facing right, centered on a solid {bg_color} background. Clean silhouette.
```

Pose prompt shape:

```text
{action pose description}, side view, solid {bg_color} background.
```

Video prompt shape:

```text
{action}, smooth animation. Solid {bg_color} background.
```

## Post-processing

### Remove background

Read `rembg.md` for the full guide.

Use solid background colors, no cast shadows, no ground shadows, and clean
silhouettes for sprites that need transparency.

Write background-removal outputs under `.godotmaker/asset-generation/work/`.
Finalize approved outputs into project asset paths with
`tools/asset_image_finalize.py`.

### Extract frames

```bash
mkdir -p .godotmaker/asset-generation/work/knight_walk_frames
ffmpeg -i assets/video/knight_walk.mp4 -vsync 0 .godotmaker/asset-generation/work/knight_walk_frames/%04d.png
```

### Trim loops

```bash
python3 tools/find_loop_frame.py .godotmaker/asset-generation/work/knight_walk_frames/
```

`window: 0` means no good loop point. Use the whole clip.

### Resize and flip

Use ImageMagick:

```bash
magick identify input.png
magick input.png -resize 720x720 -filter Lanczos .godotmaker/asset-generation/work/output_resized.png
magick input.png -flop .godotmaker/asset-generation/work/output_flipped.png
```

Finalize approved outputs into project asset paths with
`tools/asset_image_finalize.py`.

## Quality Notes

### Image resolution

Use the full generation resolution. Do not downscale for aesthetic reasons.

1. `1K`: default for textures, sprites, 3D references, and character refs.
2. `512`: quick tests where supported.
3. `2K`: backgrounds, title screens, high-detail objects, and large textures.
4. `4K`: large maps and panoramic backgrounds where supported.

### Small sprites

Minimum generation resolution is usually much larger than in-game sprite size.
If a sprite will render small in-game:

1. Prefer 128 px or larger display sizes where possible.
2. Generate a kit image so each object has enough pixels before slicing.
3. Prompt for bold simple forms, thick outlines, flat colors, and exaggerated
   proportions.

### Direction and orientation

Generators cannot reliably distinguish left/right facing or exact rotations.
Generate one direction and flip in-engine when appropriate.

### Video size consistency

When mixing still images and video-extracted frames, resize everything to the
smallest source size before background removal.

### Animation playback

Video-extracted animations often assume a source frame rate such as 24 fps. Set
frame duration consistently and do not reset the animation frame counter between
movement tiles.
