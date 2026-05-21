# Roadmap

> Turn natural-language game descriptions into playable Godot projects, powered by ECS and AI orchestration.

This roadmap tracks what has shipped, what we are working on now, and where the project is headed.

## Completed

### v0.1 — Foundation

- [x] `R-001` Project skeleton and repository setup
- [x] `R-002` Asset pipeline tools (asset_gen, rembg, sprite utilities)
- [x] `R-003` Skill infrastructure and publish pipeline

### v0.2 — Skills

- [x] `R-010` 13 core skills (orchestrator, godot-api, headless-build, gdunit-driver, gdtoolkit, gecs, game-planner, project-scaffold, visual-qa, screenshot, mcp-driver, godot-e2e, input-mapper)
- [x] `R-011` 8 reviewer skills (physics, animation, ui, tilemap, navigation, shader, audio, particles)
- [x] `R-012` Capability skills (headless-build, gdunit-driver, godot-e2e, gdtoolkit, visual-qa)

### v0.3 — Pipeline

- [x] `R-020` Multi-agent orchestrator pipeline (game-planner → scaffold → generate → validate)
- [x] `R-021` Stage gate validation with schema enforcement
- [x] `R-022` Hook system (8 hooks: pre-commit, SubagentStop, worktree lifecycle, etc.)
- [x] `R-023` Metrics and state tracking subsystem

### v0.4 — Polish

- [x] `R-030` Semantic versioning with publish-time upgrade prompts
- [x] `R-031` Hooks migration to `.godotmaker/` (git-tracked, worktree-safe)
- [x] `R-032` Wiki documentation (30 pages)
- [x] `R-033` CI workflow (lint, test, gitleaks)

### v0.x — Role-based pipeline

- [x] `R-070` **Permission isolation — file-lock baseline** — Each role's write scope is enforced by `check_file_permissions.py` reading `.godotmaker/current_role` (set as the first action of every `/gm-*` skill). Hooks reject out-of-scope writes (e.g. only `/gm-evaluate` may write `e2e/`). The file-lock + hook approach was chosen over heavier alternatives after evaluation; harder isolation is tracked as `R-073`.
- [x] `R-071` **Pipeline decomposition** — Split monolithic orchestrator skill into 9 role-based skills (`/gm-scaffold`, `/gm-gdd`, `/gm-asset`, `/gm-build`, `/gm-verify`, `/gm-evaluate`, `/gm-fixgap`, `/gm-accept`, `/gm-finalize`). Each role owns a single phase and write-permission scope; `gm-evaluate` owns `e2e/` exclusively.
- [x] `R-072` **Shared reference docs (`_shared/`)** — Cross-skill reference docs (worker/verifier/reviewer/analyst dispatch) live as a single source of truth and are reverse-deployed by `publish_shared_refs()` into each consumer's `references/` with an `<!-- AUTO-GENERATED -->` header.

## In Progress

### v0.x - Playability and Visual Contracts

- [ ] `R-080` **Playable Unit contract** - Make one minimal playable unit the core planning unit for `/gm-gdd`, the decomposer, and `PLAN.md`. Each unit must describe the player experience, the unit outcome, scenes involved, and each mechanic's player operation/content, expected effect, required visible content, and evidence.
- [ ] `R-081` **Playability scenario contract** - Turn each Playable Unit into evaluate-owned runtime coverage: player-facing operations, state assertions, visible-content checkpoints, and explicit failure criteria. Scope excludes a general AI player or RL system; the first target is deterministic proof that every required unit row can actually be played.
- [ ] `R-082` **Visual style bible** - Add a stable visual specification artifact used as the source of truth for later image prompts. It should capture art direction, palette, rendering style, UI language, camera/framing, reusable prompt suffixes, and forbidden visual traits. Evaluation should check objective drift and missing assets, not make open-ended "looks good" judgments.
- [ ] `R-083` **Reference object extraction ledger** - Extract visible objects from scene reference images into a reviewable ledger: characters, enemies, props, UI elements, background layers, approximate position, size, style notes, and whether each item needs an independent runtime asset. Image-based extraction is the preferred route, but the output must be a readable ledger that agents can correct and downstream stages can verify.
- [ ] `R-084` **Reference-derived asset generation** - Make asset generation depend on the reference/object ledger instead of only textual descriptions. Support per-object crops or derived references, character animation derivation from a reference character, UI element derivation, and explicit anchor/derivative relationships so generated assets stay stylistically coherent.
- [ ] `R-085` **Asset integration contract** - Strengthen `ASSETS.md` and `assets/manifest.json` so every generated or provided asset records its source reference/object, target scene/node/task, intended display size, runtime path, prompt/style metadata, and integration status. Resolve the current contract conflict where `/gm-asset` is barred from editing `PLAN.md` while asset planning guidance asks it to write concrete asset assignments back into `PLAN.md`.
- [ ] `R-086` **Contract protection for build and fixgap** - Prevent `/gm-build` workers and `/gm-fixgap` workers from weakening playable-slice, scenario, style, reference-object, or asset-integration contracts just to pass evaluation. Combine skill hard rules, hook-level guards where available, and evaluate/verify checks that detect unauthorized contract edits.
- [ ] `R-087` **Evidence bundle per Playable Unit** - Persist proof for each completed unit: the coverage that ran, logs, screenshots, short video or key frames, telemetry/progress result, visual-check summary, and final verdict. This gives later agents a concrete resume point and gives users/debuggers evidence that the unit's required player-facing content works.

### v0.5 — Plugin Skills

- [ ] `R-050` [Phantom Camera](https://github.com/ramokz/phantom-camera) — Camera management (inspired by Cinemachine)
- [ ] `R-051` [Dialogic](https://github.com/dialogic-godot/dialogic) — Dialogue and visual novel system
- [ ] `R-052` [Input Helper](https://github.com/nathanhoad/godot_input_helper) — Input device detection and icon mapping
- [ ] `R-053` [Scene Manager](https://github.com/maktoobgar/scene_manager) — Scene transitions and organization
- [ ] `R-054` [Godot State Charts](https://github.com/derkork/godot-statecharts) — Hierarchical state machines
- [ ] `R-055` [Godot Sound Manager](https://github.com/nathanhoad/godot_sound_manager) — Music and SFX playback
- [ ] `R-056` [GodotSteam](https://github.com/GodotSteam/GodotSteam) — Steam platform integration
- [ ] `R-057` [Beehave](https://github.com/bitbrain/beehave) — Behavior tree AI
- [ ] `R-058` [Importality](https://github.com/nklbdev/godot-4-importality) — Universal raster graphics and animation importer
- [ ] `R-059` [Spine Runtime](https://github.com/EsotericSoftware/spine-runtimes) — 2D skeletal animation (commercial license)
- [ ] `R-060` [gdfxr](https://github.com/timothyqiu/gdfxr) — Retro sound effect generator (sfxr port)

## Future / Exploring

### Permission & Pipeline

- `R-073` **Tamper-proof role identity via external harness** — `R-070`'s file-lock relies on each `/gm-*` skill honestly writing `.godotmaker/current_role`; nothing structurally prevents the main agent from rewriting the file mid-session. A separate harness process (tracked outside this repo, in a separate automation host) drives each role as its own Claude Code subprocess with the role injected via env var, so hooks can read identity from the runtime instead of the filesystem.
- `R-074` **SKILL-shared scripts as `_shared_scripts/`** — Mirror `R-072`'s pattern for executable scripts. `tools/asset_gen.py` / `find_loop_frame.py` / `rembg_matting.py` / `check_project.py` / `append_stage_event.py` are invoked from one or more SKILLs but live at top-level `tools/`, drifting from the official Claude Code "SKILL self-contained" convention. Move them to a new `skills/core/_shared_scripts/` source-of-truth and have `publish.py` fan them out into each consumer's `<skill>/scripts/` at deploy time (manifest-driven, sibling to `_shared/manifest.json`). After this lands, top-level `tools/` is reserved for user/CI-invoked scripts (`migrate.py`, `publish.py`, `check_classname.py`).
- `R-075` **Cross-session resume contract** — Today, when a predecessor `claude -p` session dies mid-`/gm-fixgap` (e.g. quota cut-off after worker DONE but before main agent wrote MEMORY / advanced GAP / archived / appended stage event), the next session's startup recovery is 100% agent improvisation: no spec, no tests, no canonical decision table. The 0509 e2e run made it work by luck — iter 2's startup archived iter 1's GAP "in absentia" because the model happened to read the right tea leaves. **Scope**: write a formal resume contract for each `/gm-*` SKILL — given (last stage event, GAP.md status, evaluation.json status, current_role file), what's the canonical next step? Add tests covering at minimum: predecessor died after worker DONE before archive; predecessor died after archive before stage event append; predecessor died mid-evaluate; ts corruption in last stage event. Lives at the SKILL contract layer, not the agent prompt layer — so the resume behavior is reproducible across model swaps.

### Framework Features

Items below are ideas under consideration — not committed to a timeline.

- `R-100` **TileMap support** — Terrain systems, tileset asset generation, and TileMap-based level design. Currently deferred; sprite-placement is the recommended terrain approach until this ships.
- `R-101` **ECS framework migration** — Migrate tindercore (C++ GDExtension) from EnTT to flecs, then adopt tindercore as the ECS runtime replacing gecs.
- `R-102` **Scene-markers skill** — Marker type → component composition mapping for ECS entity spawning.
- `R-103` **System DAG checker CLI** — Static dependency analysis for ECS systems at build time.
- `R-104` **gdUnit ECS test templates** — Reusable test fixtures for ECS system testing.
- `R-105` **DestructionSystem and Node lifecycle** — Entity destruction protocol and component add/remove lifecycle.
- `R-106` **Multi-platform game publishing** — One-click export and publish to Steam, iOS, Google Play, Web. Includes export preset generation, platform-specific assets, store metadata templates, and CI/CD integration.
- `R-107` **Pattern skills** — Per-genre architecture templates (e.g., top-down shooter, platformer, tower defense). Built from real pipeline runs, not theoretical.
- `R-108` **Tester subagent** — Dedicated E2E and gameplay testing role in the multi-agent pipeline.
- `R-109` **GDD quality review** — Automated completeness and consistency checks on generated Game Design Documents.
- `R-110` **Android build workflow** — APK/AAB export with signing, versioning, and store-ready packaging.
- `R-111` **Sprite sheet animation pipeline** — Generate multi-frame sprite sheets from single-frame AI-generated sprites.
- `R-112` **Re-evaluate gdtoolkit (gdlint / gdformat)** *(low priority)* — Disabled in v0.3.4 due to recurring `gdtoolkit/linter/class_checks.py:144 NotImplementedError` crashes on ECS-style class shapes. Rationale + restore guide in [`docs/decisions/disable-gdtoolkit.md`](docs/decisions/disable-gdtoolkit.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved. Feature proposals are welcome as [GitHub Issues](https://github.com/RandallLiuXin/GodotMaker/issues).
