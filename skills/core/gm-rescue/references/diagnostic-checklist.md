# Diagnostic checklist — what to inspect, in what order

Use this when walking the godotmaker layers in `gm-rescue` Step 3.
Order is from highest-leverage failure mode to lowest. Stop as soon
as you have a confirmed defect — you don't need to walk the whole
list every time.

## 1. Hooks (highest leverage)

A misconfigured hook can deny *every* tool call of a given shape, so
its blast radius is huge. Bad hook = stuck pipeline that nothing
else can recover from.

Files to inspect (under `hooks/` in the godotmaker repo):

- `check_stage_prerequisites.py` — denies Agent dispatch if prereqs missing.
  Common defect: a new role added to PIPELINE_ROLES without updating
  PREREQ_ROLE here, or a path that the role legitimately produces under a
  different name.
- `check_completion.py` — blocks Stop in worker-dispatching roles.
  Common defect: BLOCK_LIMIT not high enough; stale state.json
  `stop_block_count` carrying over across sessions.
- `check_file_permissions.py` — denies Write/Edit by role.
  Common defect: a path the SKILL.md tells the agent to write is
  not in the role's allow-list here.
- `check_worker_report.py` — blocks SubagentStop if the worker's
  output doesn't match required structure.
  Common defect: required section name was renamed in worker-dispatch.md
  but not here, so workers can't produce a passing report no matter
  what they write.
- `check_asset_access.py` — denies image binary Read for non-analyst agents.
  Common defect: marks a `references/` path as image when it's actually a
  text file, or vice versa.
- `check_stage_prerequisites.py`'s schema validation against
  `config/stage_schemas.json` — see §3 below.
- `stage_reminder.py` — runs `validate_schema_files` and the
  `PROGRAMMATIC_CHECKS` table at role completion.
  Common defect: a check function returns a string the user can't act
  on, or fires on a state the role legitimately produces.

What to look for in each:
- Regex over a path/role name that doesn't match a recently added value.
- A required field the upstream skill never produces.
- Cumulative state (state.json, stage.jsonl) consulted in a way that
  treats prior-tag state as current-tag state.

## 2. SKILL.md instructions (next-highest leverage)

A SKILL.md that contradicts itself or contradicts another role's SKILL.md
will produce inconsistent agent behaviour that no amount of fixgap can
converge.

Files to inspect (under `skills/core/gm-*/SKILL.md`):

- The skill that was active when the pipeline got stuck (read
  `.godotmaker/current_role`).
- The skill immediately upstream (its outputs are this skill's inputs).

What to look for:
- Hard Rule that says "you MUST X" while another section says "do NOT X".
- Resume Check that can never become satisfiable from the current state.
- "Permission" line that omits a path the Process section tells the agent
  to write to (this typically surfaces as a hook block — cross-reference §1).
- References to files / paths that no longer exist in the current layout
  (e.g., a SKILL.md still mentions `.godotmaker/milestones/` after the
  layout changed to `docs/tags/`).

## 3. Config schemas

`config/stage_schemas.json` declares each role's required output files
and `checks`. Mismatches here surface as "Cannot mark role X complete"
errors from `stage_reminder.py`.

What to look for:
- A `files` entry that names a path the role doesn't actually produce
  (or produces under a different name).
- A `checks` entry naming a function that doesn't exist in
  `PROGRAMMATIC_CHECKS` — this would raise at hook time.
- A role missing entirely from the schema, when downstream code expects
  it (e.g., the `rescue` role).

## 4. Templates

Templates rarely cause hard pipeline blocks on their own, but they
shape what gets generated, and a wrong template can produce documents
that downstream stages can't parse.

Files to inspect (under `templates/`):

- `PLAN.md` — if the `**Tag:**` header or `Tag Mechanics` / `Inherited
  Mechanics` sections are missing, every downstream skill that depends
  on them breaks (gm-build, gm-evaluate especially).
- `STRUCTURE.md`, `SCENES.md`, `ASSETS.md`, `MEMORY.md`, `ROADMAP.md`,
  `TOC.md` — same idea, smaller blast radius.
- `game-claude.md` — what gets deployed to the game project's CLAUDE.md.
  Wrong content here misroutes the user's expectations of the pipeline.

## 5. Shared references

Files under `skills/core/_shared/` are deployed into multiple skills'
`references/` directories by `publish.py`. A defect here amplifies
across every consumer.

- `worker-dispatch.md` — consumed by gm-build and gm-fixgap. If the
  brief format here drifts from what `check_worker_report.py` requires,
  every worker fails the report check.
- `verifier-dispatch.md`, `reviewer-dispatch.md`, `analyst-dispatch.md`
  — same pattern.

## 6. Tools

Last resort. Tools (`tools/asset_source_generate.py`, `tools/check_project.py`,
`tools/migrate.py`, etc.) are subprocesses; if they fail, they
typically produce a clear stderr message that the calling skill
relays to the user, so "stuck pipeline with no clear error" is
rarely a tools-layer issue.

If a tool *is* the issue:
- Check whether the tool's expected layout matches the post-tag-refactor
  layout (e.g., a tool looking for root `PLAN.md` as a whole-game plan
  when it's now per-tag).
- Check whether tool flags drifted from how the skill invokes them.

## What to skip

- The user's game code under `src/`, `scenes/`, `assets/`, `e2e/`.
  Issues there are NOT godotmaker defects — they're either AI
  implementation issues or GDD-spec issues, both belong in the
  "NOT A GODOTMAKER DEFECT" branch of the diagnosis.
- `addons/` — third-party (gecs, gdUnit4, etc.). Even if these have bugs,
  godotmaker's contract is "pin a working version", so the defect would
  be in `config/addon_versions.json`, not the addon itself.
- Anything that requires running godot or executing the user's game.
  Rescue is read-only diagnostic; runtime behaviour evidence has to come
  in via the artifacts in `gm-rescue` Step 1.
