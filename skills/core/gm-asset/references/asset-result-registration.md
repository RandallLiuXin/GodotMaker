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

`reference` outputs are source/reference evidence, not runtime assets. They
use Runtime Type `reference`, finish as `source_ready`, and are excluded from
all worker snapshots.

## Atomic registration

After a Skill has produced a passing request/result pair, register the whole
unit in one command:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --request <request.json> --result <result.json> --godot-path <godot>
```

The command fails before changing `ASSETS.md` if the declared and returned
logical output sets differ, an output is duplicated or unknown, a path escapes
the project or does not exist, or Godot cannot load the resource as its stated
type. It never writes only a subset of a multi-output production unit.

## Worker handoff

Resolve only the assets needed by a worker:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --snapshot --asset-id <asset_id>
```

The output contains only `asset_id` and `godot_artifact.type/path`. Do not add
sources, provider data, curation reports, frame lists, atlas data, or receipts.
