---
name: gm-asset
description: |
  Asset collection + generation. Reads ASSETS.md MISSING entries (rows
  whose Tag matches the current tag), dispatches an analyst subagent for
  user-provided image inspection, generates AI images through the configured
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
  2. **Scene-reference gap:** any scene listed in `SCENES.md` for the current tag whose `references/scene_{name}.png` is absent on disk.
- If **both** checks come back empty → STOP. Tell the user:
  > "No MISSING assets and no missing scene references for the current tag. Recommended next: /gm-build.
  > If you've added new art files or scenes since last run, just tell me and I'll re-scan."
- Otherwise → proceed.

## Hard Rules

1. **Direct Write/Edit by you (main agent) is restricted to project-root `ASSETS.md` and files under `.godotmaker/`.** Files in `assets/` and `references/` reach disk only via:
   - `tools/asset_gen.py` invoked through Bash for API-backed generation, OR
   - the selected runtime-native image-generation provider/tool followed by `tools/asset_image_finalize.py`, OR
   - the analyst subagent (Step 2).
   Do NOT write image files with direct Write/Edit calls.
2. **Image analysis MUST go through the analyst subagent.** Do NOT Read image binaries from `assets/` yourself — they pollute context. Dispatch analyst when you need style/dimension/role extraction.
3. **You CANNOT modify PLAN.md, GAP.md, STRUCTURE.md, SCENES.md, STYLE.md.** Asset work is isolated from gameplay planning. Code-art coupling issues surface in `/gm-evaluate` and are addressed in `/gm-fixgap` or the next tag.
4. **You CANNOT write game code.** Code lives in `/gm-build` workers.
5. **Audio MUST be user-provided** — AI audio generation is not supported. Mark audio as deferred and remind the user.

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

### Step 2 — Collect User-Provided Files

Use `AskUserQuestion`:
> "I'm about to fill in {N} missing assets. Do you want to provide any of them yourself before I generate? Audio MUST be user-provided. Place files in `assets/` and tell me when ready."

If user provides files:

1. Wait for user confirmation that files are placed.
2. Dispatch an **analyst subagent** (`subagent_type: "analyst"`, see `references/analyst-dispatch.md`) to inspect the files and generate/update `assets/manifest.json`.
   - **Do NOT read image files yourself.** All image analysis goes through the analyst.
   - Analyst extracts: type, role, dimensions, palette, style characteristics.
3. After analyst reports, update ASSETS.md: change matching `MISSING` rows to `provided`.

### Step 3 — Generate Scene Reference Images (if MISSING)

For each scene in SCENES.md whose `references/scene_{name}.png` is missing:

1. **Read `references/visual-target.md` first** — it has the prompt rules (enumerate every object, exclude effects you won't build, show HUD, etc.) and a prompt template. These reference images become the VQA contract that `gm-evaluate` enforces, so the rules matter.
2. Build the prompt for this scene using inputs from `SCENES.md` (Elements + Mood) + `STYLE.md` + `GDD.md` §4. If the user provided art in `assets/`, also reference the analyst's style summary from `assets/manifest.json`.
3. Generate the image using the selected `asset_image_model` path. For API-backed selectors, run via Bash:
   ```bash
   python tools/asset_gen.py image --model <asset_image_model> --prompt "..." \
     --size 1K --aspect-ratio 16:9 -o references/scene_{name}.png
   ```
   For `native` or `codex`, use the selected runtime-native provider/tool, then run:
   ```bash
   python tools/asset_image_finalize.py --source <generated_image_path> \
     --out references/scene_{name}.png --label scene_{name}
   ```
4. Show the result to the user. If rejected, regenerate with a tightened prompt (per `references/visual-target.md`).

### Step 4 — Generate Remaining MISSING Art

For all remaining MISSING art assets in ASSETS.md (excluding audio):

Read `STYLE.md` before crafting generation prompts.

Confirm with user:
> "I'll AI-generate the following: {list}. {if user art: 'Style will match your existing assets.'} OK to proceed?"

After confirmation, generate each asset through the selected `asset_image_model` path (per `asset-planner.md` + `asset-gen.md` for prompt construction).

Run up to 3 generation groups in parallel. Each group owns one or more target image paths. If isolated generation groups are unavailable, run the batch sequentially and state the fallback.

- API-backed selectors: each group runs `python tools/asset_gen.py image --model <asset_image_model> ... -o <target.png>` for each target. The tool finalizes and validates the output.
- `native` / `codex`: each group uses the selected runtime-native provider/tool,
  records each generated image path, then runs:
  ```bash
  python tools/asset_image_finalize.py --source <generated_image_path> \
    --out <target.png> --label <asset_id> [--resize WIDTHxHEIGHT]
  ```
- For `codex` under Claude Code, call Codex through Bash. Put the prompt in a
  temp file. The Codex prompt must explicitly require `$imagegen` / built-in
  `image_gen`, copy the selected PNG from `$CODEX_HOME/generated_images/...` to
  a requested source path under `.godotmaker/asset-generation/codex/`, and
  report failure if the image-generation tool is unavailable. After `codex exec`
  returns, verify that source path exists before finalizing it.
- Each group writes one JSON report under `.godotmaker/asset-generation/`: `{"ok": true, "provider": "<asset_image_model>", "assets": [<finalize result>, ...]}`.
- Do not select images by scanning a global "latest generated image" list. Use the generated paths reported by the group.

### Step 5 — Update ASSETS.md

After all generation calls return:
- Change generated rows from `MISSING` → `generated` with file path + generation params
- Audio rows that user did not provide → mark `deferred` (with user acknowledgment)
- Run `python tools/asset_image_report_check.py <report.json>...`
- Re-dispatch one follow-up batch for missing or invalid generated images
- Verify total MISSING count for the current tag is zero (or all remaining are deferred audio with user OK)
- New rows added this tag must carry the current tag in their `Tag` column

## Plan Discipline

ASSETS.md is the only document you may modify. Status transitions are forward-only:

```
MISSING → provided | generated | N/A | deferred
```

Never revert a `provided`/`generated` row back to `MISSING` — if the user wants to regenerate, treat it as a NEW row (with the current tag in its `Tag` column) or note in MEMORY.md.

**Tag scope:** Only modify rows whose `Tag` matches the current tag, and only add new rows tagged with the current tag. Prior tags' rows are immutable from this skill. If a prior-tag asset is broken, raise it as a fix task in `/gm-fixgap` — do not relabel the row's `Tag` column.

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
