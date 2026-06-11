# Roadmap

> Turn natural-language game descriptions into playable Godot projects, powered by ECS and AI orchestration.

This roadmap tracks what has shipped, what we are working on now, and where the project is headed.

## Completed

### v0.1 — Foundation

- [x] `R-001` Project skeleton and repository setup
- [x] `R-002` Asset pipeline tools (asset source generation, rembg, sprite utilities)
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

### v0.5 — Role-based pipeline

- [x] `R-070` **Permission isolation — file-lock baseline** — Each role's write scope is enforced by `check_file_permissions.py` reading `.godotmaker/current_role` (set as the first action of every `/gm-*` skill). Hooks reject out-of-scope writes (e.g. only `/gm-evaluate` may write `e2e/`). The file-lock + hook approach was chosen over heavier alternatives after evaluation; harder isolation is tracked as `R-073`.
- [x] `R-071` **Pipeline decomposition** — Split monolithic orchestrator skill into 9 role-based skills (`/gm-scaffold`, `/gm-gdd`, `/gm-asset`, `/gm-build`, `/gm-verify`, `/gm-evaluate`, `/gm-fixgap`, `/gm-accept`, `/gm-finalize`). Each role owns a single phase and write-permission scope; `gm-evaluate` owns `e2e/` exclusively.
- [x] `R-072` **Shared reference docs (`_shared/`)** — Cross-skill reference docs (worker/verifier/reviewer/analyst dispatch) live as a single source of truth and are reverse-deployed by `publish_shared_refs()` into each consumer's `references/` with an `<!-- AUTO-GENERATED -->` header.

### v0.5 — Playability validation

- [x] `R-080` **Playable Unit contract** - Make one minimal playable unit the core planning unit for `/gm-gdd`, the decomposer, and `PLAN.md`. Each unit must describe the player experience, the unit outcome, scenes involved, and each mechanic's player operation/content, expected effect, required visible content, and evidence.
- [x] `R-081` **Playability scenario contract** - Turn each Playable Unit into evaluate-owned runtime coverage: player-facing operations, state assertions, visible-content checkpoints, and explicit failure criteria. Scope excludes a general AI player or RL system; the first target is deterministic proof that every required unit row can actually be played.
- [x] `R-084` **Best-effort evaluate evidence archive** - When a tag is finalized, archive the existing E2E tests and screenshots under `docs/tags/<Tag>/evidence/` when available and summarize them in `final_report.json`. Evidence archive gaps are warnings, not finalize blockers.

### v0.7.0 — Art Asset Pipeline

> Completed in the current development branch; expected to ship with the next `v0.7.0` tag after final validation.

- [x] `R-082` **Asset production pipeline** - Rebuild `/gm-asset` around production units, provider-specific source claiming, deterministic image processing, asset manifests, and per-unit reports instead of prompt-only missing-row generation.
- [x] `R-083` **Character and unit asset production** - Produce canonical character art and action sources for heroes, enemies, NPCs, and gameplay units.
- [x] `R-085` **VFX and projectile asset production** - Produce projectiles, impacts, slashes, pickups, explosions, trails, and other gameplay effects.
- [x] `R-088` **Prop and scene-object asset production** - Produce props, pickups, chests, obstacles, decorations, and scene object sets.
- [x] `R-089` **Background and platform asset production** - Produce flat backgrounds, parallax-style layers, platform strips, terrain strips, and large scene backdrops.
- [x] `R-090` **UI component asset production** - Produce buttons, panels, tabs, progress bars, badges, icons, scalable UI pieces, and nine-slice-style sources.
- [x] `R-091` **Card and portrait asset production** - Produce card frames, portrait frames, rarity frames, resource badges, card slots, and card-game-specific UI assets.
- [x] `R-092` **Generated asset usage in gameplay** - Make build and fixgap hand final generated assets to workers, keep reviewer asset-use checks lightweight, and let evaluate judge scene-contract screenshots instead of asset-manifest internals.
- [x] `R-087` **Character animation runtime integration** - Use generated character action assets in Godot runtime animation setup, including idle/move/attack/hit/death state mapping, AnimationPlayer or sprite-sheet wiring, and gameplay-facing animation triggers.

## In Progress

### v0.x — Plugin Skills

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
- `R-074` **SKILL-shared scripts as `_shared_scripts/`** — Mirror `R-072`'s pattern for executable scripts. `tools/asset_source_generate.py` / `find_loop_frame.py` / `rembg_matting.py` / `check_project.py` / `append_stage_event.py` are invoked from one or more SKILLs but live at top-level `tools/`, drifting from the official Claude Code "SKILL self-contained" convention. Move them to a new `skills/core/_shared_scripts/` source-of-truth and have `publish.py` fan them out into each consumer's `<skill>/scripts/` at deploy time (manifest-driven, sibling to `_shared/manifest.json`). After this lands, top-level `tools/` is reserved for user/CI-invoked scripts (`migrate.py`, `publish.py`, `check_classname.py`).
- `R-075` **Cross-session resume contract** — Today, when a predecessor `claude -p` session dies mid-`/gm-fixgap` (e.g. quota cut-off after worker DONE but before main agent wrote MEMORY / advanced GAP / archived / appended stage event), the next session's startup recovery is 100% agent improvisation: no spec, no tests, no canonical decision table. The 0509 e2e run made it work by luck — iter 2's startup archived iter 1's GAP "in absentia" because the model happened to read the right tea leaves. **Scope**: write a formal resume contract for each `/gm-*` SKILL — given (last stage event, GAP.md status, evaluation.json status, current_role file), what's the canonical next step? Add tests covering at minimum: predecessor died after worker DONE before archive; predecessor died after archive before stage event append; predecessor died mid-evaluate; ts corruption in last stage event. Lives at the SKILL contract layer, not the agent prompt layer — so the resume behavior is reproducible across model swaps.

- `R-076` **Coding-agent hook contract audit** — Audit every GodotMaker hook against each supported coding agent runtime. For Claude Code, Codex, and future supported agents, verify hook registration coverage, input payloads, output schemas, block semantics, reminder/context injection support, and failure behavior. Fix or remove hook outputs that are not supported by a runtime, and keep runner-specific differences documented instead of assuming one hook API works everywhere.

### Framework Features

Items below are ideas under consideration — not committed to a timeline.

- `R-093` **Map and stage art-to-runtime handoff** — Turn generated backgrounds, props, platforms, and scene references into map or stage runtime structure.
- `R-094` **Interactive art generation workflow** — Add a future operator-facing workflow for reviewing generated sources, crop results, rejected variants, canonical choices, manifest mappings, and regenerate/replace/accept actions.
- `R-086` **Common UI motion skill** — Add a focused skill for common game UI motion such as panel transitions, button feedback, popups, score changes, health/XP feedback, modal entrance/exit, and state-change emphasis.
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
- `R-112` **Re-evaluate gdtoolkit (gdlint / gdformat)** *(low priority)* — Disabled in v0.3.4 due to recurring `gdtoolkit/linter/class_checks.py:144 NotImplementedError` crashes on ECS-style class shapes. Rationale + restore guide in [`docs/decisions/disable-gdtoolkit.md`](docs/decisions/disable-gdtoolkit.md).
- `R-113` **3D game support** *(low priority)* — Extend planning, asset, build, verification, and evaluation contracts beyond the current 2D-first pipeline so generated projects can target 3D scenes, cameras, physics, controls, and content.
- `R-114` **Audio asset generation** *(low priority)* — Add an audio generation and curation workflow for music, ambience, and sound effects, including provider selection, manifest mapping, import settings, and validation. Until this ships, audio remains user-provided or manually added.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved. Feature proposals are welcome as [GitHub Issues](https://github.com/RandallLiuXin/GodotMaker/issues).
