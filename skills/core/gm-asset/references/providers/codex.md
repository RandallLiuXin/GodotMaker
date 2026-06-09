# Codex Image Provider

Use this file only when `.godotmaker/config.yaml` sets
`asset_image_model: codex`.

## Saved-Path Contract

For each generated image:

1. Call `image_gen` once for the assigned asset.
2. Read that call's `ImageGenerationEnd.saved_path`.
3. Report `asset_id` and `saved_path`.
4. Do not inspect `generated_images`.
5. Do not choose files by modified time.
6. Do not copy image files from a Codex subagent.

Saved-path report shape:

```json
{
  "ok": true,
  "assets": [
    {
      "asset_id": "<asset_id>",
      "saved_path": "<ImageGenerationEnd.saved_path>"
    }
  ],
  "failures": []
}
```

## Claim Step

After saved paths are reported, run:

```bash
python tools/codex_image_claim.py --plan <batch_plan.json> --report <saved_paths.json> --project-root .
```

Then verify each planned source path exists.

## Active Codex Runtime

For each generation group:

1. Use one subagent per asset when isolated subagents are available.
2. Give each subagent exactly one asset input record.
3. Save the saved-path report under `.godotmaker/asset-generation/reports/`.
4. Claim the saved paths into planned source paths.
5. Finalize or process the planned source paths according to the production
   unit.
6. If isolated generation is unavailable, run sequentially.
7. Write the sequential fallback reason in the unit report.

## Claude Code To Codex

For each generation group:

1. Write one batch prompt file listing each asset id, prompt, and source target.
2. Run one `codex exec` call from the project root.
3. Ask Codex to spawn one subagent per asset, at most 3 concurrent.
4. Save the Codex saved-path report under `.godotmaker/asset-generation/reports/`.
5. Claim the saved paths into planned source paths.

Batch prompt shape:

```text
Use the $imagegen skill and built-in image_gen tool to generate these assets.
Spawn one subagent per asset and run them in parallel, at most 3 at a time.
Wait for all subagents to finish.

For each asset:
1. Call image_gen once for this asset.
2. Read the returned ImageGenerationEnd.saved_path.
3. Report asset_id and saved_path.
4. Do not inspect generated_images.
5. Do not copy files.

Assets:
- id: <asset_id>
  source_path: .godotmaker/asset-generation/sources/<asset_id>_source.png
  prompt: <prompt>

If built-in image generation is unavailable, report the failure.
```

Run:

```bash
codex exec --json -C <project_root> --output-last-message <summary_path> - < <batch_prompt_path>
```
