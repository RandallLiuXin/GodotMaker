# Memory: {Project Name}

<!-- Cross-tag accumulating notebook. Append-only across the whole project
     lifetime — discoveries from v0.1.0 still apply in v0.5.0 unless
     explicitly superseded. Outdated entries should be edited in place
     (mark with "(superseded by ...)") rather than deleted. -->

## System Index

<!-- Each implemented system/module has a detail file in the memory/ subdirectory
     (same folder as this MEMORY.md). Use the template from .claude/templates/memory_subsystem.md.
     One line per entry: link + one-line summary. -->

<!-- Example entries (delete when starting):
- [movement_system](memory/movement_system.md) — PlayerMovementSystem: exponential deceleration, raycast ground detection
- [collision](memory/collision.md) — CollisionSystem: layer/mask setup, Area2D vs CharacterBody2D tradeoff
- [asset_pipeline](memory/asset_pipeline.md) — Asset generation: prompt patterns, background removal issues
-->

## Discoveries

<!-- Things learned during development that weren't obvious from docs. -->

- {date}: {discovery}

## What Worked

<!-- Approaches and patterns that succeeded. Reference for similar future tasks. -->

- {approach}: {why it worked}

## What Failed

<!-- Approaches attempted and abandoned. Avoid repeating these. -->

- {approach}: {why it failed, what replaced it}

## Engine Quirks

<!-- Godot-specific gotchas encountered during this project. -->

- {quirk}: {workaround}

## Workarounds

<!-- Temporary or permanent workarounds for issues that don't have clean fixes. -->

- {issue}: {workaround applied}

## Reviewer Triage Log

<!-- Reviewer findings the build/fixgap agent decided NOT to add to
     PLAN/GAP — covers both REJECT (finding is wrong) and SKIP (finding
     is real but not worth fixing now). Each entry records: timestamp,
     Tag, file/area, finding (verbatim), severity, decision (REJECT |
     SKIP), reason (1-2 sentences), and a citation.

     Citation is required for critical/major findings (gotcha entry /
     Godot or ECS API doc reference / prior MEMORY entry / PLAN or GAP
     task ID). For minor findings the citation is optional.

     Cross-tag accumulation — consult before writing a new triage entry
     so the same class of finding is not re-triaged from scratch.

     /gm-accept reads this section, filters by current Tag, and shows
     every entry to the user as a final-gate audit trail. -->

### {ts} — {Tag} — {File:Line or area}
- **Finding:** {verbatim from reviewer report}
- **Severity:** critical | major | minor
- **Decision:** REJECT | SKIP
- **Reason:** {1-2 sentence explanation}
- **Citation:** {gotcha path / API doc ref / prior MEMORY entry / PLAN or GAP task ID — required for critical/major; "n/a" for minor}

## Component Design Decisions

<!-- Rationale for component structure choices.
     Why fields were grouped this way, why components were split or merged. -->

- **{ComponentName}**: {decision and rationale}

## System Interaction Patterns

<!-- Patterns discovered for how systems communicate through components.
     Intent components, event components, state machine transitions, etc. -->

- **{Pattern name}**: {description}

## DAG Ordering Issues

<!-- Problems encountered with system scheduling and dependency ordering. -->

- **{Issue}**: {what happened, how it was resolved}
