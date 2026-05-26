# Core Skills

Core skills come in two kinds: the nine role skills exposed as `/gm-*` commands, and twelve supporting skills that role skills load automatically. This page covers both.

## Role skills

There are nine role skills, each responsible for one part of game creation. In the normal path, `godotmaker-cli` drives them in order; in manual mode, run the `/gm-*` role commands in the same sequence because each role expects the previous one to be complete.

| Command | What it does | Needs | Produces |
|---------|-------------|-------|---------|
| `/gm-scaffold` | Creates a new Godot project with the right folder structure, required addons, and a first git commit | Nothing (run this once per project) | `project.godot`, `addons/`, initial `CLAUDE.md` or `AGENTS.md` |
| `/gm-gdd` | Interviews you about the game, then writes the design documents and work plan | A scaffolded project | `GDD.md`, `PLAN.md`, `STRUCTURE.md`, `SCENES.md`, `ASSETS.md`, `TOC.md` |
| `/gm-asset` | Generates missing art or analyses art you provide, so the build has visuals to work with | `ASSETS.md` from `/gm-gdd` | Art files in `assets/`, updated `ASSETS.md` |
| `/gm-build` | Implements the game by sending tasks to worker sub-agents one batch at a time, with reviewers checking the result | Design documents from `/gm-gdd` | Game code in `src/`, `scenes/`, unit tests, end-to-end tests |
| `/gm-verify` | Runs a mechanical check: does the project compile, do unit tests pass, are required files present | A built project | A printed pass/fail report and a `verify` event appended to `.godotmaker/stage.jsonl` |
| `/gm-evaluate` | Runs the game independently, takes screenshots, and scores the result against the GDD | A verified project | `.godotmaker/evaluation.json`, screenshots in `e2e/screenshots/` |
| `/gm-fixgap` | Reads the evaluation report, generates a list of issues, and dispatches workers to fix them | An evaluation from `/gm-evaluate` | Updated game code, `GAP.md` archived to `.godotmaker/gaps/<n>/` |
| `/gm-accept` | Shows you the current state and asks whether to accept it, go back for more fixes, or stop | A complete build cycle | Acceptance event recorded in `.godotmaker/stage.jsonl` |
| `/gm-finalize` | Archives the tag's working docs to `docs/tags/<Tag>/`, runs `git tag <Tag>` locally, resets per-tag runtime state | An accepted build | `docs/tags/<Tag>/` archive, `.godotmaker/final_report.json`, local git tag |

After `/gm-finalize` you can begin the next tag through the CLI, or manually by running `/gm-gdd` again (for example, to add a new feature). `/gm-scaffold` is a one-time setup step per project.

For a deeper look at what each role does and the decisions it makes, see [The 9 roles](../02-concepts/the-9-roles.md).

## Supporting skills

Supporting skills are reference packs loaded silently by the role skills. You never invoke them yourself — they exist so the role skills have accurate documentation and helpers available when they need them.

### Planning

| Skill | What it provides | Loaded by |
|-------|-----------------|-----------|
| `game-planner` | Interview structure, GDD template guidance, and current-tag-scoped independent audit (via the `gdd-auditor` sub-agent — one pass always, a second only when the first finds enough gaps) before the design is finalized | `/gm-gdd` |
| `project-scaffold` | Project layout rules, addon setup steps, and the ECS folder conventions | `/gm-scaffold` |
| `input-mapper` | Reference for managing Godot input actions in `project.godot` | `/gm-build`, `/gm-fixgap` |

### Godot reference

| Skill | What it provides | Loaded by |
|-------|-----------------|-----------|
| `godot-api` | Godot 4 engine class documentation — methods, properties, signals, and enums | `/gm-build`, `/gm-fixgap` |
| `gecs` | API reference for the gecs ECS addon (Entity, Component, System, World, QueryBuilder) | `/gm-build`, `/gm-fixgap` |

### Building and running

| Skill | What it provides | Loaded by |
|-------|-----------------|-----------|
| `headless-build` | How to compile-check a Godot project in headless (no-window) mode | `/gm-verify`, `/gm-build` |
| `gdunit-driver` | How to run gdUnit4 unit tests and read the results | `/gm-verify`, `/gm-build` |
| `godot-e2e` | How to write and run end-to-end game tests that control a live Godot window over a network connection | `/gm-build`, `/gm-fixgap` |

### Evaluation

| Skill | What it provides | Loaded by |
|-------|-----------------|-----------|
| `visual-qa` | How to analyse screenshots for visual defects and compare against reference images | `/gm-evaluate` |
| `screenshot` | How to capture gameplay screenshots from a running Godot instance | `/gm-evaluate`, `/gm-fixgap` |
| `mcp-driver` | How to inspect a live Godot project at runtime via godot-mcp, used when build tools alone can't diagnose a problem | `/gm-fixgap` |

The full content of any supporting skill's `SKILL.md` lives in `skills/core/<name>/` in the repository if you want to see exactly what reference material it contains.

You don't invoke supporting skills directly - the CLI or the role commands above pull in what they need.
