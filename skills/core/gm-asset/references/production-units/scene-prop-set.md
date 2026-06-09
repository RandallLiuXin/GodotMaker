# Scene Prop Set Production Unit

Use this unit for visible scene objects derived from a scene, map, or stage
reference.

## Inputs

1. Visible scene or map reference
2. Current-tag SCENES.md context
3. Current-tag ASSETS.md rows
4. Object names, roles, and final paths

## Steps

1. Make the source reference visible when the provider supports image input.
2. Create an object list from the reference and ASSETS.md rows.
3. Split the object list into compact packs, single images, or strips.
4. Generate the chosen sources through the provider doc.
5. Run curation for source sheets.
6. Finalize single-image objects.
7. Write manifest entries for final runtime props.

## Prompt Contract

State:

1. source reference role
2. object names
3. visual invariants from the source reference
4. style language from visible references or `STYLE.md`
5. solid `#FF00FF` background for extracted sources
6. no text, UI, labels, or annotations

## Post-Processing

Use the post-processing path selected for each generated object:

1. Compact separated props: use `tools/asset_sheet_process.py --snap-mode
   autoslice`.
2. Fixed strips: use `tools/asset_sheet_process.py --snap-mode grid`.
3. Single-image props: use `tools/asset_image_finalize.py`.
4. Selected candidates: use `tools/asset_curation_select.py`.

## Outputs

1. object source images
2. selected final props or segments
3. curation reports
4. manifest entry JSON
