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
2. `codex`: use Codex image generation explicitly. In Claude Code, call Codex
   through `codex exec`. In active Codex, use the active runtime image
   generation path.

## Source Claim

For any Codex-generated image:

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
python tools/asset_source_generate.py \
  --spec .godotmaker/asset-generation/specs/<asset_id>.json
```

## Finalization

Finalize accepted source images into project target paths:

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out <final_path> \
  --label <asset_id> \
  [--resize WIDTHxHEIGHT]
```

If the source is a sheet, atlas, UI kit, action sheet, or irregular reference,
send it through `asset-curation.md` before marking runtime asset rows
`generated`.

## Manifest Handoff

Upsert manifest entries with:

```bash
python tools/asset_generation_manifest_update.py \
  --entry-file .godotmaker/asset-generation/work/manifest-entries/<asset_id>.json
```

Validate the handoff manifest with:

```bash
python tools/asset_generation_manifest_check.py --check-files
```

Use `--check-files` after source generation, finalization, and curation
selection.

## Claude Code To Codex Handoff

When `asset_image_model: codex` is selected in a Claude Code project, use one
non-interactive Codex batch for the current generation group.

1. Write one batch prompt file listing each asset id, prompt, and exact source
   target path.
2. Run one `codex exec` call from the project root.
3. Ask Codex to spawn one subagent per asset, at most 3 concurrent.
4. Require each subagent to follow the Source Claim section.
5. After `codex exec` returns, verify each claimed source exists.
6. Finalize each claimed source into its project target path.

Batch prompt shape:

```text
Use the $imagegen skill and built-in image_gen tool to generate these assets.
Spawn one subagent per asset and run them in parallel, at most 3 at a time.
Wait for all subagents to finish.

For each asset:
1. Follow the Source Claim section.
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
3. Each subagent generates only its assigned asset and follows the Source Claim
   section.
4. Each subagent claims its own generated `saved_path` into the assigned
   `source_path`.
5. If isolated generation groups are unavailable, run the batch sequentially.
6. Write the sequential fallback reason in
   `.godotmaker/asset-generation/reports/<group_id>.summary.txt`.
7. Finalize each claimed source into its project target path.
8. Write one flat finalize JSON entry per asset.

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
