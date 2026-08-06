# Asset Planning Reference

Plan current-tag production units from `ASSETS.md`, `PLAN.md`, `STYLE.md`,
`STRUCTURE.md`, and `SCENES.md`. A unit owns one public request and names its
complete expected logical output set in that family's native contract:
`scene-prop-set` and `compact-prop-pack` slots, `platform-strip` segments and
kind, or `ui-kit` / `card-kit` styleboxes, atlas regions, and theme. Use
`request.spec.outputs` only for a multi-output family without a native output
declaration.

## Planning rules

1. Select a first-class Asset Skill for each missing row or related output set.
2. For `platform-strip`, set `spec.kind` to `single` or `atlas`; for
   `fx-bundle`, set `spec.mode` to `static` or `animated`.
3. Record source, output, prompt, and report paths in the production brief.
4. Keep one multi-output family invocation together. Do not infer its members
   from `ASSETS.md` or from a result after generation.
5. Dispatch independent units in batches of at most three.

## Visual Anchor Gate

Use user-provided assets, selected scene references, or previously generated
files already recorded in `ASSETS.md` as anchors. When none exists, generate
one `screen-reference` first, collect its report, then rebuild the plan.

## Completion

After standalone validation passes, call `tools/asset_result_registration.py`
with the request and result. It atomically updates all matching `ASSETS.md`
rows or none of them. `ASSETS.md` is the sole worker-facing authority.
