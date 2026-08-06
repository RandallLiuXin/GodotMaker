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

The request owns the runtime output set. `scene-prop-set` and
`compact-prop-pack` use their fixed `spec.slots`; `platform-strip` uses
`spec.segments` and its selected `spec.kind`; `ui-kit` and `card-kit` use their
`styleboxes`, `atlas_regions`, and optional `theme`. Other runtime families
derive their single runtime output from the request. They do not accept a
parallel `spec.outputs` declaration. The command rejects missing, duplicate,
extra, role-mismatched, or type-mismatched runtime outputs before it writes any
row. Runtime files must be project-local, present, loadable by Godot, and match
their declared type.

Reference outputs returned by runtime families are validated source evidence,
not catalog rows. Only reference-only families such as `screen-reference`
register a `source_ready` row; their reference path is project-relative (for
example `references/title_screen.png`) and never enters worker handoff.

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
