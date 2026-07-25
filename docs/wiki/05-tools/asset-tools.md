# Asset tools

GodotMaker generates and processes 2D art through small Python helper scripts.
`/gm-asset` calls the primary tools automatically. Manual calls are for
debugging one source, one action sheet, or one curation decision.

Primary pipeline tools:

1. `asset_source_generate.py`
2. `asset_layout_guide.py`
3. `asset_action_process.py`
4. `asset_sheet_process.py`
5. `asset_curation_select.py`
6. `asset_action_entry_draft.py`
7. `asset_curation_entry_draft.py`
8. `asset_finalize_entry_draft.py`
9. `asset_output_path.py`
10. `asset_stable_entry.py`
11. `asset_generation_index.py`
12. `asset_assets_md_update.py`
13. `asset_runtime_resolver.py`

## asset_source_generate.py

`asset_source_generate.py` generates API-backed source images from a JSON spec.
It supports Gemini, OpenAI, and xAI Grok selectors. Runtime-native `native` and
`codex` image generation is selected by `/gm-asset`, not this script.

Provider-prefixed selectors require the matching key: `GOOGLE_API_KEY` /
`GEMINI_API_KEY` for Gemini, `OPENAI_API_KEY` for OpenAI, and `XAI_API_KEY` for
Grok. To choose which provider `/gm-asset` uses, set `asset_image_model` in
[`../06-configuration/project-config.md`](../06-configuration/project-config.md).

Manual entry point:

```bash
python tools/asset_source_generate.py --spec <spec.json>
```

The spec contains the asset id, model selector, prompt, prompt path, source
path, size, aspect ratio, reference images, and report path.

## asset_layout_guide.py

`asset_layout_guide.py` creates layout-only guides for fixed-grid source
images. Use it for UI component sheets, icon packs, compact prop packs, and
action sheets.

Manual entry point:

```bash
python tools/asset_layout_guide.py \
  --out <guide.png> \
  --rows <rows> \
  --cols <cols> \
  --labels <labels>
```

The guide controls slot count, centering, and safe padding for image
generation. It is not runtime art.

## asset_sheet_process.py

`asset_sheet_process.py` splits non-character 2D source sheets into cropped
candidates and writes a curation report. It supports transparent sheets and
solid magenta `#FF00FF` sheets through `--background magenta`.

Use it for icon packs, compact prop packs, UI component sheets, and other
non-character source sheets.

Required decisions:

1. `--grid <COLSxROWS>`
2. `--names <comma-separated names>`
3. `--snap-mode autoslice` for separated objects
4. `--snap-mode grid` for strict cell grids
5. `--component-mode largest` for compact UI/icon/prop cells with stray
   fragments

Manual entry point:

```bash
python tools/asset_sheet_process.py \
  --source <source.png> \
  --out-dir <curation_dir> \
  --grid <COLSxROWS> \
  --names <names> \
  --snap-mode <autoslice|grid> \
  --report <report.json>
```

## asset_action_process.py

`asset_action_process.py` processes character, enemy, NPC, summon, and animated
prop action sources. It writes normalized frame PNGs, `sheet-transparent.png`,
`animation.gif`, `pipeline-meta.json`, and an intermediate curation report.

Required decisions:

1. `--kind body` for body-only character actions
2. `--kind fx` for detached effects
3. `--grid <COLSxROWS>`
4. `--names <comma-separated frame names>`
5. `--align feet` or `--align bottom` for grounded body actions
6. `--align center` for floating actions and detached effects
7. `--scale-reference-metadata <pipeline-meta.json>` for later body actions

The tool rejects action frames that touch source cell edges. Its `--final-dir`
and `--final-prefix` options only copy processed frames and the delivery grid
sheet into runtime paths; they do not assemble mixed atlases or row strips.

Manual entry point:

```bash
python tools/asset_action_process.py \
  --source <action_source.png> \
  --out-dir <processed_dir> \
  --grid <COLSxROWS> \
  --names <frame_names> \
  --kind <body|fx> \
  --final-dir <runtime_dir> \
  --final-prefix <asset_id>
```

For later body actions, add:

```bash
--scale-reference-metadata <accepted_action_pipeline_meta.json>
```

## asset_curation_select.py

`asset_curation_select.py` selects one candidate from a curation report and
finalizes it into a runtime asset path.

Manual entry point:

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path <final_path> \
  --asset-id <final_asset_id> \
  --project-root .
```

The tool updates the report status to `selected`, stores the candidate's final
path, and prints the same finalize metadata as `asset_image_finalize.py`.

## asset_action_entry_draft.py

`asset_action_entry_draft.py` turns one processed action `pipeline-meta.json`
into the action support metadata plus a v1 stable-entry draft. It is the
mechanical gate for the action path: frame count against the listed frames, an
empty `edge_touch_frames` set, a recorded scale reference, and containment of
every runtime path inside the asset's stable output directory.

Manual entry point:

```bash
python tools/asset_action_entry_draft.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family character-bundle \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

The draft stops at `processing_status: source_ready` and carries no
`godot_artifact`. A `grid_sheet` becomes worker-consumable only once a native
compiler produces its `SpriteFrames` and the L0-L4 runner verifies it.

## asset_curation_entry_draft.py

`asset_curation_entry_draft.py` turns one selected curation candidate into a v1
stable-entry draft. It requires the named candidate to exist, be unambiguous and
actually `selected`, the report's selected/rejected counts to be coherent, and
the finalized path to sit inside the asset's stable output directory.

Manual entry point:

```bash
python tools/asset_curation_entry_draft.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --asset-id <final_asset_id> \
  --tag <tag> \
  --production-family ui-kit \
  --source-layout single \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<final_asset_id>.json
```

## asset_finalize_entry_draft.py

`asset_finalize_entry_draft.py` turns one `asset_image_finalize.py` report into a
v1 stable-entry draft. Every path that ends in a single finalized image uses it:
screen references, backgrounds and parallax plates, and single card or portrait
frames. It requires the finalize run to have succeeded with `--require-aspect`
inside tolerance and `--label <asset_id>`, and derives the layout from the
family — `reference` pinned to `references/` for `screen-reference`, `single`
pinned to the stable output directory for every other family.

Manual entry point:

```bash
python tools/asset_finalize_entry_draft.py \
  --finalize-report <finalize_report.json> \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family screen-reference \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

## asset_output_path.py

`asset_output_path.py` is the authority for the stable output directory
`assets/generated/<production_family>/<asset_id>/`. Every worker-consumable file
for one asset lives there, so regeneration overwrites in place instead of
drifting into a timestamped or `v2` path.

Manual entry point:

```bash
python tools/asset_output_path.py --family <production_family> --asset-id <asset_id>
python tools/asset_output_path.py --entry <entry.json> --project-root . --check-files
```

## asset_stable_entry.py

`asset_stable_entry.py` validates one v1 stable entry and serializes it to
`.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`. The entry holds
stable identity plus `production_family`, `source_layout`, an optional minimal
`godot_artifact`, and `processing_status` — nothing else.

Manual entry point:

```bash
python tools/asset_stable_entry.py <entry_draft.json> --project-root . --write --check-files
```

## asset_generation_index.py

`asset_generation_index.py` owns the pointer-only root index at
`.godotmaker/asset-generation/manifest.json`. It stores identity plus one
`entry_path` per asset and never duplicates an entry body.

Manual entry point:

```bash
python tools/asset_generation_index.py --project-root . \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
python tools/asset_generation_index.py --project-root . --check-entries --check-files
```

`--check-entries` schema-validates each referenced entry. `--check-files` adds
the on-disk check for every source and artifact and implies `--check-entries`,
so it is the full handoff gate and catches an asset deleted after registration.

An old `runtime_artifact` manifest that stores full entry bodies under `assets`
is rejected with a regeneration message; there is no migration or compatibility
read.

## asset_assets_md_update.py

`asset_assets_md_update.py` promotes ASSETS.md rows from registered stable
entries. It revalidates the entry and its referenced files first and accepts only
a `ready` non-reference entry, so a row can reach `generated` only once the asset
is a finished, worker-consumable runtime asset. It records the entry pointer
instead of duplicating any path into the row.

Manual entry point:

```bash
python tools/asset_assets_md_update.py \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

## asset_runtime_resolver.py

`asset_runtime_resolver.py` resolves one registered, generated ASSETS.md row
into the minimal runtime snapshot: `asset_id`, `production_family`,
`source_layout`, and `godot_artifact`. It requires the ASSETS.md pointer and
the generated root index to agree, then validates the ready stable entry and all
referenced files. Reference-only entries never produce a worker runtime
snapshot.

Manual entry points:

```bash
python tools/asset_runtime_resolver.py --project-root . \
  --tag <tag> --asset-id <asset_id>
python tools/asset_runtime_resolver.py --project-root . \
  --manifest-entry .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

## Calling these by hand

You usually do not need to run these scripts directly. `/gm-asset` orchestrates
them based on `ASSETS.md` and the source-generation manifest.

Manual use cases:

1. Generate one source image from a tweaked spec.
2. Create one layout guide for a fixed-grid source.
3. Process one character action sheet while debugging animation output.
4. Test a provider, size, or aspect ratio before a full `/gm-asset` run.
5. Process one source sheet while debugging extraction.
6. Select one extracted candidate into a runtime asset path.
7. Print or validate one asset's stable output directory.
8. Validate and register one stable entry and its root-index pointer.
9. Resolve one registered ASSETS.md entry into its minimal runtime snapshot.

If you want to update visual targets used by `/gm-evaluate`, re-run
`/gm-asset` rather than editing generated images directly.
