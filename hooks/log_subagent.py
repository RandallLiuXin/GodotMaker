#!/usr/bin/env python3
"""SubagentStart + SubagentStop hook: log subagent lifecycle events.

Records all subagent dispatches and completions to metrics.
Parses worker/verifier reports for status, files changed, and report type.
Subagent prompt + final output capture lives in `log_agent_tool.py`,
which uses the documented PreToolUse/PostToolUse `Agent` API rather
than SubagentStart's payload (which has no `prompt` field) — see that
file's header for rationale.

Never blocks (always exit 0).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import (
    record_event, EventType, detect_report_type,
    ROLE_WORKER, ROLE_VERIFIER, ROLE_REVIEWER, ROLE_ANALYST,
    ROLE_ASSET_PRODUCER, ROLE_UNKNOWN,
    KNOWN_ROLES,
)
from check_worker_report import extract_files_changed

# Debug logging: always on. Writes to .godotmaker/traces/hook_debug.log.
_DEBUG_LOG = os.path.join(".godotmaker", "traces", "hook_debug.log")


def _debug(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(_DEBUG_LOG), exist_ok=True)
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass


def extract_status(message: str) -> str:
    match = re.search(r"### Status:\s*(DONE|PARTIAL|FAILED)", message)
    if match:
        return match.group(1)
    match = re.search(r"### Overall:\s*(PASS|FAIL|PARTIAL)", message)
    if match:
        return match.group(1)
    return "UNKNOWN"


def extract_report_type(message: str) -> str:
    return detect_report_type(message) or "unknown"


def detect_role_from_description(description: str) -> str:
    """Detect subagent role from the dispatch description field.

    Prefix match first (most reliable), then keyword fallback.
    Order: analyst → reviewer → verifier → worker (specific first).
    """
    if not description:
        return ROLE_UNKNOWN
    desc_lower = description.lower()
    # Prefix checks
    if desc_lower.startswith("asset-producer:") or desc_lower.startswith("asset producer:"):
        return ROLE_ASSET_PRODUCER
    if desc_lower.startswith("analyst:"):
        return ROLE_ANALYST
    if desc_lower.startswith("worker:"):
        return ROLE_WORKER
    if desc_lower.startswith("verifier:") or desc_lower.startswith("verify:"):
        return ROLE_VERIFIER
    if desc_lower.startswith("reviewer:") or desc_lower.startswith("review:"):
        return ROLE_REVIEWER
    # Keyword fallback — specific roles first to avoid false matches
    if "asset-producer" in desc_lower or "asset producer" in desc_lower:
        return ROLE_ASSET_PRODUCER
    if "analyst" in desc_lower or "analyze" in desc_lower:
        return ROLE_ANALYST
    if "reviewer" in desc_lower or "review" in desc_lower:
        return ROLE_REVIEWER
    if "verifier" in desc_lower or "verify" in desc_lower:
        return ROLE_VERIFIER
    if "worker" in desc_lower:
        return ROLE_WORKER
    return ROLE_UNKNOWN


_OUTCOME_EVENTS = {
    "worker_done", "worker_partial", "worker_failed",
    "verifier_pass", "verifier_fail", "verifier_partial",
}


def _has_outcome_event(agent_id: str) -> bool:
    """Check if an outcome event was already recorded for this agent_id.

    Prevents duplicate worker_done/verifier_pass when SubagentStop fires
    multiple times due to check_worker_report block retries.
    """
    from metrics import read_current_events
    for evt in read_current_events():
        if (evt.get("event") in _OUTCOME_EVENTS
                and evt.get("agent_id") == agent_id):
            return True
    return False


def lookup_role_from_events(agent_id: str) -> str:
    """Look up the role recorded at SubagentStart for a given agent_id.

    Reads metrics_current.jsonl to find the matching start event.
    """
    from metrics import read_current_events
    for evt in reversed(read_current_events()):
        if (evt.get("event") == "subagent_start"
                and evt.get("agent_id") == agent_id
                and evt.get("role")):
            return evt["role"]
    return ROLE_UNKNOWN


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    event = data.get("hook_event_name") or ""
    agent_id = data.get("agent_id") or ""
    agent_type = data.get("agent_type") or ""

    _debug(f"event={event} agent_id={agent_id[:16]} agent_type={agent_type}")
    _debug(f"  raw keys: {sorted(data.keys())}")
    for k, v in data.items():
        if k in ("prompt", "last_assistant_message"):
            _debug(f"  {k}: type={type(v).__name__} len={len(v or '')}")
        else:
            _debug(f"  {k}: {v!r}")

    if event == "SubagentStart":
        # NOTE: SubagentStart's payload schema (claude-code-src
        # `coreSchemas.ts:540`) does NOT include `description` or `prompt`.
        # `data.get("description")` and `data.get("prompt")` reliably return
        # None — the `_save_trace(agent_id, "prompt", ...)` and
        # description-based role detection that previously lived here were
        # silent dead code. Prompt capture moved to `log_agent_tool.py`
        # (PreToolUse + matcher Agent). Role detection here now relies on
        # agent_type alone, which IS in the payload.
        if agent_type in KNOWN_ROLES:
            role = agent_type
        else:
            role = ROLE_UNKNOWN
        record_event(
            EventType.SUBAGENT_START,
            agent_id=agent_id,
            agent_type=agent_type,
            role=role,
        )

    elif event == "SubagentStop":
        handle_stop(data)

    sys.exit(0)  # Never block


def handle_stop(data: dict) -> None:
    """Handle SubagentStop event. Called from main() or from check_worker_report.

    Extracted so check_worker_report can call it directly, ensuring serial
    execution (log first, then validate) without parallel hook race conditions.
    """
    agent_id = data.get("agent_id") or ""
    agent_type = data.get("agent_type") or ""
    raw_message = data.get("last_assistant_message")
    message = raw_message or ""
    _debug(f"  handle_stop agent_id={agent_id[:16]} agent_type={agent_type}")
    _debug(f"  last_assistant_message: type={type(raw_message).__name__} len={len(message)}")
    if message:
        _debug(f"  message preview: {message[:200]!r}")
    report_type = extract_report_type(message)
    status = extract_status(message)
    files = extract_files_changed(message)
    if agent_type in KNOWN_ROLES:
        role = agent_type
    else:
        role = lookup_role_from_events(agent_id)
    # Final-output capture moved to log_agent_tool.py PostToolUse — see
    # this file's header for rationale.

    record_event(
        EventType.SUBAGENT_STOP,
        agent_id=agent_id,
        agent_type=agent_type,
        role=role,
        report_type=report_type,
        status=status,
        files_changed=files,
    )

    # Record outcome-specific event based on role (primary) or report_type (fallback).
    # Only record once per agent_id to avoid duplicates when check_worker_report
    # blocks and the SubagentStop hook fires multiple times on retries.
    effective_role = role if role != ROLE_UNKNOWN else report_type
    if effective_role == ROLE_WORKER:
        outcome_map = {
            "DONE": EventType.WORKER_DONE,
            "PARTIAL": EventType.WORKER_PARTIAL,
            "FAILED": EventType.WORKER_FAILED,
        }
        if status in outcome_map and not _has_outcome_event(agent_id):
            record_event(outcome_map[status], agent_id=agent_id, files=files)

    elif effective_role == ROLE_VERIFIER:
        outcome_map = {
            "PASS": EventType.VERIFIER_PASS,
            "FAIL": EventType.VERIFIER_FAIL,
            "PARTIAL": EventType.VERIFIER_PARTIAL,
        }
        if status in outcome_map and not _has_outcome_event(agent_id):
            record_event(outcome_map[status], agent_id=agent_id)


if __name__ == "__main__":
    main()
