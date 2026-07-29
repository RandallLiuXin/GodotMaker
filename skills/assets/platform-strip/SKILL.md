---
name: platform-strip
description: Generate non-pixel-art, horizontally repeatable platform strips from real image sources as fixed Texture2D cells or AtlasTexture regions.
---

# Platform Strip Asset

Use for collision-aligned floors, bridges, rails, pipes, terrain ledges, and long horizontal hazards. Do not use for characters, UI, compact props, full backgrounds, or pixel art.

## Contract

Accept the shared Asset Skill request schema at `.godotmaker/asset-runtime/schema/asset-skill-request.schema.json` with `asset_type: "platform-strip"`.
Use the shared result schema and checker. This skill can be invoked directly or by an orchestrator with the same contract. Do not read or write `ASSETS.md`, tags, stage state, or generated manifests.

`spec` must contain exactly:

```json
{
  "kind": "single" | "atlas",
  "grid": {"columns": 3, "rows": 1, "cell_width": 160, "cell_height": 80},
  "segments": [
    {"name": "left_cap", "role": "left_cap", "slot": [0, 0]},
    {"name": "repeat_middle", "role": "repeat_middle", "slot": [1, 0]},
    {"name": "right_cap", "role": "right_cap", "slot": [2, 0]}
  ]
}
```

Grid dimensions are positive integers. Segment names and slots are unique. Declare exactly one `left_cap`, exactly one `right_cap`, and at least one `repeat_middle`. A request without a repeatable middle segment is unsupported.

`references` is optional. With references, validate every path is readable, preserve each declared role, and pass the actual images to the selected provider. Do not replace image attachments with prompt text. If the pinned provider cannot accept the supplied images, return STOP. Without references, generate from the written brief.

Honor the requested provider exactly. `native`, `codex`, `gemini`, and `openai` never fall back to another provider. For Codex, call the image provider with `referenced_image_paths` containing each readable local reference image. If that attachment cannot be made, STOP. Record the provider, model, prompt, reference paths and roles, provider payload or trace, raw source path, and processing reports under `.godotmaker/asset-generation/`.

## Produce

1. Reject pixel-art requests. Request non-pixel-art painted, illustrated, or rendered source art. Do not use nearest-neighbor scaling.
2. Create a layout-only guide with `tools/asset_layout_guide.py` using the declared grid. The guide is not art and is not a runtime output.
3. Request one real provider source sheet with one horizontal slot per declared segment. Require a solid `#FF00FF` background, a shared walkable top height, no labels, UI, actors, text, props, or grid lines. Preserve the provider's returned pixels as the raw source even when its raster dimensions differ from the target grid.
4. Store the unmodified provider image at `.godotmaker/asset-generation/sources/<asset_id>_source.png`. Write `.godotmaker/asset-generation/reports/<asset_id>_source.json` with `ok`, `asset_id`, `provider`, `raw_source`, `raw_source_sha256`, and `generation`. `generation` records `tool: "image_gen"`, a non-empty provider output or call identifier, and the attached-reference count; when references exist it also records `reference_attachment_argument: "referenced_image_paths"`. Record every reference as `{role, path, sha256, attached: true}`. Do not create, draw, or alter visual source art with temporary scripts, Pillow, System.Drawing, ImageMagick, SVG, canvas, Godot drawing, or placeholder generation.
5. Normalize the real source only with the owned deterministic tools. First use `asset_sheet_process.py` with `--grid 1x1 --background magenta --snap-mode grid` to remove the magenta background and crop the visible source bounds. Then use `asset_image_finalize.py --resize <columns*cell_width>x<rows*cell_height>` to proportionally scale and transparently pad that cropped real source to the declared fixed grid dimensions. Save its report at `.godotmaker/asset-generation/reports/<asset_id>_normalize.json`.

6. Split the normalized source with the owned deterministic tools:

   ```powershell
   python tools/asset_sheet_process.py --source <normalized-source> --out-dir <processed-dir> --grid <columns>x<rows> --names <segment-names-in-slot-order> --background magenta --snap-mode grid --preserve-cell-bounds --report <sheet-report.json>
   ```

   Use `magenta` here even after normalization: the provider sheet may retain chroma-key pixels outside the visible AABB. Use the report to reject missing art, opaque magenta pixels, edge-touching art that breaks the declared slot, or a cell that does not retain its fixed dimensions.

7. For `kind: "single"`, publish every processed cell at `res://assets/generated/platform-strip/<asset_id>/<segment>.png` and return it as `Texture2D`.
8. For `kind: "atlas"`, create an explicit fixed-slot declaration from the processed cells. Assemble it only with `tools/asset_atlas_assemble.py`; publish `<asset_id>.png` and `<asset_id>.json` in the stable platform-strip directory. Each metadata region uses the declared slot rectangle, `pivot: [0.5, 1.0]`, and `nine_slice: null`. Compile every logical region to `res://assets/generated/platform-strip/<asset_id>/<segment>.tres` as `AtlasTexture` with zero margin.
9. Run `standalone_validation.compile_and_validate()` with exactly `GM_EVAL_GODOT_PATH` or `GODOT_BIN` when either is configured; do not search for or substitute another Godot executable. Save its actual L0-L4 result at `.godotmaker/asset-generation/reports/<asset_id>_validation.json`; do not substitute a self-reported verdict.

## Result

Return exactly one shared generic result JSON object and no prose.

For `single`, declare one `sources` entry with `layout: "single"` and one runtime `Texture2D` output per segment. For `atlas`, declare one `sources` entry for the physical atlas with `layout: "region_atlas"` and one runtime `AtlasTexture` output per segment. In both forms, declare exactly one labelled preview of the physical source image. Use only stable platform-strip paths.

If the semantic strip contract, provider contract, source art, processing report, fixed slot assembly, compiler, or Godot check cannot complete, return the shared failed result with `outputs: []`, `validation.passed: false`, and explanatory notes. Do not publish partial runtime outputs.
