---
name: background-map
description: Generate and validate a fixed-viewport background, map base, or parallax plate as a ready-to-load Texture2D.
---

# Background Map Asset

Use this skill for a runtime background, map base, parallax plate, fixed battle
background, title illustration, or other fixed-viewport scenic asset. Do not
use it for scene references, actors, foreground props, UI, or collision-bearing
geometry. Background-map produces non-pixel-art scenic images only: do not
request pixel art or use nearest-neighbor processing to imitate it.

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `background-map`. Run
`standalone_validation.compile_and_validate()` before returning it. The runner
checks the family binding and stable path at L0, the PNG at L1, the registered
`single -> Texture2D` route at L2, and real headless Godot load plus Texture2D
structure at L3/L4; it overwrites rather than trusts caller-supplied validation.
It begins from the shared result schema and checker, then proves the result.

This skill can be invoked directly or by an orchestrator; its request and
result are identical in both cases. Do not read or write `ASSETS.md`, tags,
stage state, generated manifests, or dispatch state.

## Source, Reference, and Provider Contract

References are optional. With no references, generate from the brief. With one
or more references, validate every declared local path is a readable image,
preserve its `canonical`, `style`, or `screen` role, and send the actual image to
the selected provider. A textual path, a prompt-only description, or a silently
omitted reference is a failure.

Resolve a request `res://` reference against the project root before provider
dispatch, while retaining the request path and role in provenance. Providers
receive the resulting local image path as an attachment, never the literal
`res://` text.

Use exactly the declared `provider` (`native`, `codex`, `gemini`, or `openai`).
Do not substitute another provider. Read its provider document before source
generation. If it cannot execute its declared image-attachment path for every
reference, STOP with `validation.passed: false` and create no final runtime
asset.

For Codex, the source report must include this exact auditable trace shape:

```json
{
  "provider_trace": {
    "provider": "codex",
    "coding_model": "<configured coding model>",
    "reasoning": "<configured reasoning effort>",
    "tool_call_id": "<image_gen call identity>",
    "image_model_identity": "runtime_reported|not_exposed_by_subscription_runtime",
    "referenced_image_paths": ["<actual local image attachment path>"]
  }
}
```

When `image_model_identity` is `runtime_reported`, include non-empty
`image_model`. Do not substitute a generated-path string, a prose explanation,
or a role-only record for this trace.

For every attempt, retain these project-local records under
`.godotmaker/asset-generation/`:

1. `prompts/<asset_id>.txt` with the fixed viewport, target aspect and
   orientation, scene role, viewpoint, layer responsibility, style language,
   reference roles, and invariants to preserve.
2. `sources/<asset_id>_source.png`, the unmodified provider or user source.
3. `reports/<asset_id>_source.json`, recording provider, model, reasoning where
   the runtime exposes it, real reference attachments with roles, source path,
   and provider trace or failure.
4. `reports/<asset_id>_finalize.json`, the deterministic finalization report.
5. `reports/<asset_id>_validation.json`, written by the validation runner on a
   fully passing ladder. Do not edit it; run validation again after any
   regeneration.

The visual source may only be a selected provider output or a user-provided
source/reference. Never create art with Pillow, System.Drawing, ImageMagick,
SVG, canvas, Godot drawing, inline scripts, color blocks, placeholders, or fake
atlases/animations. Project-owned deterministic tools may only process an
existing real image.

## Produce

1. Use the brief and actual style or screen references to establish the scene
   role, viewpoint, target aspect, orientation, layer responsibility, and
   non-pixel-art style language.
2. Generate a source image with no gameplay actors, pickups, hazards, UI,
   labels, logos, watermarks, or text.
3. Run the existing deterministic finalizer; do not reimplement it:

   ```bash
   python tools/asset_image_finalize.py \
     --source .godotmaker/asset-generation/sources/<asset_id>_source.png \
     --out assets/generated/background-map/<asset_id>/<asset_id>.png \
     --label <asset_id> \
     --require-aspect <WIDTH:HEIGHT> \
     --resize <WIDTHxHEIGHT> \
     --report .godotmaker/asset-generation/reports/<asset_id>_finalize.json
   ```

   The source aspect must pass before resizing. On failure, keep the attempt
   incomplete and do not claim readiness.
4. Keep the raw source, final PNG, provider report, and finalize report as
   provenance. The orchestrator derives its stable `source_layout: single` and
   `godot_artifact: Texture2D` handoff from this result; this Skill never writes
   manifests itself.
5. Verify that Godot can import and load that PNG as `Texture2D`. When
   `GM_EVAL_GODOT_PATH` or `GODOT_BIN` is configured, invoke that exact
   executable; otherwise invoke the project-configured `godot` command.

Godot's normal PNG import is the native resource path for this family; do not
create a redundant `.tres` merely to wrap the image.

## Result

Return the shared generic result with one `runtime` output:

```json
{
  "asset_type": "background-map",
  "outputs": [{
    "role": "runtime",
    "name": "<asset_id>",
    "path": "res://assets/generated/background-map/<asset_id>/<asset_id>.png",
    "godot_type": "Texture2D"
  }],
  "sources": [{
    "path": "res://assets/generated/background-map/<asset_id>/<asset_id>.png",
    "layout": "single"
  }],
  "previews": [],
  "validation": {
    "passed": true,
    "levels": {"L0": true, "L1": true, "L2": true, "L3": true, "L4": true}
  }
}
```

Use the requested stable asset id in every path. A failed aspect, import, or
load check must return `validation.passed: false` with an explanatory note;
never claim a failed background is ready. Provider/reference failure must return
the same failed result with no runtime output.

Emit that generic result JSON directly as the final response, including for a
STOP. Do not write `ASSET_RESULT.json`, a manifest, or a linked result file in
place of returning the JSON: direct callers consume the response itself.
