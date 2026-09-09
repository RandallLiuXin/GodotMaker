"""Bounded failure diagnostics for Worker handoffs.

This module indexes a failed Worker run. It does not preserve arbitrary report
text, feed diagnostics into later prompts, or interpret reports from other
roles. Missing optional evidence remains missing instead of being inferred
from unrelated prose or pasted command output.
"""
import hashlib
import json
import os
import posixpath
import re

from .collector import read_current_events, record_event
from .schema import EventType, ROLE_WORKER


ERROR_EVENT_VERSION = 1
MAX_SUMMARY_CHARS = 200
MAX_EVIDENCE_PATHS = 5
MAX_EVIDENCE_PATH_CHARS = 200
MAX_TASK_ID_CHARS = 48
LARGE_OUTPUT_THRESHOLD_BYTES = 4096
MAX_OUTPUT_TAIL_CHARS = 500

ERROR_TIMEOUT = "timeout"
ERROR_FORCED_HANDOFF = "forced_handoff"
ERROR_TOOL_OR_ENV = "tool_or_environment_error"
ERROR_REPORT_REJECTED = "report_rejected"
ERROR_UNVERIFIED = "unverified_handoff"
ERROR_TASK_FAILED = "task_failed"
ERROR_TASK_PARTIAL = "task_partial"

HANDOFF_ERROR_TYPES = {
    "timeout": ERROR_TIMEOUT,
    "forced_handoff": ERROR_FORCED_HANDOFF,
    "tool_or_environment_error": ERROR_TOOL_OR_ENV,
}
RETRYABLE_ERROR_TYPES = frozenset({
    ERROR_TIMEOUT,
    ERROR_FORCED_HANDOFF,
    ERROR_TOOL_OR_ENV,
    ERROR_REPORT_REJECTED,
    ERROR_UNVERIFIED,
})
KNOWN_CLASSIFICATIONS = frozenset({
    "verified_success",
    "effective_repair_candidate",
    "incomplete_handoff",
    "orchestration_failure",
})
EVIDENCE_ROOTS = (".godotmaker/", "reports/", "e2e/", "docs/tags/")

_REPORT_HEADING_RE = re.compile(
    r"^#{1,4}[^\S\n]*Report[^\S\n]*[:：][^\S\n]*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_ANY_REPORT_HEADING_RE = re.compile(
    r"^#{1,4}[^\S\n]*([^\n]*\bReport\b[^\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)
_TASK_ID_RE = re.compile(r"^[\[(]?\s*([A-Z]{1,3}\d{1,3})\b")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FIELD_RE = re.compile(
    r"^[-*\s]*(Handoff condition|Suggested classification)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_BLOCKER_RE = re.compile(
    r"^[-*\s]*(?:Blocker|Error|Failure|Reason)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_EXIT_CODE_RE = re.compile(
    r"exit(?:ed)?(?:\s+with)?(?:\s+code)?\s*[:=]?\s*(-?\d+)\b",
    re.IGNORECASE,
)
_PATH_RE = re.compile(r"[\w.:/\\-]+")
_WS_RE = re.compile(r"\s+")


def _clip(value: str, limit: int) -> str:
    value = _WS_RE.sub(" ", (value or "").strip())
    if len(value) <= limit:
        return value
    return value[:limit - 1].rstrip() + "…"


def _section_body(message: str, name: str) -> str:
    pattern = re.compile(
        rf"^#{{1,3}}[^\S\n]*{re.escape(name)}[^\S\n]*$\n"
        r"(.*?)(?=^#{1,3}\s|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(message or "")
    return match.group(1) if match else ""


def extract_task_id(message: str) -> str:
    match = _REPORT_HEADING_RE.search(message or "")
    if not match:
        return "unknown"
    name = match.group(1).strip().strip("*_`").strip()
    if not name:
        return "unknown"
    id_match = _TASK_ID_RE.match(name)
    if id_match:
        return id_match.group(1).upper()
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug[:MAX_TASK_ID_CHARS] or "unknown"


def is_worker_report(message: str) -> bool:
    """True when the first report heading is the Worker's generic Report."""
    first = _ANY_REPORT_HEADING_RE.search(message or "")
    if not first:
        return False
    return bool(re.match(r"^Report\s*[:：]", first.group(1).strip(), re.IGNORECASE))


def extract_repair_fields(message: str) -> dict[str, str]:
    section = _section_body(message, "Repair Attempt Evidence")
    fields = {}
    for label, value in _FIELD_RE.findall(section):
        key = label.strip().lower().replace(" ", "_")
        fields[key] = value.strip().strip("*_`{}").lower().replace(" ", "_")
    return fields


def resolve_error_type(status: str, outcome_kind: str,
                       handoff_condition: str = "") -> str | None:
    if outcome_kind == "rejected_attempt":
        return ERROR_REPORT_REJECTED
    if handoff_condition in HANDOFF_ERROR_TYPES:
        return HANDOFF_ERROR_TYPES[handoff_condition]
    if outcome_kind == "unverified":
        return ERROR_UNVERIFIED
    normalized = (status or "").upper()
    if normalized == "FAILED":
        return ERROR_TASK_FAILED
    if normalized == "PARTIAL":
        return ERROR_TASK_PARTIAL
    return None


def extract_summary(message: str, error_type: str, detail: str = "") -> str:
    if detail:
        return _clip(detail, MAX_SUMMARY_CHARS)
    for section_name in ("Repair Attempt Evidence", "Notes"):
        match = _BLOCKER_RE.search(_section_body(message, section_name))
        if match:
            return _clip(match.group(1), MAX_SUMMARY_CHARS)
    return error_type.replace("_", " ")


def extract_exit_code(message: str) -> int | None:
    codes = []
    for section_name in ("Tests", "Build"):
        for raw in _EXIT_CODE_RE.findall(_section_body(message, section_name)):
            try:
                codes.append(int(raw))
            except ValueError:
                continue
    non_zero = [code for code in codes if code != 0]
    return non_zero[0] if non_zero else (codes[0] if codes else None)


def extract_large_output_reference(message: str) -> dict:
    """Return a bounded hash + tail reference for large test/build output."""
    sections = []
    for section_name in ("Tests", "Build"):
        body = _section_body(message, section_name).strip()
        if body:
            sections.append(f"{section_name}:\n{body}")
    output = "\n\n".join(sections)
    encoded = output.encode("utf-8", errors="replace")
    if len(encoded) <= LARGE_OUTPUT_THRESHOLD_BYTES:
        return {}
    tail = output[-MAX_OUTPUT_TAIL_CHARS:]
    if len(tail) < len(output):
        tail = "…" + tail[1:]
    return {
        "output_digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "output_bytes": len(encoded),
        "output_tail": tail,
    }


def _normalize_evidence_path(token: str) -> str | None:
    token = token.replace("\\", "/").rstrip(".,;:)]}")
    if not token or token.startswith("/") or re.match(r"^[A-Za-z]:/", token):
        return None
    normalized = posixpath.normpath(token)
    if normalized == ".." or normalized.startswith("../"):
        return None
    if not normalized.startswith(EVIDENCE_ROOTS):
        return None
    return normalized[:MAX_EVIDENCE_PATH_CHARS]


def extract_evidence_paths(message: str) -> list[str]:
    paths = []
    for section_name in (
        "Tests", "Build", "Repair Attempt Evidence", "Notes",
        "Visual Self-Check",
    ):
        for token in _PATH_RE.findall(_section_body(message, section_name)):
            path = _normalize_evidence_path(token)
            if path and path not in paths:
                paths.append(path)
                if len(paths) == MAX_EVIDENCE_PATHS:
                    return paths
    return paths


def read_runtime(project_dir: str = ".") -> str:
    """Read the configured top-level runtime without changing shared config code."""
    aliases = {
        "claude": "claude-code",
        "claude-code": "claude-code",
        "codex": "codex",
        "openai-codex": "codex",
        "opencode": "opencode",
        "pi": "pi",
    }
    config = os.path.join(project_dir, ".godotmaker", "config.yaml")
    try:
        with open(config, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line[:1].isspace() or line.lstrip().startswith("#"):
                    continue
                key, separator, value = line.partition(":")
                if separator and key.strip() == "agent":
                    normalized = value.split("#", 1)[0].strip().strip("\"'")
                    return aliases.get(normalized.lower(), normalized.lower()) or "unknown"
    except OSError:
        pass
    for directory, runtime in ((".agents", "codex"), (".opencode", "opencode"), (".pi", "pi")):
        if os.path.isdir(os.path.join(project_dir, directory)):
            return runtime
    return "claude-code"


def _prior_events(task_id: str, stage: str) -> list[dict]:
    try:
        events = read_current_events()
    except Exception:
        return []
    return [
        event for event in events
        if event.get("event") == EventType.WORKER_ERROR.value
        and event.get("task_id") == task_id
        and event.get("stage") == stage
    ]


def _fingerprint(task_id: str, stage: str, error_type: str,
                 summary: str, exit_code: int | None) -> str:
    payload = json.dumps(
        [task_id, stage, error_type, summary.lower(), exit_code],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_worker_error_event(*, message: str, status: str,
                             outcome_kind: str, agent_id: str = "",
                             run_id: str = "", trace_id: str = "",
                             stage: str = "", detail: str = "") -> dict | None:
    repair = extract_repair_fields(message)
    error_type = resolve_error_type(
        status,
        outcome_kind,
        repair.get("handoff_condition", ""),
    )
    if error_type is None:
        return None

    task_id = extract_task_id(message)
    summary = extract_summary(message, error_type, detail)
    exit_code = extract_exit_code(message)
    fingerprint = _fingerprint(task_id, stage, error_type, summary, exit_code)
    prior = _prior_events(task_id, stage)
    classification = repair.get("suggested_classification", "")
    if classification not in KNOWN_CLASSIFICATIONS:
        classification = ""

    event = {
        "gm_error_version": ERROR_EVENT_VERSION,
        "task_id": task_id,
        "attempt": len(prior) + 1,
        "stage": stage,
        "runtime": read_runtime(),
        "role": ROLE_WORKER,
        "agent_id": agent_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "error_type": error_type,
        "classification": classification,
        "status": (status or "").upper(),
        "outcome_kind": outcome_kind,
        "summary": summary,
        "exit_code": exit_code,
        "error_fingerprint": fingerprint,
        "evidence_paths": extract_evidence_paths(message),
        "retryable": error_type in RETRYABLE_ERROR_TYPES,
        "repeat_count": sum(
            event.get("error_fingerprint") == fingerprint for event in prior
        ),
    }
    event.update(extract_large_output_reference(message))
    return event


def record_worker_error(event: dict | None) -> bool:
    if not event:
        return False
    try:
        for prior in read_current_events():
            if (
                prior.get("event") == EventType.WORKER_ERROR.value
                and prior.get("agent_id") == event.get("agent_id")
                and prior.get("error_fingerprint") == event.get("error_fingerprint")
            ):
                return False
    except Exception:
        pass
    record_event(EventType.WORKER_ERROR, **event)
    return True
