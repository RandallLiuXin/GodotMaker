# Worker Dispatch Protocol

When dispatching a worker, fill in this EXACT template. All REQUIRED fields must be present. OPTIONAL fields may be omitted.

**Agent definition:** `.claude/agents/worker.md` — system prompt loaded automatically via `subagent_type: "worker"`.

## Agent Call

```
Agent({
  subagent_type: "worker",
  description: "Worker: implement {task_name}",
  model: "{worker_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{worker brief below}"
})
```

## Worker Brief Template

```
## Task: {name}                                         [REQUIRED]

### Objective                                            [REQUIRED]
{1-2 sentences: the game mechanic function to build}

### Context                                              [REQUIRED]
- Project: {game name and type}
- ECS Framework: gecs

### Input Files (Read These First)                       [REQUIRED]
- {path}: {what it contains}

### Game Mechanic Function                               [REQUIRED]
- Mechanic ID(s): {e.g. v0.1.0-M1}
- Player-facing outcome: {what the player can do or see}
- Integration point: {playable path connection}
- Affected systems/scenes/UI: {paths or names}

### Deliverables                                         [REQUIRED]
- [ ] {file path}: {what it should contain}
- [ ] {unit test file path}: {test scenarios — minimum 2 unit tests per changed system}
- [ ] e2e-testable interface: public methods / signals / simulate_* helpers for affected systems/scenes/UI, with unit tests covering each one
- [ ] If runtime assets include multi-frame `grid_sheet` entries: wire animation playback from metadata, not a static sheet or first frame
- [ ] If runtime assets include temporary animated FX: implement end-of-life behavior (animation finished, timer, tween completion, or equivalent state clear)
- [ ] If runtime assets include `region_atlas` entries: bind each single-element node to its named region via AtlasTexture/region, not the whole atlas image
- [ ] Run headless-build and confirm compilation
- [ ] Run unit tests and include pass/fail output
- [ ] If `Visual Self-Check` is present: capture screenshot(s), run visual-qa, include output
- [ ] Summary of what was implemented (<200 words)
- [ ] MEMORY entry: discoveries, gotchas, decisions (<100 words)

### Component Definitions                                [REQUIRED]
{Paste the actual Component class definitions, not just names}

### Scope Boundaries                                     [REQUIRED]
- MUST: {explicit requirements}
- MUST NOT: {explicit prohibitions — always include "MUST NOT modify files outside Deliverables"}

### Gotchas                                              [REQUIRED for ECS tasks]
- MUST include: "Read .claude/skills/gecs/gotchas.md before writing any code"
- Copy relevant gotchas from reviewer skills (ui/gotchas.md, animation/gotchas.md, etc.)

### Prohibited Actions                                   [REQUIRED]
- DO NOT ask for approval, wait for user input, or pause for confirmation. Execute the task directly. If required information or external state is missing, report `PARTIAL` or `FAILED` with the blocker.
- DO NOT fabricate resource paths — only use paths listed in ASSETS.md or verified to exist in the project. If you need an asset that doesn't exist, report it in your summary; do NOT invent a path.
- DO NOT modify files outside your Deliverables list — read-only access to all other files.
- DO NOT write `test_system_has_query` tests — system.q is null outside World (see gecs gotcha G14).
- DO NOT introduce E2E-only gameplay changes.
- DO NOT write files outside the project tree (system temp dirs, home directory, etc.). If you genuinely need a scratch file, create it under `.godotmaker/scratch/` (mkdir -p the directory if missing) and delete it before reporting DONE. Claude Code's own scratchpad system is gated behind a feature flag we cannot rely on, so this rule is what guarantees clean tear-down.

### Asset Runtime Snapshot                               [REQUIRED for visual tasks]
{Copy the matching ready entries from assets/manifest.json and ASSETS.md.
Include: asset_id, final_path, runtime_artifact, runtime_role, target size,
frame_count, and metadata path for `grid_sheet` or `region_atlas`.
Use cwd-relative final paths and metadata paths.
Use final runtime assets only.
Do not use `.godotmaker/asset-generation/sources/`, curation candidates,
prompt files, or scene references as runtime assets.
For `grid_sheet` with frame_count > 1, include the action metadata path,
frame_paths, fps/loop when present, and the expected runtime state or FX
lifecycle that should play it.
For `region_atlas`, include the atlas metadata path and let the worker resolve
the region and its rect from that metadata by name. Name the target region only
when the element-to-region match is not obvious from the binding.
If a required final asset or metadata file is missing, report PARTIAL or
FAILED with the missing path.}

### Visual Asset Contract                                [REQUIRED for visual tasks]
{Copy the relevant PLAN.md Runtime Asset Assignments, SCENES.md Asset
 bindings, and ASSETS.md Visual Asset Contract rows.
 Include: asset row/path, runtime size, visual role, readability requirement,
 animation/lifecycle requirement when present, anchor/derivative source, and
 final runtime asset path.
 Use existing final paths from ASSETS.md or assets/manifest.json.
 Do not use source sheets, curation candidates, prompt files, or scene
 references as runtime assets unless ASSETS.md explicitly lists that path as
 the final asset.
 Do not replace an available final asset with placeholder art, procedural
 shapes, or freshly drawn stand-ins.}

### Visual Self-Check                                    [REQUIRED for fixgap visual tasks]
- Source: {evaluation.json.visual_checks scene and blocking finding}
- Reference: {references/scene_name.png}
- Target state: {scene or gameplay state to capture}
- Verify: {observable visual criteria from evaluation vqa_calls[].context or SCENES.md Acceptance criteria}
- Output directory: `reports/fixgap-visual/{task_id}/`

### Scene Layout Reference                                [REQUIRED for UI/scene tasks]
{Copy the relevant scene description from SCENES.md here.
 Include: element positions, sizes, layout type, mood.
 Worker MUST follow these layout specs — element positions and proportions
 must match the description. Reference image at references/scene_{name}.png}
```

## Dispatch Rules

1. **Never delegate understanding.** Your brief must include specific file paths, Component fields, expected behavior. Not "implement movement based on the design."
2. **One objective per worker.** ONE game mechanic function + its tests.
3. **Workers write their own tests.** Minimum 2 unit tests per changed system.
4. **Workers must not spawn sub-workers.**
5. **Include game context.** Add the relevant Playable Unit fields to the brief.
6. **MEMORY entry is mandatory.** Every worker reports what they learned.
7. **Test file naming**: `test_{source_file_stem}.gd` — e.g., system file `s_movement.gd` → test file `test_s_movement.gd`. check_project.py enforces this pattern.
8. **gdUnit4 version compatibility**: Godot 4.4 → gdUnit4 v5.x, Godot 4.5+ → gdUnit4 v6.x. Headless mode requires `--ignoreHeadlessMode`.
9. **E2E input handling**: do NOT use `Input.is_action_just_pressed()` in ECS systems. Use `_input()` callback + flag variable pattern, expose `simulate_*()` methods so the Evaluator's e2e tests can drive the mechanic function.
10. **E2E state setup**: when the brief asks for a test interface, implement a
bounded setup helper or `simulate_*` method that calls the real runtime code
path.
11. **Production behavior changes**: change normal gameplay behavior, balance,
progression, content, or timing only when the worker brief cites GDD.md,
PLAN.md, or evaluation evidence that cites GDD.md or PLAN.md.
12. **UI scene root must be Control**: Any scene containing UI (menus, HUD, panels) must use a Control node as root, not Node2D. Control anchor/layout only works when the entire ancestor chain is Control nodes.
13. **Entity.name must be set explicitly**: When creating Entity instances programmatically, set `entity.name = "MyEntity"` before `add_entity()`. Without this, Godot assigns unpredictable auto-names (`@Node@2`), breaking E2E test node paths.
14. **Worker self-check is mandatory**: Workers must run the self-check protocol before submitting their report. If self-check is not mentioned in the report, reject it.
15. **UI/scene tasks require SCENES.md reference.** When dispatching a worker for any UI screen, HUD, menu, or scene layout task, you MUST copy the relevant scene description from SCENES.md into the brief. Workers without layout specs will produce inconsistent UIs.
16. **Worker model from config.** Read `worker_model` from `.godotmaker/config.yaml` (default: `sonnet`) and include it as `model:` in every Agent() call. See the Agent Call template at the top.
17. **Cwd-relative paths in the brief.** Fill every `{path}` placeholder as cwd-relative (e.g. `src/systems/s_jump.gd`, not `D:/.../src/systems/s_jump.gd`).
18. **Non-interactive execution.** Every worker brief MUST prohibit approval requests, user-input waits, and confirmation pauses.
19. **Visual tasks require runtime assets.** Fill `Asset Runtime Snapshot` and
`Visual Asset Contract` for visual tasks.
20. **Multi-frame assets are runtime behavior.** If the snapshot lists a
`grid_sheet` with frame_count > 1, the worker brief must require animated
runtime playback from metadata. Do not collapse the task into "readable
presentation" or static feedback.
21. **Temporary FX need lifecycle.** Animated projectile, impact, pickup,
slash, aura, or feedback effects must state how the effect starts and how it
disappears or clears.
22. **Region atlases are single regions.** If the snapshot lists a
`region_atlas`, require selecting the element's named region from the atlas
metadata via AtlasTexture/region. Name the target region only when the match is
not obvious from the binding. Never assign the whole atlas image as one texture
where a single element is required.
23. **Fixgap visual tasks require worker self-check output.** Fill `Visual Self-Check` for blocking findings from `evaluation.json.visual_checks` or visual critical/major issues. Use `reports/fixgap-visual/{task_id}/`, not `e2e/` or `.godotmaker/`.

## Worker Utility Convention

Workers may create shared utility functions. Follow these rules:

1. **Location**: All utility/helper functions go in `src/utils/` directory.
2. **One file per domain**: e.g., `src/utils/math_utils.gd`, `src/utils/spawn_utils.gd`.
3. **After creating utilities**: Report them in your MEMORY entry so the dispatching role can update the utils API doc.
4. **Before creating utilities**: Check `.godotmaker/utils_api.md` (if it exists) for existing utilities. Do NOT duplicate.
5. **Dispatching-role responsibility**: After each worker completes, the dispatching role updates `.godotmaker/utils_api.md` with new utility function signatures and descriptions. Include this doc path in subsequent worker briefs under "Input Files".

---

## Parallel Worker Dispatch (Worktree Isolation)

Workers with **no file ownership overlap** can run in parallel using git worktree isolation. This lets the dispatching role continue dispatching without waiting for each worker to finish.

### When to parallelize

- Two or more tasks have **completely disjoint file sets** (no shared .gd/.tscn/.tres files)
- Both tasks are in the same `/gm-build` cycle (risk or main phase)
- Neither task depends on the other's output

### Batch design rule

Don't dispatch task-by-task — design batches. Before each round, inspect every pending task's **Affected files** list in `PLAN.md` and group tasks into the largest possible batch (up to 3) whose file sets are pairwise disjoint. Sequential dependencies (B reads a class B-task creates) belong in different batches; file-disjoint independent work belongs together.

A typical `/gm-build` cycle runs as 3–6 batches: each batch is "dispatch parallel → wait for all → merge → build-check → commit", repeated until `PLAN.md` is fully `verified`. Fix tasks discovered by the Reviewer use the same batching rule.

### Precondition for parallel dispatch

Use `isolation: "worktree"` whenever the runtime supports it; fall back to
sequential worker briefs only when it does not.

Do NOT fall back to sequential because the tree has untracked or ignored files
(`.uid`, `.godot/`). Keep the main tree clean by committing between batches (see
Merge procedure).

### How to dispatch

For runtimes that support it, use the delegated agent tool with isolated
workspace support for each parallel worker:

```
Agent({
  subagent_type: "worker",
  description: "Worker: implement {mechanic_function_A}",
  model: "{worker_model}",
  isolation: "worktree",
  prompt: "{worker brief A}"
})

Agent({
  subagent_type: "worker",
  description: "Worker: implement {mechanic_function_B}",
  model: "{worker_model}",
  isolation: "worktree",
  prompt: "{worker brief B}"
})
```

Send **both Agent calls in the same message** when the runtime uses batched
calls to trigger parallel execution.

### Merge procedure after parallel workers complete

If a worker's branch is missing or `git diff main..{branch}` is empty, treat the work as lost and re-dispatch. Otherwise merge them back:

1. **Check for conflicts** before merging:
   ```bash
   git diff main..{branch_A} --name-only
   git diff main..{branch_B} --name-only
   ```
   Verify no overlapping files. If overlap exists, merge sequentially and resolve conflicts.

2. **Merge each branch**:
   ```bash
   git merge {branch_A} --no-edit
   git merge {branch_B} --no-edit
   ```

3. **Run build after merge** to catch integration issues and refresh main's class_name cache (workers' worktree caches are gitignored and don't propagate):
   ```bash
   godot --headless --import 2>&1
   ```

4. **If merge conflict occurs**: resolve manually, prioritizing the more recent/complete implementation. Then re-run both workers' unit tests to confirm.

5. **Commit the merged batch** before dispatching the next one:
   ```bash
   git add -A
   git commit -m "build: merge batch (<task ids>) + import metadata"
   ```

### Rules

- **Never parallelize workers that share files** — the merge will conflict
- **Shared read-only files are OK** — multiple workers can READ the same files
- **Verifiers/reviewers run sequentially** after merge — they need the combined project state
- **Max 3 parallel workers** at once — more than 3 increases merge complexity
- **Always build-check after merge** — parallel workers can't know about each other's changes
