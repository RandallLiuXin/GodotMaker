---
name: gm-asset
description: |
  Asset stage manager. Reads current-tag ASSETS.md gaps, accepts user-provided
  assets, plans visual production units, dispatches asset-producer subagents,
  collects reports, registers generated-asset stable entries, updates ASSETS.md.
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

### First-Class Result Adapter
- Validate the generic result with `tools/asset_skill_contract_check.py`.
- When `validation.passed` is false, report the failure and do not create a
  stable-entry draft.
- When it passes, map its `sources`, `outputs`, and validation evidence into
  the existing Asset Producer Report and the inputs of the appropriate
  deterministic entry-draft builder.
- One Skill call may return several logical outputs. Exactly one runtime output
  per logical asset becomes a stable entry; every other output is reported as a
  reference. Never draft a second entry or a `godot_artifact` for a reference.
  A bundle family delivers many logical assets from one production, so it draws
  one entry per runtime output and declares a matching ASSETS.md row for each;
  that is the same rule, not an exception to it.
- For `character-bundle`, pass the Skill's archived resolved request, one
  action processing report per required action, and its validated result to
  `tools/asset_action_entry_draft.py` bundle mode. It registers exactly one
  worker-consumable `SpriteFrames` entry, and reaches `ready` only from a result
  whose L0-L4 levels all passed and whose build still matches the fingerprint
  recorded when that artifact was compiled. A provider-generated canonical is
  reported as a reference output beside that one entry; a user-supplied
  canonical is not republished at all.
- For `compact-prop-pack`, pass the request and fully validated result to
  `tools/asset_compact_prop_pack_entry_draft.py`. It writes one ready logical
  entry draft per AtlasTexture while retaining the shared physical bundle path.
- For `fx-bundle`, use `tools/asset_curation_entry_draft.py` request mode for a
   static `single -> Texture2D` result, or `tools/asset_action_entry_draft.py`
   request mode for its one animated `grid_sheet -> SpriteFrames` result. Both
   start compiled. Re-run the same builder with `--result` once the Skill's
   L0-L4 production loop succeeds; that run promotes the same entry to `ready`
   against the build fingerprint recorded when the artifact was published, and
   is the only way an FX entry becomes worker-consumable.
- For `scene-prop-set`, pass the original request, successful result, and first
  declared logical prop to `tools/asset_scene_prop_set_entry_draft.py` before
  writing its ready draft. The builder binds metadata geometry to the request.
- For `ui-kit` and `card-kit`, pass the request and the validator-owned result
  to `tools/asset_ui_card_entry_draft.py`. One kit production compiles many
  separately bindable resources, so it writes one ready draft per runtime
  output — the `Theme`, every `StyleBoxTexture`, and every `AtlasTexture` — each
  carrying the kit's `bundle_id`. A worker binds one of these per node, so none
  of them may be collapsed into a single primary artifact.
- For `tileset`, pass the request and passing result to
  `tools/asset_tileset_entry_draft.py`. It writes one ready `tile_atlas ->
  TileSet` entry. Do not ask the Skill for a map: the entry is a tile library,
  and layout stays a worker decision.
- The manager consumes only that adapted report and its drafts in Step 5; the
  first-class Skill never reads registration, manifest, tag, or stage state.

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
- Stable output directory: `assets/generated/{production_family}/{asset_id}/`
- Raw source paths: {scratch paths under .godotmaker/asset-generation/sources/}
- Runtime output paths: {finalized image and support metadata under the stable
  output directory; only these may appear in a stable entry}
- Reference paths: {paths under references/ for reference-only assets}
- Prompt paths: {paths}
- Report path: {path}
- Stable entry drafts: {paths under .godotmaker/asset-generation/work/entries/}

### Scope
- Write only the listed outputs.
- Use only the production contract and docs it references.
- Return the required Asset Producer Report.
```

Do not dispatch one subagent per ASSETS.md row when the work is one bundle.
Dispatch one subagent per production unit.

### Step 5 - Register Stable Entries

Read `references/asset-runtime-pipeline.md`.

For each `asset-producer` report:

For a first-class Skill result, the producer is the manager's adapter: it
validates the generic result, materializes the normal report and deterministic
draft-builder inputs, and then follows this same registration path. The manager
does not register a generic result directly.

1. Confirm status is `DONE`, `PARTIAL`, or `FAILED`.
2. Confirm listed source, runtime output, prompt, report, and stable-entry draft
   files exist when claimed.
3. Confirm every entry draft came from a deterministic builder —
   `tools/asset_action_entry_draft.py` for processed action output,
   `tools/asset_curation_entry_draft.py` for a selected curation candidate,
   `tools/asset_finalize_entry_draft.py` for a finalized screen reference,
   `tools/asset_compact_prop_pack_entry_draft.py` for a fully ready compact
   prop atlas bundle,
   `tools/asset_scene_prop_set_entry_draft.py` for a compiled scene prop atlas,
   `tools/asset_ui_card_entry_draft.py` for a validated ui-kit or card-kit
   delivery, or `tools/asset_tileset_entry_draft.py` for a compiled tileset.
   Every production path has one, so reject a hand-written draft: the builders
   are what enforce frame count, edge-touch rejection, scale reference, curation
   selection, aspect validation, promotion fingerprints, and stable-path
   containment.
4. For a bundle family — `ui-kit`, `card-kit`, `compact-prop-pack` — declare the
   rows its outputs will fill before writing any entry, naming the planned
   request row it serves:

```bash
python tools/asset_bundle_rows.py --assets-md ASSETS.md \
  --request <request.json> --tag <tag> --supersede <planned_request_row>
```

   One bundle production delivers many separately bindable resources, so
   ASSETS.md has no row for them until this runs and step 8 would fail closed.
   The planned request row is not one of those resources; `--supersede` closes
   it as `N/A` against the bundle that serves it. Do not hand-write these rows.

5. Write each draft to its canonical stable-entry path:

```bash
python tools/asset_stable_entry.py <entry_draft.json> --project-root . --write --check-files
```

6. Upsert the written entry into the pointer-only root index:

```bash
python tools/asset_generation_index.py --project-root . \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

7. Before marking any runtime entry `generated`, run the full root-index gate:

```bash
python tools/asset_generation_index.py --project-root . --check-entries --check-files
```

8. Update the matching ASSETS.md rows only after the root-index gate passes:

   - Mark a `ready` non-reference entry `generated` after the full root-index
     gate passes.
   - Mark a `screen-reference` entry `generated` only at `source_ready`
     after its finalized file, canonical entry, and root-index pointer validate.
   - Do not create a `godot_artifact` or worker runtime handoff for a reference.

```bash
python tools/asset_assets_md_update.py \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

Keep runtime entries below `ready` as `MISSING`. Do not hand-edit an ASSETS.md
status, the root index, or a stable entry.

9. Redispatch failed or incomplete production units once when the failure is
   actionable from the report.

Each command fails closed. Do not hand-edit
`.godotmaker/asset-generation/manifest.json` or an entry file to make a gate
pass.

### Step 6 - Update ASSETS.md

For current-tag rows only:

1. Confirm a `ready` non-reference entry is `generated`; confirm a validated
   `source_ready` reference-only entry is `generated`.
2. Mark provided files `provided`.
3. Mark unprovided audio `deferred`.
4. Keep runtime rows without a registered `ready` entry as `MISSING`. Mark a
   registered, validated `screen-reference` at `source_ready` as
   `generated`.
5. Confirm `Generation Params` include the stable entry pointer only.
6. Update the Visual Asset Contract for gameplay-visible generated assets.

Report registered reference-only entries as non-runtime assets. Do not mark a
runtime row `generated`, invent a `godot_artifact`, or edit `processing_status`.

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

Keep generated runtime rows below `ready` as `MISSING`. Registered, validated
reference-only rows may complete only at `source_ready`. If runtime rows
remain, report the asset stage blocked on compiler work.

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
