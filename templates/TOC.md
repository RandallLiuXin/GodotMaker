# Document Index: {Name}

<!-- Master index of all project documents. Updated by each /gm-* role on completion. -->

## Cross-Tag (live, accumulating)
- `GDD.md` — Game Design Document, the design "north star" updated each tag (produced by `/gm-gdd`)
- `ROADMAP.md` — Tag-by-tag release plan (produced by `/gm-gdd` first run, edited by /gm-gdd subsequent runs)
- `STYLE.md` — Visual prompt style guide for image generation (produced by `/gm-gdd`)
- `MEMORY.md` — Knowledge base index, append-only across tags
- `memory/` — Per-system memory subsystem files
- `ASSETS.md` — Asset manifest (produced by `/gm-asset`)

## Current-Tag (overwritten each /gm-gdd run)
- `PLAN.md` — Task breakdown with status tracking, scoped to the current tag (produced by `/gm-gdd`)
- `STRUCTURE.md` — ECS architecture for the current tag's additions/refactors (produced by `/gm-gdd`)
- `SCENES.md` — UI/scene layout descriptions for current tag (produced by `/gm-gdd`)

## Per-Tag Archives (immutable once sealed)
- `docs/tags/<Tag>/GDD-snapshot.md` — GDD as it stood when this tag shipped
- `docs/tags/<Tag>/PLAN.md`, `STRUCTURE.md`, `STYLE.md`, `SCENES.md`, `MEMORY.md` — frozen working docs (ASSETS.md is cross-tag and stays at the root)
- `docs/tags/<Tag>/evaluation-final.json` — final approved evaluator verdict for the tag
- `docs/tags/<Tag>/CHANGELOG.md` — changelog entry for the tag (produced by `/gm-finalize`)

## Pipeline Records (runtime)
- `.godotmaker/stage.jsonl` — Append-only event log for the current tag (cleared by `/gm-finalize` between tags)
- `.godotmaker/evaluation.json` — Latest evaluator verdict for the current tag (overwritten each `/gm-evaluate`)
- `.godotmaker/final_report.json` — Latest tag's seal report (overwritten each `/gm-finalize`)
- `.godotmaker/metrics.jsonl` — Append-only event metrics, accumulates across tags
- `.godotmaker/traces/` — Subagent output traces, accumulates across tags
- `GAP.md` — Gap-fix task list (present only during `/gm-fixgap`; archived to `.godotmaker/gaps/<n>/` afterwards)

## Reference
- `references/` — Scene reference images (produced by `/gm-asset`)
- `assets/manifest.json` — Asset manifest (produced by `/gm-asset`, if user provides assets)
- `e2e/` — End-to-end test suite (produced by `/gm-evaluate`)
