# Background Removal

Background removal CLI, prompting strategy, troubleshooting, and batch mode.
Read when generating or processing a 2D visual asset that needs transparency.

Applies to: characters, props, icons, UI elements, and selected 2D source-sheet outputs.
Does NOT apply to: textures or backgrounds.

**CRITICAL: Never prompt for "transparent background"; the generator draws a checkerboard. Always use a solid color background, then remove it.**

## BG color strategy

Pick a prompt bg color that is:

1. distinct from the subject so the mask separates cleanly
2. close to the expected in-game environment so residual fringe blends naturally

Examples: forest game -> `dark-green`; sky/water -> `steel-blue`; dungeon ->
`dark-gray`; generic -> `medium-gray`.

Avoid pure chromakey colors like `#00FF00`; they create unnatural green
fringing.

The prompt must include a solid flat background color:

```text
{name}, {description}. Centered on a solid {bg_color} background.
```

## GPU acceleration

The script auto-detects NVIDIA GPUs and uses CUDA when available. If a GPU is
present but CUDA deps are missing, it prints a warning and falls back to CPU.

Required for GPU:

```bash
pip install onnxruntime-gpu nvidia-cudnn-cu12==9.*
```

Verify CUDA:

```bash
python -c "import onnxruntime; print(onnxruntime.get_available_providers())"
```

CPU fallback works but is slower for batch processing.

## CLI

Dependencies live in `tools/requirements.txt`. If rembg is not installed:

```bash
pip install rembg[gpu,cli]   # use rembg[cpu,cli] if no GPU
```

### Single image

```bash
python3 tools/rembg_matting.py \
  assets/img/car.png -o assets/img/car_nobg.png --preview
```

### Batch

```bash
python3 tools/rembg_matting.py \
  --batch source_dir/ -o clean_dir/
```

- BiRefNet session loads once for the batch.
- BG color is sampled per image from corners.
- Same flags apply to all images.

## Modes

`-m auto` selects based on mask coverage:

| Mode | Auto when | Behavior |
|------|-----------|----------|
| `trust` | 5-70% mask fg | Keep all mask-fg pixels, aggressively remove bg |
| `adapt` | >70% mask fg | Adaptive threshold; fg pixels can be removed if bg-colored |
| `color` | <5% mask fg | Color matting only |

## Reading output

```text
BG color: RGB(74, 106, 65)
Mask: fg=52480 (20.0%)
Regime: trust (bg_thresh=0.05)
```

**BG color wrong:** regenerate image with subject centered on a solid
background.

**Transparent: 0:** background detection failed.

## QA verification

Always pass `--preview` when removing backgrounds. This generates a `_qa.png`
file with the transparent result composited on a contrasting solid color. Read
the `_qa` image to check for remnants, fringing, or missing foreground. Delete
the `_qa` file after inspection.

Claude's image reader cannot evaluate transparency directly. Use the preview
for visual verification.

## Fixing results

Read output PNG. Then:

**Background remnants:** `--bg-thresh 0.03`.

**Missing foreground:** `-m trust`. Or in adapt: `--fg-thresh 0.30`.

**Fringing:** `-m adapt --fg-thresh 0.10`. Also try `--bg-thresh 0.03`.
Regenerate with a more distinct bg color if fringing persists.

**Mask failed:** regenerate the source image.

Tune `--bg-thresh` and `--fg-thresh` together to trade off bg removal and fg
preservation.

For batch: tune on a single image first, then apply flags to the full batch.
