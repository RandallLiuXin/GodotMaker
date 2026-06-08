# Asset tools

GodotMaker generates and processes 2D art through small Python helper scripts.
`/gm-asset` calls the primary tools automatically. Manual calls are for
debugging one source, one action sheet, or one curation decision.

Primary pipeline tools:

1. `asset_source_generate.py`
2. `asset_layout_guide.py`
3. `asset_action_process.py`
4. `asset_action_manifest_entry.py`
5. `asset_sheet_process.py`
6. `asset_curation_select.py`
7. `asset_curation_manifest_entry.py`

Optional curation utility:

1. `rembg_matting.py`

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

## rembg_matting.py

`rembg_matting.py` is an optional curation utility for removing solid-color
backgrounds before source-sheet processing.

Manual entry points:

```bash
python tools/rembg_matting.py <input.png> -o <output.png>
python tools/rembg_matting.py --batch <input_dir> -o <output_dir>
python tools/rembg_matting.py <input.png> --preview
```

The tool uses a neural network (BiRefNet) to identify the subject and color
matting to clean up the edges. You can force a mode with `-m trust`,
`-m adapt`, or `-m color`.

GPU acceleration is used automatically if an NVIDIA GPU with CUDA is available.
On CPU it is slower but still works.

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

## asset_action_manifest_entry.py

`asset_action_manifest_entry.py` turns one processed action
`pipeline-meta.json` plus its `character_action_source` entry into a
`character_frame_output` manifest entry.

Manual entry point:

```bash
python tools/asset_action_manifest_entry.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --source-entry <character_action_source_entry.json> \
  --asset-id <frame_output_asset_id> \
  --project-root . \
  --out <frame_output_entry.json>
```

Upsert the generated entry with `asset_generation_manifest_update.py`.

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

## asset_curation_manifest_entry.py

`asset_curation_manifest_entry.py` turns one selected curation candidate plus
its source-sheet manifest entry into a validated runtime manifest entry.

Manual entry point:

```bash
python tools/asset_curation_manifest_entry.py \
  --report <report.json> \
  --source-entry <source_sheet_entry.json> \
  --candidate <candidate_id_or_name> \
  --asset-id <final_asset_id> \
  --project-root . \
  --out <final_asset_entry.json>
```

Upsert the generated entry with `asset_generation_manifest_update.py`.

## Calling these by hand

You usually do not need to run these scripts directly. `/gm-asset` orchestrates
them based on `ASSETS.md` and the source-generation manifest.

Manual use cases:

1. Generate one source image from a tweaked spec.
2. Create one layout guide for a fixed-grid source.
3. Process one character action sheet while debugging animation output.
4. Build one character frame-output manifest entry from action metadata.
5. Test a provider, size, or aspect ratio before a full `/gm-asset` run.
6. Remove a solid background before source-sheet curation.
7. Process one source sheet while debugging extraction.
8. Select one extracted candidate into a runtime asset path.
9. Build one runtime manifest entry from a selected curation candidate.

If you want to update visual targets used by `/gm-evaluate`, re-run
`/gm-asset` rather than editing generated images directly.
