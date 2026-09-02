---
name: screen-reference
description: Generate, finalize, and validate a non-pixel-art full-screen visual reference for scene direction and evaluation, without producing a runtime asset.
---

# Screen Reference Asset

Use this Skill for a full-screen visual anchor for scene direction and visual
evaluation. It is reference-only: it does not create a runtime Godot resource,
has no `godot_artifact`, and must not enter worker runtime handoff.
Do not compile it to `Texture2D`, `AtlasTexture`, or any other native runtime
resource.

Do not request or produce pixel art. Do not use nearest-neighbor scaling to
imitate pixel art. Raw visual material may come only from the selected image
provider or an explicitly supplied user source/reference. Do not create art,
placeholder images, colour blocks, SVGs, canvases, Godot drawings, or image
assets with ad-hoc scripts.

## Invocation

Accept one request matching the shared Asset Skill request schema in
`.godotmaker/asset-runtime/schema/asset-skill-request.schema.json`. Require
`asset_type` to be `screen-reference`. `references` is optional. When it is
present and non-empty, every `{ role, path }` is a required visual input:

1. resolve the path inside the project and require a readable image before
   calling a provider;
2. preserve its `canonical`, `style`, or `screen` role in the prompt and
   source-generation provenance;
3. attach the actual image bytes to the selected provider request. A path
   mentioned only in text is not an attachment;
4. STOP before writing a raw source or final output when an input is unreadable
   or the selected provider cannot attach it.

Use the configured provider named by the request or production brief. `native`,
`codex`, `gemini`, `openai`, and `wan` are binding selections: execute that documented
path or STOP. Never silently switch providers. For `codex`, non-empty
references require the `image_gen` call's `referenced_image_paths` argument.

This Skill can be invoked directly or by an orchestrator with the same contract.
Do not read or write `ASSETS.md`, tags, stage state, generated indexes, or
worker dispatch state. The `/gm-asset` manager later registers its validated
generic result directly in the matching catalog row.

## Production contract

`spec` must declare the target `size` (`WIDTHxHEIGHT`) and `aspect_ratio`
(`WIDTH:HEIGHT`). Build a prompt that names the game and screen purpose,
camera/viewpoint, visible gameplay objects, approximate layout, HUD or UI safe
regions, style language, target aspect/orientation, and each supplied reference
role. Do not add labels, callouts, debug overlays, or unrequested objects.

Treat object positions and sizes in the provider image as approximate visual
direction. The raw provider source is not required to satisfy the final canvas
or object pixel dimensions. Once the provider returns a readable image, claim
it to the deterministic raw-source path before applying final canvas checks.
Pixel-exact runtime sprite dimensions remain the responsibility of runtime
Asset Skills such as `compact-prop-pack` and `fx-bundle`, not this reference.

For every accepted image, retain these deterministic paths:

1. prompt: `.godotmaker/asset-generation/prompts/<asset_id>.txt`;
2. raw provider source: `.godotmaker/asset-generation/sources/<asset_id>_source.png`;
3. source/provider report: `.godotmaker/asset-generation/reports/<asset_id>_source.json`;
4. final reference: `references/<asset_id>.png`;
5. finalize report: `.godotmaker/asset-generation/reports/<asset_id>_finalize.json`.

For `openai`, `gemini`, and `wan`, write a source-generation spec using
`reference_inputs` for role-preserving references, then run:

```bash
python tools/asset_source_generate.py --spec <spec.json>
```

The successful source report must identify the selected provider and model,
actual reference attachment count, each reference role/path/hash, raw source,
and prompt path. For `native` and `codex`, use their provider documents and
write an equivalent JSON report before finalization. It must contain `ok: true`,
`asset_id`, `raw_source`, `raw_source_sha256`, `reference_attachment_count`, and a
`generation` object with `tool: "image_gen"`. When references are supplied,
that object must also record `reference_attachment_argument:
"referenced_image_paths"` and the matching attachment count, and each
`reference_inputs` item must preserve `role`, `path`, `sha256`, and
`attached: true`. A missing report, provider failure, or absent attachment
evidence is a STOP.

Finalize only the provider/user source with the existing controlled tool:

```bash
python tools/asset_image_finalize.py \
  --source .godotmaker/asset-generation/sources/<asset_id>_source.png \
  --out references/<asset_id>.png \
  --label <asset_id> \
  --require-aspect <WIDTH:HEIGHT> \
  --resize <WIDTHxHEIGHT> \
  --fit cover \
  > .godotmaker/asset-generation/reports/<asset_id>_finalize.json
```

The explicit `cover` fit proportionally scales and center-crops the raw image
to fill the final canvas without transparent padding. After finalization,
require the report dimensions to equal `spec.size` and validate the finalized
reference. If aspect validation, finalization, or finalized-output validation
fails, STOP. Keep the captured finalize report as result evidence; the
reference result has no runtime artifact and is registered as `source_ready`
by the manager.

## Result

Return the shared generic result with one reference output, its deterministic
raw source, no `godot_type`, and no runtime outputs. Run
`standalone_validation.compile_and_validate()` before returning it; it replaces
any caller-supplied validation claim and proves the stable final reference and
raw source are readable PNG files.
It begins from the shared result schema and checker, then proves the result.

```json
{
  "asset_type": "screen-reference",
  "outputs": [{
    "role": "reference",
    "name": "<asset_id>",
    "path": "references/<asset_id>.png"
  }],
  "sources": [{
    "path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
    "layout": "single"
  }],
  "previews": [],
  "validation": {
    "passed": true,
    "levels": {"L0": true, "L1": true}
  }
}
```

L2-L4 are not applicable because a screen reference has no Godot artifact and
is never handed to a worker. Preserve the provider and finalize reports so the
manager and private Eval can audit the production gates separately; L5 is not
applicable and L6 is visual/semantic review.
