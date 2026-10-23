# Asset Planning Reference

Plan current-tag production units from `ASSETS.md`, `PLAN.md`, `DESIGN.md`,
`STRUCTURE.md`, and `SCENES.md`. The `/gm-asset` manager owns one public request
per unit and names its complete expected logical output set in that family's
native contract:
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
5. Keep logical output names unique across the whole Asset Table, not only
   within the current tag. Snapshot resolution matches rows by name across all
   tags, and prior-tag rows are immutable — a later-tag redesign of an asset
   must plan a new logical name instead of repeating a prior-tag row name. A
   completed row is owned by its production unit and must never be reused by a
   different request.
6. Dispatch independent units in batches of at most three.
7. Plan Asset Table rows only for registered logical outputs. For a runtime
   family, each row name must match a declared runtime output name. Canonical
   images, action sheets, source grids, and other provenance remain in the
   request, result, and reports; do not plan them as rows.
8. Record `family=<asset_type>` in every planned row's Generation Params.
   Re-registration ownership of completed reference rows is checked against
   that field; a row without it cannot be re-registered by its own unit.
9. Plan a character portrait for a UI display slot as its own `portrait`
   unit. When the character has an identity anchor, such as the canonical
   image in its `character-bundle` result, attach it as a `canonical`
   reference. Never route a portrait to `background-map`, which owns scenic
   backgrounds only, or add it to a `character-bundle`, whose one runtime
   output is its `SpriteFrames`.
10. Before dispatch, write the complete request to
   `.godotmaker/asset-generation/<asset_id>-request.json`, validate it with
   `tools/asset_skill_contract_check.py --kind request`, and then treat that
   file as immutable. The producer reads this manager-owned request and writes
    the matching `.godotmaker/asset-generation/<asset_id>-result.json`; it never
    creates, derives, or rewrites the canonical request.

## UI-kit pre-dispatch planning

`ui-kit` is the one family whose complete request depends on reference-derived
Theme tokens. The manager must close that dependency before dispatch; an
`asset-producer` may not derive or repair the canonical request.

1. Build the non-derived request fields (`asset_type`, `asset_id`, `brief`,
   `references`, and pinned `provider`) in
   `.godotmaker/asset-generation/work/<asset_id>/planning-request.json`. This is
   a manager-owned draft, not the canonical request.
2. The manager must not read reference image binaries. Dispatch `visual-qa` in
   Question mode with every request reference and ask it to report palette,
   contrast, shape, outline, shadow, material, and any contradiction with the
   verbatim `brief` rules. Use that inspection as evidence; a contradiction is
   a blocker. If inspection cannot run, stop the unit before request creation.
3. Write the manager-owned
   `.godotmaker/asset-generation/work/<asset_id>/theme_plan.json` from the
   selected rules and inspected evidence. It must contain the exact Theme
   tokens and observations required by the `ui-kit` Asset Skill; it may resolve
   stated rules but may not add a new visual rule.
4. Before the canonical request exists, run the deterministic UI-kit planners
   in this order against the draft and manager-owned Theme plan:

   ```powershell
   python tools/asset_ui_source_sheet_plan.py --request .godotmaker/asset-generation/work/<asset_id>/planning-request.json --scheme .agents/skills/ui-kit/references/source-sheet-scheme.json --rendering-medium "<theme_plan rendering_medium>" --out .godotmaker/asset-generation/work/<asset_id>/source_sheet_plan.json
   python tools/asset_ui_stylebox_plan.py --source-sheet-plan .godotmaker/asset-generation/work/<asset_id>/source_sheet_plan.json --theme-plan .godotmaker/asset-generation/work/<asset_id>/theme_plan.json --asset-id <asset_id> --out .godotmaker/asset-generation/work/<asset_id>/stylebox_plan.json
   python tools/asset_ui_theme_recipe.py --theme-plan .godotmaker/asset-generation/work/<asset_id>/theme_plan.json --asset-id <asset_id> --out .godotmaker/asset-generation/work/<asset_id>/theme_recipe.json
   ```

5. Build the complete canonical `spec` from those plans. Copy
   `stylebox_plan.styleboxes` exactly into `spec.styleboxes`; derive the complete
   icon `required_regions` / `atlas_regions` declarations from the source plan;
   declare all required states; and point `spec.stylebox_plan_path` and
   `spec.theme.recipe_path` at their final files under
   `res://assets/generated/ui-kit/<asset_id>/`. Then write and validate the
   canonical request as Planning Rule 9 requires. Never write it earlier and
   patch it after dispatch.
6. List the four manager-owned planning files in the producer brief. The
   producer reads them without modification, publishes byte-identical copies
   of `theme_plan.json`, `source_sheet_plan.json`, `stylebox_plan.json`, and
   `theme_recipe.json` under `assets/generated/ui-kit/<asset_id>/`, and declares
   those stable `res://` copies as result sources. The generation-workspace
   files remain the planning audit; only the stable copies satisfy L1 and enter
   the reusable result.

## Visual Authority

`DESIGN.md` is the project's visual specification authority for every generated
visual unit. Reference images are visual conditioning: they carry identity,
palette, and continuity into a provider call, but they never outrank, extend,
or replace a `DESIGN.md` rule.

`DESIGN.md` is also the only visual document the asset stage reads. A project
may still carry an older visual file beside it; that file is closed history.
Do not open it, and never let its text enter a brief, a prompt, a reference
selection, or provenance.

## Design Rule Selection

Every generated visual unit carries its applicable `DESIGN.md` rules verbatim
in `request.brief`, next to the content brief. Copy the selected headings and
their bullets as written. Do not summarize them, do not rewrite them as tokens
or JSON, and do not persist a derived style file: scoped retrieval selects
sections of the one `DESIGN.md`, it never produces a second style source.

Select by asset type:

| Asset type | Visual Identity | Image Style dimensions | UI Visual Language | Do / Don't |
| --- | --- | --- | --- | --- |
| `background-map` | yes | 1-9 | no | yes |
| `character-bundle` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `fx-bundle` | yes | 1, 2, 3, 4, 5, 6, 9 | no | yes |
| `compact-prop-pack` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `scene-prop-set` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `platform-strip` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `portrait` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `tileset` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `ui-kit` | yes | 1, 2, 3, 4, 5, 6, 8, 9 | yes | yes |
| `card-kit` | yes | 1, 2, 3, 4, 5, 6, 8, 9 | yes | yes |

`background-map` owns the frame, so it takes all nine dimensions. A subject
family produces sprites a scene composes later, so dimension 8
(Composition And Visual Hierarchy) is not its authority. A UI family produces
flat reusable surfaces, so dimension 7 (Space, Perspective, And Depth) is not
its authority. `ui-kit` and `card-kit` additionally take UI Visual Language;
their technical output shape still comes only from the Asset Skill contract.

Skip any selected section whose body is `{unspecified}` or `N/A`. Select
nothing beyond the row above — the brief stays bounded, and it carries exactly
one style source.

## Optional Image Inputs

Do not create a foundation image or a per-scene reference. A unit may use a
user-provided character identity anchor or style image, or a previously
generated canonical image already recorded in production evidence, as an
optional provider input. When no such image exists, generate the requested
runtime unit directly from its applicable `DESIGN.md` rules.

Optional images are conditioning and provenance only. They do not create
`ASSETS.md` rows, do not become an evaluation target, and do not change which
`DESIGN.md` sections the unit receives.

## Reference Conflict Disposition

Decide one disposition per reference before the request is built:

1. `consistent` — the reference contradicts no selected `DESIGN.md` rule.
   Attach it in its `canonical` or `style` role.
2. `excluded_candidate` — a candidate that is in no request yet contradicts a
   selected rule. Drop it from selection and record an `excluded_reference`
   entry in the plan artifact with its path, the conflicting section heading,
   and the observed contradiction. This is the only case where a conflicting
   reference may be dropped.
3. `blocker` — a reference already in `request.references`, named by the user,
   or required by a family binding contradicts a selected rule. Keep it in the
   request and stop the unit with a locatable blocker naming the reference role
   and path plus the `DESIGN.md` section heading. Never silently drop it,
   downgrade its role, or let it override the rule.

## Completion

After standalone validation passes, call `tools/asset_result_registration.py`
with the request and result. It atomically updates all matching `ASSETS.md`
rows or none of them. `ASSETS.md` is the sole worker-facing authority.
