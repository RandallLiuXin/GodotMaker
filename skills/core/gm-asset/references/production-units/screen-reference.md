# Screen Reference Production Unit

Use this unit for full-screen scene references and build/evaluate visual
targets.

## Inputs

1. `STYLE.md` seed or existing visual references
2. Relevant `SCENES.md` scene section
3. Matching current-tag Visual Asset Contract rows
4. Existing user-provided asset summary when available

## Steps

1. Write one prompt per scene reference.
2. Include target size and target aspect.
3. Generate a source image through the provider doc.
4. Finalize with aspect validation.
5. Write one report entry per scene.
6. Write manifest entries with `family: screen_reference` and
   `production_shape: reference_only`.
7. Write `runtime_artifact: reference` in the manifest entry.

## Prompt Contract

Describe:

1. game genre and scene purpose
2. camera/viewpoint
3. gameplay-visible objects
4. approximate layout
5. HUD or UI elements from `SCENES.md`
6. style language from existing visual references or `STYLE.md`
7. target aspect and orientation

Do not add labels, callouts, debug overlays, or extra objects.

## Post-Processing

Finalize accepted scene references:

```bash
python tools/asset_image_finalize.py \
  --source <source_path> \
  --out <final_path> \
  --label <asset_id> \
  --require-aspect <WIDTH:HEIGHT> \
  --resize <WIDTHxHEIGHT>
```

If aspect validation fails, leave the production unit incomplete.

## Outputs

1. `.godotmaker/asset-generation/prompts/<asset_id>.txt`
2. `.godotmaker/asset-generation/sources/<asset_id>_source.png`
3. `references/scene_<name>.png`
4. `.godotmaker/asset-generation/reports/<unit_id>.json`
5. manifest entry JSON
