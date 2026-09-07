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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import (
    record_event, EventType, normalize_report, outcome_matches_role,
    OUTCOME_REQUIRED_ROLES,
    ROLE_WORKER, ROLE_VERIFIER, ROLE_REVIEWER, ROLE_ANALYST,
    ROLE_ASSET_PRODUCER, ROLE_UNKNOWN,
    KNOWN_ROLES, get_current_role,
)
from metrics.diagnostics import build_error_event, record_error_event
from check_worker_report import extract_files_changed

# How a stop relates to the run's terminal status. Only `terminal` writes an
# outcome-specific event, so a report that never passed validation can neither
# read as a result nor claim the one terminal outcome.
OUTCOME_TERMINAL = "terminal"
OUTCOME_REJECTED_ATTEMPT = "rejected_attempt"  # the hook blocked this stop
OUTCOME_UNVERIFIED = "unverified"              # released without passing validation

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
    "asset_producer_done", "asset_producer_partial", "asset_producer_failed",
}

_OUTCOME_MAPS = {
    ROLE_WORKER: {
        "DONE": EventType.WORKER_DONE,
        "PARTIAL": EventType.WORKER_PARTIAL,
        "FAILED": EventType.WORKER_FAILED,
    },
    ROLE_VERIFIER: {
        "PASS": EventType.VERIFIER_PASS,
        "FAIL": EventType.VERIFIER_FAIL,
        "PARTIAL": EventType.VERIFIER_PARTIAL,
    },
    ROLE_ASSET_PRODUCER: {
        "DONE": EventType.ASSET_PRODUCER_DONE,
        "PARTIAL": EventType.ASSET_PRODUCER_PARTIAL,
        "FAILED": EventType.ASSET_PRODUCER_FAILED,
    },
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


def classify_stop(verdict, report, effective_role: str) -> str:
    """Decide whether this stop is the run's terminal result.

    Only a report that actually passed validation may become `terminal`, and
    only a `terminal` stop writes an outcome-specific event. The hook can
    release an agent without accepting its report — it blocks, or its deadloop
    escape hatch force-allows — and treating either as a result is how an
    unvalidated report claimed the single terminal outcome.
    """
    if verdict is not None and getattr(verdict, "rejected", False):
        return OUTCOME_REJECTED_ATTEMPT

    # A block declaring a different role than the one this subagent was
    # dispatched as verifies nothing here. The hook already fails closed on the
    # mismatch; re-checking the equality closes the paths where it never ran
    # (force-allow, or no active pipeline role), which would otherwise let a
    # worker block write an asset_producer_* result.
    if report.outcome is not None and not outcome_matches_role(report, effective_role):
        return OUTCOME_UNVERIFIED

    # For a role that carries a machine outcome, that block IS the verification,
    # so it alone decides. A valid block still counts even when the hook was
    # bypassed; a missing one has no terminal status to claim.
    if effective_role in OUTCOME_REQUIRED_ROLES:
        return OUTCOME_TERMINAL if report.outcome is not None else OUTCOME_UNVERIFIED

    # Other roles are verified only by the markdown gate, which force-allow skips.
    if verdict is not None and getattr(verdict, "force_allowed", False):
        return OUTCOME_UNVERIFIED
    return OUTCOME_TERMINAL


def handle_stop(data: dict, verdict=None) -> None:
    """Handle SubagentStop event. Called from the on_subagent_stop dispatcher.

    `verdict` is the report hook's `ReportVerdict` for this same stop, computed
    before this call. `classify_stop` turns it into an `outcome_kind`; only a
    `terminal` stop writes an outcome event, so neither a format rejection nor
    a force-allowed report can read as a producer result or pre-empt the
    retry's real one.
    """
    agent_id = data.get("agent_id") or ""
    agent_type = data.get("agent_type") or ""
    raw_message = data.get("last_assistant_message")
    message = raw_message or ""
    _debug(f"  handle_stop agent_id={agent_id[:16]} agent_type={agent_type}")
    _debug(f"  last_assistant_message: type={type(raw_message).__name__} len={len(message)}")
    if message:
        _debug(f"  message preview: {message[:200]!r}")

    # One parser for hook, metrics, and the manager handoff.
    report = normalize_report(message)
    report_type = report.report_type
    status = report.status
    files = extract_files_changed(message)
    if agent_type in KNOWN_ROLES:
        role = agent_type
    else:
        role = lookup_role_from_events(agent_id)
    # Final-output capture moved to log_agent_tool.py PostToolUse — see
    # this file's header for rationale.

    # Role for outcome purposes: the dispatched role first, report type second.
    effective_role = role if role != ROLE_UNKNOWN else report_type
    outcome = report.outcome or {}
    kind = classify_stop(verdict, report, effective_role)

    record_event(
        EventType.SUBAGENT_STOP,
        agent_id=agent_id,
        agent_type=agent_type,
        role=role,
        report_type=report_type,
        status=status,
        files_changed=files,
        outcome_kind=kind,
        unit_id=outcome.get("unit_id"),
        blockers=outcome.get("blockers", []),
        outcome_error=report.outcome_error,
    )

    # Failure diagnostics, not learnings: a clean run writes nothing here, and
    # nothing written here is fed back into a later prompt.
    record_error_event(build_error_event(
        message=message,
        role=effective_role,
        status=status,
        outcome_kind=kind,
        agent_id=agent_id,
        run_id=data.get("session_id") or "",
        stage=get_current_role(),
    ))

    if kind != OUTCOME_TERMINAL:
        return

    # Record outcome-specific event based on role (primary) or report_type (fallback).
    # Only record once per agent_id to avoid duplicates when check_worker_report
    # blocks and the SubagentStop hook fires multiple times on retries.
    outcome_map = _OUTCOME_MAPS.get(effective_role)
    if outcome_map and status in outcome_map and not _has_outcome_event(agent_id):
        record_event(
            outcome_map[status],
            agent_id=agent_id,
            files=files,
            unit_id=outcome.get("unit_id"),
            blockers=outcome.get("blockers", []),
        )


if __name__ == "__main__":
    main()
