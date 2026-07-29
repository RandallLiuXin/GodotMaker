# Gemini Image Provider

Use this file when `.godotmaker/config.yaml` sets `asset_image_model` to
`gemini` or `gemini:<model>`.

## Source Generation

Write one spec per generated source under
`.godotmaker/asset-generation/specs/`:

```json
{
  "asset_id": "<asset_id>",
  "model": "<gemini selector>",
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

## Reference Images

Put every required local reference in `reference_inputs` as
`{"role":"canonical|style|screen","path":"<local path>"}`. Use only images
listed by the production-unit brief or selected by the manager. The generator
sends every listed image as provider input and records each role and path in its
provider report.

## Handoff

After generation:

1. Verify the planned source path exists.
2. Run the production-unit processing or finalization steps.
3. Keep the source-generation report path in the unit report.
