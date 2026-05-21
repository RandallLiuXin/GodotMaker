#!/usr/bin/env python3
"""PreToolUse hook: validate role completion outputs and remind of next role.

When a gm-* skill appends to .godotmaker/stage.jsonl (recording role completion),
this hook:
  1. VALIDATES that the completed role's required outputs exist. Blocks if not.
  2. Injects an additionalContext reminder pointing to the next role's command.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import (
    record_event, EventType, PIPELINE_ROLES,
    load_stage_schemas, validate_schema_files,
    get_current_tag,
)
from playability_contract import check_evaluation_playable_unit_complete

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
# Programmatic check functions
# ---------------------------------------------------------------------------

def check_plan_all_verified() -> str | None:
    """Build role: PLAN.md must have all tasks marked `verified`."""
    return _check_task_table_all_verified("PLAN.md")


def check_gap_archived() -> str | None:
    """Fixgap role: GAP.md must be archived (moved out of project root).

    The fixgap role's When Done step archives the completed GAP.md to
    `.godotmaker/gaps/<iteration>/GAP.md`. If GAP.md is still at root
    when the fixgap event is recorded, the role skipped the archive.
    """
    if os.path.isfile("GAP.md"):
        return ("GAP.md is still at project root — it must be archived to "
                ".godotmaker/gaps/<iteration>/GAP.md before completing fixgap.")
    return None


def check_evaluation_playable_unit() -> str | None:
    """Evaluate role: evaluation.json must cover every PLAN Playable Unit row."""
    issues = check_evaluation_playable_unit_complete()
    if issues:
        return "Playable Unit evaluation contract failed:\n" + "\n".join(
            f"  - {issue}" for issue in issues
        )
    return None


_TAG_ARCHIVE_FILES = (
    "GDD-snapshot.md",
    "PLAN.md",
    "STRUCTURE.md",
    "STYLE.md",
    "SCENES.md",
    "MEMORY.md",
    "evaluation-final.json",
    "CHANGELOG.md",
)


def check_tag_archived() -> str | None:
    """Finalize role: docs/tags/<Tag>/ must contain a full archive of the
    just-finalized tag. The current tag is read from PLAN.md's `**Tag:**`
    header (still scoped to the tag being finalized at this point).
    """
    tag = get_current_tag()
    if not tag:
        return ("PLAN.md missing or has no `**Tag:** vX.Y.Z` header — finalize "
                "needs this to know which docs/tags/<Tag>/ directory to verify.")
    archive = os.path.join("docs", "tags", tag)
    if not os.path.isdir(archive):
        return f"docs/tags/{tag}/ not created — finalize must archive the tag's working docs there."
    missing = [f for f in _TAG_ARCHIVE_FILES if not os.path.isfile(os.path.join(archive, f))]
    if missing:
        return (f"docs/tags/{tag}/ missing required files: {', '.join(missing)}")
    return None


def _check_task_table_all_verified(path: str) -> str | None:
    """Shared: a task table at `path` must have no non-verified tasks."""
    if not os.path.isfile(path):
        return f"{path} not found"
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    pending = re.findall(r"\|\s*pending\s*\|", content, re.IGNORECASE)
    in_progress = re.findall(r"\|\s*in_progress\s*\|", content, re.IGNORECASE)
    completed = re.findall(r"\|\s*completed\s*\|", content, re.IGNORECASE)
    leftover = []
    if pending:
        leftover.append(f"{len(pending)} pending")
    if in_progress:
        leftover.append(f"{len(in_progress)} in_progress")
    if completed:
        leftover.append(f"{len(completed)} completed (not yet verified)")
    if leftover:
        return f"{path} has tasks not yet verified: {', '.join(leftover)}"
    return None


PROGRAMMATIC_CHECKS = {
    "plan_all_verified": check_plan_all_verified,
    "evaluation_playable_unit": check_evaluation_playable_unit,
    "gap_archived": check_gap_archived,
    "tag_archived": check_tag_archived,
}


# ---------------------------------------------------------------------------
# Role extraction
# ---------------------------------------------------------------------------

def extract_latest_role(tool_input: dict) -> str | None:
    """Extract the role of the LAST event in a Write/Edit tool input.

    The hook runs when a gm-* skill writes/edits .godotmaker/stage.jsonl.
    The relevant event is the one being added — i.e. the last valid
    {"role": X, "ts": Y} line in the payload. Returns None if no such
    event is found.
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
            latest = role
    return latest


# ---------------------------------------------------------------------------
# Reminder helper
# ---------------------------------------------------------------------------

def get_next_role_reminder(completed_role: str) -> str | None:
    next_step = ROLE_NEXT.get(completed_role)
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

    completed_role = extract_latest_role(tool_input)
    if not completed_role:
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Validate role outputs before allowing completion
    # -----------------------------------------------------------------------
    schemas = load_stage_schemas()
    if schemas:
        role_schema = schemas.get(completed_role, {})
        issues = validate_schema_files(role_schema)

        for check_name in role_schema.get("checks", []):
            check_fn = PROGRAMMATIC_CHECKS.get(check_name)
            if check_fn:
                result = check_fn()
                if result:
                    issues.append(result)

        if issues:
            reason = (
                f"Cannot mark role '{completed_role}' as complete — validation failed:\n"
                + "\n".join(f"  - {i}" for i in issues)
            )
            record_event(EventType.GATE_CHECK, gate=f"role_{completed_role}",
                         result="fail", issues=issues)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }}))
            sys.exit(0)

    record_event(EventType.GATE_CHECK, gate=f"role_{completed_role}",
                 result="complete")

    reminder = get_next_role_reminder(completed_role)
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
