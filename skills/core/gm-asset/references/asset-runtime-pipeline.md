# Asset Runtime Pipeline Reference

This file describes how `/gm-asset` turns a planned visual asset into fixed
source, final, diagnostic, and manifest paths. Use `asset-planner.md` for planning
and `asset-prompt-contracts.md` for prompt shapes.

## Provider Paths

Project default is controlled by `.godotmaker/config.yaml` `asset_image_model`.

### API-backed providers

API-backed providers are valid `tools/asset_source_generate.py --spec
<spec.json>` backends.

| Selector | Backend |
|----------|---------|
| `gemini:<model>` or `gemini` | Gemini image generation |
| `openai:<model>` or `openai` | OpenAI image generation/editing |
| `grok:<model>` or `grok` | xAI Grok image generation |

Use API-backed providers only when the required API key is configured. Missing
API keys are hard failures.

### Runtime-native providers

Runtime-native providers are not valid `tools/asset_source_generate.py`
backends.

1. `native`: use the active coding-agent runtime's native image-generation
   provider/tool.
2. `codex`: read `references/providers/codex-image.md`.

## API Source Generation

Write one spec per generated source under
`.godotmaker/asset-generation/specs/`:

```json
{
  "asset_id": "<asset_id>",
  "model": "<gemini|openai|grok selector>",
  "prompt": "<full prompt>",
  "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
  "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
  "size": "1K",
  "aspect_ratio": "1:1",
  "reference_images": [],
  "report_path": ".godotmaker/asset-generation/reports/<asset_id>_source.json"
}
```

Run:

```bash
python tools/asset_source_generate.py --spec <spec.json>
```

## Layout Guides

Create layout guides before fixed-grid image generation.

```bash
python tools/asset_layout_guide.py \
  --out <guide.png> \
  --rows <rows> \
  --cols <cols> \
  --labels <labels>
```

Store guides under `.godotmaker/asset-generation/guides/`.

Use guides for:

1. UI component sheets.
2. Icon packs.
3. Compact prop packs.
4. Character or FX action sheets.

Make the guide visible to the selected image-generation runtime before calling
the provider. Treat the guide as layout control only.

## Finalization

Finalize accepted source images with `tools/asset_image_finalize.py`. Provide
the source path, final path, asset label, and optional resize.

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out <final_path> \
  --label <asset_id>
```

For scene references, backgrounds, parallax plates, and fixed-viewport sources,
validate the source aspect before resize:

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out <final_path> \
  --label <asset_id> \
  --require-aspect <WIDTH:HEIGHT> \
  --resize <WIDTHxHEIGHT>
```

If aspect validation fails, do not use the finalized output. Regenerate the
source or leave the asset incomplete.

If the source is a sheet, atlas, UI kit, action sheet, or irregular reference,
send it through `asset-curation.md` before marking runtime asset rows
`generated`.

## Manifest Handoff

Upsert manifest entries with `tools/asset_generation_manifest_update.py`.
Validate the handoff manifest with `tools/asset_generation_manifest_check.py
--check-files`.

```bash
python tools/asset_generation_manifest_update.py --entry-file <entry.json>
python tools/asset_generation_manifest_check.py --check-files
```

Use `--check-files` after source generation, finalization, and curation
selection.

## Art Asset Batch

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
      "target_size": "<WIDTHxHEIGHT or null>",
      "target_aspect": "<WIDTH:HEIGHT or null>",
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

Run each group through the selected provider path. Finalize each accepted
source into its project target path and write one flat finalize JSON entry per
asset.

Diagnostic report shape:

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

## Scene Reference Batch

Scene references use the same provider paths, claim/finalize steps, and
diagnostic entry shape as art assets.

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
    "target_size": "1280x720",
    "target_aspect": "16:9",
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
      "target_size": "1280x720",
      "target_aspect": "16:9",
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
