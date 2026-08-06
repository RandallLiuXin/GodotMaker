"""Test helpers for hook scripts."""
import json
import os
import subprocess
import sys

# tests/hooks/ → project_root/hooks/
HOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "hooks"
)


def run_hook(script_name: str, input_data: dict) -> tuple[str, int, dict | None]:
    """Run a hook script with JSON input, return (stdout, exit_code, parsed_json).

    Args:
        script_name: Hook script filename (e.g., "check_file_permissions.py")
        input_data: Dict to serialize as JSON stdin

    Returns:
        (stdout_text, exit_code, parsed_json_or_None)
    """
    script_path = os.path.join(HOOKS_DIR, script_name)
    result = subprocess.run(
        [sys.executable, script_path],
        input=json.dumps(input_data),
        capture_output=True, text=True, timeout=10,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    stdout = result.stdout.strip()
    parsed = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    return stdout, result.returncode, parsed


def is_blocked(parsed: dict | None) -> bool:
    """Check if hook response indicates a block.

    Supports both formats:
    - Top-level: {"decision": "block"} (SubagentStop, Stop)
    - PreToolUse: {"hookSpecificOutput": {"permissionDecision": "deny"}}
    """
    if parsed is None:
        return False
    if parsed.get("decision") == "block":
        return True
    hso = parsed.get("hookSpecificOutput", {})
    if hso.get("permissionDecision") == "deny":
        return True
    return False


def write_completed_roles(roles):
    """Write .godotmaker/stage.jsonl with role-completion events.

    Accepts:
    - dict {role: ts}: written as one event per pair (order via dict iteration)
    - list[str]: roles in order, timestamps auto-generated
    - list[dict]: explicit list of {"role": X, "ts": Y} events written verbatim
    """
    os.makedirs(".godotmaker", exist_ok=True)
    if isinstance(roles, dict):
        events = [{"role": r, "ts": ts} for r, ts in roles.items()]
    elif roles and isinstance(roles[0], dict):
        events = roles
    else:
        events = [{"role": r, "ts": f"2026-01-01T{i:02d}:00:00Z"}
                  for i, r in enumerate(roles, start=1)]
    with open(os.path.join(".godotmaker", "stage.jsonl"), "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def write_current_role(role: str):
    """Write .godotmaker/current_role with the given role name."""
    os.makedirs(".godotmaker", exist_ok=True)
    with open(os.path.join(".godotmaker", "current_role"), "w") as f:
        f.write(role)


def write_metrics(events: list[dict]):
    """Write .godotmaker/metrics_current.jsonl with the given events."""
    os.makedirs(".godotmaker", exist_ok=True)
    with open(".godotmaker/metrics_current.jsonl", "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def asset_producer_outcome(status="DONE", unit_id="ui_kit", blockers=None,
                           passed=None, **overrides):
    """Render a valid asset-producer machine outcome block as report markdown.

    Defaults are internally consistent: DONE passes with no blockers, PARTIAL
    and FAILED carry one. `overrides` replace top-level fields verbatim so a
    test can inject an invalid value.
    """
    if blockers is None:
        blockers = [] if status == "DONE" else ["provider returned no usable sheet"]
    if passed is None:
        passed = status == "DONE"
    payload = {
        "gm_outcome_version": 1,
        "report_type": "asset-producer",
        "status": status,
        "unit_id": unit_id,
        "outputs": {
            "sources": [".godotmaker/asset-generation/sources/ui_source.png"],
            "runtime": [],
            "prompts": [],
            "reports": [],
            "request": [],
            "result": [],
        },
        "validation": {"passed": passed, "notes": "checked"},
        "blockers": blockers,
    }
    payload.update(overrides)
    return "### Machine Outcome\n```json\n" + json.dumps(payload, indent=2) + "\n```"


def read_metrics(event=None):
    """Read .godotmaker/metrics_current.jsonl, optionally filtered by event name."""
    events = []
    try:
        with open(".godotmaker/metrics_current.jsonl", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    except FileNotFoundError:
        return []
    if event is not None:
        events = [e for e in events if e.get("event") == event]
    return events


def cleanup_metrics():
    """Remove test metrics artifacts."""
    import shutil
    metrics_dir = os.path.join(os.getcwd(), ".godotmaker")
    if os.path.exists(metrics_dir):
        shutil.rmtree(metrics_dir)
