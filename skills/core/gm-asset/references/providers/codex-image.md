# Codex Image Provider

Read this file only when `.godotmaker/config.yaml` sets
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

## Active Codex Runtime

For each generation group:

1. Use one subagent per asset when Codex subagents are available.
2. Give each subagent exactly one asset input record.
3. Save the saved-path report under `.godotmaker/asset-generation/reports/`.
4. Run `tools/codex_image_claim.py --plan <batch_plan.json> --report <saved_paths.json> --project-root .`.
5. Verify each claimed source exists.
6. Finalize each claimed source into its project target path.
7. If isolated generation groups are unavailable, run the batch sequentially.
8. Write the sequential fallback reason in
   `.godotmaker/asset-generation/reports/<group_id>.summary.txt`.

## Claude Code To Codex

For each generation group:

1. Write one batch prompt file listing each asset id, prompt, and source target.
2. Run one `codex exec` call from the project root.
3. Ask Codex to spawn one subagent per asset, at most 3 concurrent.
4. Save the Codex saved-path report under `.godotmaker/asset-generation/reports/`.
5. Run `tools/codex_image_claim.py --plan <batch_plan.json> --report <saved_paths.json> --project-root .`.
6. Verify each claimed source exists.
7. Finalize each claimed source into its project target path.

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
- id: <asset_id_1>
  source_path: .godotmaker/asset-generation/sources/<asset_id_1>_source.png
  prompt: <prompt 1>
- id: <asset_id_2>
  source_path: .godotmaker/asset-generation/sources/<asset_id_2>_source.png
  prompt: <prompt 2>

If built-in image generation is unavailable, report the failure.
```

Run `codex exec` from the project root with JSON output enabled, the batch
prompt on stdin, and the final message written under
`.godotmaker/asset-generation/reports/`.

```bash
codex exec --json -C <project_root> \
  --output-last-message <summary_path> \
  - < <batch_prompt_path>
```

Use the configured provider only.
