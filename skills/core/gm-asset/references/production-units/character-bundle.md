# Historical Character Bundle Production Unit

This document records the pre-standalone production unit. Do not use it as the
execution contract for new work; use
`skills/assets/character-bundle/SKILL.md` and
`skills/assets/_shared/animation-planning.md` instead.

The retained production intent is one identity anchor, action sources processed
with `asset_action_process.py`, stable frame PNGs, delivery sheets, GIF previews,
action metadata, and one aggregated SpriteFrames artifact. The current skill
keeps canonical-first generation when no suitable user character image exists,
uses real image attachments for every action, preserves edge-recovery evidence,
and keeps runtime frames at the resolved gameplay canvas (256 px by default).

## Scope decisions carried forward

- `character_portrait` output is outside the current public character-bundle
  runtime scope. It was intentionally not migrated; portrait work needs its own
  family and contract.
- Detached projectile, slash, muzzle, dust, aura, pickup, and impact effects
  belong to `fx-bundle`, not the character runtime artifact.
- GIF previews remain part of character-bundle delivery.
- The caller describes actions and motion intent. The Skill resolves frame
  count, FPS, frame names, grid, source batches, and durations before provider
  generation, then validates the resolved request mechanically.
