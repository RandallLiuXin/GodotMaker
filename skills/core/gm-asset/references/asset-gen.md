# Asset Generation Reference

This file describes how `/gm-asset` generates 2D visual sources, claims
runtime-native image outputs, finalizes accepted files, and records handoff
metadata. Use `asset-planner.md` to decide which assets are required.

## Scope

Use this file for:

1. Choosing the provider path for an already-planned 2D visual asset.
2. Running API-backed image generation.
3. Claiming runtime-native image outputs.
4. Finalizing generated images.
5. Writing prompt/source/final metadata for the asset-generation manifest.
6. Applying family-specific prompt contracts.

Do not use this file to modify PLAN.md, GDD.md, STRUCTURE.md, SCENES.md, or
STYLE.md.

Read `asset-family-contract.md` before writing prompts.

## Provider Paths

Project default is controlled by `.godotmaker/config.yaml` `asset_image_model`.

### API-backed providers

API-backed providers are valid `tools/asset_gen.py image --model <selector>`
backends.

| Selector | Backend | Best for |
|----------|---------|----------|
| `gemini:<model>` or `gemini` | Gemini image generation | Prompt-following, references, characters, UI, backgrounds |
| `openai:<model>` or `openai` | OpenAI image generation/editing | OpenAI Images API projects |
| `grok:<model>` or `grok` | xAI Grok image generation | Textures, simple props, simple scenic backgrounds |

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

## Source Claim And Finalization

### Codex source claim protocol

For any Codex-generated image, claim the generated source before finalizing any
project asset:

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

### Generate image with asset_gen.py

Use API-backed providers only.

```bash
python3 tools/asset_gen.py image \
  --model <selector> \
  --prompt "the full prompt" \
  --size 1K \
  --aspect-ratio 1:1 \
  -o <target.png>
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

### Validate generation reports

Validate one or more reports with:

```bash
python3 tools/asset_image_report_check.py .godotmaker/asset-generation/reports/group_1.json
```

Each `assets[]` item in a generation report is the flat JSON printed by
`tools/asset_image_finalize.py`.

## Batch Contracts

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
mkdir -p .godotmaker/asset-generation/sources .godotmaker/asset-generation/prompts .godotmaker/asset-generation/reports
codex exec --json --dangerously-bypass-approvals-and-sandbox \
  -C "$PWD" --output-last-message .godotmaker/asset-generation/reports/codex_batch.summary.txt \
  - < .godotmaker/asset-generation/reports/codex_batch.prompt.txt
```

Do not silently switch providers when the configured provider is `codex`.

### Art asset batch

Use this input schema for non-scene visual assets:

```json
{
  "group_id": "assets_001",
  "kind": "art_asset",
  "provider": "<asset_image_model>",
  "items": [
    {
      "asset_id": "<asset_id>",
      "family": "<asset family>",
      "production_shape": "<production shape>",
      "prompt": "<prompt>",
      "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
      "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
      "final_path": "assets/img/<asset_id>.png",
      "resize": null
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/assets_001.json"
}
```

When the active runtime is Codex and `asset_image_model` is `native` or
`codex`:

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

Report shape:

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
    "family": "screen_reference",
    "production_shape": "reference_only",
    "prompt": "<prompt>",
    "prompt_path": ".godotmaker/asset-generation/prompts/scene_main.txt",
    "source_path": ".godotmaker/asset-generation/sources/scene_main_source.png",
    "final_path": "references/scene_main.png",
    "resize": null
  },
  "parallel_items": [
    {
      "asset_id": "scene_shop",
      "family": "screen_reference",
      "production_shape": "reference_only",
      "prompt": "<prompt>",
      "prompt_path": ".godotmaker/asset-generation/prompts/scene_shop.txt",
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

## Prompt Contracts

### Scene reference

Use scene references as visual targets for a scene. They are written under
`references/scene_{name}.png` and are not gameplay assets.

Prompt shape:

```text
Screenshot of a {2D game}. {camera/viewpoint}. Game objects: {visible objects with position and approximate size}. Environment: {layers and playfield}. HUD: {visible UI elements}. Visual style: {STYLE.md Style Anchor + Prompt Suffix}. No text labels unless the scene explicitly needs UI text.
```

Read `visual-target.md` before writing the prompt.

### Style reference

Use style references as source images for later derivatives.

Prompt shape:

```text
{game genre and viewpoint}. Cohesive visual target sheet showing color palette, material language, shape language, UI treatment, and representative gameplay props. No text labels.
```

Record the source as `style_reference` with `production_shape:
reference_only`.

### Character canonical

Use a canonical character image before generating action sheets or variants.

Prompt shape:

```text
{character name}, {role and visual identity}. Neutral readable pose, clean silhouette, full body visible, centered on a solid {bg_color} background. {STYLE.md prompt suffix}. No text, no UI, no cropped body parts.
```

Record the source as `character_canonical` with `production_shape:
single_image`.

### Character action source

Use one source per action.

Prompt shape:

```text
{character name} performing {action}. {rows}x{cols} sprite sheet, exactly {frame_count} frames, one action only, same character identity in every frame, consistent scale, centered in each cell, solid {bg_color} background. {STYLE.md prompt suffix}. No text, no UI, no borders.
```

Record the source as `character_action_source` with `production_shape:
action_sheet`. Mark `processing_status` as `needs_curation` until final frames
or final sprite sheets exist.

### Projectile or impact effect source

Use separate sources for projectiles, impacts, pickup effects, explosions, and
spawn effects.

Prompt shape:

```text
{effect name}, {effect behavior}. {rows}x{cols} effect sprite sheet, exactly {frame_count} frames, transparent-friendly solid {bg_color} background, centered in each cell, consistent scale, no text, no UI.
```

Use `projectile_fx_source` or `impact_fx_source` and mark the source
`needs_curation` until final frames exist.

### Compact prop pack

Use compact prop packs for compact similarly sized props.

Prompt shape:

```text
{prop names}. {rows}x{cols} grid, one centered prop per cell, consistent scale, solid {bg_color} background, no text, no UI, no borders. {STYLE.md prompt suffix}.
```

Record rows, columns, expected item names, and final target paths in the
manifest. Mark the source `needs_curation` until extracted prop files exist.

### UI component sheet

Use UI component sheets for icons, small buttons, tabs, badges, counters, and
compact HUD pieces.

Prompt shape:

```text
{component names}. Clean game UI component sheet, {rows}x{cols} grid, one isolated component per cell, consistent lighting and material style, solid {bg_color} background, no text or numbers, no composite screens. {STYLE.md UI rules}.
```

Use `ui_component_sheet` or `icon_pack`. Mark the source `needs_curation` until
each final component path exists.

### Panel source

Use panel sources for large panels, card frames, dialogue boxes, shop slots,
and menu containers.

Prompt shape:

```text
{panel name}, isolated game UI panel, empty content area, clean edges, no text, no numbers, no icons unless requested, solid {bg_color} background. {STYLE.md UI rules}.
```

Use `panel_source`. Do not force large panels into compact grid sheets.

### Background

Use backgrounds for runtime backgrounds and parallax layers.

Prompt shape:

```text
{description in the art style}. {composition instructions}. Intended game display: {viewport or parallax behavior}. No gameplay actors, pickups, hazards, UI, or text.
```

### Runtime sprite

Use runtime sprites only when a single final image is enough.

Prompt shape:

```text
{name}, {description}. Centered on a solid {bg_color} background. Clean silhouette. {STYLE.md prompt suffix}. No text, no UI.
```

### Texture

Use textures for repeated terrain, floors, walls, UI materials, and tileable
surfaces.

Prompt shape:

```text
{name}, {description}. Uniform lighting, seamless tileable texture, clean edges, no text, no labels.
```

## Post-processing

### Remove background

Read `rembg.md` for the full guide.

Use solid background colors, no cast shadows, no ground shadows, and clean
silhouettes for sprites that need transparency.

Write background-removal outputs under `.godotmaker/asset-generation/work/`.
Finalize approved outputs into project asset paths with
`tools/asset_image_finalize.py`.

### Manifest update

After generation and finalization, update
`.godotmaker/asset-generation/manifest.json` with the fields from
`asset-family-contract.md`. Keep source-only and needs-curation assets in the
manifest even when no final runtime asset exists yet.

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

1. `1K`: default for references, characters, sprites, UI sources, textures,
   and props.
2. `512`: quick tests where supported.
3. `2K`: backgrounds, title screens, high-detail objects, and large textures.
4. `4K`: large maps and panoramic backgrounds where supported.

### Small sprites

Minimum generation resolution is usually much larger than in-game sprite size.
If a sprite will render small in-game:

1. Prefer 128 px or larger display sizes where possible.
2. Generate a source sheet so each object has enough pixels before selection.
3. Prompt for bold simple forms, thick outlines, flat colors, and exaggerated
   proportions.

### Direction and orientation

Generators cannot reliably distinguish left/right facing or exact rotations.
Generate one direction and flip in-engine when appropriate.
