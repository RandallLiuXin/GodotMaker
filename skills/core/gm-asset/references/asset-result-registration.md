# ASSETS.md Runtime Registration

`ASSETS.md` is the sole generated-asset runtime catalog. One Asset Skill result
is one production-unit handoff; its `outputs` determine the exact logical rows
that may be completed. No stable entries, manifest pointers, root indexes, or
bundle manifests participate in the active contract.

## Runtime table

Use the `Asset Table` columns `Runtime Type`, `Runtime Path`, and `Status`.
Every worker-consumable logical asset has exactly one row. Runtime Type and
Runtime Path must describe the final resource a worker loads. A PNG is valid
for `Texture2D`; `AtlasTexture`, `SpriteFrames`, `Theme`,
`StyleBoxTexture`, and `TileSet` must use their final native resource path.

For runtime families, `reference` outputs are already-validated source or
canonical evidence: they do not create a logical row, enter the registration
comparison set, or appear in worker snapshots. A reference-only family such as
`screen-reference` registers its one reference output with Runtime Type
`reference` and Status `source_ready`; its path is a project-local relative
path such as `references/title_screen.png`, not `res://`.

## Atomic registration

After a Skill has produced a passing request/result pair, register the whole
unit in one command:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --request <request.json> --result <result.json> --godot-path <godot>
```

The command fails before changing `ASSETS.md` if the declared and returned
runtime logical output sets differ, a runtime output is duplicated or unknown,
a path escapes the project or does not exist, or Godot cannot load a runtime
resource as its stated type. It never writes only a subset of a multi-output
production unit.

## Worker handoff

Resolve only the assets needed by a worker:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --snapshot --asset-id <asset_id>
```

The output contains only `asset_id` and `godot_artifact.type/path`. Do not add
sources, provider data, curation reports, frame lists, atlas data, or receipts.
