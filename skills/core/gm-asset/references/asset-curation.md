# Asset Curation Reference

Use this file for shared candidate-selection states and ASSETS.md handoff
rules. Use the assigned production-unit doc for extraction and post-processing
commands.

## Scope

Use curation to:

1. Track generated source sheets and extracted candidates.
2. Select final runtime assets from candidates.
3. Mark unsuitable sources for regeneration.
4. Record canonical, variant, selected, and rejected candidates.

Do not bind an irregular source sheet, UI kit, object atlas, or full scene
reference directly to a gameplay-visible ASSETS.md row.

## Curation States

Candidate states:

1. `candidate`
2. `selected`
3. `variant`
4. `rejected`

Source outcomes:

1. `selected`
2. `needs_curation`
3. `needs_regeneration`
4. `rejected`

## Curation Record Shape

Write curation reports under `.godotmaker/asset-generation/curation/`:

```json
{
  "version": 1,
  "asset_id": "<source_asset_id>",
  "tag": "<tag>",
  "source_path": ".godotmaker/asset-generation/sources/<source>.png",
  "strategy": "<strategy>",
  "status": "needs_curation",
  "candidates": [
    {
      "candidate_id": "<source>.<candidate>",
      "name": "<candidate>",
      "path": ".godotmaker/asset-generation/curation/<source>/<candidate>.png",
      "state": "candidate",
      "bbox": [0, 0, 0, 0],
      "role": "<runtime role>",
      "final_path": "assets/<path>.png"
    }
  ],
  "rejected": [],
  "notes": ""
}
```

## Canonical Selection

1. Select one canonical reference for each generated character, enemy family,
   UI family, prop family, and environment family.
2. Use `canonical_reference` for derivative assets.
3. Use `derived_from` for animation frames, UI states, enemy variants, prop
   variants, and VFX derived from a source.
4. Mark conflicting alternatives as `variant` or `rejected`.
5. Record rejected candidates in the curation report.

## ASSETS.md Handoff

Only update ASSETS.md rows to `generated` when:

1. The row's `File Path` points to a final runtime asset.
2. The matching manifest entry is `processed` or `ready`.
3. The matching curation report is `selected` or no curation is required.
4. The Visual Asset Contract names the canonical or derived source.

If curation is incomplete, leave the row `MISSING` or mark the source entry as
`needs_curation` in the manifest.
