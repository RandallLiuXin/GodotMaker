# Writing a Hook

Hooks are small Python scripts that the coding-agent runtime calls on specific events during a session. They enforce rules that the AI cannot bypass on its own — file permission boundaries, required outputs before a role can finish, report quality gates. Hook registration is runner-specific: Claude Code and Codex use config files, while OpenCode uses a plugin adapter. The scripts live in `hooks/` and are deployed to `.godotmaker/hooks/` by `publish.py`.

For the full per-hook reference (exact payloads, block conditions, edge cases), see [../../hooks.md](../../hooks.md). This page covers how to write a new hook, not how every existing hook works.

---

## Anatomy of a hook

A hook is a Python script with this shape:

```python
import json
import sys

def main():
    data = json.load(sys.stdin)

    # Inspect the event
    tool_name = data.get("tool_name", "")
    file_path = data.get("tool_input", {}).get("file_path", "")

    # Allow silently — exit 0, no stdout
    if not should_block(file_path):
        return

    # Block — write structured JSON to stdout, exit 0
    # (The runner hook surface reads stdout, not the exit code, for the decision)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": data.get("hook_event_name", "PreToolUse"),
            "permissionDecision": "deny",
            "permissionDecisionReason": "Reason shown to the agent."
        }
    }))

if __name__ == "__main__":
    main()
```

Three outcomes:

| Outcome | How to signal it |
|---------|-----------------|
| Allow silently | Exit 0, nothing on stdout |
| Allow with a reminder | Exit 0, print JSON with `additionalContext` |
| Block the action | Exit 0, print JSON with `permissionDecision: "deny"` (PreToolUse) or `decision: "block"` (Stop / SubagentStop) |

The runner hook surface reads stdout for the decision; it does not use the exit
code to block. If a hook crashes (non-zero exit, or malformed JSON on stdout),
the runtime may log the error and continue — hooks must never silently break the
pipeline by crashing.

### Block format for PreToolUse

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Human-readable explanation."
  }
}
```

### Block format for Stop and SubagentStop

```json
{
  "decision": "block",
  "reason": "Human-readable explanation."
}
```

### Allow with additional context

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Text injected into the conversation."
  }
}
```

---

## Events you can hook into

| Event | When it fires | Key payload fields |
|-------|--------------|-------------------|
| `SessionStart` | At the start of a supported root runtime session | `hook_event_name` |
| `PreToolUse` (Write\|Edit) | Before every file write or edit | `tool_name`, `tool_input.file_path`, `tool_input.content`, `agent_id` |
| `PreToolUse` (Agent) | Before every sub-agent dispatch | `tool_name`, `tool_input.description`, `agent_id` |
| `PreToolUse` (Read) | Before every file read | `tool_name`, `tool_input.file_path`, `agent_id` |
| `SubagentStart` | When a sub-agent begins | `agent_id`, `agent_type`, `description` |
| `SubagentStop` | When a sub-agent finishes | `agent_id`, `agent_type`, `last_assistant_message` |
| `Stop` | When the main agent tries to end the session | `agent_id` (empty for main agent) |

`agent_id` is empty for the main agent and non-empty for sub-agents. This is how hooks distinguish between the role skill and its workers.

Runner payloads are not identical. Claude Code and Codex provide
Claude-style `agent_id`, `SubagentStart`, and `SubagentStop` payloads.
OpenCode uses an adapter plugin and does not expose the same subagent
lifecycle payloads, so hooks that depend on those fields must either declare
Claude Code / Codex support only or provide an explicit OpenCode fallback.

---

## Existing hooks

A condensed summary. For full detail on each hook, see [../../hooks.md](../../hooks.md).

| Script | Event | Blocks? | Purpose |
|--------|-------|---------|---------|
| `session_start.py` | SessionStart | No | Clear session metrics and state, inject GodotMaker version into context |
| `check_file_permissions.py` | PreToolUse (Write\|Edit) | Yes | Enforce per-role write rules driven by `.godotmaker/current_role` |
| `stage_reminder.py` | PreToolUse (Write\|Edit) | Yes | Intercept `stage.jsonl` appends, validate role outputs, inject next-role pointer |
| `check_stage_prerequisites.py` | PreToolUse (Agent) | Yes | Block `build` / `fixgap` from dispatching workers if prerequisite role did not complete |
| `check_asset_access.py` | PreToolUse (Read) | Yes | Block the main agent from reading image files in `assets/` (forces analyst sub-agent) |
| `log_subagent.py` | SubagentStart | No | Record sub-agent start with role detection; called again by `on_subagent_stop.py` for stop metrics |
| `on_subagent_stop.py` | SubagentStop | Delegates | Serial dispatcher: runs `log_subagent.handle_stop` then `check_worker_report.main_with_data` to avoid a metrics file race |
| `check_completion.py` | Stop | Yes | Final gate for `build` / `fixgap`: blocks if workers ran without verifier + reviewer |

---

## Anti-deadloop pattern

Two hooks can block the same agent repeatedly: `check_worker_report.py` (blocks a sub-agent's stop until its report is valid) and `check_completion.py` (blocks the main agent's stop until quality steps are done). Without a safety valve, a stubborn agent could be blocked indefinitely.

Both hooks implement a `BLOCK_LIMIT` counter stored in `.godotmaker/state.json`:

- `check_worker_report.py` uses the key `worker_report_block:{agent_id}` with `BLOCK_LIMIT = 2`. After 2 blocks for the same sub-agent, the hook force-allows with a warning.
- `check_completion.py` uses the key `stop_block_count` with `BLOCK_LIMIT = 5`. After 5 blocks in the same session, the hook force-allows with a warning.

When you write a hook that can block repeatedly, implement the same pattern:

```python
from metrics import state

BLOCK_LIMIT = 3
COUNTER_KEY = "my_hook_block_count"

count = state.increment(COUNTER_KEY)
if count > BLOCK_LIMIT:
    # Force-allow with a warning
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "...",
            "additionalContext": f"POTENTIAL BUG: Force-allowing after {BLOCK_LIMIT} blocks."
        }
    }))
    return
```

The counters are reset by `session_start.py` on every new session.

---

## Metrics and state

Hooks may read and write two kinds of persistent data.

### Metrics (append-only)

Call `record_event()` from `hooks/metrics/__init__.py` to append a JSONL line:

```python
from metrics import record_event, EventType

record_event(EventType.HOOK_BLOCK, hook="my_hook", reason="...", file="player.gd")
```

Events are written to two files simultaneously:
- `.godotmaker/metrics_current.jsonl` — current session, truncated on `SessionStart`
- `.godotmaker/metrics_total.jsonl` — lifetime log, never truncated

Read the current session's events with `read_current_events()`.

**Race condition warning:** Claude Code runs multiple `SubagentStop` hooks in parallel by default. If two hooks both read and write `metrics_current.jsonl` at the same time, you get intermittent `JSONDecodeError` crashes. This is exactly why `on_subagent_stop.py` exists — it serialises `log_subagent` and `check_worker_report` inside one process. If you add a new `SubagentStop` hook, add it to `on_subagent_stop.py` as a serial call rather than registering it as a separate hook.

### State (mutable counters)

Use `state.get`, `state.put`, and `state.increment` from `hooks/metrics/state` for values that change during a session (block counts, flags):

```python
from metrics import state

count = state.increment("my_counter")   # Returns new value
state.put("my_flag", True)
value = state.get("my_flag", default=False)
```

State is stored in `.godotmaker/state.json` and reset on every `SessionStart`.

---

## Registering a new hook

1. Create your hook script in `hooks/<my_hook>.py`.

2. Add it to every supported runner surface that should trigger it:
   `agent-runtimes/claude-code/config/settings.json` for Claude Code,
   `agent-runtimes/codex/config/hooks.json` for Codex, or
   `agent-runtimes/opencode/plugins/godotmaker-hooks.js` for OpenCode.

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Write|Edit",
           "hooks": [
             {"type": "command", "command": "python .godotmaker/hooks/check_file_permissions.py"},
             {"type": "command", "command": "python .godotmaker/hooks/my_hook.py"}
           ]
         }
       ]
     }
   }
   ```

   Hooks for the same event+matcher run in the order listed. If an earlier hook blocks, later hooks for that event may not run.

3. Publish to a test project and exercise the trigger:

   ```bash
   python tools/publish.py /path/to/scratch-game
   ```

4. Write unit tests under `tests/hooks/test_my_hook.py`. See [Testing](testing.md) for the pattern.
