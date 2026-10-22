# Asset Planning Reference

Plan current-tag production units from `ASSETS.md`, `PLAN.md`, `DESIGN.md`,
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
| `screen-reference` | yes | 1-9 | yes | yes |
| `background-map` | yes | 1-9 | no | yes |
| `character-bundle` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `fx-bundle` | yes | 1, 2, 3, 4, 5, 6, 9 | no | yes |
| `compact-prop-pack` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `scene-prop-set` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `platform-strip` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `tileset` | yes | 1, 2, 3, 4, 5, 6, 7, 9 | no | yes |
| `ui-kit` | yes | 1, 2, 3, 4, 5, 6, 8, 9 | yes | yes |
| `card-kit` | yes | 1, 2, 3, 4, 5, 6, 8, 9 | yes | yes |

The two full-frame families own the frame, so they take all nine dimensions.
A subject family produces sprites a scene composes later, so dimension 8
(Composition And Visual Hierarchy) is not its authority. A UI family produces
flat reusable surfaces, so dimension 7 (Space, Perspective, And Depth) is not
its authority. `ui-kit` and `card-kit` additionally take UI Visual Language;
their technical output shape still comes only from the Asset Skill contract.

Skip any selected section whose body is `{unspecified}` or `N/A`. Select
nothing beyond the row above — the brief stays bounded, and it carries exactly
one style source.

## Visual Anchor Gate

Use user-provided assets, selected scene references, or previously generated
files already recorded in `ASSETS.md` as anchors.

When no anchor exists, plan exactly one foundation unit and nothing else: a
single `screen-reference` whose `request.brief` carries the complete
`DESIGN.md` visual contract verbatim — Visual Identity, all nine Image Style
dimensions, UI Visual Language, Do, and Don't — plus the content brief for the
screen it depicts, drawn from `SCENES.md` and `PLAN.md`. It has no reference
input, and its only style source is `DESIGN.md`. Record the selected headings
in the plan artifact as its design provenance. Collect its report, then rebuild
the plan with it as the anchor.

## Reference Conflict Disposition

Decide one disposition per reference before the request is built:

1. `consistent` — the reference contradicts no selected `DESIGN.md` rule.
   Attach it in its `canonical`, `style`, or `screen` role.
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
