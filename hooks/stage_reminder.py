#!/usr/bin/env python3
"""PreToolUse hook: remind the active runtime of the next pipeline role.

When a gm-* skill appends to .godotmaker/stage.jsonl (recording role completion),
this runtime-specific hook injects an additionalContext reminder pointing to
the next role's command. Completion enforcement belongs to
tools/append_stage_event.py so every runtime passes through the same gate.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import PIPELINE_ROLES

ROLE_NEXT = {
    "scaffold": "/gm-gdd",
    "gdd": "/gm-asset",
    "asset": "/gm-build",
    "build": "/gm-verify",
    "verify": "/gm-evaluate",
    "evaluate": "/gm-accept (if approved) or /gm-fixgap (if rejected)",
    "fixgap": "/gm-verify",
    "accept": "/gm-finalize",
    "finalize": None,
}

# Sanity check: ROLE_NEXT must cover every pipeline role. Catches drift at
# import time when a new role is added to PIPELINE_ROLES without updating the
# next-step mapping here. Explicit raise survives `python -O`.
if set(ROLE_NEXT) != set(PIPELINE_ROLES):
    raise RuntimeError(
        f"ROLE_NEXT keys {sorted(ROLE_NEXT)} must equal "
        f"PIPELINE_ROLES {sorted(PIPELINE_ROLES)}"
    )


# ---------------------------------------------------------------------------
# Role extraction
# ---------------------------------------------------------------------------

def extract_latest_event(tool_input: dict) -> dict | None:
    """Extract the LAST stage event in a Write/Edit tool input.

    The hook runs when a gm-* skill writes/edits .godotmaker/stage.jsonl.
    The relevant event is the one being added — i.e. the last valid
    {"role": X, "ts": Y} line in the payload. Keeping the full event is
    required because completion semantics may depend on fields such as
    ``outcome`` and ``next_role``. Returns None if no such event is found.
    """
    content = tool_input.get("content") or tool_input.get("new_string", "")
    if not content:
        return None

    latest = None
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        role = entry.get("role")
        ts = entry.get("ts")
        if role and ts and role in PIPELINE_ROLES:
            latest = entry
    return latest


def extract_latest_role(tool_input: dict) -> str | None:
    """Return the role from :func:`extract_latest_event`."""
    event = extract_latest_event(tool_input)
    return event.get("role") if event else None


# ---------------------------------------------------------------------------
# Reminder helper
# ---------------------------------------------------------------------------

def get_next_role_reminder(completed_role: str, event: dict | None = None) -> str | None:
    event_next_role = event.get("next_role") if event else None
    next_step = (
        f"/gm-{event_next_role}"
        if isinstance(event_next_role, str) and event_next_role
        else ROLE_NEXT.get(completed_role)
    )
    if not next_step:
        return None
    return f"[Role '{completed_role}' complete] Next: {next_step}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("hook_event_name") != "PreToolUse":
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    normalized = file_path.replace("\\", "/")
    if not normalized.endswith(".godotmaker/stage.jsonl"):
        sys.exit(0)

    completed_event = extract_latest_event(tool_input)
    if not completed_event:
        sys.exit(0)
    completed_role = completed_event["role"]

    reminder = get_next_role_reminder(completed_role, completed_event)
    if reminder:
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": reminder,
            }
        }
        json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
