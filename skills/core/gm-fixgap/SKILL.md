---
name: gm-fixgap
description: |
  Fix gaps identified by the Evaluator. Generates GAP.md from evaluation.json,
  dispatches workers to address critical/major issues, then runs one final
  verify+review pass. Unlike gm-build (PLAN.md-driven), gm-fixgap is GAP.md-driven.
  Explicit invocation only — use /gm-fixgap.
disable-model-invocation: true
---

# GodotMaker Fix Gap

$ARGUMENTS

You are fixing specific issues identified by the Evaluator. You read the evaluation report, generate a GAP.md task list, dispatch workers to address each gap, then run one final verify+review pass.

**Loop position:** `/gm-fixgap` is never terminal. The cycle is `/gm-fixgap → /gm-verify → /gm-evaluate`. Evaluate either approves (→ `/gm-accept`) or surfaces new gaps (→ another `/gm-fixgap`).

## Session Setup

**FIRST ACTION — before anything else:** Write `fixgap` to `.godotmaker/current_role`.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`.

- If **no event with `role == "evaluate"`** exists anywhere in the file OR `.godotmaker/evaluation.json` does not exist → STOP. Tell user to run `/gm-evaluate` first.
- If `evaluation.json` `result` is `"approve"` → STOP. Tell the user:
  > "The latest evaluation was already approved. Recommended next: /gm-accept.
  > If you need to redo this step or have other plans, just tell me."
- If the **last event** has `role == "fixgap"` AND `GAP.md` is not at project root (already archived) → STOP. Tell the user:
  > "Fixgap already completed for the latest evaluation at {timestamp}. Recommended next: /gm-verify.
  > If you need to redo this step or have other plans, just tell me."
- Otherwise → proceed (fresh fixgap or repeat fixgap is both valid).

Then read context:
- `GAP.md` (if present) → existing fix progress; find tasks not yet `verified`. If missing, Step 1 will generate it from `evaluation.json` (and `verify_report.json`).
- `.godotmaker/evaluation.json` → the source of truth for product-layer issues to fix
- `.godotmaker/verify_report.json` → mechanical-layer failures from the most recent verify
- `PLAN.md` → read-only; current tag's `**Tag:**` header tells you which tag's gaps you're fixing. The same tag-scope discipline as gm-build applies: previous tags' code is touchable only when a GAP item explicitly names it.
- `STRUCTURE.md` → architecture (fixes need to respect existing system boundaries)
- `MEMORY.md` index + sub-files → past decisions and known gotchas

## Hard Rules

1. **You CANNOT write .gd/.tscn/.tres directly.** All game code goes through Worker dispatch.
2. **You and your workers CANNOT write to e2e/ directory.** E2E tests are owned by the Evaluator.
3. **Workers CANNOT modify GAP.md/PLAN.md/STRUCTURE.md/ASSETS.md.**
4. **Worker reports are validated by hooks** — incomplete reports are blocked and retried.
5. **Only fix what `evaluation.json` or a fresh `verify_report.json` identified.** Do not add features or refactor unrelated code.
6. **MUST NOT self-certify completion.** Dispatch verifiers, then reviewers. Triaging a reviewer finding to REJECT or SKIP requires a citation per `references/reviewer-finding-triage.md` (mandatory for critical/major; optional for minor).
7. **Do not promote non-blocking visual findings.** If evaluation or verification marks a visual finding as style-only or non-blocking, keep it in notes/minor issues; do not create a new C/J task from it.

## Honest Reporting

- If tests fail, report failures with output — do not claim success
- If a verification step was not run, say SKIP — do not imply PASS
- If a worker's output is unclear, re-verify before accepting
- Never characterize incomplete work as done

## Plan Discipline (Single-Direction State)

GAP.md tasks transition forward only:

```
pending → in_progress → completed → verified
```

- **Never** move backward (e.g., `verified` → `pending`)
- **Never** skip states
- Update GAP.md IMMEDIATELY when a task changes status

**When you ACCEPT a reviewer finding against a verified task:** Do NOT change the existing task's state. Add a NEW task (status `pending`) in GAP.md describing the fix. The original task stays `verified`. The new task goes through the full lifecycle. (REJECT or SKIP findings go to MEMORY.md instead — see `references/reviewer-finding-triage.md`.)

This way the state is always monotonic and the audit trail is preserved.

A `failed` task requires a new task or user escalation — do not retry in place.

Do NOT update PLAN.md task statuses — fixgap operates from `evaluation.json` gaps, not the original plan.

## Build Cycle

### Step 1 — Read Evaluation (+ Verify Feedback), Generate or Resume GAP.md

GAP.md may need tasks from two sources:

1. **`.godotmaker/evaluation.json`** — product-layer issues found by the evaluator. Always processed.
2. **`.godotmaker/verify_report.json`** — mechanical-layer failures from the most recent verify pass. Processed only when fresh.

#### 1a. Pull issues from `evaluation.json`

Create one critical evaluation-source GAP task for each `playable_unit.rows.*`
entry with `result == "fail"`. Include the row key, test path, and evidence
entries. Fix the game code or runtime path. Do not reduce the `PLAN.md` or
`e2e/` contract.

- `critical_issues` — must fix all (→ task IDs `C1`, `C2`, …)
- `major_issues` — fix as many as possible (→ task IDs `J1`, `J2`, …)
- `gameplay_issues` — fix only if related to a critical/major (→ `G1`, `G2`, …)
- `minor_issues` — skip unless trivial

Evaluation-source visual tasks must cite the blocking finding reported by
evaluation. Do not create a C/J task from a style-only or non-blocking visual
finding.

#### 1b. Pull failures from `verify_report.json`

Run this sub-step only if `.godotmaker/verify_report.json` exists, `result == "fail"`, and its `ts` is later than the most recent `role == "fixgap"` event in `stage.jsonl` (or there is no prior fixgap event). Otherwise (file missing, `result == "pass"`, or stale `ts`) → skip 1b; GAP.md comes from 1a only.

Translate failures into tasks using the existing `C` / `J` prefixes — verify-source tasks share the numbering pool with evaluation-source tasks. **Each task carries both a classification (C/J) and an execution mode** (worker / main-agent-direct / escalate-to-user); Step 3 follows the execution mode without re-classifying.

**Project-code tasks** (`checks.<name>.result == "fail"`) — execution = **dispatch worker** (normal Worker → Verifier → Reviewer cycle):
- `checks.build.errors[]` / `checks.unit_tests.failures[]` → **C** (compile/runtime failures block forward progress).
- `checks.unit_tests` with `failed > 0` and empty `failures[]` → **C**, one task: "investigate test runner output".
- `checks.static_check.issues[]` of `check == "missing_unit_test"` → **J** (gap, not a hard block).
- Other `checks.static_check.issues[]` → **C** (project-completeness gate).
- `checks.lint.issues[]`, `checks.lint.format_drift` → **J** (technical debt).
- Unknown `static_check.issues[].check` discriminator → use the raw value verbatim, default **C**.

**Config tasks** (`checks.<name>.result == "error"`, paired with `tooling_notes[]`):
- Routable fallback WITH operand present (per the fallback table in `gm-verify/SKILL.md` Section B) → **J**, execution = **main-agent-direct** (apply the structured edit using the operand; Hard Rule 1 only restricts `.gd/.tscn/.tres`; mark `verified` after the next verify round confirms the crash is gone). NO worker dispatch.
- `escalate`, OR routable with missing operand, OR unknown discriminator → **C**, execution = **escalate-to-user** (surface `tool` + `error` + `crashed_on` and any original `suggested_fallback` verbatim, halt the cycle, leave `pending` until the user resolves it). NO worker dispatch.

Each task records its origin via a `Source: verify_report.json | evaluation.json` line in the task block (and `verify` / `evaluation` in the Task Status table). Numbering follows insertion order — existing rows keep their numbers, new rows get the next available number per letter. Execution priority dispatches verify-source before evaluation-source regardless of number.

#### 1c. Write or merge GAP.md

**If `GAP.md` does not exist:**
Generate it from `.claude/templates/GAP.md`. Within each letter list verify-source tasks first (so they get the lower numbers), then evaluation-source. All tasks start as `pending`. Record both source timestamps in the header — `Source Evaluation: <evaluation iteration / ts>` and (when applicable) `Source Verify: <verify_report ts>`.

**If `GAP.md` already exists:**
- `Source Evaluation` header differs from current `evaluation.json` → archive and generate a fresh one.
- Header matches AND 1b applies → **append** new verify-source tasks as `pending` rows with the next available number per letter; existing rows keep their numbers and statuses. Update the `Source Verify` header to the new ts.
- Header matches AND 1b does not apply → resume (skip already-`verified` tasks).

**Backward compatibility (per-row).** Apply on each row independently — interrupted upgrades leave mixed-annotated state:
- Row missing `Source:` line or `Source` column entry → treat as `evaluation`, fill when you next touch that row.
- Row already annotated → leave its `Source:` as-is.
- New verify-source rows always include both the `Source:` line and the column entry.

### Step 2 — Plan Fixes

For each non-`verified` task in GAP.md:
1. Identify which system/file needs to change (record in the task's `Affected files/systems`)
2. Determine if the fix is code (dispatch worker) or config (you can do it)
3. Group related issues that touch the same files into one worker brief

### Step 3 — Dispatch Workers

Worker-dispatch tasks only — Step 1b classified main-agent-direct and escalate-to-user tasks; handle those per their classification, not here.

- Read `references/worker-dispatch.md` for the brief template.
- Dispatch verify-source before evaluation-source within `pending`.
- Use `subagent_type: "worker"`. Max 3 in parallel with disjoint file sets via `isolation: "worktree"`.
- In each brief, paste the specific finding from GAP.md, the file(s) to modify, and the correct behavior from GDD.md.
- Update task status `pending` → `in_progress` when dispatched, `in_progress` → `completed` when worker reports DONE.

### Step 4 — Final Verify + Review (single pass after all fixes)

Unlike gm-build, fixgap does NOT batch every ≥N workers. Because the issue
count from a single evaluation is small, run **one** verify + review pass
after **all** GAP.md tasks reach `completed`.

**Verifier:**
- Read `references/verifier-dispatch.md` for the brief template
- Use `subagent_type: "verifier"`. Pass all completed workers' deliverables.
- A new FAIL task must cite an unresolved blocking finding or a blocking regression.
- On FAIL for a task: add a NEW pending task in GAP.md (the failed task stays `completed`). Loop back to Step 3.
- On PASS: update those tasks from `completed` → `verified`.

If verification exposes a design constraint conflict, stop splitting it into
smaller visual tasks. Record the conflict in GAP.md notes, choose the
interpretation already stated by SCENES.md if clear, or escalate for a design
decision.

**Reviewer** (after verifier passes):
- Read `references/reviewer-dispatch.md` for the brief template
- Use `subagent_type: "reviewer"`. Reviewer reports back; do not let it modify project files.
- Triage each finding per `references/reviewer-finding-triage.md` into one of three options:
  - **ACCEPT** → add NEW `pending` task to GAP.md.
  - **REJECT** → finding is wrong; append a record to MEMORY.md "Reviewer Triage Log" section (citation required for critical/major).
  - **SKIP** → finding is real but not worth fixing now; same MEMORY.md section (citation required for critical/major).
- Defaults when uncertain: critical/major → ACCEPT; minor → SKIP.
- If you ACCEPTED any findings → loop back to Step 3.

The cycle ends when ALL GAP.md tasks are `verified` AND the most recent
review round added no ACCEPTED tasks.

### Step 5 — Archive GAP.md

Move the completed `GAP.md` to `.godotmaker/gaps/<source-evaluation-iteration>/GAP.md`
so the project root is clean for the next round.

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

**In your context:** GAP.md status, STRUCTURE.md architecture, worker briefs (~200 tokens), worker summaries (~100 tokens), verification results, design decisions.

**Out of your context (delegate to workers):** Fix code, test code, build/lint output, screenshot analysis.

**When context gets large:** Summarize completed fixes. Reference documents by path. Write decisions to MEMORY.md for recovery after compaction.

## When Done

After all GAP.md tasks are `verified`, the final reviewer added no new tasks, and GAP.md has been archived:

1. From the project root run `python tools/append_stage_event.py fixgap` to append a `{"role": "fixgap", "ts": "<server-generated UTC>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.
2. `git add -A && git commit -m "chore(fixgap): <Tag>"`
3. Inform the user: `Fixgap complete. Recommended next: /gm-verify` (then re-run `/gm-evaluate` to confirm the gaps are closed).
