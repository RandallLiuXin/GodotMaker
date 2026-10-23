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
not catalog rows. They never enter registration or worker handoff.

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

| Tool | Purpose |
|---|---|
| `asset_source_generate.py` | Calls an image provider from a JSON spec and creates source images with provenance records. |
| `asset_layout_guide.py` | Creates slot, label, and safe-margin reference images for fixed-grid source images. |
| `asset_image_finalize.py` | Checks transparency, bounds, proportions, and the final file for a single image. |
| `asset_sheet_process.py` | Removes backgrounds, slices sheets, extracts candidates, and reports on UI, icon, and prop sheets. |
| `asset_action_process.py` | Processes character or animated-effect action sheets into frames, transparent sheets, and animation reports. |
| `asset_curation_select.py` | Selects candidates from curation reports and writes them to final asset paths. |
| `asset_atlas_assemble.py` | Assembles fixed-layout PNG atlases and region metadata from explicit slot rectangles. |
| `asset_ui_source_sheet_plan.py` / `asset_ui_stylebox_plan.py` | Produces deterministic plans for UI component sheets and StyleBoxTexture compilation. |
| `asset_tileset_profile.py` | Generates TileSet profiles, atlas guidance, and native TileSet compilation recipes. |
| `asset_family_registry.py` | Prints or checks the public Asset Skill family, variant, output-type, and cardinality contracts. |

Run the common structural check with:

```bash
python tools/asset_family_registry.py --check
```

In most cases, do not chain these tools manually. Let `/gm-asset` orchestrate
them according to `ASSETS.md`, the request, and the Skill contract. Run them
directly to diagnose one source, test a fixed grid, inspect slicing output, or
reproduce a registration failure.
