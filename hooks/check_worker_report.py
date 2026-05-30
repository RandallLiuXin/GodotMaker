#!/usr/bin/env python3
"""SubagentStop hook: validate worker/verifier report completeness.

Worker reports MUST have: Status, Files Changed, Tests (with unittest
results), Build, Memory Entry.

Verifier reports MUST have: Overall, Results, Adversarial Probes.

Blocks (JSON decision: "block") if required sections are missing. When no
current_role is set, no /gm-* pipeline role is active and regular subagent
conversations are allowed without report-format enforcement.

Anti-deadloop: if a specific agent has been blocked BLOCK_LIMIT times,
force-allow with a warning to prevent infinite retry loops.
"""
import glob as globmod
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import (
    record_event, read_current_events, EventType,
    detect_report_type, event_has_role,
    REPORT_REQUIRED_SECTIONS, REPORT_FORMAT_HINTS, REPORT_REQUIRED_LABELS,
    get_current_role, state,
)

BLOCK_LIMIT = 2  # Max blocks per subagent before force-allowing

WORKER_TEST_SUBSTANCE = [
    r"test[_/].*\.gd",
    r"(\d+\s*(passed|failed|tests?))|Commands?\s*run",
]

# Most dangerous Godot built-in names that conflict with class_name.
# Maintained separately from tools/check_classname.py (full list).
# This subset covers names that caused actual build failures in past projects.
GODOT_RESERVED_NAMES: set[str] = {
    "Key", "Node", "Node2D", "Node3D", "World", "System", "Resource", "Timer",
    "Signal", "Error", "Input", "Label", "Button", "Control", "Camera2D",
    "Camera3D", "Sprite2D", "Object", "RefCounted",
}


def _resolve_file(relative_path: str, worktree_dirs: list[str]) -> str | None:
    """Resolve a relative file path, checking CWD first then worktrees.

    SubagentStop hooks run from the main project CWD, but worktree agents
    write files into .claude/worktrees/agent-*/. This helper checks both.

    worktree_dirs should be pre-computed once by the caller (via glob) to
    avoid repeated filesystem scans across many invocations.

    Returns the resolved path if found, or None.
    """
    # Check main project first
    if os.path.isfile(relative_path):
        return relative_path

    # Check all worktrees
    for wt in worktree_dirs:
        candidate = os.path.join(wt, relative_path)
        if os.path.isfile(candidate):
            return candidate

    return None


def _extract_section(message: str, heading: str) -> str | None:
    """Extract content under a ### heading from a markdown report."""
    match = re.search(
        rf"### {re.escape(heading)}\s*\n(.*?)(?=\n### [A-Z]|\n## |\Z)",
        message, re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def _block(reason: str, state_key: str | None = None, **extra) -> None:
    """Record block event, increment deadloop counter, print decision JSON, and exit."""
    if state_key:
        state.increment(state_key)
    record_event(EventType.HOOK_BLOCK, hook="check_worker_report", reason=reason, **extra)
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def check_sections(message: str, required: list[tuple[str, str]]) -> list[str]:
    missing = []
    for name, pattern in required:
        if not re.search(pattern, message, re.IGNORECASE):
            missing.append(name)
    return missing


def extract_files_changed(message: str) -> list[str]:
    """Extract file paths from the '### Files Changed' section of a worker report."""
    section = _extract_section(message, "Files Changed")
    if section is None:
        return []
    # Match file paths: lines like "- `path/to/file.gd`: description" or "- path/to/file.gd"
    paths = re.findall(r"`([^`]+\.\w+)`", section)
    # Also match bare paths (no backticks)
    paths += re.findall(r"^[-*]\s+(\S+\.\w+)", section, re.MULTILINE)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for p in paths:
        clean = p.strip("`").strip()
        if clean.startswith("res://"):
            clean = clean[len("res://"):]
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def check_resource_paths(gd_contents: dict[str, str], worktree_dirs: list[str]) -> str | None:
    """Check that res:// paths referenced in worker's .gd files actually exist.

    Checks both main project and worktree directories.
    """
    try:
        missing = []
        for _gd_file, content in gd_contents.items():
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for m in re.finditer(r'res://([^"\'`\s]+)', line):
                    res_path = m.group(1)
                    if not _resolve_file(res_path, worktree_dirs):
                        full_ref = f"res://{res_path}"
                        if full_ref not in missing:
                            missing.append(full_ref)

        if missing:
            paths_str = ", ".join(missing[:5])
            return (
                f"Worker references non-existent resource: {paths_str}. "
                f"Fix the path or report as missing in ASSETS.md."
            )
    except Exception:
        pass
    return None


def check_classname_conflicts(gd_contents: dict[str, str]) -> str | None:
    """Check that class_name declarations in worker's .gd files don't conflict with Godot built-ins."""
    try:
        for _gd_file, content in gd_contents.items():
            match = re.search(r"^class_name\s+(\w+)", content, re.MULTILINE)
            if match:
                name = match.group(1)
                if name in GODOT_RESERVED_NAMES:
                    return (
                        f"class_name '{name}' conflicts with Godot built-in '{name}'. "
                        f"Rename to '{name}Entity' or '{name}Comp'."
                    )
    except Exception:
        pass
    return None


def check_test_substance(message: str) -> str | None:
    content = _extract_section(message, "Tests")
    if content is None:
        return None
    if not content or len(content) < 20:
        return "Tests section is empty — must include unittest results"

    has_substance = any(
        re.search(p, content, re.IGNORECASE) for p in WORKER_TEST_SUBSTANCE
    )
    if not has_substance:
        return "Tests section lacks substance — must include test file paths and pass/fail results"

    has_unittest = bool(re.search(r"unit\s*test|gdunit|test_.*\.gd", content, re.IGNORECASE))
    if not has_unittest:
        return (
            "Tests section missing unittest results — every system must have unit tests. "
            "Include the test file name (e.g., test_movement.gd) and run output (e.g., '5 tests -- 5 passed, 0 failed')."
        )

    return None


def check_reviewer_substance(message: str) -> str | None:
    """Check that reviewer report sections have content, not just headings."""
    ecs_review = _extract_section(message, "ECS Review")
    issues_found = _extract_section(message, "Issues Found")

    if not ecs_review:
        return "ECS Review section is empty — reviewer must describe what was checked and findings"
    if not issues_found:
        return "Issues Found section is empty — reviewer must list issues or explain what was verified"
    return None


def main():
    """Entry point for tests that invoke this script directly via subprocess."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    if data.get("hook_event_name") != "SubagentStop":
        sys.exit(0)
    main_with_data(data)


def main_with_data(data: dict) -> None:
    """Validate a worker/verifier report. Called from on_subagent_stop.py dispatcher."""
    message = data.get("last_assistant_message") or ""
    if not message:
        sys.exit(0)

    if not get_current_role():
        sys.exit(0)

    # Anti-deadloop: per-agent block counter
    agent_id = data.get("agent_id") or ""
    state_key = f"worker_report_block:{agent_id}" if agent_id else "worker_report_block:main"
    block_count = state.get(state_key, 0)
    if block_count >= BLOCK_LIMIT:
        record_event(EventType.GATE_CHECK, gate="worker_report",
                     result="force_allow",
                     reason=f"Agent {agent_id} blocked {block_count} times, force-allowing",
                     agent_id=agent_id)
        warning = (
            f"Force-allowing after {block_count} failed attempts. "
            f"Your report for agent {agent_id} did not pass validation. "
            f"You MUST inform the user that this report has unresolved quality issues "
            f"and may need manual review. Do NOT silently proceed as if everything passed."
        )
        print(json.dumps({"decision": "allow", "reason": warning}), file=sys.stderr)
        sys.exit(0)

    # Compute worktree directories once to avoid repeated glob calls in _resolve_file
    worktree_dirs = globmod.glob(os.path.join(".claude", "worktrees", "agent-*"))

    report_type = detect_report_type(message)

    if report_type is None:
        # Check if this agent was dispatched with a known role (worker/verifier/reviewer)
        # If so, it MUST output a report in the required format — block and demand it.
        from log_subagent import lookup_role_from_events
        role = lookup_role_from_events(agent_id) if agent_id else "unknown"

        if role in REPORT_FORMAT_HINTS:
            reason = (
                f"You are a {role} but your output does not contain a properly formatted report. "
                f"You MUST end your response with a report in this format:\n\n"
                f"{REPORT_FORMAT_HINTS[role]}\n\n"
                f"Re-output your report now."
            )
            _block(reason, state_key=state_key, agent_id=agent_id, role=role)

        # Unknown role and no report format — not a worker/verifier/reviewer, allow
        sys.exit(0)

    if report_type in REPORT_REQUIRED_SECTIONS:
        sections = REPORT_REQUIRED_SECTIONS[report_type]
        missing = check_sections(message, sections)
        if missing:
            label = report_type.capitalize()
            reason = (
                f"{label} report missing required sections: {', '.join(missing)}. "
                f"Must include: {REPORT_REQUIRED_LABELS[report_type]}.\n"
                f"Add each missing section as a ### heading with content underneath. "
                f"Refer to the report format in your agent definition for the exact template."
            )
            _block(reason, state_key=state_key, missing=missing)

    if report_type == "worker":
        test_issue = check_test_substance(message)
        if test_issue:
            _block(test_issue, state_key=state_key)

        if os.path.exists("project.godot"):
            files = extract_files_changed(message)
            gd_contents: dict[str, str] = {}
            for f in files:
                if f.endswith(".gd"):
                    resolved = _resolve_file(f, worktree_dirs)
                    if resolved:
                        try:
                            with open(resolved, encoding="utf-8", errors="ignore") as fh:
                                gd_contents[f] = fh.read()
                        except OSError:
                            pass

            res_issue = check_resource_paths(gd_contents, worktree_dirs)
            if res_issue:
                _block(res_issue, state_key=state_key)

            classname_issue = check_classname_conflicts(gd_contents)
            if classname_issue:
                _block(classname_issue, state_key=state_key)

    if report_type == "reviewer":
        reviewer_issue = check_reviewer_substance(message)
        if reviewer_issue:
            _block(reviewer_issue, state_key=state_key)

    record_event(EventType.HOOK_ALLOW, hook="check_worker_report",
                 report_type=report_type)

    # Inject progress reminder on successful validation
    reminder = build_progress_reminder()
    if reminder:
        result = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": reminder,
            }
        }
        print(json.dumps(result))


def build_progress_reminder() -> str | None:
    """Build a progress summary from current session metrics."""
    try:
        events = read_current_events()
    except Exception:
        return None

    if not events:
        return None

    workers = sum(1 for e in events
                  if e.get("event") == "subagent_stop"
                  and event_has_role(e, "worker")
                  and e.get("status") == "DONE")
    verifiers = sum(1 for e in events
                    if e.get("event") == "subagent_stop"
                    and event_has_role(e, "verifier"))
    reviewers = sum(1 for e in events
                    if e.get("event") == "subagent_stop"
                    and event_has_role(e, "reviewer"))

    return (
        f"[Progress] Workers: {workers} done | "
        f"Verifiers: {verifiers} | Reviewers: {reviewers}. "
        f"Reminder: Every worker needs a verifier + reviewer. "
        f"Do NOT stop before /gm-verify completes."
    )


if __name__ == "__main__":
    main()
