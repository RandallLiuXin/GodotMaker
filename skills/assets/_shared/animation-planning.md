# Animation Planning

Use this reference before resolving an animated character or FX request. The caller describes motion intent and gameplay feel; the Asset Skill records the exact frame plan before generation. Treat the ranges below as production guidance, not mandatory limits.

| Use | Typical unique frames | Typical fps | Notes |
| --- | ---: | ---: | --- |
| Character idle | 6-8 | 6-8 | Prefer a readable one-second breathing or stance cycle. |
| Character walk or run | 8-12 | 8-12 | Preserve contact, passing, and recoil poses. |
| Character short attack or dodge | 6-10 | 10-14 | Include anticipation, event, and recovery; use duration holds deliberately. |
| Character complex skill or combo | 12-18 | 10-14 | Split into source batches when one provider sheet would make cells too small. |
| Character hit or death | 5-10 | 8-12 | Match the gameplay interruption and recovery. |
| Ambient FX | 6-10 | 6-10 | Use slower loops only when the effect is intentionally calm. |
| Impact, slash, explosion, or dash FX | 8-16 | 12-20 | Favor a clear onset, peak, and dissipate sequence. |

Plan temporal cadence before choosing a frame count. Describe the readable phases of the motion—for example settle, anticipation, acceleration, event/contact, follow-through, and recovery—and assign frames or intentional duration holds to each phase. Do not mechanically map one named pose beat to one frame: add transition frames where they make acceleration, impact, or recovery readable, and do not add duplicate frames only to meet a number. Compute playback seconds as `sum(frame_durations) / fps`.

Before provider dispatch, write a resolved plan under `.godotmaker/asset-generation/plans/<asset_id>_animation_plan.json` and the compiler input under `.godotmaker/asset-generation/plans/<asset_id>_resolved_request.json`. For each action record its name, `cadence` as an ordered list of `{phase, frame_names}` entries covering every resolved frame exactly once, pose beats, frame count, fps, loop, frame durations, grid, source-batch plan, `runtime_canvas_px`, and short rationale. Copy the resolved actions into the internal request used by the SpriteFrames compiler.

Choose a power-of-two runtime canvas for the whole bundle. Default to 256 px. Use 128 only for a deliberate small-display target; use 512 or larger when the requested display size or source detail requires it. Keep source cells large enough for the selected canvas and safe area. When a fixed-size provider source would make a dense action sheet too small, split that action across source batches rather than silently downsampling the character.

Use visual style language such as `hand-drawn cel-shaded fantasy`, `comic-book ink and flat color`, or `painterly storybook`. Pixel-art production is a separate unsupported capability, not a visual-style default.
