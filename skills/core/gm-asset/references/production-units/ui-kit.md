# UI Kit Production Unit

Use this unit for reusable interface components such as buttons, panels, tabs,
badges, counters, HUD pieces, icons, progress bars, and scalable UI pieces.
Do not use this unit for card frames, portrait frames, rarity frames, card
slots, or card-game-specific UI assets.

## Inputs

1. Visible UI references or style seed
2. UI rows in ASSETS.md
3. Scene references that show the UI context
4. Required component names and final paths

## Steps

1. Group related UI pieces into one kit source when they share one interface
   style.
2. Use separated components on solid `#FF00FF` by default.
3. Generate the source through the provider doc.
4. Run `tools/asset_sheet_process.py --snap-mode autoslice` for separated
   components.
5. Use `--snap-mode grid` only for deliberate equal-cell layouts.
6. Choose the final artifact shape: selected component PNGs or processed UI
   atlas.
7. For selected component PNGs, run `tools/asset_curation_select.py`.
8. For processed UI atlases, write runtime atlas metadata with named regions
   and rects beside the final atlas.
9. Write stable entry drafts.
10. Mark rows generated only after final UI artifacts and metadata are ready.

## Prompt Contract

State:

1. component list
2. shared UI style
3. separated reusable pieces
4. clear spacing
5. no text or numbers
6. no composite screen
7. no card frame or portrait-frame layout
8. solid `#FF00FF` background

## Post-Processing

Extract separated UI components:

```bash
python tools/asset_sheet_process.py \
  --source <ui_source.png> \
  --out-dir <curation_dir> \
  --grid <COLSxROWS> \
  --names <component_names> \
  --background magenta \
  --snap-mode autoslice \
  --component-mode largest
```

`--grid` is required in both snap modes; in autoslice it sets the cell buckets
and per-cell names that detected components are assigned to. Match `--grid` and
`--names` to the component layout requested in the prompt.

Use `--snap-mode grid` only for deliberate equal-cell layouts.
Do not use a source kit or source panel as an independent final UI artifact.

Final selected component PNG:

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path assets/generated/ui-kit/<final_asset_id>/<final_asset_id>.png \
  --asset-id <final_asset_id> \
  --project-root .
```

Build the stable entry draft deterministically:

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

The draft stops at `processing_status: source_ready` with no `godot_artifact`.
Do not hand-write it, and do not add an artifact to make the asset look finished:
the native compiler that produces one is not implemented yet.

Final processed UI atlas:

1. Write a transparent processed atlas under
   `assets/generated/ui-kit/<asset_id>/`.
2. Write runtime atlas metadata beside the atlas.
3. Draft the entry with `--source-layout region_atlas`.
4. Leave `godot_artifact` absent until the atlas compiler lands.

## Outputs

1. UI kit source
2. extracted candidates
3. selected final UI PNGs or processed UI atlas
4. runtime atlas metadata when final is an atlas
5. curation report
6. stable entry drafts
