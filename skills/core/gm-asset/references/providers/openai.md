# OpenAI Image Provider

Use this file when `.godotmaker/config.yaml` sets `asset_image_model` to
`openai` or `openai:<model>`.

## Source Generation

Write one spec per generated source under
`.godotmaker/asset-generation/specs/`:

```json
{
  "asset_id": "<asset_id>",
  "model": "<openai selector>",
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

1. `OPENAI_API_KEY` is set.
2. The Python `openai` package is installed.
3. `size` is `1K`.
4. Use at most 16 reference images.

## Reference Images

Put every required local reference in `reference_inputs` as
`{"role":"canonical|style|screen","path":"<local path>"}`. Use only images
listed by the production-unit brief or selected by the manager. The generator
records each role and path in its provider report.

When `reference_inputs` is non-empty, the source generator uses the OpenAI image
edit endpoint and sends every listed reference image. One reference is sent as a
single image file; multiple references are sent as an image-file list.

## Handoff

After generation:

1. Verify the planned source path exists.
2. Run the production-unit processing or finalization steps.
3. Keep the source-generation report path in the unit report.
