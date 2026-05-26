## Acceptance Gate Rules

Use these rules before choosing the final verdict:

- `fail` means an acceptance criterion is not visibly satisfied, or a
  visual/logical/motion bug blocks readability, operation, state truth, or
  layout stability.
- `warning` means the acceptance criteria pass, and a material non-blocking
  issue was observed while checking the caller-provided context. Do not expand
  the review scope to search for warnings.
- `pass` means the acceptance criteria pass and remaining differences are
  minor/style-only.
- If Task Context and reference disagree, evaluate against Task Context and
  mention the disagreement.
- Pure reference/style mismatch should be a `note`, not a failing verdict.
- Evaluate visible screenshots and caller-provided `Verify:` criteria only.
  Do not infer prior play history unless `Verify:` asks for it.

## What to Look For

### Implementation Quality

Flag these as `fail` only when they block acceptance, readability, operation,
state truth, or layout stability:

- Grid/uniform placement when reference shows organic arrangement
- Uniform/default scale when reference shows varied, purposeful sizing
- Flat composition when reference has depth and layering
- Stretched, tiled, or carelessly applied materials
- Objects unrelated to environment
- Camera framing misses required context or blocks readability/operation

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
