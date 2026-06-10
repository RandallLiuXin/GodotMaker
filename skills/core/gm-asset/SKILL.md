---
name: gm-asset
description: |
  Asset stage manager. Reads current-tag ASSETS.md gaps, accepts user-provided
  assets, plans visual production units, dispatches asset-producer subagents,
  collects reports, updates ASSETS.md and the asset-generation manifest.
  Explicit invocation only - use /gm-asset.
disable-model-invocation: true
---

# GodotMaker Asset

$ARGUMENTS

You manage the asset stage for the current tag. Read the tag from `PLAN.md`'s
`**Tag:**` header. Process only `ASSETS.md` rows whose `Tag` matches the current
tag and whose `Status` is `MISSING`.

## Session Setup

Write `asset` to `.godotmaker/current_role` before any other action.

## Resume Check

Asset is re-runnable per tag. Use the current state of `ASSETS.md`,
`SCENES.md`, `references/`, and `.godotmaker/asset-generation/`.

Stop when any required input is missing:

1. `project.godot`: tell user to run `/gm-scaffold`.
2. `ROADMAP.md`, `STYLE.md`, `ASSETS.md`, `SCENES.md`, or `PLAN.md`: tell user
   to run `/gm-gdd`.
3. Missing `**Tag:**` header in `PLAN.md`: tell user to re-run `/gm-gdd`.

Proceed when either check has current-tag work:

1. Current-tag Asset Table rows with status `MISSING`.
2. Current-tag scene references whose `references/scene_{name}.png` or report
   is missing or stale against `SCENES.md` and the Visual Asset Contract.

If both checks are empty, stop with:

```text
No MISSING assets and no missing scene references for the current tag. Recommended next: /gm-build.
If you've added new art files or scenes since last run, just tell me and I'll re-scan.
```

## Manager Rules

1. Write directly only to project-root `ASSETS.md` and `.godotmaker/`.
2. Do not read image binaries from `assets/` or `references/`.
3. Dispatch `analyst` for user-provided asset inspection.
4. Dispatch `asset-producer` for generated visual production units.
5. Do not generate raw visual art in the manager context.
6. Do not write generated image files with direct Write/Edit.
7. Do not modify `GDD.md`, `PLAN.md`, `GAP.md`, `STRUCTURE.md`, `SCENES.md`, or
   `STYLE.md`.
8. Do not write game code.
9. Mark audio rows `deferred` unless the user provided matching files.
10. Do not modify prior-tag rows.

## Provider Selection

Read `.godotmaker/config.yaml` and use `asset_image_model`.

| `asset_image_model` | Provider doc |
| --- | --- |
| `native` | `references/providers/native.md` |
| `codex` | `references/providers/codex.md` |
| `gemini:<model>` or `gemini` | `references/providers/gemini.md` |

If the configured provider is unavailable, stop and ask the user to choose
another `asset_image_model`.

Include the selected provider doc in every `asset-producer` brief.

## Asset Producer Model

Read `asset_producer_model` from `.godotmaker/config.yaml` and include it as
`model:` in every `asset-producer` Agent call.

## Production Unit Entry Points

Use `references/asset-planner.md` for production-unit selection.

| Production unit | First entry document |
| --- | --- |
| `screen-reference` | `references/production-units/screen-reference.md` |
| `character-bundle` | `references/production-units/character-bundle.md` |
| `fx-bundle` | `references/production-units/fx-bundle.md` |
| `ui-kit` | `references/production-units/ui-kit.md` |
| `card-kit` | `references/production-units/card-kit.md` |
| `compact-prop-pack` | `references/production-units/compact-prop-pack.md` |
| `background-map` | `references/production-units/background-map.md` |
| `platform-strip` | `references/production-units/platform-strip.md` |
| `scene-prop-set` | `references/production-units/scene-prop-set.md` |

## Process

### Step 1 - Inventory Current-Tag Work

1. Read `ASSETS.md`.
2. Read `PLAN.md`, `STYLE.md`, `SCENES.md`, and `STRUCTURE.md`.
3. Build a current-tag missing list.
4. Split the list into audio, user-provided candidates, scene references, and
   generated visual production units.
5. Keep prior-tag rows unchanged.

### Step 2 - Detect User-Provided Files

Read `references/analyst-dispatch.md`.

Run:

```bash
python tools/asset_user_preflight.py --project-root .
```

When image candidates exist:

1. Dispatch `analyst` with only the candidate paths.
2. Use the analyst report and `assets/manifest.json`.
3. Update high-confidence `direct_runtime` current-tag rows to `provided`.
4. Keep `source_for_processing` rows in the generated visual production plan.
5. Leave uncertain files unchanged.

For audio candidates:

1. Match exact paths first.
2. Use clear filename or asset-id matches only.
3. Update matching current-tag rows to `provided`.

### Step 3 - Build Production Plan

Read:

1. `references/asset-planner.md`
2. `references/asset-runtime-pipeline.md`

Write plan artifacts under `.godotmaker/asset-generation/work/`.

Use `references/asset-planner.md` for grouping, dependencies, batch rules, and
plan artifact fields.

Apply the Visual Anchor Gate from `references/asset-planner.md` before
dispatching generated visual work.

### Step 4 - Dispatch Asset Producers

Dispatch `asset-producer` for every generated visual production unit.

Agent call shape:

```text
Agent({
  subagent_type: "asset-producer",
  description: "Asset Producer: {unit_id}",
  model: "{asset_producer_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{brief below}"
})
```

Read `references/asset-curation.md` when the selected production unit produces
source sheets, candidates, extracted frames, or selected final assets.

Brief shape:

```text
## Asset Production Unit: {unit_id}

### Objective
{one concrete generated visual production unit}

### First Entry Document
- {references/production-units/<unit>.md}

### Provider
- {references/providers/<provider>.md}
- Configured provider: {provider from plan.provider}

### Shared Docs
- {references/asset-runtime-pipeline.md}
- {references/asset-curation.md when needed}

### Inputs
- ASSETS.md rows: {row ids or names}
- Style seed: STYLE.md
- Scene docs: SCENES.md sections or references
- Canonical references: {paths}

### Outputs
- Source paths: {paths under .godotmaker/asset-generation/sources/}
- Final paths: {paths under assets/ or references/}
- Prompt paths: {paths}
- Report path: {path}
- Manifest entry files: {paths}

### Scope
- Write only the listed outputs.
- Use only the first entry document and docs it references.
- Return the required Asset Producer Report.
```

Do not dispatch one subagent per ASSETS.md row when the work is one bundle.
Dispatch one subagent per production unit.

### Step 5 - Collect Reports

Read `references/asset-runtime-pipeline.md`.

For each `asset-producer` report:

1. Confirm status is `DONE`, `PARTIAL`, or `FAILED`.
2. Confirm listed source, final, prompt, report, and manifest-entry files exist
   when claimed.
3. Confirm every ready manifest entry contains `runtime_artifact`.
4. Upsert manifest entries:

```bash
python tools/asset_generation_manifest_update.py --entry-file <entry.json>
```

5. Run full manifest validation:

```bash
python tools/asset_generation_manifest_check.py --check-files
```

6. Update the matching ASSETS.md rows only after manifest validation passes:

```bash
python tools/asset_assets_md_update.py --entry-file <entry.json>
```

7. Redispatch failed or incomplete production units once when the failure is
   actionable from the report.

### Step 6 - Update ASSETS.md

For current-tag rows only:

1. Confirm final generated runtime assets are `generated`.
2. Mark provided files `provided`.
3. Mark unprovided audio `deferred`.
4. Keep rows with incomplete curation or missing final paths as `MISSING`.
5. Confirm `Generation Params` include the manifest entry pointer only.
6. Update the Visual Asset Contract for gameplay-visible generated assets.

Do not mark source sheets, references, or curation candidates as final runtime
assets unless the production-unit report selected them as final outputs.

## Plan Discipline

ASSETS.md status transitions are forward-only:

```text
MISSING -> provided | generated | N/A | deferred
```

If the user wants to regenerate an accepted prior asset, add a current-tag row
or leave a fix task for a later role.

## Completion

After ASSETS.md has no current-tag `MISSING` rows except deferred audio:

1. From the project root run:

```bash
python tools/append_stage_event.py asset
```

2. Check whether the project working tree is dirty:

```bash
git status --porcelain
```

3. If the command prints any rows, commit the asset-stage outputs:

```bash
git add -A
git commit -m "chore(asset): <Tag>"
```

4. Inform the user:

```text
Asset complete. Recommended next: /gm-build
```
