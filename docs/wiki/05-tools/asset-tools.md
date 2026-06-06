# Asset tools

GodotMaker generates and processes 2D art through small Python helper scripts.
`/gm-asset` calls them automatically. You can also run them by hand to test a
single source, background-removal pass, or sheet-processing pass.

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

`rembg_matting.py` removes solid-color backgrounds from images, producing PNG
files with transparent backgrounds.

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

## Calling these by hand

You usually do not need to run these scripts directly. `/gm-asset` orchestrates
them based on `ASSETS.md` and the source-generation manifest.

Manual use cases:

- Generate one source image from a tweaked spec.
- Test a provider, size, or aspect ratio before a full `/gm-asset` run.
- Remove a solid background from a provided source image.
- Process one source sheet while debugging extraction.

If you want to update visual targets used by `/gm-evaluate`, re-run
`/gm-asset` rather than editing generated images directly.
