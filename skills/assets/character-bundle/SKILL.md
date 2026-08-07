---
name: character-bundle
description: Produce one illustrated character SpriteFrames resource from high-level body-action intent, optional character and style references, and a resolved animation plan.
---

# Character Bundle

Produce one player, enemy, NPC, summon, boss, creature, or skin as one `SpriteFrames` resource. Read `.godotmaker/asset-runtime/asset-skill-contract.md` and `.godotmaker/asset-runtime/animation-planning.md`. This standalone skill does not read or write `ASSETS.md`, tags, stage state, manifests, or worker dispatch state.

## Request and planning

Require `asset_type: "character-bundle"`. The caller supplies a non-empty ordered `spec.actions` list. Each action needs a unique `name` and a concise `intent` describing pose beats, gameplay feel, and motion trajectory; it may state whether the action loops. The caller does not prescribe frame count, FPS, frame durations, names, or grid. Resolve those from the shared animation-planning guidance. A caller may choose a power-of-two `spec.frame_canvas_px`; otherwise default the runtime canvas to 256 px.

Before provider dispatch, write `.godotmaker/asset-generation/plans/<asset_id>_animation_plan.json` and `.godotmaker/asset-generation/plans/<asset_id>_resolved_request.json`. The plan top level records `asset_id`, `frame_canvas_px`, and `identity_anchor_origin`. For every action, first resolve temporal cadence: named motion phases, transition frames, and any intentional holds. Then record `name`, `cadence` as an ordered list of `{phase, frame_names}` entries covering every resolved frame exactly once, pose beats, frame count, fps, loop, frame durations, grid, source-batch plan, `runtime_canvas_px`, and rationale. Do not choose the frame count by mechanically assigning one frame to each pose beat. The resolved request has ordered `required_actions`; every resolved action retains its public `intent` and has `name`, `grid`, ordered `frame_names`, positive `fps`, explicit `loop`, and one positive `frame_durations` value per frame. `grid.columns * grid.rows` equals the frame count. Validate this resolved request with `tools/asset_animated_bundle_contract_check.py --kind request` before processing or compiling.

Use exact resolved grid and frame order for a source batch, but do not treat planning guidance as a reason to reject a valid artistic request. When a fixed-size provider source would make a dense action too small for the chosen canvas and safe area, split the action into source batches and preserve every batch's prompt, raw source, attachments, and report. Combine their resolved frames in action order before compiling one SpriteFrames resource.

Use an explicit visual style or attached style image. Examples are `hand-drawn cel-shaded fantasy`, `comic-book ink and flat color`, and `painterly storybook`. Pixel-art production is unsupported in this family; stop clearly when it is requested. Do not use nearest-neighbor resampling.

## References and identity anchor

External references are optional. Validate each path is a readable image, preserve its `canonical`, `style`, or `screen` role, resolve `res://` from the project root, and attach the actual images to the declared provider. Never replace an image attachment with a path in prompt text. Use only the declared `native`, `codex`, `gemini`, or `openai` provider; do not silently switch. Stop clearly when the selected provider cannot generate or attach the required images.

Choose one identity anchor:

1. Use a suitable user `canonical` image directly for every action. Do not generate a duplicate canonical merely to satisfy the workflow.
2. When a user character image is cropped or unsuitable as a full-body action anchor, derive a full-body canonical from it and retain the source relationship.
3. When no user character image exists, generate a full-body canonical. Finalize it and copy the finalized image to `assets/generated/character-bundle/<asset_id>/<asset_id>_canonical.png`; return it as a `reference` output so the user receives the generated character image.

Record `identity_anchor_origin` as `user_provided`, `provider_derived`, or `provider_generated`. Every action receives the identity anchor as an actual image attachment. It also receives every external reference in role-preserving attachment order.

## Provenance

Keep raw sources, finalized anchors, prompts, reports, rejected attempts, and curation output under `.godotmaker/asset-generation/`. Store a distinct prompt and provider report for every provider attempt, including retries and source batches. Use `canonical/<asset_id>_canonical.png`, `sources/<asset_id>_<action>_source.png`, `reports/<asset_id>_canonical_source.json`, `reports/<asset_id>_<action>_provider.json`, and `reports/<asset_id>_<action>_process.json` for a single source batch; add `_batch<N>` before the suffix for additional batches. Each provider report records provider, model when available, coding model, reasoning, source path, reference roles, attached local paths, attachment count, and `provider_trace`.

`provider_trace` contains `provider`, `tool_call_id`, `image_model_identity`, `coding_model`, `reasoning`, and ordered absolute `referenced_image_paths`. Use `image_model_identity: "not_exposed_by_subscription_runtime"` only when the runtime does not reveal it. For Codex, call image generation once per attempt and pass every attachment through `referenced_image_paths`.

Use only provider outputs or user-provided images as visual sources. Do not draw, synthesize, or edit art with ad hoc Pillow, System.Drawing, ImageMagick, SVG, canvas, Godot drawing, inline scripts, color blocks, placeholders, or fake atlases. Existing controlled asset tools may process real provider or user images.

## Produce

1. Validate the public request shape. Resolve and archive the animation plan and resolved request.
2. Select or create the identity anchor. A generated anchor must be full-body, match the selected style, and preserve an intended ground reference. When its provider source uses the controlled magenta background, finalize it with `tools/asset_image_finalize.py --background magenta`; preserve an already-transparent user image rather than replacing its pixels.
3. For every resolved source batch, generate a sheet with the identity anchor and all external references attached. Prompt for the concrete pose beats, exact grid, full-body separation, safe gutters, selected visual style, and only the intended body action. Keep every intended body and prop contour complete inside its source frame; a wide pose may use the available frame area but must not cross into a neighboring frame.
4. Process real source sheets with `tools/asset_action_process.py`. Use `--kind body`, `--align feet`, the resolved batch grid and names, `--cell-size <frame_canvas_px>`, and `--recover-edge-touch`. This is the strict path and includes the existing AABB/autoslice edge-touch recovery. Preserve candidates, recovery reports, frames, transparent sheets, GIFs, and final stable PNG paths. When that path exits `2` with `status: "needs_regeneration"`, first preserve and inspect its report. For an AABB/autoslice recovery failure, next run `tools/asset_connected_component_recovery.py` against the real source sheet with the same declared grid, background, noise threshold, a separate recovered-sheet output path, and a machine-readable report. It is family-neutral: do not pass an asset kind or make it inspect Skill state. If it succeeds, re-run `asset_action_process.py` on its recovered-sheet output using the same resolved grid, names, timing, and stable delivery paths. If the connected-component tool also returns its recoverable failure, explicitly re-run `asset_action_process.py` on the preserved real source with `--fixed-grid-fallback`; this forced declared-grid delivery ignores edge-touch, cross-cell, and truncation visual rejections, preserves frame count/order/timing, and requires human visual review. Record and retain its structured warning; visual degradation alone is not STOP and the complete action still proceeds to compile and L0-L4/L5 validation. Do not invoke the connected-component tool for a normal successful sheet. Provider retry remains appropriate when the report identifies a source defect, but do not compile or return a partial action. Use the first action as the current scale reference; later actions may use `--scale-reference-metadata` and `--match-scale-reference`. Treat scale diagnostics as a repair signal, not a substitute for visual review.
5. For an action with more than one source batch, process batches into work paths, then use `tools/asset_action_batch_merge.py` to copy their real processed frames in resolved order and assemble the sole stable sheet/GIF/report. The merge tool is deterministic delivery assembly, not an art source. For every action write one stable frame PNG per frame, one delivery sheet, and one GIF preview under `assets/generated/character-bundle/<asset_id>/`.
6. Build one final `SpriteFrames` artifact from the resolved actions. Do not publish a per-action SpriteFrames, portrait runtime artifact, PackedScene, character controller, or detached FX as the runtime result. Preserve action reports and the resolved request as result evidence.
7. Run `standalone_validation.compile_and_validate()` for L0-L4 using the archived resolved request, not the high-level `ASSET_REQUEST.json`. The validator also resolves that archive when given the high-level request, and rejects a missing or mismatched resolved request. If compiler, Godot load, or consumer smoke fails, inspect the report and attempt a scoped repair or regeneration before returning failure. Do not claim readiness until the repaired artifact passes.
8. Only after every applicable L0-L4 level passes, write the final generic result. It must name the one `SpriteFrames` output and retain the resolved request and action reports as evidence. `/gm-asset` verifies the declared final output type/path and records it directly in `ASSETS.md`; the skill creates no registry record or index.
9. When `eval/consumer_smoke.gd` exists, run it after L0-L4 with every resolved `<action>:<loop>` pair. Preserve its command, executable, output, and JSON report as L5 evidence. Do not use compiler success as a smoke substitute.

## Result

Return one generic asset result with exactly one runtime `SpriteFrames`, one `grid_sheet` source and one GIF preview per resolved action in action order, and L0-L4 validation. A generated canonical is an additional `reference` output under the same stable directory and carries no `godot_type`; a user-supplied canonical is not duplicated as output. A second runtime output is never valid, whatever its Godot type. Keep L5 evidence and provider provenance in their dedicated files, not as extra public result fields.

When no complete action set can be produced because of a real STOP (for example an unavailable required provider/reference, compiler failure, or Godot load failure), return `validation.passed: false` with an explanatory note and no runtime output. A fixed-grid visual fallback is instead a complete, warning-bearing delivery: never return a partial SpriteFrames bundle.
