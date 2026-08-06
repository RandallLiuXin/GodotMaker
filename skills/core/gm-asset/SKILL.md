---
name: gm-asset
description: |
  Asset stage manager. Reads current-tag ASSETS.md gaps, accepts user-provided
  assets, plans visual production units, dispatches asset-producer subagents,
  collects validated Asset Skill results, updates ASSETS.md directly, and emits
  minimal worker runtime snapshots from that one authority.
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

1. Any current-tag `ASSETS.md` row, including an Audio table row, with status
   `MISSING`. Under Manager Rule 9, mark unavailable audio rows `deferred`
   before considering the no-work path; only explicitly deferred audio is
   exempt from this check.
2. Current-tag scene references whose `references/scene_{name}.png` or report
   is missing or stale against `SCENES.md` and the Visual Asset Contract.

If neither check has work — no current-tag row is `MISSING`, unavailable audio
is explicitly `deferred`, and all current-tag scene references are current —
record the completed asset stage before stopping:

```bash
python tools/append_stage_event.py asset
```

Then stop with:

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
| `openai:<model>` or `openai` | `references/providers/openai.md` |

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
| `screen-reference` | First-class `screen-reference` Asset Skill |
| `character-bundle` | First-class `character-bundle` Asset Skill |
| `fx-bundle` | First-class `fx-bundle` Asset Skill |
| `ui-kit` | First-class `ui-kit` Asset Skill |
| `card-kit` | First-class `card-kit` Asset Skill |
| `compact-prop-pack` | First-class `compact-prop-pack` Asset Skill |
| `background-map` | First-class `background-map` Asset Skill |
| `platform-strip` | First-class `platform-strip` Asset Skill |
| `scene-prop-set` | First-class `scene-prop-set` Asset Skill |
| `tileset` | First-class `tileset` Asset Skill |

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

Every family is a first-class Asset Skill. Put the named Skill in the brief;
there is no production-unit document left to substitute for one:

| Family | Production contract in the brief |
| --- | --- |
| `background-map` | First-class Asset Skill: `background-map` |
| `character-bundle` | First-class Asset Skill: `character-bundle` |
| `fx-bundle` | First-class Asset Skill: `fx-bundle` |
| `platform-strip` | First-class Asset Skill: `platform-strip` |
| `screen-reference` | First-class Asset Skill: `screen-reference` |
| `ui-kit` | First-class Asset Skill: `ui-kit` |
| `card-kit` | First-class Asset Skill: `card-kit` |
| `scene-prop-set` | First-class Asset Skill: `scene-prop-set` |
| `compact-prop-pack` | First-class Asset Skill: `compact-prop-pack` |
| `tileset` | First-class Asset Skill: `tileset` |

Brief shape:

```text
## Asset Production Unit: {unit_id}

### Objective
{one concrete generated visual production unit}

### Production Contract
- First-class Asset Skill: {background-map | character-bundle | fx-bundle | platform-strip | screen-reference | ui-kit | card-kit | compact-prop-pack | scene-prop-set | tileset}
- Invoke that named Skill with one shared generic asset request. Every
  production unit is a first-class Skill; there is no production-unit document
  to read and no fallback contract for a family.

### First-Class Result Registration

One production unit may return many outputs. Register all runtime outputs together or none through `tools/asset_result_registration.py`; do not choose an anchor output, create a stable entry, or write a family-specific entry draft.

- Validate the generic result with `tools/asset_skill_contract_check.py`.
- On a failed validation, report the failure and do not register it.
- On success, retain sources and evidence in the producer report and send only the request/result to direct registration. Each runtime output needs a named logical asset row. For runtime families, reference outputs are validated evidence only and are not registered; only reference-only families register a `source_ready` reference row.
- The manager consumes the validated result directly. It never reads or writes registration drafts, manifests, or family-specific adapter state.
### Provider
- {references/providers/<provider>.md}
- Configured provider: {provider from plan.provider}

### Shared Docs
- `references/asset-result-registration.md`
- {references/asset-runtime-pipeline.md}
- {references/asset-curation.md when needed}

### Inputs
- ASSETS.md rows: {row ids or names}
- Style seed: STYLE.md
- Scene docs: SCENES.md sections or references
- Canonical references: {paths}

### Outputs
- Generated output directory: `assets/generated/{asset_type}/{asset_id}/`
- Raw source paths: {scratch paths under .godotmaker/asset-generation/sources/}
- Runtime output paths: {final loadable Godot resources for the logical rows}
- Reference paths: {paths under references/ for reference-only assets}
- Prompt paths: {paths}
- Report path: {path}

### Scope
- Write only the listed outputs.
- Use only the production contract and docs it references.
- Return the required Asset Producer Report, ending with its machine outcome
  block.
```

Do not dispatch one subagent per ASSETS.md row when the work is one bundle.
Dispatch one subagent per production unit.

### Step 5 - Register Validated Results

Use this procedure for every production unit.

Resolve the configured Godot executable from `.claude/godotmaker.yaml`'s
`godot_path`; when it is absent, use `godot` from `PATH`.

1. Require one validated request and result JSON for the entire production
   unit. The request declares the complete logical output set; the result must
   match it exactly.
2. Ensure `ASSETS.md` uses the Runtime Type / Runtime Path runtime table. Every
   worker-consumable logical output has one row. Sources, atlases, candidates,
   and curation evidence remain in production reports.
3. Register all outputs atomically and verify each runtime resource through
   Godot before its row becomes `generated`:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --request <validated-request.json> --result <validated-result.json> \
  --godot-path <configured-godot-path>
```

   Missing, duplicated, unexpected, out-of-project, missing, unloadable, or
   wrong-type runtime outputs fail closed and leave all rows unchanged. Runtime-family
   reference outputs remain validated evidence and do not create rows; a
   reference-only family output becomes `source_ready` and is never a worker
   runtime asset.

4. Do not create stable entries, manifest pointers, root indexes, bundle
   manifests, or family-specific entry drafts. Do not use an anchor output for
   a multi-output production unit.
5. Do not hand-edit Runtime Type, Runtime Path, or Status to bypass direct
   result registration.

### Current ASSETS.md Finalization

For current-tag rows only, use the result-registration command above. Runtime
rows are complete only with `Status: generated`, an explicit Runtime Type, and
a final loadable Runtime Path. Only reference-only family rows use
`Runtime Type: reference` and `Status: source_ready`; they never enter a worker
snapshot. Reference outputs returned by runtime families remain result evidence,
not rows. `Generation Params` may retain production inputs and evidence links,
but never runtime metadata or a manifest pointer.

## Plan Discipline

ASSETS.md status transitions are forward-only:

```text
MISSING -> provided | generated | source_ready | deferred
```

If the user wants to regenerate an accepted prior asset, add a current-tag row
or leave a fix task for a later role.

## Completion

Runtime rows are complete at `generated` only after direct registration.
Reference-only rows complete at `source_ready`; runtime-family reference outputs
remain result evidence. If any output cannot be validated, report the failing
production unit and leave its rows unchanged.

After ASSETS.md has no current-tag `MISSING` rows and all unavailable
current-tag audio rows are explicitly `deferred`:

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
