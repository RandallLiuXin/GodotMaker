# Asset tools

GodotMaker generates and processes 2D art through small Python helper scripts.
`/gm-asset` calls the primary tools automatically. You can also run them by
hand to test source generation, source-sheet processing, or candidate
selection.

Primary pipeline tools:

1. `asset_source_generate.py`
2. `asset_sheet_process.py`
3. `asset_curation_select.py`

Optional curation utility:

1. `rembg_matting.py`

## asset_source_generate.py

`asset_source_generate.py` generates API-backed source images from a JSON spec.
It supports Gemini, OpenAI, and xAI Grok selectors. Runtime-native `native` /
`codex` image generation is selected by `/gm-asset`, not this script.

Provider-prefixed selectors require the matching key: `GOOGLE_API_KEY` /
`GEMINI_API_KEY` for Gemini, `OPENAI_API_KEY` for OpenAI, and `XAI_API_KEY` for
Grok. To choose which provider `/gm-asset` uses, set `asset_image_model` in
[`../06-configuration/project-config.md`](../06-configuration/project-config.md).

### Generate a source image

Write a spec:

```json
{
  "asset_id": "player_canonical",
  "model": "gemini:gemini-3.1-flash-image-preview",
  "prompt": "top-down player character, blue outfit, centered on a solid green background",
  "prompt_path": ".godotmaker/asset-generation/prompts/player_canonical.txt",
  "source_path": ".godotmaker/asset-generation/sources/player_canonical_source.png",
  "size": "1K",
  "aspect_ratio": "1:1",
  "reference_images": [],
  "report_path": ".godotmaker/asset-generation/reports/player_canonical_source.json"
}
```

Run:

```bash
python tools/asset_source_generate.py \
  --spec .godotmaker/asset-generation/specs/player_canonical.json
```

The script writes the prompt file, source image, and optional report. Final
runtime assets are selected and finalized by the rest of the asset pipeline.

## rembg_matting.py

`rembg_matting.py` is an optional curation utility for removing solid-color
backgrounds before source-sheet processing.

```bash
# Single image
python tools/rembg_matting.py assets/sprites/enemy_raw.png -o assets/sprites/enemy.png

# Batch
python tools/rembg_matting.py --batch raw_frames/ -o clean_frames/

# Preview
python tools/rembg_matting.py assets/sprites/enemy_raw.png --preview
```

The tool uses a neural network (BiRefNet) to identify the subject and color
matting to clean up the edges. You can force a mode with `-m trust`, `-m adapt`,
or `-m color`.

GPU acceleration is used automatically if an NVIDIA GPU with CUDA is available.
On CPU it is slower but still works.

## asset_sheet_process.py

`asset_sheet_process.py` splits 2D source sheets into cropped candidates and
writes a curation report. It supports transparent sheets and solid magenta
`#FF00FF` sheets through `--background magenta`. Magenta mode removes the solid
background and edge-connected magenta fringe. Use it for regular grids such as
icon packs, compact prop packs, UI component sheets, and simple animation
sources.

```bash
python tools/asset_sheet_process.py \
  --source .godotmaker/asset-generation/sources/ui_kit_source.png \
  --out-dir .godotmaker/asset-generation/curation/ui_kit_source/ \
  --grid 4x3 \
  --names play_button,shop_button,coin_icon,gem_icon,panel,tab,badge,slot,arrow_left,arrow_right,close_button,empty_slot \
  --asset-id ui_kit_source \
  --tag v0.1.0 \
  --background magenta \
  --magenta-threshold 100 \
  --magenta-edge-threshold 150 \
  --snap-mode autoslice \
  --component-mode largest \
  --component-padding 8 \
  --min-component-area 100 \
  --report .godotmaker/asset-generation/curation/ui_kit_source.json
```

Pass `--snap-mode` explicitly. Use `--snap-mode autoslice` for compact prop
packs, icon packs, and UI component sheets with separated objects. Use
`--snap-mode grid` for strict regular grids and animation frame sheets. Use
`--component-mode largest` to discard smaller fragments in one grid slot. The
report includes `candidates[]`, `rejected[]`, `strategy`, `component_count`,
selected-component metadata, and `status`. Selected candidates are later
finalized into runtime paths under `assets/`.

## asset_curation_select.py

`asset_curation_select.py` selects one candidate from a curation report and
finalizes it into a runtime asset path.

```bash
python tools/asset_curation_select.py \
  --report .godotmaker/asset-generation/curation/ui_kit_source.json \
  --candidate ui_kit_source.action_button \
  --final-path assets/ui/action_button.png \
  --asset-id action_button \
  --project-root .
```

The tool updates the report status to `selected`, stores the candidate's final
path, and prints the same finalize metadata as `asset_image_finalize.py`.

## Calling these by hand

You usually do not need to run these scripts directly. `/gm-asset` orchestrates
them based on `ASSETS.md` and the source-generation manifest.

Manual use cases:

- Generate one source image from a tweaked spec.
- Test a provider, size, or aspect ratio before a full `/gm-asset` run.
- Remove a solid background before source-sheet curation.
- Process one source sheet while debugging extraction.
- Select one extracted candidate into a runtime asset path.

If you want to update visual targets used by `/gm-evaluate`, re-run
`/gm-asset` rather than editing generated images directly.
