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

## Provider Success Boundary

The provider step owns generation and source handoff, not final asset
validation. A generation attempt succeeds when `image_gen` returns exactly one
current-turn path and that path is a readable image that the claim step can
copy. Do not reject the raw provider image because its canvas dimensions,
aspect fit, background edges, object positions, or object pixel sizes differ
from the final production-unit contract.

Claim a successful raw image first. Then let the named production unit run its
controlled finalization and validate the finalized output. This boundary is
the same for Active Codex Runtime and for another coding agent invoking Codex.

## Reference Images

References are optional. When a production unit supplies one or more required
references, each is binding input rather than prompt-only context:

1. verify every path is a readable image before calling `image_gen`;
2. preserve its production role in the generation prompt and provider report;
3. call `image_gen` with `referenced_image_paths` containing every required
   local reference path; putting a path in text is not reference use;
4. record the exact attached paths, roles, and `referenced_image_paths` count
   in the provider report, plus configured coding model and reasoning effort;
5. STOP when the active Codex image path cannot accept those attachments.
   Record the image model when the runtime exposes it; otherwise record
   `image_model_identity: not_exposed_by_subscription_runtime`.

Generated-path report shape:

```json
{
  "ok": true,
  "assets": [
    {
      "asset_id": "<asset_id>",
      "generated_path": "<generated image path>",
      "references": [{"role":"style","path":"<local image path>"}],
      "provider_trace": {
        "provider": "codex",
        "coding_model": "<configured coding model>",
        "reasoning": "<configured reasoning effort>",
        "tool_call_id": "<image_gen call identity>",
        "image_model_identity": "runtime_reported|not_exposed_by_subscription_runtime",
        "image_model": "<runtime image model identity when exposed>",
        "referenced_image_paths": ["<actual attachment path>"]
      }
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
python .godotmaker/asset-runtime/tools/codex_image_claim.py --plan <batch_plan.json> --report <generated_paths.json> --project-root . --out-report <claim_result.json>
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
1. Call image_gen once per attempt for this asset. When references are listed,
   call it with `referenced_image_paths` containing exactly those local paths.
2. Identify the generated image path from this Codex turn. If the turn output
   does not expose a path, compare this `CODEX_THREAD_ID` image directory
   before and after this one call. Report failure if `CODEX_THREAD_ID` is
   missing or the directory delta is not exactly one new image file.
3. Retry transient tool or provider failures at most 2 times.
4. Report asset_id, generated_path, every reference role/path, and a
   provider_trace containing provider, coding_model, reasoning, tool_call_id,
   image_model_identity, image_model when exposed, and the exact
   referenced_image_paths passed to image_gen.
5. Do not inspect unrelated Codex threads.
6. Do not choose files by modified time.
7. Do not copy files.
8. When an asset has references, pass every source_path reference to `image_gen`
   through `referenced_image_paths` and report the attached paths and roles.
9. Do not create placeholder or procedural images.
10. Treat a readable current-turn image as provider success. Do not measure the
    raw image against final canvas, background-edge, layout, or object-pixel
    requirements; claim it so the production unit can finalize and validate it.

Assets:
- id: <asset_id>
  source_path: .godotmaker/asset-generation/sources/<asset_id>_source.png
  prompt: <prompt>
  references:
    - role: <canonical|style|screen>
      path: <local readable image path>
  require_provider_trace: true

If a required reference cannot be attached, built-in image generation is
unavailable, or retries fail, report failure
with ok=false and failures.
```

Run:

```bash
codex exec --json --dangerously-bypass-approvals-and-sandbox -C <project_root> --output-last-message <summary_path> - < <batch_prompt_path>
```
