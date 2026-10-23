# CLAUDE.md

Generated Godot game project. The `/gm-*` skills drive the build pipeline — invoke them rather than recreating their flow manually.

## How the pipeline runs (tag-iterative)

This project ships in **tags** (SemVer: v0.1.0, v0.2.0, …). Each tag is one full pass through the pipeline.

## Don't get caught here

### Pipeline

- **Don't bypass the role lock.** `.godotmaker/current_role` decides who may write what. If a hook denies a write, dispatch the right subagent or switch to the right `/gm-*` skill — don't try to `--force` past it.
- **Don't write `e2e/` outside the Evaluator role.** Workers expose `simulate_*()` interfaces and write unit tests for them. The Evaluator (`/gm-evaluate`) maintains the single `e2e/` suite that always reflects the current game.
- **Don't manually edit `.godotmaker/stage.jsonl`.** Each `/gm-*` skill appends its own role timestamp on completion. `/gm-finalize` truncates it between tags.
- **Read `MEMORY.md` before dispatching a worker.** Past mistakes are indexed there — workers will repeat them otherwise. `MEMORY.md` accumulates across tags.

### Tag scope

- **`PLAN.md`/`STRUCTURE.md`/`SCENES.md` describe ONLY the current tag.** Previous tags' versions live in `docs/tags/<prev_tag>/` and are immutable. Don't add new content for an already-shipped tag — open a new tag instead.
- **`STYLE.md`, `ASSETS.md`, and `MEMORY.md` accumulate across tags.** Don't split per tag — append rows / entries; the `Tag` column on each ASSETS row marks the introducing tag.
- **Don't silently rewrite prior-tag code.** Workers may touch files outside the current tag's scope only when `PLAN.md` has an explicit refactor task naming those files. "Cleanup detours" are not allowed.
- **Don't modify any file under `docs/tags/`.** Those archives are the historical record of what shipped at each tag.

### Resources

- Never fabricate resource paths. Use only paths listed in `ASSETS.md` or already on disk. If you need an asset that does not exist, report it — do not invent.
- Never edit `references/scene_*.png`. They are the visual ground truth that `/gm-evaluate` compares the running game against. To regenerate them, re-run `/gm-asset` Step 3.

## Where to look

| Question | File |
|---|---|
| Cross-tag design intent | `GDD.md` |
| Tag-by-tag release plan | `ROADMAP.md` |
| Current tag's task list / progress | `PLAN.md` (`**Tag:**` header at top) |
| Current tag's systems / components / archetypes | `STRUCTURE.md` |
| Current tag's scene layouts | `SCENES.md` |
| Initial visual seed | `STYLE.md` |
| Asset manifest (cross-tag, with introducing-tag column) | `ASSETS.md` |
| What a previous tag shipped | `docs/tags/<prev_tag>/` |
| Past discoveries + gotchas (cross-tag) | `MEMORY.md` (index) |
| Each role's full contract | `.claude/skills/gm-*/SKILL.md` |
| ECS API + the full gotcha list | `.claude/skills/gecs/` |
| godot-e2e API | `.claude/skills/godot-e2e/SKILL.md` |

## Conventions

- GDScript for all game logic; English for code and comments
- TDD: write tests alongside implementation
- One System per file (`{name}_system.gd`), one Component per file (`{name}.gd`)
- Unit tests in `test/`, named `test_{name}.gd`
- E2E tests in `e2e/` (maintained by `/gm-evaluate`)
- Physics callbacks must never manipulate the node tree directly — use deferred calls
- Only one System writes Transform per entity
- Scene tree is for UI/menus only; gameplay entities use ECS
- All systems must have corresponding unit tests
- The `e2e/` suite must pass before `/gm-evaluate` approves the tag
