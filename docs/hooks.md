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

Runner note: this subagent write gate requires a runtime-provided `agent_id`.
OpenCode child sessions do not expose that payload, so the OpenCode adapter
does not run this Python subagent write gate for child sessions; it relies on
OpenCode-native agent edit permissions for that boundary.

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

**handle_stop:** invoked from `on_subagent_stop.py`. Extracts report type,
status, files changed from the assistant message. Looks up role from the
matching start event. Records `SUBAGENT_STOP` metric plus outcome-specific
events: `WORKER_DONE`, `VERIFIER_PASS`, etc.

### on_subagent_stop.py

**Event:** SubagentStop
**Blocks:** Yes (delegates to `check_worker_report`)

Runner support: Claude Code / Codex only. The OpenCode adapter does not emit
Claude-style subagent lifecycle hooks.

Single dispatcher for the `SubagentStop` event. Reads stdin once and runs
serially:

1. `log_subagent.handle_stop(data)` — record metrics, save traces (never blocks)
2. `check_worker_report.main_with_data(data)` — validate report (may block)

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
1. Detect `report_type` from message content (layered: exact marker → regex → fallback)
2. If `report_type` detected → check required sections for that type
3. If `report_type` is None but role is known (from start event) → block and demand a formatted report

**Per-role required sections:**

| Role | Required Sections |
|------|------------------|
| worker | Status, Files Changed, Tests, Build, Memory Entry |
| verifier | Overall, Results, Adversarial Probes |
| reviewer | Reviewers Matched, ECS Review, Issues Found, Summary |
| analyst | Status, Asset Summary, Art Style Summary, Files Generated |
| asset-producer | Status, Production Unit, Outputs, Tools, Validation, Handoff |

**Worker-specific deep checks:**
- `check_test_substance()` — Tests section must include unittest results with actual pass/fail output
- `check_resource_paths()` — `res://` paths in .gd files must exist
- `check_classname_conflicts()` — `class_name` declarations must not conflict with Godot built-ins

**Progress reminder:** On successful validation, injects a progress summary
(workers done, verifiers done, reviewers done) as additional context.

**Reviewer substance check:** ECS Review and Issues Found sections must each
have ≥50 characters of content. Prevents empty/trivial reviews.

**Anti-deadloop:** `BLOCK_LIMIT = 2` per `agent_id` — after 2 blocks for the
same subagent, force-allow with a warning rather than re-block forever.

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
