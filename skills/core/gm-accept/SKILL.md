---
name: gm-accept
description: |
  Present final results to the user for acceptance.
  Shows evaluation results, evaluator screenshots, and asks for confirmation.
  Explicit invocation only — use /gm-accept.
disable-model-invocation: true
---

# GodotMaker Accept

$ARGUMENTS

You are presenting the **current tag's** completed work to the user for acceptance. This is a per-tag gate — accepting now does NOT mean the whole game is done; it means this tag (vX.Y.Z) is ready to be sealed, archived, and git-tagged by `/gm-finalize`. The user can choose to continue to the next tag (`/gm-gdd` again) or stop the project here.

## Session Setup

**FIRST ACTION — before anything else:** Write `accept` to `.godotmaker/current_role`. Do this on every invocation, even when the file already contains `accept` (for example an idempotent re-entry) — reading the file is not a substitute. The write must actually happen and must be your first action.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`. Also read `.godotmaker/evaluation.json`.

- If **no event with `role == "evaluate"`** exists anywhere in the file OR `evaluation.json` does not exist → STOP. Tell user to run `/gm-evaluate` first.
- If `evaluation.json` `result` is `"reject"` → STOP. Tell user to run `/gm-fixgap` first.
- If the **last event** has `role == "accept"` AND its `decision == "accept"` → STOP. Tell the user:
  > "Accept already recorded at {timestamp}. Recommended next: /gm-finalize.
  > If you need to redo this step or have other plans, just tell me."
- Otherwise → proceed (re-invocation is valid if the previous accept event recorded a `fix` or `done` decision).

## Process

### 1. Gather Results

Read these files:
- `.godotmaker/evaluation.json` — evaluator results (mandatory)
- `PLAN.md` — task completion status
- `MEMORY.md` — known issues and discoveries
- `GDD.md` — original requirements

### 2. Collect Screenshots

Do NOT capture new screenshots. Use the screenshots already captured by the Evaluator:
- Look in `e2e/screenshots/` for `scene_{name}.png` files
- These correspond to reference images in `references/scene_{name}.png`
- If no evaluator screenshots exist, note this as a gap

### 3. Present to User

Format a clear summary:

```
## Tag Summary — {Tag from PLAN.md}

**Project:** {name}
**Tag delivers:** {one-liner from ROADMAP.md entry for this tag}

### What This Tag Built
- {N} new systems, {M} new components added in this tag
- Tag mechanics delivered: {Tag Mechanics list from PLAN.md, all PASS per evaluation.json `tag_mechanics`}
- Inherited mechanics still passing: {list each `<prev>-MN: pass` from evaluation.json `inherited_mechanics`}

### Test Results
- Unit tests: {from gm-verify results or PLAN.md}
- E2E suite: {evaluation.json `e2e_tests.passed`/`e2e_tests.total` — single suite covering both this tag's mechanics and inherited mechanics}

### Evaluation Result: APPROVED
- Mandatory checks: all passed
- Visual checks: {summary}
- Gameplay issues: {from evaluation.json, or "none"}

### Known Limitations
- {from MEMORY.md and evaluation minor_issues}

### Reviewer Triage Decisions for This Tag

(Read MEMORY.md "Reviewer Triage Log" section, filter to entries whose
Tag matches the current tag from PLAN.md. If none → write "(none)".)

| Time | File/Area | Severity | Decision | Finding | Reason | Citation |
|------|-----------|----------|----------|---------|--------|----------|
| ...  | ...       | ...      | ...      | ...     | ...    | ...      |

(If the user thinks any REJECT or SKIP was wrong, they choose "Fix
issues" in Step 4 and tell me which finding to revisit; gm-fixgap will
pick it up.)

### How to Run
{instructions}

### Screenshots
{show evaluator screenshots side-by-side with references}

### What's Next
- After /gm-finalize this tag will be archived to docs/tags/{Tag}/ and `git tag {Tag}` will be created.
- Remaining tags in ROADMAP.md: {list of unshipped tags}
- To start the next tag, re-run /gm-gdd; to stop here, just don't.
```

### 4. Ask for Decision

Use AskUserQuestion to ask:
- **Accept** → I'll record acceptance and recommend /gm-finalize.
- **Fix issues** → tell me what to fix and I'll dispatch /gm-fixgap.
- **Done for now** → progress is saved; you can resume any time."

Do NOT proceed until the user replies. Their reply drives the When Done branch below.

## When Done

Always append a trace event to `.godotmaker/stage.jsonl` recording the user's decision, regardless of which branch was chosen. From the project root run:

```
python tools/append_stage_event.py accept --decision=<accept|fix|done>
```

This appends a `{"role": "accept", "ts": "<server-generated UTC>", "decision": "<accept|fix|done>"}` line. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.

Then: `git add -A && git commit -m "chore(accept): <Tag> <decision>"`.

Then, based on the decision:
- **accept** → Inform the user: `Accepted. Recommended next: /gm-finalize`
- **fix** → Inform the user to run `/gm-fixgap` with specific fix instructions
- **done** → Inform the user: `Progress saved; resume any time`

Note: only events with `decision == "accept"` count as the role having truly completed for `/gm-finalize`'s prerequisite check. The `fix` and `done` events are kept as audit trail.
