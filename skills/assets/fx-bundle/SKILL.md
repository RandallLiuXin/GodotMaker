---
name: fx-bundle
description: Produce a standalone static Texture2D effect or one explicitly timed animated SpriteFrames effect.
---

# FX Bundle

Use this Skill for one detached foreground effect: a projectile, impact,
explosion, pickup, muzzle flash, slash arc, aura loop, or dust effect. It
delivers either one static `Texture2D` or one animated `SpriteFrames`; it never
delivers a `PackedScene`, particle node, trail, shader, sound, light, collision
shape, lifecycle script, or a multi-node effect.

Read `.godotmaker/asset-runtime/asset-skill-contract.md` before accepting the
request. For animation rhythm, also read
`.godotmaker/asset-runtime/animation-planning.md`; it supplies planning ranges,
not a reason to change an explicit request or reject a valid style.

Validate the shared request with `tools/asset_skill_contract_check.py`, then
validate this family with
`tools/asset_animated_bundle_contract_check.py --kind request`. At final
handoff, call the latter with `--request <request.json> --result <result.json>`.
The family checker binds `spec.mode` to the runtime type and source layout.

## Boundary and STOP

The request has `asset_type: "fx-bundle"` and `spec.mode` equal to `static` or
`animated`. References are optional. Pixel-art requests are unsupported in this
version: stop clearly rather than quantizing, nearest-neighbour scaling, or
labelling ordinary art as pixel art.

Stop only when a required input is unreadable, a declared provider or required
reference attachment is objectively unavailable, the request is contradictory,
or it asks for an unsupported deliverable such as a particle `PackedScene`.
An image-processing, import, compiler, metadata, path, or validation failure is
a production diagnostic: repair it and recheck it before deciding to stop.

This is a standalone Skill. Do not require `/gm-asset`, tags, stage state,
`ASSETS.md`, generated manifests, or worker registration. A caller may register
the returned ready entry separately.

## Request contract

- `static` has no `required_actions` or `actions`. It returns one transparent
  `Texture2D` at `assets/generated/fx-bundle/<asset_id>/<asset_id>.png` with a
  `single` source layout.
- `animated` has exactly one required action and exactly one action with the
  same name. The action has `grid.columns`, `grid.rows`, non-empty ordered
  `frame_names`, positive `fps`, explicit boolean `loop`, and one positive
  relative duration per frame. The grid contains exactly one cell per frame.
  It returns one `SpriteFrames` resource at
  `assets/generated/fx-bundle/<asset_id>/<asset_id>.tres` with a `grid_sheet`
  source layout.

Never infer timing, frame order, grid, or loop state. Reject duplicates,
missing frames, non-positive timing, mismatched durations, or mismatched grid
cell count.

## Provider, references, and provenance

1. Read the declared provider guide under
   `skills/core/gm-asset/references/providers/<provider>.md`. Execute that
   provider route only; do not silently substitute `native`, `codex`, `gemini`,
   or `openai`.
2. With no references, generate from the request's identity, gameplay role,
   direction, scale, frame count or static target, intended visual style,
   isolated foreground, solid `#FF00FF` source background, and no text or UI.
3. With references, validate every referenced path is readable, preserve its
   role, and attach the actual image to the chosen provider. A pathname in a
   text prompt is not an attachment. For Codex, resolve each `res://` reference
   to its actual local readable path and pass those exact paths through
   `referenced_image_paths`; for the scripted OpenAI/Gemini routes use
   `asset_source_generate.py` reference inputs. If the selected route cannot
   attach them, stop rather than dropping or replacing the reference.
4. For Codex, write a one-item generation plan with `require_provider_trace:
   true`, then record the actual generated image path, tool-call ID, coding
   model/reasoning, image-model identity (or
   `not_exposed_by_subscription_runtime`), reference roles, and resolved
   attachment paths. Claim that image with
   `python .godotmaker/asset-runtime/tools/codex_image_claim.py --plan
   <plan.json> --report <generated-paths.json> --project-root . --out-report
   <claim.json>`. Never directly copy a Codex image into the project. Missing
   claim evidence is a STOP.
5. Write `.godotmaker/asset-generation/traces/<asset_id>.json`. It contains
   `asset_id`; `provider.requested`, `provider.actual`, and, when applicable,
   `provider.referenced_image_paths` (the resolved local attachment paths);
   ordered `references` with the request `role`, `path`, `sha256`, and
   `attachment`; `artifacts.raw_sources`, `provider_claim`, `process_reports`,
   `final_frames`, `source_layout`, and `godot_artifact`; and ordered `steps`.
   Every artifact path is a contained `res://` or project-relative path.
   Each step records `reason`, `command_or_code`, `inputs`, `outputs`,
   `modified_files`, `diagnostic`, and `repair`. Project tools are preferred,
   but a temporary image tool or diagnostic script is allowed when this trace
   is truthful; its name alone is never a failure.

References influence scale, direction, palette, and visual style. Do not claim
they were attached or validated unless the provider trace proves it.

## Production loop

Work in the following loop until every applicable L0-L4 check passes or a real
STOP condition occurs. Never mark the first failed check as the final result.

1. Generate and preserve a raw source image. Keep the foreground on a solid
   `#FF00FF` background before deterministic cleanup, with no text or UI.
2. Choose the static or animated path below. Keep raw sheets, final PNGs,
   reports, source layout, stable entry, and Godot artifact in the trace.
3. Construct the shared asset result and run
   `standalone_validation.compile_and_validate()` for the applicable L0-L4
   checks. Read the diagnostic, then repair source art, processing parameters,
   metadata, paths, or Godot artifact and rerun the checks.
4. The entry builders below write `processing_status: compiled`. Only after all
   applicable L0-L4 levels pass, promote that same stable entry to
   `processing_status: ready`, set `validation.passed: true`, write the final
   result, and run the request/result handoff checker. L5/L6 visual judgment
   belongs to the private Eval, not this production Skill.

### Godot executable for L3/L4

L3 is a real Godot import/load probe, not a PATH-presence check. When
`GM_EVAL_GODOT_PATH` is set, it is the pinned executable for this run: pass
that exact value to `compile_and_validate(..., godot_path=...)` (or leave its
historical `"godot"` placeholder for the shared validator to resolve). Do not
replace it with a bare `godot`, discover another installation, or mark L3 as
passed without invoking it. Outside an Eval, resolve the configured executable
with `python tools/agent_runtime.py godot_path`; if it is genuinely absent or
unrunnable, record the diagnostic and STOP only after the production repair
options are exhausted.

### Static path

Use `tools/asset_sheet_process.py --snap-mode autoslice` only when every
disconnected foreground component is itself one logical effect. Do not supply
`--grid` to autoslice. Follow it with curation and
`tools/asset_curation_select.py`; selection invokes
`asset_image_finalize.py` for transparent cleanup, aspect-preserving scaling,
centering, and padding before the stable PNG is published.

If disconnected sparks, fragments, glow, or dust semantically form one effect,
preserve the whole composition instead. Use an explicit one-cell/grid curation
route or finalize the full source deterministically; do not let autoslice split
one effect into unrelated runtime assets. If autoslice `--names` does not match
the detected regions it returns `needs_regeneration` without partial output.
Treat that as a repair diagnostic: regenerate or relayout the source, or correct
the intended naming; never drop regions or silently assemble a different effect.

After selecting one candidate at the stable PNG path, write its compiler-bound
entry with:

```bash
python tools/asset_curation_entry_draft.py \
  --report <curation-report.json> \
  --candidate <candidate> \
  --request <request.json> \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family fx-bundle \
  --project-root <project_root> \
  --out <entry.json>
```

This produces the `single -> Texture2D` compiled entry. Do not promote or hand
it to a worker until the production loop's L0-L4 validation has passed.

### Animated path

Use `tools/asset_action_process.py` with `--kind fx`, the declared explicit
grid, ordered frame names, action name, FPS, loop flag, durations, magenta
cleanup, and `--align center`. Preserve raw sheet, processed transparent frames,
delivery sheet, GIF preview, processing report, and action metadata. Animation
never uses autoslice or an atlas assembler. Publish each processed frame at
`assets/generated/fx-bundle/<asset_id>/<asset_id>_<action>_<frame>.png`; this is
the canonical frame path consumed by the L0-L4 SpriteFrames validation route.

Compile its one action through the shared `grid_sheet -> SpriteFrames` route:

```bash
python tools/asset_action_entry_draft.py \
  --metadata <pipeline-meta.json> \
  --request <request.json> \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family fx-bundle \
  --project-root <project_root> \
  --out <entry.json>
```

The builder verifies frame order, grid, timing, loop state, center alignment,
stable paths, and compiles exactly one `SpriteFrames` resource into a compiled
entry. The production loop promotes it only after L0-L4 pass.

## Result shape

An animated result has one `SpriteFrames` runtime output and one stable
`grid_sheet` source. A static result has one `Texture2D` runtime output at the
same stable PNG path as its `single` source. Both final results include explicit
passing `L0` through `L4` evidence; no other runtime Godot type is valid.
