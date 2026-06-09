"""Event type definitions for the metrics system."""
import re
from enum import Enum


ROLE_WORKER = "worker"
ROLE_VERIFIER = "verifier"
ROLE_REVIEWER = "reviewer"
ROLE_ANALYST = "analyst"
ROLE_ASSET_PRODUCER = "asset-producer"
ROLE_UNKNOWN = "unknown"
KNOWN_ROLES = {
    ROLE_WORKER,
    ROLE_VERIFIER,
    ROLE_REVIEWER,
    ROLE_ANALYST,
    ROLE_ASSET_PRODUCER,
}


class EventType(str, Enum):
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"

    HOOK_BLOCK = "hook_block"
    HOOK_ALLOW = "hook_allow"

    COMPACTION = "compaction"

    GATE_CHECK = "gate_check"
    STAGE_COMPLETE = "stage_complete"
    SPOT_CHECK = "spot_check"

    ERROR = "error"
    RETRY = "retry"

    WORKER_DONE = "worker_done"
    WORKER_PARTIAL = "worker_partial"
    WORKER_FAILED = "worker_failed"

    VERIFIER_PASS = "verifier_pass"
    VERIFIER_FAIL = "verifier_fail"
    VERIFIER_PARTIAL = "verifier_partial"

    SKILL_READ = "skill_read"

    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"

    E2E_RUN = "e2e_run"
    UNIT_TEST_RUN = "unit_test_run"
    BUILD_CHECK = "build_check"
    SCREENSHOT_CAPTURE = "screenshot_capture"

    WORKER_BRIEF = "worker_brief"


REPORT_MARKERS = {
    ROLE_WORKER: "## Report:",
    ROLE_VERIFIER: "## Verification Report:",
    ROLE_REVIEWER: "## Review Report:",
    ROLE_ANALYST: "## Analyst Report:",
    ROLE_ASSET_PRODUCER: "## Asset Producer Report:",
}

REPORT_PATTERNS = {
    ROLE_ANALYST: re.compile(r"#{1,4}\s*Analyst\s+Report\s*[:：]?", re.IGNORECASE),
    ROLE_WORKER: re.compile(r"#{1,4}\s*Report\s*[:：]?", re.IGNORECASE),
    ROLE_VERIFIER: re.compile(r"#{1,4}\s*Verification\s+Report\s*[:：]?", re.IGNORECASE),
    ROLE_REVIEWER: re.compile(r"#{1,4}\s*Review\s+Report\s*[:：]?", re.IGNORECASE),
    ROLE_ASSET_PRODUCER: re.compile(r"#{1,4}\s*Asset\s+Producer\s+Report\s*[:：]?", re.IGNORECASE),
}

REPORT_FALLBACK = {
    ROLE_ANALYST: re.compile(r"###\s*Candidate\s+Summary", re.IGNORECASE),
    ROLE_WORKER: re.compile(r"###\s*Status:\s*(DONE|PARTIAL|FAILED)", re.IGNORECASE),
    ROLE_VERIFIER: re.compile(r"###\s*Overall:\s*(PASS|FAIL|PARTIAL)", re.IGNORECASE),
    ROLE_REVIEWER: re.compile(r"###\s*Reviewers?\s*Matched", re.IGNORECASE),
    ROLE_ASSET_PRODUCER: re.compile(r"###\s*Production\s+Unit", re.IGNORECASE),
}

REPORT_REQUIRED_SECTIONS = {
    ROLE_WORKER: [
        ("Status", r"### Status:\s*(DONE|PARTIAL|FAILED)"),
        ("Files Changed", r"### Files Changed"),
        ("Tests", r"### Tests"),
        ("Build", r"### Build"),
        ("Memory Entry", r"### Memory Entry"),
    ],
    ROLE_VERIFIER: [
        ("Overall", r"### Overall:\s*(PASS|FAIL|PARTIAL)"),
        ("Results", r"### Results"),
        ("Adversarial Probes", r"### Adversarial Probes"),
    ],
    ROLE_REVIEWER: [
        ("Reviewers Matched", r"### Reviewers Matched"),
        ("ECS Review", r"### ECS Review"),
        ("Issues Found", r"### Issues Found"),
        ("Summary", r"### Summary"),
    ],
    ROLE_ANALYST: [
        ("Status", r"### Status:\s*(DONE|PARTIAL|FAILED)"),
        ("Candidate Summary", r"### Candidate Summary"),
        ("Manifest", r"### Manifest"),
        ("Row Matches", r"### Row Matches"),
        ("Processing Sources", r"### Processing Sources"),
        ("Uncertain Files", r"### Uncertain Files"),
    ],
    ROLE_ASSET_PRODUCER: [
        ("Status", r"### Status:\s*(DONE|PARTIAL|FAILED)"),
        ("Production Unit", r"### Production Unit"),
        ("Outputs", r"### Outputs"),
        ("Tools", r"### Tools"),
        ("Validation", r"### Validation"),
        ("Handoff", r"### Handoff"),
    ],
}

REPORT_FORMAT_HINTS = {}
for _role, _sections in REPORT_REQUIRED_SECTIONS.items():
    _heading = REPORT_MARKERS.get(_role, f"## {_role.capitalize()} Report:")
    _lines = [_heading] + [f"### {name}" for name, _ in _sections]
    REPORT_FORMAT_HINTS[_role] = "\n".join(_lines)

REPORT_REQUIRED_LABELS = {
    role: ", ".join(name for name, _ in sections)
    for role, sections in REPORT_REQUIRED_SECTIONS.items()
}


def event_has_role(event: dict, role: str) -> bool:
    return event.get("role") == role or event.get("report_type") == role


def detect_report_type(message: str) -> str | None:
    if not message:
        return None
    for rtype, marker in REPORT_MARKERS.items():
        if marker in message:
            return rtype
    for rtype, pattern in REPORT_PATTERNS.items():
        if pattern.search(message):
            return rtype
    for rtype, pattern in REPORT_FALLBACK.items():
        if pattern.search(message):
            return rtype
    return None
