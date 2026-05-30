#!/usr/bin/env python3
"""PreToolUse hook: block active pipeline roles from reading asset images.

The active /gm-* skill in the main session must delegate asset analysis to an
analyst subagent. Regular coding-agent conversations with no current_role are
not pipeline sessions and are allowed to read assets directly. Subagents are
also allowed; only the main agent (empty agent_id) is blocked during a
pipeline role.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import get_current_role


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".bmp", ".tga"}


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("hook_event_name") != "PreToolUse":
        sys.exit(0)
    if data.get("tool_name") != "Read":
        sys.exit(0)

    agent_id = data.get("agent_id", "")
    if agent_id:
        sys.exit(0)

    if not get_current_role():
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    normalized = file_path.replace("\\", "/").lower()

    if "/assets/" not in normalized and not normalized.startswith("assets/"):
        sys.exit(0)

    _, ext = os.path.splitext(normalized)
    if ext not in IMAGE_EXTENSIONS:
        sys.exit(0)

    reason = (
        f"The active pipeline role cannot read image files in assets/ directly. "
        f"Dispatch an analyst subagent to analyze '{os.path.basename(file_path)}' instead. "
        f"See analyst-dispatch.md for the protocol."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


if __name__ == "__main__":
    main()
