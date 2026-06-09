# Character Bundle Production Unit

Use this unit for player characters, enemies, NPCs, summons, bosses, and
recurring creatures.

## Inputs

1. Visible canonical references or `STYLE.md` seed
2. Current-tag ASSETS.md rows
3. Character role and required actions
4. Canonical reference paths when available

## Steps

1. Generate or use one canonical identity source.
2. Finalize the accepted canonical reference with
   `tools/asset_image_finalize.py`.
3. Make the canonical visible before derivative actions when the provider
   supports image references.
4. Generate one body action source per action.
5. Generate detached projectile, slash, muzzle, dust, aura, pickup, and impact
   effects as separate FX sources.
6. Process body actions with `tools/asset_action_process.py`.
7. Build frame-output manifest entries with
   `tools/asset_action_manifest_entry.py`.
8. Write one report with canonical, action, frame, GIF, and manifest paths.

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

When `--final-dir` is used, `--final-prefix` is required. The tool writes
runtime frame files as `<final-prefix>_<frame-name>.png` unless the frame name
already starts with `<final-prefix>_`.

For later body actions, add
`--scale-reference-metadata <accepted_idle_or_run_metadata.json>`.

Create frame-output manifest entries:

```bash
python tools/asset_action_manifest_entry.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --source-entry <character_action_source_entry.json> \
  --asset-id <frame_output_asset_id> \
  --project-root . \
  --out <frame_output_entry.json>
```

Reject processed outputs with non-empty `edge_touch_frames`.

## Defaults

1. idle: `2x2`, body, feet or bottom anchor
2. run/walk: `2x2` or `2x3`, body, feet anchor
3. attack/shoot/cast body: `2x2` or `2x3`, body
4. hurt: `2x2`, body
5. death/transformation: `2x3`, `2x4`, or `3x3`
6. four-direction top-down locomotion: `4x4`

## Outputs

1. canonical source and final reference
2. action source sheets
3. processed frame PNGs
4. delivery sheet or frame sequence
5. GIF preview
6. action metadata
7. manifest entry JSON files
