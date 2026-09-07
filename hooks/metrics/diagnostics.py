"""Structured failure diagnostics for pipeline subagent runs.

Workers do not accumulate learnings. What a run leaves behind when it goes
wrong is a bounded, machine-readable error event on the existing metrics
stream — not a memory entry, not a project rule, and not prompt context for
the next dispatch.

One event per failed handoff, shaped like:

    {"event": "worker_error", "gm_error_version": 1, "task_id": "M01",
     "attempt": 2, "stage": "build", "runtime": "codex", "role": "worker",
     "error_type": "tool_or_environment_error",
     "summary": "Headless Godot load failed", "exit_code": 1,
     "error_fingerprint": "…", "evidence_paths": [".godotmaker/traces/…"],
     "retryable": true}

Three properties the rest of the pipeline depends on:

- **Bounded.** Summaries, evidence path lists, and output digests all have
  hard caps. Large stdout/stderr travels as `{sha256, bytes, tail}`, never as
  a copy of the output.
- **Deduplicated.** `error_fingerprint` is stable across attempts of the same
  failure, and an identical (agent_id, fingerprint) pair is recorded once, so
  a SubagentStop that fires repeatedly cannot inflate the log.
- **Diagnostic only.** Nothing here is read back into a worker or agent
  prompt. Promoting a recurring failure into a framework fix is a separate,
  human-confirmed trace-analysis step.
"""
import hashlib
import os
import re

from .collector import read_current_events, record_event
from .schema import (
    EventType, ROLE_ANALYST, ROLE_ASSET_PRODUCER, ROLE_WORKER,
)


ERROR_EVENT_VERSION = 1

# Hard bounds. A diagnostic record is an index into evidence, not the
# evidence itself.
MAX_SUMMARY_CHARS = 200
MAX_EVIDENCE_PATHS = 5
MAX_EVIDENCE_PATH_CHARS = 200
MAX_DIGEST_TAIL_CHARS = 400
MAX_TASK_ID_CHARS = 48

# Error types. `handoff condition` values from the worker report's Repair
# Attempt Evidence section map straight through; the rest are derived from
# how the stop was classified.
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

# `retryable` means: re-dispatching the SAME brief can plausibly succeed
# without new information. Orchestration and environment faults qualify;
# a production FAILED/PARTIAL does not, because the worker already reported
# a blocker the dispatching role has to answer first.
RETRYABLE_ERROR_TYPES = frozenset({
    ERROR_TIMEOUT, ERROR_FORCED_HANDOFF, ERROR_TOOL_OR_ENV,
    ERROR_REPORT_REJECTED, ERROR_UNVERIFIED,
})

# Roles whose report `Status` is a statement about their own run, in
# DONE / PARTIAL / FAILED terms — for these a non-DONE status IS a failed
# handoff. A verifier's `Overall: PASS | FAIL | PARTIAL` is a verdict about
# the project instead: a verifier that reports FAIL did its job, and that
# result already travels as a `verifier_fail` event. So status never derives
# an error type for it; only the run-level faults above that — a rejected
# report, a timeout, a tool fault, an unverified release — do, and those
# apply to every role.
STATUS_IS_RUN_OUTCOME_ROLES = frozenset({
    ROLE_WORKER, ROLE_ASSET_PRODUCER, ROLE_ANALYST,
})

# Classifications defined by `repair-attempt-accounting.md`. Carried through
# verbatim so the counters and the diagnostic stream agree.
KNOWN_CLASSIFICATIONS = frozenset({
    "verified_success", "effective_repair_candidate",
    "incomplete_handoff", "orchestration_failure",
})

# Evidence lives under the runtime's own output roots. Anything else named in
# a report is prose, not an artifact we can point a later reader at.
EVIDENCE_PREFIXES = (".godotmaker/", "reports/", "e2e/", "docs/tags/")

_TASK_ID_RE = re.compile(r"^[\[\(]?\s*([A-Z]{1,3}\d{1,3})\b")
_REPORT_HEADING_RE = re.compile(
    r"^#{1,4}\s*(?:Report|Verification Report|Asset Producer Report|Analyst Report)"
    r"\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_EVIDENCE_FIELD_RE = re.compile(
    r"^[-*\s]*(Handoff condition|Suggested classification)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_EXIT_CODE_RE = re.compile(
    r"exit(?:ed with|ed|\s*code)?\s*[:=]?\s*(-?\d{1,3})\b", re.IGNORECASE
)
# The `Tests` and `Build` sections, each up to the next same-or-shallower
# heading. `#{1,3}\s` cannot match the `#### Unit Tests` sub-heading inside
# Tests, so the sub-section stays part of the captured output.
_OUTPUT_SECTION_RE = re.compile(
    r"^#{1,3}\s*(?:Tests|Build)\s*$\n(.*?)(?=\n#{1,3}\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
_PATH_RE = re.compile(r"[\w./\\-]+")
_DIGIT_RUN_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _clip(text: str, limit: int) -> str:
    text = _WS_RE.sub(" ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# Canonical runtime ids and their accepted spellings, and the project-local
# directory each runtime publishes into. Both mirror
# `tools/agent_runtime.py` — `normalize_agent` and `detect_agent`'s fallback.
# A hook must never crash, and `tools/` is not on its import path, so this is
# a deliberate copy rather than a cross-tree import;
# `tests/hooks/test_worker_error_diagnostics.py` pins the two together so
# they cannot drift apart silently.
RUNTIME_ALIASES = {
    "codex": "codex", "openai-codex": "codex",
    "opencode": "opencode", "open-code": "opencode",
    "pi": "pi", "pi-coding-agent": "pi", "pi-coding": "pi",
    "claude": "claude-code", "claude-code": "claude-code",
    "anthropic-claude-code": "claude-code",
}
RUNTIME_CONFIG_DIRS = (
    (".agents", "codex"),
    (".opencode", "opencode"),
    (".pi", "pi"),
)
RUNTIME_DEFAULT = "claude-code"


def normalize_runtime(value: str | None) -> str | None:
    """Canonical runtime id for a configured spelling, or None if unknown."""
    if not value:
        return None
    return RUNTIME_ALIASES.get(value.strip().lower().replace("_", "-"))


def read_runtime(project_dir: str = ".") -> str:
    """The selected coding agent, resolved the way `detect_agent` resolves it.

    The `agent:` key in `.godotmaker/config.yaml` first, then the same
    published-directory fallback `detect_agent` uses for projects that predate
    that key, then its same `claude-code` default. Aliases are normalized, so
    `agent: claude` is recorded as `claude-code` and correlates with the other
    runtimes rather than becoming a fourth spelling of one of them.

    Only top-level keys count: an indented `agent:` belongs to some nested
    block, not to the project's runtime selection.
    """
    path = os.path.join(project_dir, ".godotmaker", "config.yaml")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip() or line[:1] in (" ", "\t", "#"):
                    continue
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                if key.strip() in ("agent", "agent_runtime"):
                    runtime = normalize_runtime(value.strip().strip("\"'"))
                    if runtime:
                        return runtime
    except OSError:
        pass

    for directory, runtime in RUNTIME_CONFIG_DIRS:
        if os.path.isdir(os.path.join(project_dir, directory)):
            return runtime
    return RUNTIME_DEFAULT


def extract_task_id(message: str) -> str:
    """Stable task identity for a report, so attempts of one task group.

    Prefers the PLAN.md / GAP.md task id the brief's task name starts with
    (`M01`, `R2`, `C1`); falls back to a bounded slug of the task name, which
    is equally stable because a re-dispatch reuses the same brief.
    """
    match = _REPORT_HEADING_RE.search(message or "")
    if not match:
        return "unknown"
    name = match.group(1).strip().strip("*_`").strip()
    if not name:
        return "unknown"
    id_match = _TASK_ID_RE.match(name)
    if id_match:
        return id_match.group(1)
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    return slug[:MAX_TASK_ID_CHARS] or "unknown"


def extract_repair_fields(message: str) -> dict:
    """Read `Handoff condition` and `Suggested classification` off a report."""
    fields: dict[str, str] = {}
    for label, value in _EVIDENCE_FIELD_RE.findall(message or ""):
        key = label.strip().lower().replace(" ", "_")
        cleaned = value.strip().strip("*_`{}").strip().lower().replace(" ", "_")
        if cleaned and key not in fields:
            fields[key] = cleaned
    return fields


def extract_exit_code(message: str) -> int | None:
    """First explicit exit code in the report, or None when it names none."""
    match = _EXIT_CODE_RE.search(message or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def extract_evidence_paths(message: str) -> list[str]:
    """Bounded list of artifact paths the report points at.

    Only paths under a known evidence root are kept — a diagnostic record
    references where the output lives, it never carries the output.
    """
    paths: list[str] = []
    for token in _PATH_RE.findall(message or ""):
        candidate = token.replace("\\", "/").rstrip(".,;:)]}")
        if not candidate.startswith(EVIDENCE_PREFIXES):
            continue
        if len(candidate) > MAX_EVIDENCE_PATH_CHARS:
            continue
        if candidate not in paths:
            paths.append(candidate)
        if len(paths) >= MAX_EVIDENCE_PATHS:
            break
    return paths


def extract_command_output(message: str) -> str:
    """The report's Tests and Build sections — where command output lands."""
    return "\n".join(
        match.group(1) for match in _OUTPUT_SECTION_RE.finditer(message or "")
    )


def digest_output(output: str) -> dict | None:
    """Reference a large command output by hash + tail instead of copying it.

    Returns None for output that is small enough to already be readable in the
    report itself — a digest of two lines helps nobody.
    """
    if not output or len(output) <= MAX_DIGEST_TAIL_CHARS:
        return None
    raw = output.encode("utf-8", errors="replace")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "tail": output[-MAX_DIGEST_TAIL_CHARS:],
    }


def error_fingerprint(task_id: str, stage: str, error_type: str,
                      summary: str) -> str:
    """Stable id for "this same failure", used to dedupe and to count repeats.

    Digit runs are collapsed so line numbers, durations, and pids do not make
    two occurrences of one failure look like two different failures.
    """
    normalized = _DIGIT_RUN_RE.sub("#", _WS_RE.sub(" ", (summary or "").lower()).strip())
    seed = "|".join((task_id or "", stage or "", error_type or "", normalized))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def resolve_error_type(status: str, outcome_kind: str,
                       handoff_condition: str, role: str) -> str | None:
    """The one error type for this stop, or None when the run is clean.

    Run-level faults come first and hold for every role: a rejected report is
    an orchestration fault regardless of what the report claims, and an
    explicit handoff condition outranks status because a timeout or a tool
    fault explains a `FAILED` that the status alone does not.

    Status is read last, and only for the roles whose status vocabulary
    describes their own run — see `STATUS_IS_RUN_OUTCOME_ROLES`. `role` is
    required rather than defaulted, so a caller cannot silently skip that
    branch by omitting it.
    """
    if outcome_kind == "rejected_attempt":
        return ERROR_REPORT_REJECTED
    mapped = HANDOFF_ERROR_TYPES.get(handoff_condition or "")
    if mapped:
        return mapped
    if outcome_kind == "unverified":
        return ERROR_UNVERIFIED
    if role not in STATUS_IS_RUN_OUTCOME_ROLES:
        return None
    status = (status or "").upper()
    if status == "FAILED":
        return ERROR_TASK_FAILED
    if status == "PARTIAL":
        return ERROR_TASK_PARTIAL
    return None


def _prior_events(task_id: str, stage: str) -> list[dict]:
    try:
        events = read_current_events()
    except Exception:
        return []
    return [
        evt for evt in events
        if evt.get("event") == EventType.WORKER_ERROR.value
        and evt.get("task_id") == task_id
        and evt.get("stage") == stage
    ]


_BLOCKER_RE = re.compile(
    r"^[-*\s]*(?:Blocker|Error|Failure|Reason)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def _summary_for(message: str, error_type: str) -> str:
    """One short line naming the failure, taken from the report when it says.

    Never the raw output: a summary is a label, and the evidence paths and
    output digest are how a reader reaches the full text.
    """
    match = _BLOCKER_RE.search(message or "")
    if match:
        return match.group(1)
    notes = re.search(r"###\s*Notes\s*\n(.+)", message or "")
    if notes and notes.group(1).strip():
        return notes.group(1)
    return error_type.replace("_", " ")


def build_error_event(*, message: str, role: str, status: str,
                      outcome_kind: str, agent_id: str = "",
                      run_id: str = "", stage: str = "") -> dict | None:
    """Normalize one stop into a diagnostic event, or None if it is clean."""
    repair = extract_repair_fields(message)
    error_type = resolve_error_type(status, outcome_kind,
                                    repair.get("handoff_condition", ""), role)
    if error_type is None:
        return None

    task_id = extract_task_id(message)
    summary = _clip(_summary_for(message, error_type), MAX_SUMMARY_CHARS)
    fingerprint = error_fingerprint(task_id, stage, error_type, summary)
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
        "role": role,
        "agent_id": agent_id,
        "run_id": run_id,
        "error_type": error_type,
        "classification": classification,
        "status": (status or "").upper(),
        "outcome_kind": outcome_kind,
        "summary": summary,
        "exit_code": extract_exit_code(message),
        "error_fingerprint": fingerprint,
        "evidence_paths": extract_evidence_paths(message),
        "retryable": error_type in RETRYABLE_ERROR_TYPES,
        "repeat_count": sum(
            1 for evt in prior if evt.get("error_fingerprint") == fingerprint
        ),
    }
    # A worker that pasted a whole build log instead of its tail: the digest
    # replaces the copy, so the diagnostic stream stays bounded either way.
    digest = digest_output(extract_command_output(message))
    if digest is not None:
        event["output_digest"] = digest
    return event


def record_error_event(event: dict | None) -> bool:
    """Write one diagnostic event, unless it duplicates one already recorded.

    Returns True when an event was written. Dedupe is per
    (agent_id, error_fingerprint): SubagentStop can fire more than once for a
    single agent, and one failure must not become several records.
    """
    if not event:
        return False
    try:
        for evt in read_current_events():
            if (evt.get("event") == EventType.WORKER_ERROR.value
                    and evt.get("agent_id") == event.get("agent_id")
                    and evt.get("error_fingerprint") == event.get("error_fingerprint")):
                return False
    except Exception:
        pass
    record_event(EventType.WORKER_ERROR, **event)
    return True
