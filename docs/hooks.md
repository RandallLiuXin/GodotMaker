# Hooks Reference

Complete reference for all GodotMaker hooks. Hooks are Python scripts that run
on coding-agent runtime events to enforce pipeline rules.

Hook registration is runner-specific:
`agent-runtimes/claude-code/config/settings.json` for Claude Code and
`agent-runtimes/codex/config/hooks.json` for Codex. OpenCode uses
`agent-runtimes/opencode/plugins/godotmaker-hooks.js` as an adapter plugin.
The scripts are deployed to `.godotmaker/hooks/` via publish.

OpenCode uses a degraded adapter for runner-level hooks; see the OpenCode
runtime provider docs for its subagent permission boundary.
In the inventory below, `SubagentStart` and `SubagentStop` entries apply to
Claude Code / Codex hook payloads; the OpenCode adapter does not emit those
Claude-style lifecycle events.

---

## Hook Inventory

| Hook | Event | Matcher | Blocks? | Purpose |
|------|-------|---------|---------|---------|
| `session_start.py` | SessionStart | — | No | Clear session metrics, reset state |
| `check_file_permissions.py` | PreToolUse | Write\|Edit | Yes | Per-role write rules driven by `.godotmaker/current_role` |
| `stage_reminder.py` | PreToolUse | Write\|Edit | Yes | Detect `stage.jsonl` appends, validate role outputs, inject next-role reminder |
| `check_stage_prerequisites.py` | PreToolUse | Agent | Yes | Before worker dispatch, verify the prerequisite role completed and its outputs exist |
| `check_asset_access.py` | PreToolUse | Read | Yes | During an active role, block the main/root agent from reading image files in `assets/` |
| `log_subagent.py` | SubagentStart | — | No | Claude Code / Codex: record subagent start metrics (role detection, agent_id). OpenCode does not emit this lifecycle hook. |
| `on_subagent_stop.py` | SubagentStop | — | Yes | Claude Code / Codex: serialise `log_subagent.handle_stop` + `check_worker_report` to avoid metrics-file race. OpenCode does not emit this lifecycle hook. |
| `check_completion.py` | Stop | — | Yes | Final gate: for `build` / `fixgap` only, blocks if workers were dispatched without verifier + reviewer |

---

## Detailed Descriptions

### session_start.py

**Event:** SessionStart
**Blocks:** Never

Three things at every session start:

1. Clears `metrics_current.jsonl` (session log) and resets `state.json` counters.
2. Removes any stale `.godotmaker/current_role` left from a previous session,
   so the next `/gm-*` skill writes a fresh value.
3. Reads `.godotmaker/version` and injects `[GodotMaker vX.Y.Z]` as
   `additionalContext` so the role and the user know which framework version
   is deployed.

### check_file_permissions.py

**Event:** PreToolUse (Write|Edit)
**Blocks:** Yes

Reads `.godotmaker/current_role` (written as the first action of each `/gm-*`
skill) and applies that role's write rules. Per-role summary:

| Role | May write |
|------|-----------|
| `scaffold` | anything (project bootstrap) |
| `gdd` | `.md` planning docs, `project.godot`, `.godotmaker/` (no `assets/`) |
| `asset` | `ASSETS.md`, `.godotmaker/` (generated images go through asset-producer or asset tools; user-provided image analysis goes through analyst) |
| `build` / `fixgap` | nothing in `e2e/`; nothing in game code (`.gd` / `.tscn` / `.tres`) directly — must dispatch a Worker |
| `verify` | `.godotmaker/stage.jsonl`, `.godotmaker/current_role`, and `.godotmaker/verify_report.json` only (read-only otherwise) |
| `evaluate` | `e2e/`, `.godotmaker/evaluation.json`, `.godotmaker/stage.jsonl`, `.godotmaker/current_role` |
| `accept` / `finalize` | anything except `e2e/` and game code (`.gd` / `.tscn` / `.tres`) |

During an active pipeline role, general subagents are blocked from `e2e/`
and from planning docs (`PLAN.md` / `STRUCTURE.md` / `ASSETS.md` /
`GAP.md`). `asset-producer` may write `assets/`, `references/`, and
`.godotmaker/asset-generation/`.

**Project memory is never a subagent's to write.** Every subagent type —
worker, decomposer, asset-producer, any other delegated role — is blocked from
root `MEMORY.md` and from every file under the project-root `memory/`,
regardless of extension: a learning saved as `memory/learning.txt` is project
memory exactly as much as `memory/movement.md` is. Workers report execution
results and failure evidence; the dispatching role decides what becomes durable
project knowledge.

The `memory/` rule anchors on the project root rather than matching a `memory/`
path segment anywhere, so a game's own `src/memory/` source directory stays
writable. Both anchors are built from the hook's cwd, which is the project
root, so relative and absolute input are handled alike.

The path is normalized before any segment is read, in **two** readings, and a
write is the notebook if either one says so:

| Reading | Built with | Sees |
|---|---|---|
| what the caller named | `abspath` — `..` folded, symlinks left alone | a root `memory/` that is itself a link out of the project |
| where the write lands | `realpath` — `..` folded, symlinks followed | a link such as `Notes -> memory/` |

Neither is sufficient alone. So `src/../memory/learning.txt` and
`Notes/learning.txt` are both blocked, while `src/memory/../notes.md` is not,
and a path that neither reading places under the root `memory/` is not the
notebook either.

The path keeps its original case through this: lower-casing it before
`realpath` would look up a name that does not exist on a case-sensitive
filesystem and silently fail to follow the very link the rule is meant to
catch. Only the comparison is case-insensitive. The
`.claude/worktrees/<agent>/` prefix is stripped after normalization, since a
worker writes from inside its worktree. `MEMORY.md` itself is a basename
match, like the planning docs.

**What this gate does and does not cover.** It is a `PreToolUse` hook on
`Write|Edit`, so it governs those tools and nothing else. A subagent that
shells out — `sed -i`, a heredoc, `python -c` — writes without passing through
here, on every runtime. That is the same boundary the planning-doc and
`e2e/` rules have always had, not something specific to project memory: the
tool gate is the enforcement layer, the role definition is what closes the
rest. It also only applies while a `/gm-*` role is active; with no
`.godotmaker/current_role` the hook records the write and allows it.

Runner note: the role-ownership part of this gate requires a runtime-provided
`agent_id`. OpenCode child sessions do not expose that payload, so the OpenCode
adapter relies on OpenCode-native agent edit permissions there. The memory rule
needs no role identity, so the adapter does run it for child sessions, passing
`is_subagent: true` with `permission_scope: "memory"` — the payload keys that
select the identity-free subset of the subagent rules.

When no role is set, no `/gm-*` pipeline role is active. The hook records the
file operation but does not block, so users can run ordinary coding-agent
conversations in a GodotMaker project directory.

Also records `FILE_WRITE` / `FILE_EDIT` metrics events for every file operation.

### stage_reminder.py

**Event:** PreToolUse (Write|Edit)
**Blocks:** Yes

Triggers when a `/gm-*` skill appends a role-completion event to
`.godotmaker/stage.jsonl`. Each line is `{"role": <role>, "ts": <iso>}`.

1. **Validates role outputs** — reads `config/stage_schemas.json` (keys are
   role names, not stage numbers) and checks `files` existence + runs
   `checks` programmatic validators. Blocks the append if validation fails.
2. **Injects reminder** — points to the next role's `/gm-*` command via
   the `ROLE_NEXT` table.

Programmatic checks:

| Check | Role | What it asserts |
|-------|------|-----------------|
| `plan_all_verified` | `build` | every `PLAN.md` task row has status `verified` (no `pending` / `in_progress` / `completed`) |
| `gap_archived` | `fixgap` | `GAP.md` has been moved to `.godotmaker/gaps/<iteration>/GAP.md` |

Role-output schema lives at `config/stage_schemas.json`. Current shape:
- `scaffold` → `project.godot`
- `gdd` → `GDD.md`, `PLAN.md`, `STRUCTURE.md`
- `evaluate` → `.godotmaker/evaluation.json`
- `finalize` → `.godotmaker/final_report.json`
- `asset` / `verify` / `accept` rely on Resume Check inside their SKILL.md.

### check_stage_prerequisites.py

**Event:** PreToolUse (Agent)
**Blocks:** Yes

Only enforces for the two roles that drive worker orchestration:

| Role | Prerequisite role | Extra check |
|------|-------------------|-------------|
| `build` | `gdd` completed in `stage.jsonl` | `project.godot` exists (scaffold artifact, lifetime-once) |
| `fixgap` | `evaluate` completed in `stage.jsonl` | (validated via `evaluate` schema → `.godotmaker/evaluation.json`) |

The hook also re-validates the prerequisite role's `files` from
`config/stage_schemas.json` — so for `build` it confirms `GDD.md`, `PLAN.md`,
`STRUCTURE.md` still exist on disk, and for `fixgap` it confirms
`.godotmaker/evaluation.json` is still there.

Other dispatching roles (e.g. `asset` dispatches analyst or asset-producer)
self-validate via their
SKILL.md Resume Check; their preconditions don't fit this hook's
role-completion model. Only checks the main agent (the gm-* skill itself),
not sub-subagent dispatches.

### check_asset_access.py

**Event:** PreToolUse (Read)
**Blocks:** Yes

Blocks the main agent from reading image files in `assets/` only while a
pipeline role is active (`.godotmaker/current_role` exists).
Image extensions: .png, .jpg, .jpeg, .svg, .webp, .gif, .bmp, .tga.

Regular conversations with no active role are allowed. Subagents are allowed
when the runtime provides a subagent identity. OpenCode child sessions do not
expose the same `agent_id` payload, so its adapter keeps this gate on the root
stage session only. Non-image files (.json, .ogg) are allowed.

Purpose: force the main agent to delegate asset analysis to the analyst
subagent instead of consuming context with raw image data.

### log_subagent.py

**Event:** SubagentStart (and called by `on_subagent_stop.py` for SubagentStop)
**Blocks:** Never

Runner support: Claude Code / Codex only. The OpenCode adapter does not emit
Claude-style subagent lifecycle hooks.

**SubagentStart:** Detects role and records `SUBAGENT_START` metric with
`agent_id`, `agent_type`, `role`, `description`.

Role detection order:
1. **Runtime-provided `agent_type`** — if Claude Code passes an `agent_type`
   that matches `KNOWN_ROLES` (`worker`, `verifier`, `reviewer`, `analyst`,
   `asset-producer`),
   that's the role. This is the structural identity Claude Code stamps when
   you call `Agent({subagent_type: "verifier", ...})` and the agent can't
   forge it.
2. **Description prefix fallback** — if `agent_type` is generic, fall back to
   `detect_role_from_description`:
   1. `asset-producer:` → asset-producer
   2. `analyst:` → analyst
   3. `worker:` → worker
   4. `verifier:` / `verify:` → verifier
   5. `reviewer:` / `review:` → reviewer

**handle_stop:** invoked from `on_subagent_stop.py`. Reads report type and
status through `metrics.outcome.normalize_report` — the same entry point the
report hook uses. Looks up role from the matching start event. Records
`SUBAGENT_STOP` metric plus outcome-specific events: `WORKER_DONE`,
`VERIFIER_PASS`, `ASSET_PRODUCER_PARTIAL`, etc.

Every `SUBAGENT_STOP` carries `outcome_kind`:

| `outcome_kind` | Meaning |
|---|---|
| `terminal` | The report passed validation. Writes the one outcome-specific event. |
| `rejected_attempt` | The report hook blocked this stop. Writes no outcome event. |
| `unverified` | Released without passing validation. Writes no outcome event. |

Only a `terminal` stop writes an outcome-specific event, so a report that never
passed validation can neither read as a result nor pre-empt the retry's real
status. `unverified` covers the two ways an agent is released without its
report being accepted: the anti-deadloop force-allow below, and a role that
must carry a machine outcome block reaching this point without a valid one.

#### Failure diagnostics (`worker_error`)

A stop that did not go cleanly also writes one `worker_error` event through
`metrics/diagnostics.py`. This is the whole of what a run leaves behind when it
fails — workers produce no memory or learning entries.

| Field | Value |
|---|---|
| `task_id` | The PLAN/GAP task id the report's heading starts with (`M01`, `R2`), else a bounded slug of the task name |
| `attempt` | 1 + prior `worker_error` events for the same `task_id` + `stage` this session |
| `stage` | Active pipeline role (`build`, `fixgap`, …) |
| `runtime` | Selected coding agent, resolved exactly as `tools/agent_runtime.detect_agent` resolves it — the `agent:` key in `.godotmaker/config.yaml` with aliases normalized (`claude` → `claude-code`), then the published-directory fallback, then `claude-code` |
| `role` | Dispatched role (`worker`, `verifier`, …) |
| `agent_id` / `run_id` | Subagent id and session id, when the runtime supplies them |
| `error_type` | `report_rejected`, `timeout`, `forced_handoff`, `tool_or_environment_error`, `unverified_handoff`, `task_failed`, `task_partial` |
| `classification` | The report's suggested `repair-attempt-accounting.md` classification, when it names a known one |
| `summary` | One line, ≤200 chars |
| `exit_code` | The first exit code the report names, else `null` |
| `error_fingerprint` | 16 hex chars over task/stage/type/summary, digit runs collapsed |
| `evidence_paths` | ≤5 paths under `.godotmaker/`, `reports/`, `e2e/`, `docs/tags/` |
| `retryable` | Whether re-dispatching the same brief can plausibly succeed |
| `repeat_count` | Prior events this session carrying the same fingerprint |

`error_type` resolution runs run-level faults first, and those hold for every
role: a blocked report is `report_rejected`, then an explicit `Handoff
condition` from the report's Repair Attempt Evidence, then an unverified
release. An explicit handoff condition outranks status because a timeout or
tool fault explains a `FAILED` that the status alone does not.

`Status` is read last, and only for the roles whose status vocabulary
describes their own run in `DONE` / `PARTIAL` / `FAILED` terms — worker,
asset-producer, analyst. A verifier's `Overall: PASS | FAIL | PARTIAL` is a
verdict about the project, not about the run: a verifier reporting `FAIL` did
its job, and that outcome already travels as `verifier_fail`. So no verifier
status produces a `worker_error` — but a verifier that times out, has its
report rejected, or is released unverified still does.

Three properties this record holds to:

- **A clean run writes nothing.** No success ever produces an error event, and
  no empty event is written to "record" a success.
- **Bounded and deduplicated.** Every field above has a hard cap. When a report
  pastes a large command output into its `Tests` or `Build` section, the event
  carries an `output_digest` of `{sha256, bytes, tail}` instead of a copy. The
  same `(agent_id, error_fingerprint)` pair is recorded once, so a SubagentStop
  that fires repeatedly cannot inflate the log.
- **Diagnostic only.** Nothing here is injected into a later worker or agent
  prompt, and nothing here becomes a project rule on its own. Turning a
  recurring failure into a framework fix is a separate, human-confirmed trace
  analysis.

### on_subagent_stop.py

**Event:** SubagentStop
**Blocks:** Yes (delegates to `check_worker_report`)

Runner support: Claude Code / Codex only. The OpenCode adapter does not emit
Claude-style subagent lifecycle hooks.

Single dispatcher for the `SubagentStop` event. Reads stdin once and runs
serially:

1. `check_worker_report.evaluate(data)` — decide the verdict (no side effects)
2. `log_subagent.handle_stop(data, verdict=…)` — record metrics, labelled by
   that verdict (never blocks)
3. `check_worker_report.apply_verdict(verdict)` — emit the decision (may block)

**Why validate first:** the verdict decides whether the stop is a terminal
record or a rejected attempt. Recording before validating wrote the rejected
attempt as the run's result, and the duplicate-outcome guard then discarded the
retry's real status.

**Why a dispatcher:** Claude Code runs multiple `SubagentStop` hooks in
parallel by default. Both handlers touch `metrics_current.jsonl` —
`log_subagent` reads while `check_worker_report` writes — which caused
intermittent `JSONDecodeError` crashes. Serialising them inside one process
removes the race.

### check_worker_report.py

**Event:** SubagentStop (called via `on_subagent_stop.py`)
**Blocks:** Yes

Validates report format and content for subagent roles while a `/gm-*`
pipeline role is active. With no `.godotmaker/current_role`, ordinary
subagent conversations are allowed and this hook does not block.

**Format detection flow:**
1. Resolve `report_type` and `status` through `metrics.outcome.normalize_report`
   — the machine outcome block first, then the markdown layers (exact marker →
   regex → fallback)
2. If the role must carry a machine outcome block → validate it, fail closed
3. If `report_type` detected → check required sections for that type
4. If `report_type` is None but role is known (from start event) → block and demand a formatted report

**Machine outcome block:** an `asset-producer` report must end with exactly one
fenced JSON object carrying `gm_outcome_version`. It is the status protocol —
the markdown headings are the human-readable summary. The hook, the metrics
log, and the `/gm-asset` manager all read it through the same parser, so a
mangled heading can no longer produce a `report_type: unknown` /
`status: UNKNOWN` record beside a status the manager read correctly.

| Field | Rule |
|---|---|
| `gm_outcome_version` | `1` |
| `report_type` | Must equal the role the subagent was dispatched as |
| `status` | `DONE`, `PARTIAL`, or `FAILED` |
| `unit_id` | Non-empty string |
| `outputs` | Object of path arrays, keyed only by `sources`, `runtime`, `prompts`, `reports`, `request`, `result` |
| `validation` | `{passed: bool, levels?: {L0–L5: bool}, notes?: string}` |
| `blockers` | Array of strings; empty only when `status` is `DONE` |

`DONE` additionally requires `validation.passed`; `PARTIAL` and `FAILED`
require at least one blocker. A missing or invalid field is rejected with the
field name, and that stop is logged as a `rejected_attempt` — or `unverified`
if force-allow eventually released it. Neither writes an outcome event.

**Role binding:** the role a subagent was dispatched as (payload `agent_type`,
falling back to its `subagent_start` event) outranks anything the report claims
about itself, and a block declaring a different `report_type` fails closed. A
report cannot promote or demote its own role, so a record can never carry one
role's `role` with another role's outcome. `log_subagent.classify_stop` re-checks
the same equality, which covers the paths where the hook validated nothing
(force-allow, or no active pipeline role).

**Per-role required sections:**

| Role | Required Sections |
|------|------------------|
| worker | Status, Files Changed, Tests, Build |
| verifier | Overall, Results, Adversarial Probes |
| reviewer | Reviewers Matched, ECS Review, Issues Found, Summary |
| analyst | Status, Asset Summary, Art Style Summary, Files Generated |
| asset-producer | Status, Production Unit, Outputs, Tools, Validation, Handoff |

**Worker-specific deep checks:**
- `check_test_substance()` — Tests section must include unittest results with actual pass/fail output
- `check_resource_paths()` — `res://` paths in .gd files must exist
- `check_classname_conflicts()` — `class_name` declarations must not conflict with Godot built-ins

**Progress reminder:** On successful validation, injects a progress summary
(workers done, verifiers done, reviewers done) as additional context. It
carries counts only — no failure diagnostics are injected into a later prompt.

**Legacy `Memory Entry`:** workers no longer produce one and it is no longer
required. A report written before it was dropped still validates; the section
is ignored, and nothing reads it back into `MEMORY.md` or `memory/`.

**Reviewer substance check:** ECS Review and Issues Found sections must each
have ≥50 characters of content. Prevents empty/trivial reviews.

**Anti-deadloop:** `BLOCK_LIMIT = 2` per `agent_id` — after 2 blocks for the
same subagent, force-allow with a warning rather than re-block forever.

Force-allow releases the agent; it does **not** accept the report. That stop is
logged as `unverified` and writes no outcome-specific event, so an unvalidated
report can never claim the run's terminal status. For a role that must carry a
machine outcome block, the warning also tells the agent the report is not a
terminal result and its outputs must not be registered.

**Gaps:**
- Verifier reports: no check that tests were actually run (only format)
- No per-worker screenshot validation (screenshots are the Evaluator's job
  during `/gm-evaluate`)

### check_completion.py

**Event:** Stop
**Blocks:** Yes

Final gate when the active gm-* skill tries to end the conversation.
Only fires for the worker-dispatching roles (`build`, `fixgap`); for all
other roles the hook is a no-op and they self-enforce via their SKILL.md
Resume Check.

**Worker-dispatch diligence:** if any workers were dispatched in this
session, both verifier and reviewer must also have run (per gm-build /
gm-fixgap rules). If only workers ran, the hook blocks with a message
listing which role(s) are missing.

**Anti-deadloop:** `BLOCK_LIMIT = 5` — after 5 blocks in the same session,
force-allow with a warning rather than re-block forever.

---

## Event Flow Diagram

```
SessionStart
  └── session_start.py (clear metrics)

PreToolUse(Write|Edit)
  ├── check_file_permissions.py (per-role write rules from current_role)
  └── stage_reminder.py (validate stage.jsonl append, inject next-role pointer)

PreToolUse(Agent)
  └── check_stage_prerequisites.py (block build/fixgap if prereq role not done)

PreToolUse(Read)
  └── check_asset_access.py (block main agent from reading assets/ images)

SubagentStart
  └── log_subagent.py (Claude Code / Codex: record start + role)

SubagentStop
  └── on_subagent_stop.py (Claude Code / Codex: serial report gate)

Stop
  └── check_completion.py (build/fixgap diligence check only; no-op for other roles)
```

---

## Known Gaps (TODO)

1. **Verifier test execution:** No hook verifies that verifiers actually RAN
   tests (vs just reporting format-correct results). Spot-check is prompt-level
   only.
