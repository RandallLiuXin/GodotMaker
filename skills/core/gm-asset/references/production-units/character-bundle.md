# Character Bundle Production Unit

Use this unit for player characters, enemies, NPCs, summons, bosses, and
recurring creatures.

## Inputs

1. Visible canonical references or `STYLE.md` seed
2. Current-tag ASSETS.md rows
3. Character role and required actions
4. Canonical reference paths when available
5. `character_portrait` rows when present
6. Visual Asset Contract runtime size for gameplay display

## Steps

1. Generate or use one canonical identity source.
2. Finalize the accepted canonical reference for identity reuse with
   `tools/asset_image_finalize.py`.
3. Make the canonical visible before derivative actions when the provider
   supports image references.
4. Generate one body action source per required action.
5. Generate detached projectile, slash, muzzle, dust, aura, pickup, and impact
   effects as separate FX sources.
6. Process body actions with `tools/asset_action_process.py`, writing runtime
   frames into `assets/generated/character-bundle/<asset_id>/`.
7. Write action metadata beside the delivery sheet in the same directory.
8. Write one report with canonical, action, frame, GIF, and entry-draft paths.
9. Use processed action frames or delivery sheets as runtime character assets.
10. Write `source_layout.type: grid_sheet` in runtime character animation
    stable entries.
11. Generate display-sized single images for `character_portrait` rows.
12. Keep runtime body frames at or above the Visual Asset Contract gameplay
    display size.

## Prompt Contract

For the canonical:

1. full body
2. neutral readable pose
3. stable silhouette
4. solid `#FF00FF` background
5. no text or UI

For each body action:

1. one action only
2. exact grid
3. same character identity
4. same costume and palette
5. consistent body scale
6. stable feet or bottom anchor
7. no detached wide FX in the body sheet

## Post-Processing

Finalize the canonical source:

```bash
python tools/asset_image_finalize.py \
  --source <canonical_source.png> \
  --out <canonical_final.png> \
  --background magenta \
  --resize <WIDTHxHEIGHT>
```

Process each action source:

```bash
python tools/asset_action_process.py \
  --source <action_source.png> \
  --out-dir <processed_dir> \
  --grid <COLSxROWS> \
  --names <frame_names> \
  --kind body \
  --final-dir <runtime_dir> \
  --final-prefix <asset_id>
```

If grid processing rejects an action source for edge-touch, rerun the same
command with `--recover-edge-touch`.

When `--final-dir` is used, `--final-prefix` is required. The tool writes
runtime frame files as `<final-prefix>_<frame-name>.png` unless the frame name
already starts with `<final-prefix>_`.

For later body actions, add
`--scale-reference-metadata <accepted_idle_or_run_metadata.json>`.

Use `--final-dir assets/generated/character-bundle/<asset_id>/` and
`--final-prefix <asset_id>`, so the tool writes the delivery sheet as
`<asset_id>_sheet.png` and each runtime frame as `<asset_id>_<frame>.png` inside
the stable output directory.

Build the action support metadata and the stable entry draft in one step:

```bash
python tools/asset_action_entry_draft.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family character-bundle \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

The builder writes the support metadata to
`assets/generated/character-bundle/<asset_id>/<asset_id>.json` and a draft with
`source_layout.type: grid_sheet` at `processing_status: source_ready`. It rejects
a frame count that disagrees with the listed frames, any non-empty
`edge_touch_frames`, a missing scale reference, and any runtime path outside the
stable output directory — do not hand-write either file to get past those checks.

The draft carries no `godot_artifact`. A `grid_sheet` becomes worker-consumable
only once the `SpriteFrames` compiler and the L0-L4 runner exist; neither is
implemented, so the asset stops here.

Keep `source_recovery.report` and `source_recovery.archived_source_path` when
recovery is used.

## Defaults

1. Use `2x4` or larger grids for body loops.
2. Use `3x4`, `4x4`, or larger grids for locomotion.
3. Use `3x4`, `4x4`, or larger grids for expressive body actions.
4. Use `2x3` or larger grids for short reactions.
5. Record `fps`, `loop`, and frame names in action metadata.
6. Choose frame names from the brief and ASSETS rows.

## Outputs

1. canonical source and final reference
2. portrait or display-slot final images when `character_portrait` rows exist
3. action source sheets
4. processed frame PNGs
5. delivery sheet or frame sequence
6. GIF preview
7. action metadata support file beside the delivery sheet
8. stable entry drafts
