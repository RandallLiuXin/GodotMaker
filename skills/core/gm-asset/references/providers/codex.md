# Codex Image Provider

Use this file only when `.godotmaker/config.yaml` sets
`asset_image_model: codex`.

## Generated-Path Contract

For each generated image:

1. Call `image_gen` once per attempt for the assigned asset.
2. Identify the generated image path from the current Codex turn. If the
   turn output does not expose a path, compare the current `CODEX_THREAD_ID`
   image directory before and after this one call. Report failure if
   `CODEX_THREAD_ID` is missing or the directory delta is not exactly one new
   image file.
3. Retry transient tool or provider failures at most 2 times.
4. Report `asset_id` and `generated_path`.
5. Do not inspect unrelated Codex threads.
6. Do not choose files by modified time.
7. Do not copy image files from a Codex subagent.
8. Do not report a project `source_path` as `generated_path`.
9. Do not create placeholder or procedural images when generation fails.

Generated-path report shape:

```json
{
  "ok": true,
  "assets": [
    {
      "asset_id": "<asset_id>",
      "generated_path": "<generated image path>"
    }
  ],
  "failures": []
}
```

Failure report shape:

```json
{
  "ok": false,
  "assets": [],
  "failures": [
    {
      "asset_id": "<asset_id>",
      "error": "<provider or tool failure>"
    }
  ]
}
```

## Claim Step

After generated paths are reported, run:

```bash
python tools/codex_image_claim.py --plan <batch_plan.json> --report <generated_paths.json> --project-root . --out-report <claim_result.json>
```

Use the claim result as the provider success record.

## Active Codex Runtime

For each generation group:

1. Use one subagent per asset when isolated subagents are available.
2. Give each subagent exactly one asset input record.
3. Save the generated-path report under `.godotmaker/asset-generation/reports/`.
4. Stop affected assets when the report is failed or incomplete.
5. Claim the generated paths into planned source paths.
6. Finalize or process the planned source paths according to the production
   unit.
7. If isolated generation is unavailable, run sequentially.
8. Write the sequential fallback reason in the unit report.

## Claude Code To Codex

For each generation group:

1. Write one batch prompt file listing each asset id, prompt, and source target.
2. Run one `codex exec` call from the project root.
3. Ask Codex to spawn one subagent per asset, at most 3 concurrent.
4. Save the Codex generated-path report under `.godotmaker/asset-generation/reports/`.
5. Stop affected assets when the report is failed or incomplete.
6. Claim the generated paths into planned source paths.
7. Save the claim result under `.godotmaker/asset-generation/reports/`.

Batch prompt shape:

```text
Use the $imagegen skill and built-in image_gen tool to generate these assets.
Spawn one subagent per asset and run them in parallel, at most 3 at a time.
Wait for all subagents to finish.

For each asset:
1. Call image_gen once per attempt for this asset.
2. Identify the generated image path from this Codex turn. If the turn output
   does not expose a path, compare this `CODEX_THREAD_ID` image directory
   before and after this one call. Report failure if `CODEX_THREAD_ID` is
   missing or the directory delta is not exactly one new image file.
3. Retry transient tool or provider failures at most 2 times.
4. Report asset_id and generated_path.
5. Do not inspect unrelated Codex threads.
6. Do not choose files by modified time.
7. Do not copy files.
8. Do not create placeholder or procedural images.

Assets:
- id: <asset_id>
  source_path: .godotmaker/asset-generation/sources/<asset_id>_source.png
  prompt: <prompt>

If built-in image generation is unavailable or retries fail, report failure
with ok=false and failures.
```

Run:

```bash
codex exec --json --dangerously-bypass-approvals-and-sandbox -C <project_root> --output-last-message <summary_path> - < <batch_prompt_path>
```
