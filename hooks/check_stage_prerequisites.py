#!/usr/bin/env python3
"""PreToolUse hook (Agent/Task tool): verify role prerequisites before dispatch.

Only enforces for roles that drive worker orchestration:
  - build → requires gdd completed + scaffold artifacts present
  - fixgap → requires evaluate completed + evaluation.json present

Scaffold artifacts are checked on disk because gm-finalize truncates
stage.jsonl at every tag boundary, so the scaffold event is no longer
in stage.jsonl after the first finalize.

Other dispatching roles (asset → analyst) self-validate via their SKILL.md
Resume Check; their preconditions don't match this hook's stage-schema model.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import (
    record_event, EventType,
    get_current_role, get_completed_roles,
    load_stage_schemas, WORKER_DISPATCH_ROLES,
)


PREREQ_ROLE = {
    "build": "gdd",
    "fixgap": "evaluate",
}

# Sanity check: PREREQ_ROLE must cover exactly the worker-dispatching roles.
# Use an explicit raise instead of assert so the check survives `python -O`.
if frozenset(PREREQ_ROLE) != WORKER_DISPATCH_ROLES:
    raise RuntimeError(
        f"PREREQ_ROLE keys {sorted(PREREQ_ROLE)} must equal "
        f"WORKER_DISPATCH_ROLES {sorted(WORKER_DISPATCH_ROLES)}"
    )

# Roles that need scaffold artifacts on disk (lifetime-once, not in stage.jsonl
# after the first tag's finalize truncates the log).
SCAFFOLD_REQUIRED = frozenset({"build"})


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("tool_name") not in {"Agent", "Task"}:
        sys.exit(0)

    # Only check main agent (the gm-* skill orchestrating dispatch)
    if data.get("agent_id", ""):
        sys.exit(0)

    role = get_current_role()
    prereq = PREREQ_ROLE.get(role)
    if not prereq:
        sys.exit(0)  # No worker-dispatch role active, nothing to enforce

    completed = get_completed_roles()
    issues = []

    if role in SCAFFOLD_REQUIRED and not os.path.isfile("project.godot"):
        issues.append("project.godot not found — run /gm-scaffold first")

    if prereq not in completed:
        issues.append(f"Role '{prereq}' has not completed yet — run /gm-{prereq} first")

    schemas = load_stage_schemas()
    if schemas:
        prereq_schema = schemas.get(prereq, {})
        # Inline existence check here (not validate_schema_files) to keep the
        # role-aware "{prereq} output missing: X" message style.
        for filepath in prereq_schema.get("files", []):
            if not os.path.exists(filepath):
                issues.append(f"{prereq} output missing: {filepath}")

    if issues:
        reason = (
            f"Cannot dispatch worker — '{role}' role prerequisites missing:\n"
            + "\n".join(f"  - {m}" for m in issues)
        )
        record_event(EventType.HOOK_BLOCK, hook="check_stage_prerequisites",
                     role=role, missing=issues)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
        sys.exit(0)

    record_event(EventType.HOOK_ALLOW, hook="check_stage_prerequisites", role=role)


if __name__ == "__main__":
    main()
