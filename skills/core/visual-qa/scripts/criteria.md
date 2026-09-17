## Design Rule Checks

`/gm-evaluate` builds its Question-mode context with
`tools/design_rules.py build-request`, which lists every rule the project's
`DESIGN.md` states, each with a `rule_id` and a `required` / `normal` marker.
When the caller supplies such a rule list:

- Answer **every** applicable rule by its `rule_id`. A rule you did not answer
  is a rule that was never checked.
- Per rule report `verdict` (`pass` | `fail` | `uncertain`), the observable
  evidence in the capture, `confidence` (`high` | `medium` | `low`), and the
  capture you read it from. Report a rule marked `N/A` as `not_applicable`.
- Report `uncertain` when the capture cannot settle the rule. Do not round an
  `uncertain` up to `fail` or down to `pass`.
- If the capture shows the rule both ways across frames or regions, say so and
  set `evidence_conflict`.
- Do **not** assign severity and do not decide what blocks the tag.
  `tools/design_rules.py grade` derives that from the rule text and your
  reported confidence, so the same evidence always lands on the same verdict.
- Judge each rule on its own observable terms. Overall resemblance to a
  reference image is never a criterion: two captures in the same visual
  language with different compositions both pass, and copying a reference's
  composition does not excuse a rule violation.
- The rule list is the project's design contract. Never supplement it from
  another style document, and never infer a rule the list does not state.

Scene content requirements supplied alongside the rules stay a separate,
independent check — a capture can satisfy every design rule and still miss its
required visible content.

## Acceptance Gate Rules

Use these rules before choosing the final verdict:

- `fail` means an acceptance criterion is not visibly satisfied, or a
  visual/logical/motion bug blocks operation, state truth, or layout stability.
- `warning` means the acceptance criteria pass, and a material non-blocking
  issue was observed while checking the caller-provided context. Do not expand
  the review scope to search for warnings.
- `pass` means the acceptance criteria pass and remaining differences are
  minor/style-only.
- If Task Context and reference disagree, evaluate against Task Context and
  mention the disagreement.
- A reference image is provenance and auxiliary context: it shows where the
  visual language came from. It is never the acceptance bar. When a reference
  and the project's design rules disagree, the rules win and the disagreement
  is reported.
- Pure reference/style mismatch should be a `note`, not a failing verdict.
- Evaluate visible screenshots and caller-provided `Verify:` criteria only.
  Do not infer prior play history unless `Verify:` asks for it.

## What to Look For

### Implementation Quality

Flag these as `fail` only when they block acceptance, operation, state truth, or
layout stability:

- Grid/uniform placement when reference shows organic arrangement
- Uniform/default scale when reference shows varied, purposeful sizing
- Flat composition when reference has depth and layering
- Stretched, tiled, or carelessly applied materials
- Objects unrelated to environment
- Camera framing misses required context or blocks operation

### Visibility Scope

Only report visibility, contrast, or readability findings when the caller's
`Verify:` criteria explicitly require the object, UI, or text to be visible or
readable.

### Visual Bugs

- Z-fighting
- Texture stretching, tiling seams, missing textures
- Geometry clipping
- Floating objects that should be grounded
- Shadow artifacts
- Lighting leaks through opaque geometry
- Culling errors
- UI overlap, truncated text, offscreen elements

### Logical Inconsistencies

- Impossible orientations
- Scale mismatches
- Misplaced objects
- Broken spatial relationships
- UI showing impossible values

### Placeholder Remnants

- Primitive geometry contrasting with surrounding detail
- Default Godot materials
- Debug artifacts in normal gameplay captures
- Collision overlay mismatch in `--debug-collisions` captures
- Orphaned UI elements at default positions

### Motion & Animation

In dynamic mode, compare consecutive frames:

- Stuck entities
- Jitter/teleportation
- Sliding
- Physics breaks
- Animation mismatches
- Camera issues
- Collision failures
- Timing mismatches
