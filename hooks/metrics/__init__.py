"""GodotMaker metrics system.

Self-contained metrics collection and reporting.
All hooks import from this package to record events.

Usage from hooks:
    from metrics import record_event, EventType
    record_event(EventType.HOOK_BLOCK, hook="check_file_permissions", reason="...")

Generate report:
    python -m hooks.metrics.reporter .godotmaker/metrics.jsonl -o report.html
"""
import json
import os
import re

from .collector import record_event, read_events, read_current_events, start_session
from .schema import (
    EventType, REPORT_MARKERS, detect_report_type, event_has_role,
    REPORT_REQUIRED_SECTIONS, REPORT_FORMAT_HINTS, REPORT_REQUIRED_LABELS,
    ROLE_WORKER, ROLE_VERIFIER, ROLE_REVIEWER, ROLE_ANALYST,
    ROLE_ASSET_PRODUCER, ROLE_UNKNOWN,
    KNOWN_ROLES,
)
from . import state


PIPELINE_ROLES = (
    "scaffold", "gdd", "asset",
    "build", "verify", "evaluate", "fixgap", "accept", "finalize",
)

# Roles that drive a worker-orchestration workflow (worker → verifier →
# reviewer rounds). Subject to prereq + scaffold-artifact checks on Agent
# dispatch and to diligence checks on Stop.
WORKER_DISPATCH_ROLES = frozenset({"build", "fixgap"})

STAGE_SCHEMAS_PATH = os.path.join(".godotmaker", "stage_schemas.json")


def load_stage_schemas() -> dict | None:
    """Load .godotmaker/stage_schemas.json. Returns None if missing or malformed."""
    try:
        with open(STAGE_SCHEMAS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def validate_schema_files(role_schema: dict) -> list[str]:
    """Return ["Required file missing: <path>", ...] for each missing file in
    role_schema['files']. Empty list if every file is present.
    """
    issues = []
    for filepath in role_schema.get("files", []):
        if not os.path.exists(filepath):
            issues.append(f"Required file missing: {filepath}")
    return issues


def get_completed_roles() -> dict:
    """Read role-completion log from .godotmaker/stage.jsonl.

    Returns dict mapping role name → latest ISO timestamp string.
    Empty dict if file missing or malformed. Roles that completed multiple
    times (e.g. fixgap) appear once with their most-recent timestamp.
    """
    roles = {}
    try:
        with open(os.path.join(".godotmaker", "stage.jsonl"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                role = entry.get("role")
                ts = entry.get("ts")
                if role and ts:
                    roles[role] = ts  # latest wins (file is in chronological order)
    except (OSError, FileNotFoundError):
        pass
    return roles


def get_role_events() -> list[dict]:
    """Return the full role-completion event log as a list of {role, ts} dicts."""
    events = []
    try:
        with open(os.path.join(".godotmaker", "stage.jsonl"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if entry.get("role") and entry.get("ts"):
                    events.append(entry)
    except (OSError, FileNotFoundError):
        pass
    return events


def is_role_completed(role: str) -> bool:
    """Check if a specific pipeline role has completed at least once."""
    return role in get_completed_roles()


def get_current_role() -> str:
    """Read the active pipeline role from .godotmaker/current_role.

    Returns the role name (lowercased) or "" if no role lock is set.
    """
    role_file = os.path.join(".godotmaker", "current_role")
    try:
        with open(role_file, encoding="utf-8") as f:
            return f.read().strip().lower()
    except (OSError, FileNotFoundError):
        return ""


TAG_HEADER_RE = re.compile(r"^\*\*Tag:\*\*\s*(v\d+\.\d+\.\d+)\s*$", re.MULTILINE)


def get_current_tag() -> str:
    """Read the current tag from PLAN.md's `**Tag:**` header.

    Returns the tag string (e.g. "v0.2.0") or "" if PLAN.md is missing
    or has no Tag header. Used for session-start banners and other
    informational displays — DO NOT rely on this for gating; use the
    git-tag-vs-ROADMAP comparison in gm-gdd's Mode Detection for that.
    """
    try:
        with open("PLAN.md", encoding="utf-8", errors="replace") as f:
            m = TAG_HEADER_RE.search(f.read())
            return m.group(1) if m else ""
    except OSError:
        return ""


__all__ = [
    "record_event", "read_events", "read_current_events", "start_session",
    "EventType", "REPORT_MARKERS", "detect_report_type", "event_has_role",
    "REPORT_REQUIRED_SECTIONS", "REPORT_FORMAT_HINTS", "REPORT_REQUIRED_LABELS",
    "ROLE_WORKER", "ROLE_VERIFIER", "ROLE_REVIEWER", "ROLE_ANALYST",
    "ROLE_ASSET_PRODUCER", "ROLE_UNKNOWN",
    "KNOWN_ROLES",
    "state",
    "PIPELINE_ROLES",
    "WORKER_DISPATCH_ROLES",
    "STAGE_SCHEMAS_PATH",
    "load_stage_schemas",
    "validate_schema_files",
    "get_completed_roles",
    "get_role_events",
    "is_role_completed",
    "get_current_role",
    "get_current_tag",
    "TAG_HEADER_RE",
]
