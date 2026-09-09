# Reviewer Skills

Reviewer skills are domain experts that catch Godot-specific mistakes in generated code. Godot has many subtle rules — physics callbacks that cannot change game state, UI containers that ignore manual positioning, audio streams that silently use far more memory than their file size suggests — and an AI writing game code will occasionally get these wrong. Reviewer skills exist to catch those mistakes before they end up in your project.

A reviewer sub-agent (a separate Claude instance, run automatically) loads the relevant reviewer skills during `/gm-build` and `/gm-fixgap`, based on which Godot systems the freshly written code touches. It reads the code, checks it against the skill's known pitfalls, and produces a report. You do not need to trigger this yourself.

## The eight reviewer skills

| Skill | What it covers | Example issue caught |
|-------|---------------|----------------------|
| `physics` | Collision detection, physics bodies, collision layers, physics callbacks | Calling `queue_free()` directly inside a `body_entered` callback — Godot locks the physics space during collision events, so any state-changing operation must be deferred |
| `animation` | AnimationPlayer, AnimationTree, AnimatedSprite2D, state machines | Using `AnimationPlayer.play()` while `AnimationTree.active = true` — AnimationTree overwrites all tracked properties every frame, making direct playback calls have no visible effect |
| `ui` | Control nodes, containers, layouts, focus, mouse input, themes | Setting `position` or `scale` on a child of a Container — containers take full control of their children's transforms and will override any manual positioning |
| `tilemap` | TileMapLayer, TileSet, terrain painting, tile collision | Calling `get_cell_tile_data()` and modifying the result — it returns a shared reference, so changing one cell's data silently changes every tile using that same tile type |
| `navigation` | NavigationAgent, pathfinding, avoidance, navmesh baking | Setting `target_position` directly in `_ready()` — the NavigationServer doesn't finish syncing region data until after the first physics frame, so any query before that returns an empty path |
| `shader` | ShaderMaterial, GLSL uniforms, screen textures, material sharing | Passing an integer where a shader uniform expects a float — Godot does not validate types when setting uniforms from script, so the mismatch fails silently and the shader uses its default value |
| `audio` | AudioStreamPlayer, audio buses, polyphony, stream lifecycle | Preloading many compressed OGG files at startup — a compressed audio file is decoded into raw PCM in memory at runtime, so a 5 MB OGG can consume around 50 MB of RAM |
| `particles` | GPUParticles, CPUParticles, trails, sub-emitters, collision | Changing the `amount` property on a particle node at runtime — the engine reallocates the entire particle buffer on that change, instantly destroying all currently visible particles |

## How a reviewer skill is shaped

Each reviewer skill lives in `skills/reviewer/<name>/` and contains three files:

- `SKILL.md` — the entry point: when to apply this skill, what code patterns trigger a review, and the overall review procedure.
- `gotchas.md` — the knowledge base: a numbered list of specific Godot engine pitfalls, each with a symptom, a root cause, and the correct fix. These are the "things that will go wrong."
- `checklist.md` — the action list: concrete checks the reviewer runs against the code, each mapped back to a specific gotcha. For example, check item S1 looks for the pattern described in gotcha G1.

The reviewer sub-agent reads all three files and produces a structured report that names any issues found by their gotcha ID (for example, "physics G1: direct `queue_free()` in `body_entered`").

## When reviewers find issues

The main agent triages every finding into one of three options: ACCEPT (add a new task to `PLAN.md` for the next worker batch to fix), REJECT (the finding is wrong), or SKIP (the finding is real but not worth fixing now). Defaults when uncertain: critical/major → ACCEPT; minor → SKIP. For critical/major a REJECT or SKIP requires a mandatory citation — a gotcha entry, an API doc reference, a prior architecture decision or project constraint, or an existing task ID. Minor findings have no citation requirement. Raw findings and triage decisions are not persisted in `MEMORY.md`.

The cycle loops until the reviewer's last pass added zero ACCEPTED tasks.

Importantly, this step cannot be silently skipped. A hook script called `check_completion.py` runs when `/gm-build` or `/gm-fixgap` tries to finish its session. If workers ran but the verifier and reviewer did not, the hook blocks the session from ending. Quality checks are mandatory, not optional.
