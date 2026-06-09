# UI Kit Production Unit

Use this unit for buttons, panels, tabs, badges, counters, card frames, HUD
pieces, and icons that share one interface style.

## Inputs

1. Visible UI references or `STYLE.md` seed
2. UI rows in ASSETS.md
3. Scene references that show the UI context
4. Required component names and final paths

## Steps

1. Group related UI pieces into one kit source when style consistency matters.
2. Use separated components on solid `#FF00FF` by default.
3. Generate the source through the provider doc.
4. Run `tools/asset_sheet_process.py --snap-mode autoslice` for separated
   components.
5. Use `--snap-mode grid` only for deliberate equal-cell layouts.
6. Select final candidates with `tools/asset_curation_select.py`.
7. Write selected-candidate manifest entries.

## Prompt Contract

State:

1. component list
2. shared UI style
3. separated reusable pieces
4. clear spacing
5. no text or numbers
6. no composite screen
7. solid `#FF00FF` background

## Post-Processing

Extract separated UI components:

```bash
python tools/asset_sheet_process.py \
  --source <ui_source.png> \
  --out-dir <curation_dir> \
  --background magenta \
  --snap-mode autoslice \
  --component-mode largest
```

Use `--snap-mode grid` only for deliberate equal-cell layouts.

Select final candidates:

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path <final_path> \
  --asset-id <final_asset_id> \
  --project-root .
```

Create selected-candidate manifest entries with
`tools/asset_curation_manifest_entry.py`.

## Outputs

1. UI kit source
2. extracted candidates
3. selected final UI assets
4. curation report
5. manifest entry JSON
