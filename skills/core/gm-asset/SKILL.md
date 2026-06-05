---
name: gm-asset
description: |
  Asset collection + generation. Reads ASSETS.md MISSING entries (rows
  whose Tag matches the current tag), dispatches an analyst subagent for
  image inspection, generates AI images through the configured
  asset_image_model path, updates ASSETS.md status. ASSETS.md is cross-tag — every
  row carries a Tag column marking the introducing tag. Re-runnable any
  time during a tag. Explicit invocation only — use /gm-asset.
disable-model-invocation: true
---

# GodotMaker Asset

$ARGUMENTS

You are filling in the missing assets in `ASSETS.md` for the **current tag** (read the tag from `PLAN.md`'s `**Tag:**` header). `ASSETS.md` is a cross-tag accumulating manifest: every row has a `Tag` column marking the tag that introduced it. Process only rows whose `Tag` matches the current tag AND whose `Status` is `MISSING`. Previous tags' assets stay on disk and stay listed in `ASSETS.md` with their original `Tag` value — do not re-list, re-generate, or relabel them. Image analysis runs in an analyst subagent (context isolation for image binaries); AI generation follows `.godotmaker/config.yaml`'s `asset_image_model`.

This skill is **per-tag re-runnable**: a user can call `/gm-asset` between build batches when they add new art files. Each invocation processes whatever is currently `MISSING` for the current tag.

## Session Setup

**FIRST ACTION — before anything else:** Write `asset` to `.godotmaker/current_role`.

## Resume Check

Asset is re-runnable per tag, so the gate is the current state of `ASSETS.md` plus the scene-reference snapshot under `references/`, not events in `stage.jsonl`.

- If `project.godot` does not exist → STOP. Tell user to run `/gm-scaffold` first.
- If `ROADMAP.md` does not exist → STOP. Tell user to run `/gm-gdd` first.
- If `STYLE.md` does not exist → STOP. Tell user to run `/gm-gdd` first.
- If `ASSETS.md` does not exist → STOP. Tell user to run `/gm-gdd` first.
- If `SCENES.md` does not exist → STOP. Tell user to run `/gm-gdd` first.
- If `PLAN.md` is missing the `**Tag:**` header → STOP. Tell user the file is stale and to re-run `/gm-gdd` to regenerate it for the current tag.
- Build two work-pending checks for the current tag:
  1. **ASSETS.md gap:** any current-tag row in the Asset Table whose status is `MISSING` (i.e. not `provided` / `generated` / `N/A` / `deferred`).
  2. **Scene-reference gap:** any scene listed in `SCENES.md` for the current tag whose `references/scene_{name}.png` is absent on disk, whose scene-reference report is missing, or whose report contract summary no longer matches the scene's Asset bindings / matching Visual Asset Contract rows.
- If **both** checks come back empty → STOP. Tell the user:
  > "No MISSING assets and no missing scene references for the current tag. Recommended next: /gm-build.
  > If you've added new art files or scenes since last run, just tell me and I'll re-scan."
- Otherwise → proceed.

## Hard Rules

1. **Direct Write/Edit by you (main agent) is restricted to project-root `ASSETS.md` and files under `.godotmaker/`.** Files in `assets/` and `references/` reach disk only via:
   - `tools/asset_gen.py` invoked through Bash for API-backed generation.
   - `tools/codex_image_claim.py` followed by `tools/asset_image_finalize.py`.
   - Runtime-native generation followed by `tools/asset_image_finalize.py`.
   - The analyst subagent (Step 2).
   Do NOT write image files with direct Write/Edit calls.
2. **Image analysis MUST go through the analyst subagent.** Do NOT Read image binaries from `assets/` or `references/` yourself. Dispatch analyst when you need style/dimension/role extraction.
3. **You CANNOT modify PLAN.md, GAP.md, STRUCTURE.md, SCENES.md, STYLE.md.**
4. **You CANNOT write game code.**
5. **Audio MUST be user-provided.** Mark audio as deferred and remind the user.

## Model Selection

Read `.godotmaker/config.yaml` before generation. Use `asset_image_model` for image assets and scene references:

- `native`: use the active agent runtime's native image-generation provider/tool.
- `codex`: use Codex image generation explicitly. If the active runtime is
  Codex, use the active Codex runtime-native image-generation provider/tool. If
  the active runtime is Claude Code, invoke non-interactive `codex exec` through
  Bash and instruct Codex to use `$imagegen` / built-in `image_gen`.
- `gemini:<model>`, `openai:<model>`, `grok:<model>`: call `tools/asset_gen.py image --model <selector> ...`.

If the selected provider is unavailable, STOP and ask the user to choose another `asset_image_model`.

## Process

### Step 1 — Inventory MISSING (current tag only)

Read `ASSETS.md` Asset Table. Filter to rows whose `Tag` matches the current tag. Among those, build a list of MISSING items grouped by type:
- **Art (sprites, textures, references):** can be user-provided or AI-generated
- **Audio:** must be user-provided
- **Scene reference images:** AI-generated based on SCENES.md descriptions

Do NOT touch rows from prior tags — even if they look broken, that's a `/gm-fixgap` concern. New rows you add for newly-discovered assets must carry the current tag in their `Tag` column.

### Step 2 — Detect User-Provided Files

Run the deterministic preflight before any AI generation:

```bash
python tools/asset_user_preflight.py --project-root .
```

The script scans supported file suffixes under `assets/`, excludes paths already
consumed by completed ASSETS.md rows or `assets/manifest.json`, and prints JSON:

```json
{
  "ok": true,
  "candidate_count": 2,
  "image_candidate_count": 1,
  "audio_candidate_count": 1,
  "needs_analyst": true,
  "candidates": [
    {"path": "assets/player.png", "kind_hint": "image", "reason": "..."},
    {"path": "assets/audio/hit.ogg", "kind_hint": "audio", "reason": "..."}
  ]
}
```

Candidates can include `match_kind: "exact_path"` with `matched_asset_id`,
`matched_asset_type`, and `matched_status` when the file path exactly matches an
unfilled ASSETS.md row.

If `candidate_count > 0`, treat the listed files as user-provided candidates
already placed on disk:

1. For image candidates, dispatch an **analyst subagent**
   (`subagent_type: "analyst"`, see `references/analyst-dispatch.md`) to
   inspect only the listed candidate paths and generate/update
   `assets/manifest.json`.
   - **Do NOT read image files yourself.** All image analysis goes through the analyst.
   - Analyst extracts: type, role, dimensions, palette, style characteristics.
2. For audio candidates, do not dispatch analyst. Prefer preflight candidates
   with `match_kind: "exact_path"`; otherwise match only by clear
   filename/asset-id match.
3. After analyst reports, update ASSETS.md: change high-confidence matching
   `MISSING` / `deferred` rows to `provided`.
4. Leave uncertain candidates in `assets/manifest.json` or on disk without
   changing ASSETS.md. Do not guess.

If no candidates are found, continue to generation. In an interactive session
you may still ask the user whether they want to add files before generation,
but CLI-driven runs must not depend on that question being answered.

### Step 3 — Generate Scene Reference Images (if MISSING)

Build the missing scene-reference list from SCENES.md. For each missing scene,
plan a fixed source path, final path, and report path:

```json
{
  "group_id": "scene_refs_001",
  "kind": "scene_reference",
  "provider": "<asset_image_model>",
  "contract_summary": "<SCENES.md Asset bindings + ASSETS.md Visual Asset Contract rows used>",
  "anchor_item": {
    "asset_id": "scene_main",
    "prompt": "<prompt>",
    "source_path": ".godotmaker/asset-generation/sources/scene_main_source.png",
    "final_path": "references/scene_main.png"
  },
  "parallel_items": [
    {
      "asset_id": "scene_shop",
      "prompt": "<prompt>",
      "source_path": ".godotmaker/asset-generation/sources/scene_shop_source.png",
      "final_path": "references/scene_shop.png"
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/scene_refs_001.json"
}
```

If one scene should anchor the visual style for the rest, generate that anchor
scene first. Then generate the remaining missing scene references in parallel
groups of up to 3. If isolated generation groups are unavailable, run
sequentially and write the fallback reason in the report and summary.

For each missing scene:

1. Read `references/visual-target.md`.
2. Build the prompt for this scene using inputs from `SCENES.md` (Elements + Mood + Asset bindings) + matching ASSETS.md Visual Asset Contract rows + `STYLE.md` + `GDD.md` section 4. If the user provided art in `assets/`, also reference the analyst's style summary from `assets/manifest.json`.
3. Generate the scene image using the selected `asset_image_model` path:
   - API-backed selector: run `python tools/asset_gen.py image --model <asset_image_model> --prompt "..." --size 1K --aspect-ratio 16:9 -o references/scene_{name}.png`.
   - Active Codex runtime with `asset_image_model: native` or `asset_image_model: codex`: follow `references/asset-gen.md` Active Codex runtime batch for this scene.
   - Claude Code with `asset_image_model: codex`: follow `references/asset-gen.md` Codex handoff from Claude Code for this scene.
   - Other runtime-native provider: generate a source image path, then run `python tools/asset_image_finalize.py --source <generated_image_path> --out references/scene_{name}.png --label scene_{name}`.
4. Write the scene's flat finalize JSON entry and contract summary to the scene-reference generation report.
5. Show the result to the user. If rejected, regenerate with a tightened prompt (per `references/visual-target.md`).

### Step 4 — Generate Remaining MISSING Art

For all remaining MISSING art assets in ASSETS.md (excluding audio):

Read `STYLE.md` before crafting generation prompts.

Confirm with user:
> "I'll AI-generate the following: {list}. {if user art: 'Style will match your existing assets.'} OK to proceed?"

After confirmation, generate each asset through the selected `asset_image_model` path (per `asset-planner.md` + `asset-gen.md` for prompt construction).

Run generation groups in batches of up to 3 art assets. Each group uses this
input schema:

```json
{
  "group_id": "assets_001",
  "kind": "art_asset",
  "provider": "<asset_image_model>",
  "items": [
    {
      "asset_id": "<asset_id>",
      "prompt": "<prompt>",
      "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
      "final_path": "assets/img/<asset_id>.png",
      "resize": null
    }
  ],
  "report_path": ".godotmaker/asset-generation/reports/assets_001.json"
}
```

If isolated generation groups are unavailable, run the batch sequentially and
write the fallback reason in the report and summary.

Use the selected `asset_image_model` path:

- API-backed selector: each group runs `python tools/asset_gen.py image --model <asset_image_model> ... -o <target.png>` for each target. The tool finalizes and validates the output.
- Active Codex runtime with `asset_image_model: native` or `asset_image_model: codex`: follow `references/asset-gen.md` Active Codex runtime batch. Use one Codex subagent per asset when subagents are available.
- Claude Code with `asset_image_model: codex`: follow `references/asset-gen.md` Codex handoff from Claude Code.
- Other runtime-native provider: generate each source image path, then run `python tools/asset_image_finalize.py --source <generated_image_path> --out <target.png> --label <asset_id> [--resize WIDTHxHEIGHT]`.

Each group writes one JSON report under `.godotmaker/asset-generation/reports/`: `{"ok": true, "provider": "<asset_image_model>", "assets": [<finalize JSON>, ...]}`. Each `assets[]` item is the flat JSON printed by `tools/asset_image_finalize.py`, so `tools/asset_image_report_check.py` can validate it.

### Step 5 - Update ASSETS.md

After all generation calls return:
- Change generated rows from `MISSING` to `generated` with file path + generation params
- Audio rows that user did not provide: mark `deferred` (with user acknowledgment)
- Run `python tools/asset_image_report_check.py <report.json>...`
- Re-dispatch one follow-up batch for missing or invalid generated images
- Verify total MISSING count for the current tag is zero (or all remaining are deferred audio with user OK)
- New rows added this tag must carry the current tag in their `Tag` column
- Update `ASSETS.md` Visual Asset Contract for generated or provided visual
  assets. Bind each gameplay-visible object to its scene/mechanic use,
  runtime size, visual role, readability requirement, and anchor/derivative
  source.

## Plan Discipline

ASSETS.md is the only document you may modify. Status transitions are forward-only:

```text
MISSING -> provided | generated | N/A | deferred
```

Never revert a `provided`/`generated` row back to `MISSING`; if the user wants to regenerate, treat it as a NEW row (with the current tag in its `Tag` column) or note in MEMORY.md.

**Tag scope:** Only modify rows whose `Tag` matches the current tag, and only add new rows tagged with the current tag. Prior tags' rows are immutable from this skill. If a prior-tag asset is broken, raise it as a fix task in `/gm-fixgap`; do not relabel the row's `Tag` column.

## Available Skills & Tools

**Skills:**
| Skill | Purpose |
|-------|---------|
| screenshot | Capture for visual cross-check |
| visual-qa | Style consistency check |

**CLI tools (call via Bash):**
| Tool | Purpose |
|------|---------|
| `tools/asset_gen.py` | API-backed image generation (Gemini / OpenAI / Grok) |
| `tools/asset_user_preflight.py` | Find unconsumed user-provided asset candidates under `assets/` |
| `tools/codex_image_claim.py` | Copy Codex saved_path into a project source path |
| `tools/asset_image_finalize.py` | Copy, resize, and validate generated image assets |
| `tools/asset_image_report_check.py` | Validate generation group reports and image files |

**Reference docs (read for prompt construction):**
- `references/asset-planner.md` — generation brief template
- `references/asset-gen.md` — `asset_gen.py` usage details

**Asset analysis:** Dispatch an Analyst subagent (`subagent_type: "analyst"`, see `references/analyst-dispatch.md`).

## Context Management

Keep `ASSETS.md` state and the MISSING list in context. Delegate image binaries to the analyst subagent (do NOT Read images directly). Generation prompts can stay in context — they're cheap text.

## When Done

After ASSETS.md has no MISSING rows (or all remaining are deferred audio with user acknowledgment):

1. From the project root run `python tools/append_stage_event.py asset` to append a `{"role": "asset", "ts": "<server-generated UTC>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.
   (The Resume Check above reads `ASSETS.md`, not this event — the stage.jsonl entry exists so `stage_reminder.py` can suggest `/gm-build` next.)
2. `git add -A && git commit -m "chore(asset): <Tag>"`
3. Inform the user: `Asset complete. Recommended next: /gm-build` (or re-invoke /gm-asset later if you add more art).
