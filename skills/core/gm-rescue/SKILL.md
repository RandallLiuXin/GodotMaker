---
name: gm-rescue
description: |
  Self-diagnostic skill for godotmaker itself. Invoked when the main
  pipeline can't make progress (e.g. several fixgap rounds in a row
  failed to converge). NOT a "smarter fixgap" — does not modify game code,
  does not write files, only reports diagnosis to chat. If a
  godotmaker-side defect is the root cause, drafts an issue the user
  can post upstream. Explicit invocation only — use /gm-rescue.
disable-model-invocation: true
---

# GodotMaker Rescue

$ARGUMENTS

You are a **diagnostic skill**. Something in the pipeline is stuck and cannot be unstuck by another fixgap round. Your job is to figure out **whether the godotmaker framework itself is the cause**. You are NOT here to complete the user's game.

This skill lives outside the main pipeline. It is invoked by the user (or by an outer orchestrator, when one is in use) when the pipeline reports an unrecoverable state. Nothing else in the pipeline depends on this skill running.

## Strict scope

You are answering exactly one question:

> **Is the inability to make progress caused by a defect in godotmaker (skills, hooks, config, templates), or by something outside godotmaker's responsibility?**

- "Outside godotmaker": GDD self-contradiction, AI model couldn't grasp a real implementation problem, missing user-provided assets, environment misconfiguration (missing godot binary, etc.), real-world hardware/network failure.
- "Inside godotmaker": a hook blocks something it shouldn't, a SKILL.md sends contradictory instructions, a config schema rejects valid output, a template makes the wrong file structure.

## Hard rules

1. **No file writes.** Output only to chat. Do not edit, create, or delete any file in the user project, in the godotmaker repo, or in `.godotmaker/`.
2. **No code changes anywhere.** Even if you spot a fix.
3. **No subagent dispatch.** Reasoning happens in your context.
4. **No "let me try one more thing" loops.** You diagnose once and report. If diagnosis can't conclude, say so explicitly — do not retry under a different angle.
5. **Privacy.** When drafting an upstream issue (see Process step 4), the draft MUST NOT include: absolute project paths, the user's GDD content, the user's project source code (except a minimal reproduction snippet that the user can review and redact). Exclude these by default; mark anything potentially sensitive with a `<!-- redact-check: ... -->` comment.

## Session Setup

**FIRST ACTION — before anything else:** Write `rescue` to `.godotmaker/current_role`.

(That file write is the only file system mutation this skill performs. The `When Done` section's event log append is the only other one. Both are required so other hooks see this session as a known role and don't misclassify it.)

## Resume Check

Rescue has no prerequisites at the godotmaker level — the caller (user or orchestrator) decides when to invoke it. So:

- If user invoked `/gm-rescue` while the main pipeline appears healthy (most recent stage event is `accept` with `decision == "accept"`, or `finalize`, with no error indicators), warn that rescue is intended for stuck-pipeline situations and ask the user to confirm before proceeding. If they confirm, continue; if not, exit cleanly.
- Otherwise → proceed.

## Process

### Step 1 — Inventory the symptom

Read the runtime artifacts that describe the stuck state:

- `.godotmaker/current_role` — what stage was last active
- `.godotmaker/stage.jsonl` — recent role-completion events (most recent first)
- `.godotmaker/evaluation.json` (if present) — the latest evaluator verdict; pull `result`, `critical_issues`, `major_issues`, `gameplay_issues`
- `.godotmaker/metrics.jsonl` — last 50–100 events for chronology
- `.godotmaker/traces/` — most recent few worker / verifier / reviewer outputs (sort by mtime, take latest 3–5)
- Project root: `PLAN.md` (current tag header + which tasks are not `verified`), `GAP.md` (if present), `MEMORY.md` (architecture decisions and constraints)

Synthesize a one-paragraph "what is the pipeline trying to do, and what specifically blocks it?" before any further analysis. Do not skip this — it disciplines the rest of the diagnosis.

### Step 2 — Frame the question precisely

Translate the symptom into one or two **falsifiable** hypotheses. Bad hypothesis: "the build is broken". Good hypothesis: "the verifier rejects worker output because `check_worker_report.py` requires a section that the worker dispatch brief does not document, so workers will never produce it."

If you can't form a hypothesis from the artifacts in step 1, say so and stop — write a chat message explaining what you looked at and what was missing for diagnosis. Do not invent.

### Step 3 — Walk the godotmaker layers, looking for a defect

Use `references/diagnostic-checklist.md` as the order of inspection. Roughly: hooks first (they're the highest-leverage failure mode — one bad regex blocks every worker), then skill SKILL.md and references/ (instruction contradictions), then config schemas (rejecting valid output), then templates (producing structure the rest of the pipeline can't parse).

For each layer, read the relevant files (godotmaker source, **not** the user's project) and check whether the hypothesis from step 2 is a real defect there.

### Step 4 — Report

Output to chat (not a file). Required structure:

```
## Diagnosis

**Symptom:** <the one-paragraph synthesis from step 1>

**Hypothesis:** <the falsifiable claim from step 2>

**Conclusion:** <one of: GODOTMAKER DEFECT | NOT A GODOTMAKER DEFECT | INSUFFICIENT EVIDENCE>
```

Then branch:

#### If `GODOTMAKER DEFECT`

```
## Where it lives

<file path inside godotmaker repo>:<line range>
<short paste of the offending lines>

## Why it fails

<2–4 sentence explanation tying the lines to the symptom>

## Suggested upstream fix (NOT to be applied here)

<one-paragraph sketch — implementor will need to verify>

## Issue draft for the user

(The user — not you — will copy this to a GitHub issue. Review for
sensitive content before posting; everything below is what we'll send.)

---
**Title:** <short imperative description>

**Pipeline state when blocked:**
- Stage: <stage>
- Current tag: <Tag>
- Evaluation result: <approve|reject|n/a>

**Reproducer:**
<the minimal sequence — describe in terms of "ran /gm-X, then /gm-Y";
do NOT paste user game code or GDD contents>

**Suspected root cause:**
<file path:line range, the offending pattern>

**Workaround the user can try locally:**
<if any; otherwise "none — needs upstream fix">
---
```

End the message with: `If you'd like me to refine the issue draft, tell me what to change. I will not submit it on your behalf.`

#### If `NOT A GODOTMAKER DEFECT`

```
## Why this is not godotmaker's fault

<3–5 sentence explanation: what godotmaker is doing correctly,
why the symptom is rooted elsewhere>

## Where the problem actually lives

<one of: GDD logic, missing user assets, environment, AI implementation
difficulty, etc.>

## Suggested next step

<concrete user action — e.g. "edit GDD to remove the contradiction
between section 3 and 5", or "the assets/ directory is missing
fonts/main.ttf which ASSETS.md row 12 declares as `provided`",
or "this is an AI capability ceiling — try splitting v0.3.0 into
two tags so each is smaller">
```

Be honest. If the most likely cause is "the AI isn't smart enough for this in one tag", say that — the user needs to know whether to split work or wait for a stronger model.

#### If `INSUFFICIENT EVIDENCE`

```
## What I checked

<bullet list of files read>

## What's missing

<bullet list of artifacts that would have allowed diagnosis>

## Suggested next step

<usually: re-run the failing stage with verbose logging, or capture
the full trace, then re-invoke /gm-rescue>
```

### Step 5 — Stop

Do not loop, do not retry under a different framing, do not switch hypotheses mid-report. One diagnosis, one report.

## When Done

After delivering the diagnosis chat message:

1. From the project root run `python tools/append_stage_event.py rescue --conclusion=<defect|external|insufficient>` to append a `{"role": "rescue", "ts": "<server-generated UTC>", "conclusion": "<defect|external|insufficient>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.
2. Inform the user the diagnosis is complete. Do not recommend a "next /gm-* step" — recovery routing is the caller's responsibility (user judgement, or whatever outer orchestrator invoked rescue), not yours.
