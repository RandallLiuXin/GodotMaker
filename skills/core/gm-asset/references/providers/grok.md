# Grok Image Provider

Use this file when `.godotmaker/config.yaml` sets `asset_image_model` to
`grok` or `grok:<model>`. The bare selector uses `grok-imagine-image`.

## Source Generation

Write one spec per generated source under
`.godotmaker/asset-generation/specs/`:

```json
{
  "asset_id": "<asset_id>",
  "model": "<grok selector>",
  "prompt": "<full prompt>",
  "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
  "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
  "size": "1K",
  "aspect_ratio": "1:1",
  "reference_inputs": [],
  "report_path": ".godotmaker/asset-generation/reports/<asset_id>_source.json"
}
```

Run:

```bash
python tools/asset_source_generate.py --spec <spec.json>
```

## Requirements

1. `XAI_API_KEY` is set.
2. The Python `xai-sdk` package is installed.
3. `size` is `1K` or `2K`.
4. Use at most one reference image. If a production unit requires more than
   one reference, stop before generation instead of dropping inputs or
   changing providers.

## Reference Images

Put the required local reference, when present, in `reference_inputs` as
`{ "role": "canonical|style", "path": "<local image path>" }`. Use
only an image listed by the production-unit brief or selected by the manager.
The tool validates that the input is readable, sends its actual bytes to Grok,
and records role/path/hash provenance in its report.

## Handoff

After generation:

1. Verify the planned source path exists.
2. Run the production-unit processing or finalization steps.
3. Keep the source-generation report path in the unit report.
