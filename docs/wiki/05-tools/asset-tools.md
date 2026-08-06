# Asset tools

`ASSETS.md` is the sole generated-runtime catalog. Asset Skills produce a
validated generic result; they do not register per-resource records, indexes,
or worker handoff files.

## Register a completed result

`asset_result_registration.py` validates the entire request/result production
unit and atomically records every declared logical output in `ASSETS.md`.

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --request <request.json> --result <result.json> --godot-path <godot_path>
```

The request owns the output set. `scene-prop-set` uses its fixed `spec.slots`;
every other multi-output family must list `spec.outputs`, where each item has
`name`, `role` (`runtime` or `reference`), and, for runtime assets, the final
`godot_type`. The command rejects missing, duplicate, extra, role-mismatched,
or type-mismatched outputs before it writes any row. Runtime files must be
project-local, present, loadable by Godot, and match their declared type.

Reference outputs become `source_ready` and never enter worker handoff.

## Worker snapshot

Derive the minimal handoff directly from already-generated catalog rows:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --snapshot --asset-id <logical_asset_id>
```

Each returned object contains only `asset_id` and `godot_artifact` (`type` and
`path`). Do not edit generated rows or build a second index by hand.

## Production helpers

Asset source generation, image finalization, sheet processing, atlas assembly,
curation, and family validation helpers remain available to create and verify
the actual files. Their output evidence belongs in Skill reports; registration
is always the single result-to-`ASSETS.md` command above.
