---
name: portrait
description: Generate and validate one character portrait for a UI display slot as a ready-to-load Texture2D.
---

# Portrait Asset

Use this skill for one character or creature portrait shown in a UI display
slot: a character-select card, dialogue bust, profile panel, or roster entry.
The subject is the character itself, framed for a display slot larger than its
gameplay frames. Do not use it for gameplay actor animation (use
`character-bundle`), scenic backgrounds or maps (use `background-map`), or
portrait frames, card frames, and other UI chrome (use `card-kit` or `ui-kit`).

## Invocation

Accept one asset request matching the shared Asset Skill request schema in
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `portrait`. Run
`standalone_validation.compile_and_validate()` before returning it. The runner
checks the family binding and stable path at L0, the PNG at L1, the registered
`single -> Texture2D` route at L2, and real headless Godot load plus Texture2D
structure at L3/L4; it overwrites rather than trusts caller-supplied validation.
It begins from the shared result schema and checker, then proves the result.

This skill can be invoked directly or by an orchestrator; its request and
result are identical in both cases. Do not read or write `ASSETS.md`, tags,
stage state, generated manifests, or dispatch state.

## Identity, Reference, and Provider Contract

Carry every visual rule stated in `brief` into the prompt as written; it is
the visual specification for this portrait. References are optional and
condition those rules with concrete identity, palette, and continuity — they
never outrank or extend them, and a contradiction between the two is a STOP
with a blocker naming the reference role, its path, and the rule.

A character identity anchor, such as the canonical image recorded in a
`character-bundle` result, enters only as a `canonical` request reference. It
is provider input and provenance: it is never copied into `outputs`, never
registered, and never replaced by an extra generated anchor. With no
references, generate the portrait from the brief alone.

With one or more references, validate every declared local path is a readable
image, preserve its `canonical` or `style` role, and send the actual image to
the selected provider. A textual path, a prompt-only description, or a silently
omitted reference is a failure. Resolve a request `res://` reference against
the project root before provider dispatch, while retaining the request path and
role in provenance.

Use exactly the declared `provider` (`native`, `codex`, `gemini`, `openai`, `grok`, or `wan`).
Do not substitute another provider. Read its provider document before source
generation. If it cannot execute its declared image-attachment path for every
reference, STOP with `validation.passed: false` and create no final runtime
asset. For Codex, record the same `provider_trace` shape the provider document
requires, with every attached identity anchor in `referenced_image_paths`.

For every attempt, retain these project-local records under
`.godotmaker/asset-generation/`:

1. `prompts/<asset_id>.txt` with the display slot size and aspect, framing
   (bust, half body, or full body), facing, expression, reference roles, and
   identity invariants to preserve.
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
atlases. Project-owned deterministic tools may only process an existing real
image.

## Produce

1. Use the brief and any identity anchor to establish who is shown, the
   framing, facing, expression, and the display slot's aspect.
2. Generate one portrait source with exactly one subject and no UI frame,
   labels, logos, watermarks, or text. Keep the subject's identity consistent
   with the anchor when one is supplied.
3. Run the existing deterministic finalizer; do not reimplement it:

   ```bash
   python tools/asset_image_finalize.py \
     --source .godotmaker/asset-generation/sources/<asset_id>_source.png \
     --out assets/generated/portrait/<asset_id>/<asset_id>.png \
     --label <asset_id> \
     --require-aspect <WIDTH:HEIGHT> \
     --resize <WIDTHxHEIGHT> \
     --report .godotmaker/asset-generation/reports/<asset_id>_finalize.json
   ```

   The source aspect must pass before resizing. On failure, keep the attempt
   incomplete and do not claim the portrait is complete.
4. Keep the raw source, final PNG, provider report, and finalize report as
   provenance. This Skill never writes manifests itself.
5. Verify that Godot can import and load that PNG as `Texture2D`. When
   `GM_EVAL_GODOT_PATH` or `GODOT_BIN` is configured, invoke that exact
   executable; otherwise invoke the project-configured `godot` command.

Godot's normal PNG import is the native resource path for this family; do not
create a redundant `.tres` merely to wrap the image.

## Result

Return the shared generic result with exactly one `runtime` output and no
`reference` output:

```json
{
  "asset_type": "portrait",
  "outputs": [{
    "role": "runtime",
    "name": "<asset_id>",
    "path": "res://assets/generated/portrait/<asset_id>/<asset_id>.png",
    "godot_type": "Texture2D"
  }],
  "sources": [{
    "path": "res://assets/generated/portrait/<asset_id>/<asset_id>.png",
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
never claim a failed portrait is complete. Provider/reference failure must
return the same failed result with no runtime output.

Emit that generic result JSON directly as the final response, including for a
STOP. Do not write `ASSET_RESULT.json`, a manifest, or a linked result file in
place of returning the JSON: direct callers consume the response itself.
