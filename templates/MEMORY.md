# Architecture and Constraints: {Project Name}

<!-- Cross-tag record for stable architecture and project constraints only.
     Do not record task history, runtime failures, gotchas, workarounds,
     reviewer triage, or other dynamic learning. Update an entry only when the
     project's durable design or constraint changes. -->

## System Architecture Index

<!-- Add a memory/{name}.md file only when a system needs more detail than a
     single entry can hold. Use .claude/templates/memory_subsystem.md. -->

<!-- Example entries (delete when starting):
- [movement](memory/movement.md) — ownership, dependencies, and ordering constraints
- [save_system](memory/save_system.md) — persistence boundary and schema constraints
-->

## Architecture Decisions

<!-- Record durable decisions that affect module boundaries, ownership,
     dependencies, state flow, or public contracts. -->

- **{Decision}:** {chosen architecture and rationale}

## Project Constraints

<!-- Record stable constraints future implementation must preserve. Link to
     the authoritative design or requirement when one exists. -->

- **{Constraint}:** {required boundary or invariant} — {source}
