---
name: gm-build
description: |
  Implement game mechanic functions via worker dispatch. Covers risk-first then main implementation.
  Dispatches workers until PLAN is clean, then runs one verify+review pass; loops until convergence.
  Explicit invocation only — use /gm-build.
disable-model-invocation: true
---

# GodotMaker Build

$ARGUMENTS

You are implementing a Godot game by dispatching Worker subagents. Risk tasks first, then main tasks — both surfaced from PLAN.md, which is **scoped to the current tag** (read the `**Tag:**` header at the top of PLAN.md). You do NOT build the whole game in one go; later tags will add features on top of this one.

## Session Setup

**FIRST ACTION — before anything else:** Write `build` to `.godotmaker/current_role`.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`.

- If `project.godot` does not exist → STOP. Tell user to run `/gm-scaffold` first.
- If `ROADMAP.md` does not exist → STOP. Tell user to run `/gm-gdd` first.
- If **no event with `role == "gdd"`** exists anywhere in the file → STOP. Tell user to run `/gm-gdd` first.
- If `PLAN.md` is missing the `**Tag:**` header → STOP. Tell user the file is stale and to re-run `/gm-gdd` to regenerate it for the current tag.
- If the **last event** has `role == "build"` AND all PLAN.md tasks are `verified` → STOP. Tell the user:
  > "Build already completed for the current tag at {timestamp}. Recommended next: /gm-verify.
  > If you need to redo this step or have other plans, just tell me."
- Otherwise → proceed (this includes resume from interrupted run AND new tasks added by reviewer).

Then read context:
- `PLAN.md` → current tag's `**Tag:**` header + Tag Mechanics + Inherited Mechanics + Playable Unit + pending/in_progress/completed tasks (anything not `verified`)
- `STRUCTURE.md` → architecture and build order (current tag scope: previous tags' systems already exist on disk and may be touched only when PLAN.md explicitly lists a refactor task for them)
- `MEMORY.md` index + sub-files (cross-tag accumulating notebook) → avoid repeating known mistakes
- `docs/tags/<prev_tag>/STRUCTURE.md` (only if PLAN.md has Inherited Mechanics or refactor tasks touching prior systems) → know what already exists before adding/refactoring

## Hard Rules

1. **You CANNOT write .gd/.tscn/.tres directly.** All game code goes through Worker dispatch.
2. **You and your workers CANNOT write to e2e/ directory.** E2E tests are owned by the Evaluator.
3. **Workers CANNOT modify PLAN.md/STRUCTURE.md/ASSETS.md.**
4. **Worker reports are validated by hooks** — incomplete reports are blocked and retried.
5. **MUST NOT skip stages.** Fix issues first; report to user after 5 attempts.
6. **MUST NOT self-certify completion.** Dispatch verifiers, then reviewers. Triaging a reviewer finding to REJECT or SKIP requires a citation per `references/reviewer-finding-triage.md` (mandatory for critical/major; optional for minor).
7. **Tag scope discipline.** Workers MAY touch files from previous tags **only if** PLAN.md has an explicit refactor / fix task naming those files. New systems live alongside existing ones; do not silently rewrite prior-tag code as a "cleanup" detour.
8. **Build the Playable Unit.** PLAN.md tasks must integrate into the Playable Unit's player-experienced path. Do not treat isolated systems, simulation helpers, or unit tests as sufficient.

## Honest Reporting

- If tests fail, report failures with output — do not claim success
- If a verification step was not run, say SKIP — do not imply PASS
- If a worker's output is unclear, re-verify before accepting
- Never characterize incomplete work as done

## Plan Discipline (Single-Direction State)

Tasks transition forward only:

```
pending → in_progress → completed → verified
```

- **Never** move backward (e.g., `verified` → `pending`)
- **Never** skip states
- Update PLAN.md IMMEDIATELY when a task changes status

**When you ACCEPT a reviewer finding against a verified task:** Do NOT change the existing task's state. Add a NEW task (status `pending`) describing the fix. The original task stays `verified`. The new task goes through the full lifecycle. (REJECT or SKIP findings go to MEMORY.md instead — see `references/reviewer-finding-triage.md`.)

This way the state is always monotonic and the audit trail is preserved.

A `failed` task requires a new task or user escalation — do not retry in place.

## Build Cycle

The cycle has three steps and runs until convergence (PLAN clean **and** the
last verify+review pass produced no new ACCEPTED tasks). Reviewer is invoked
**once per cycle iteration** — after every PLAN task reaches `completed`,
not on a worker-count cadence.

### Step 0 — Process Verify Feedback

Run this step before Step 1 only if `.godotmaker/verify_report.json` exists, `result == "fail"`, and its `ts` is later than the most recent `role == "build"` event in `stage.jsonl` (or there is no prior build event). Otherwise → skip to Step 1.

Translate failures into `pending` tasks at the bottom of `PLAN.md`.

**Project-code tasks** (any `checks.<name>.result == "fail"`) — go through the normal Worker → Verifier → Reviewer cycle:

- `checks.build.errors[]` → one task per distinct compile error (file + line + message in Notes).
- `checks.unit_tests.failures[]` → one task per failing test. If `failed > 0` but `failures[]` is empty, one task: "investigate test runner output".
- `checks.lint.issues[]` → group by file when multiple issues hit the same file; otherwise one per issue.
- `checks.lint.format_drift` → one task: "run `<format_drift.command>` to format the drifted files (`<file_count>` files)".
- `checks.static_check.issues[]` → one task per issue, using `check` as the title prefix (e.g. `missing_unit_test: s_player_input`). For unknown `check` discriminators, use the raw value verbatim — generic project-code fix.

**Config tasks** (any `checks.<name>.result == "error"`, paired with one `tooling_notes[]` entry) — main agent applies directly, NO worker dispatch:

- Routable fallback (`exclude_file` / `scope_narrow` / `add_gdlintrc_rule` / `skip_check`) WITH operand present (per the fallback table in `gm-verify/SKILL.md` Section B) → apply the structured edit using the note's operand. Mark `verified` after the next verify round confirms the tool no longer crashes there. Hard Rule 1 only restricts `.gd/.tscn/.tres`.
- `escalate`, OR routable with missing operand, OR unknown discriminator → do NOT auto-fix. Surface `tool` + `error` + `crashed_on` (and any original `suggested_fallback`) to the user verbatim, halt the build cycle, leave the task `pending` until the user resolves the underlying issue.

Do NOT delete project code as a "fix" for a tool crash.

### Step 1 — Dispatch Workers (until PLAN is clean)

- Read `references/worker-dispatch.md` for the brief template
- Use `subagent_type: "worker"`. Each worker implements ONE game mechanic function + its tests.
- Include the relevant Playable Unit fields in each worker brief.
- Max 3 in parallel with disjoint file sets via `isolation: "worktree"` (send all Agent calls in one message).
- After each worker reports DONE, mark its task in PLAN.md as `completed`.
- **`main_scene` retarget is your job.** Scaffold leaves `run/main_scene="res://scenes/main.tscn"` (placeholder). After the worker that creates this tag's entry scene (per SCENES.md) completes and the `.tscn` is on disk, `Edit` `project.godot`'s `[application] run/main_scene` to `res://<path>`.
- Continue dispatching until PLAN.md has no `pending` or `in_progress` tasks (everything is `completed` or `verified`). Then go to Step 2.

### Step 2 — Verify + Review Pass

Run ONE verifier, then ONE reviewer, on the integrated state:

**Verifier:**
- Read `references/verifier-dispatch.md` for the brief template
- Use `subagent_type: "verifier"`. Pass all `completed`-but-not-yet-`verified` workers' deliverables.
- On FAIL: add NEW `pending` fix tasks in PLAN.md. Failed tasks stay `completed`. Go back to Step 1.
- On PASS: update those tasks from `completed` → `verified`.

**Reviewer** (after verifier passes):
- Read `references/reviewer-dispatch.md` for the brief template
- Use `subagent_type: "reviewer"`. Reviewer reports back; do not let it modify project files.
- Ask the reviewer to check gameplay authenticity for the integrated Playable Unit.
- Triage each finding per `references/reviewer-finding-triage.md` into one of three options:
  - **ACCEPT** → add NEW `pending` fix task to PLAN.md.
  - **REJECT** → finding is wrong; append a record to MEMORY.md "Reviewer Triage Log" section (citation required for critical/major).
  - **SKIP** → finding is real but not worth fixing now; same MEMORY.md section (citation required for critical/major).
- Defaults when uncertain: critical/major → ACCEPT; minor → SKIP.
- If you ACCEPTED any findings → go back to Step 1.
- If verifier passed AND reviewer added zero ACCEPTED tasks → exit cycle (proceed to "When Done").

The build cycle continues until ALL tasks are `verified` AND the most recent
verify+review pass produced no new ACCEPTED tasks AND the verifier passed.

## Retry Limits

Max 5 attempts to fix the same task. After 5 failures, stop and escalate to
the user with a summary of what was tried — do not retry the identical
action, do not suppress errors, do not claim success without verification.

## Parallel Worker Rules

- **Never parallelize workers that share files**
- Workers with disjoint file sets use `isolation: "worktree"`
- **Max 3 parallel workers** at once (file isolation constraint)
- After parallel workers complete, merge branches and build-check
- See `references/worker-dispatch.md` → Parallel Worker Dispatch for merge procedure

## Memory System

```
MEMORY.md              <- Index + cross-cutting knowledge
memory/
  {system_name}.md     <- Per-system details (template: .claude/templates/memory_subsystem.md)
```

- Read MEMORY.md before dispatching workers
- Update after every verification round (you write, not workers/reviewers)

## Available Skills & Tools

| Skill | Purpose | Path |
|-------|---------|------|
| gecs | ECS framework API + patterns | .claude/skills/gecs/SKILL.md |
| headless-build | Compile verification | .claude/skills/headless-build/SKILL.md |
| gdunit-driver | Unit test execution | .claude/skills/gdunit-driver/SKILL.md |
| godot-api | Godot API reference | .claude/skills/godot-api/SKILL.md |
| screenshot | Gameplay screenshot capture | .claude/skills/screenshot/SKILL.md |
| mcp-driver | Runtime debugging via godot-mcp | .claude/skills/mcp-driver/SKILL.md |

**Asset analysis:** Dispatch an Analyst subagent (`subagent_type: "analyst"`, see `references/analyst-dispatch.md`) when you need to analyze user-provided assets.

## Context Management

Your context window is finite. Protect it:

**In your context:** PLAN.md status, STRUCTURE.md architecture, worker briefs (~200 tokens), worker summaries (~100 tokens), verification results, design decisions.

**Out of your context (delegate to workers):** Asset generation, system implementation code, test code, build/lint output, screenshot analysis.

**When context gets large:** Summarize completed phases. Reference documents by path. Write decisions to MEMORY.md for recovery after compaction.

## When Done

When ALL PLAN.md tasks are `verified` AND the most recent verify+review pass produced no new ACCEPTED fix tasks:

1. From the project root run `python tools/append_stage_event.py build` to append a `{"role": "build", "ts": "<server-generated UTC>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.
2. `git add -A && git commit -m "chore(build): <Tag>"`
3. Inform the user: `Build complete. Recommended next: /gm-verify`