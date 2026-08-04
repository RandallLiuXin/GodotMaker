"""Machine-readable terminal outcome for pipeline subagent reports.

Markdown headings are a human-readable presentation layer. The terminal
status of an `asset-producer` run travels in a fenced JSON block instead, so
the report hook, the metrics logger, the `/gm-asset` manager, and the stage
manager all read one value through one parser instead of three regexes over
free-form prose.

A report carries exactly one outcome block:

    ```json
    {
      "gm_outcome_version": 1,
      "report_type": "asset-producer",
      "status": "PARTIAL",
      "unit_id": "ui_kit",
      "outputs": {
        "sources": [".godotmaker/asset-generation/sources/ui_source.png"],
        "runtime": [],
        "prompts": [],
        "reports": [],
        "entry_drafts": []
      },
      "validation": {"passed": false, "notes": "atlas regions unverified"},
      "blockers": ["provider returned no usable surface sheet"]
    }
    ```

Validation fails closed: a malformed block raises `OutcomeError` naming the
offending field, so a diagnosable rejection replaces a silent `UNKNOWN`.
"""
import json
import re
from dataclasses import dataclass

from .schema import (
    KNOWN_ROLES, ROLE_ASSET_PRODUCER, ROLE_UNKNOWN, detect_report_type,
)


OUTCOME_VERSION = 1
OUTCOME_VERSION_KEY = "gm_outcome_version"

STATUS_UNKNOWN = "UNKNOWN"
TERMINAL_STATUSES = ("DONE", "PARTIAL", "FAILED")

# Roles whose report MUST carry a valid outcome block. Every other role still
# travels as markdown only; this issue's scope is asset-producer and its
# direct consumers.
OUTCOME_REQUIRED_ROLES = frozenset({ROLE_ASSET_PRODUCER})

OUTPUT_CATEGORIES = ("sources", "runtime", "prompts", "reports", "entry_drafts")
VALIDATION_LEVELS = ("L0", "L1", "L2", "L3", "L4")

TOP_LEVEL_KEYS = (
    OUTCOME_VERSION_KEY, "report_type", "status", "unit_id",
    "outputs", "validation", "blockers",
)

OUTCOME_TEMPLATE = """```json
{
  "gm_outcome_version": 1,
  "report_type": "asset-producer",
  "status": "DONE | PARTIAL | FAILED",
  "unit_id": "{unit_id}",
  "outputs": {
    "sources": [], "runtime": [], "prompts": [], "reports": [], "entry_drafts": []
  },
  "validation": {"passed": true, "notes": "short note"},
  "blockers": []
}
```"""

# Loose markdown fallbacks. Kept case-insensitive and heading-level tolerant so
# a legacy or slightly-off report degrades to the same value the manager reads
# off the prose, never to a contradictory UNKNOWN.
_MD_STATUS_RE = re.compile(
    r"#{1,6}\s*\*{0,2}Status\*{0,2}\s*[:：]\s*\*{0,2}\s*(DONE|PARTIAL|FAILED)",
    re.IGNORECASE,
)
_MD_OVERALL_RE = re.compile(
    r"#{1,6}\s*\*{0,2}Overall\*{0,2}\s*[:：]\s*\*{0,2}\s*(PASS|FAIL|PARTIAL)",
    re.IGNORECASE,
)


class OutcomeError(ValueError):
    """A machine outcome block is present but does not satisfy the contract."""


@dataclass(frozen=True)
class NormalizedReport:
    """One report read through one parser.

    `report_type` and `status` are what every consumer must use. `outcome` is
    the validated block when the report carries one, `outcome_error` explains
    why it was rejected, and `has_outcome_block` distinguishes "no block at
    all" from "block present but invalid".
    """
    report_type: str
    status: str
    outcome: dict | None
    outcome_error: str | None
    has_outcome_block: bool


def extract_markdown_status(message: str) -> str:
    """Best-effort status from report prose. Returns UNKNOWN when absent."""
    if not message:
        return STATUS_UNKNOWN
    match = _MD_STATUS_RE.search(message)
    if match:
        return match.group(1).upper()
    match = _MD_OVERALL_RE.search(message)
    if match:
        return match.group(1).upper()
    return STATUS_UNKNOWN


def _iter_fenced_blocks(message: str):
    """Yield the body of every closed fenced code block in the message."""
    fence = None
    body: list[str] = []
    for line in message.splitlines():
        stripped = line.strip()
        if fence is None:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]
                body = []
            continue
        # A closing fence is the fence characters alone, nothing else.
        if stripped.startswith(fence) and not stripped.strip(fence[0]):
            yield "\n".join(body)
            fence = None
            continue
        body.append(line)


def find_outcome_payloads(message: str) -> tuple[list[dict], list[str]]:
    """Split fenced blocks that claim to be outcome blocks into (parsed, errors).

    A block claims to be an outcome block by mentioning the version key. That
    keeps an unrelated JSON sample in the report from being mistaken for one,
    while a typo inside a real block still surfaces as an error instead of
    being skipped.
    """
    payloads: list[dict] = []
    errors: list[str] = []
    for block in _iter_fenced_blocks(message):
        text = block.strip()
        if OUTCOME_VERSION_KEY not in text:
            continue
        try:
            data = json.loads(text)
        except ValueError as exc:
            errors.append(f"outcome block is not valid JSON: {exc}")
            continue
        if isinstance(data, dict) and OUTCOME_VERSION_KEY in data:
            payloads.append(data)
        else:
            errors.append(
                f"outcome block must be a JSON object carrying '{OUTCOME_VERSION_KEY}'"
            )
    return payloads, errors


def _require_non_empty_str(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutcomeError(f"'{field}' must be a non-empty string")
    return value.strip()


def _validate_outputs(value) -> dict:
    if not isinstance(value, dict):
        raise OutcomeError("'outputs' must be an object of path lists")
    unknown = sorted(set(value) - set(OUTPUT_CATEGORIES))
    if unknown:
        raise OutcomeError(
            f"'outputs' has unknown categories: {', '.join(unknown)}. "
            f"Allowed: {', '.join(OUTPUT_CATEGORIES)}"
        )
    normalized = {}
    for category in OUTPUT_CATEGORIES:
        raw = value.get(category, [])
        if not isinstance(raw, list):
            raise OutcomeError(f"'outputs.{category}' must be an array of paths")
        paths = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                raise OutcomeError(
                    f"'outputs.{category}' entries must be non-empty strings"
                )
            paths.append(item.strip())
        normalized[category] = paths
    return normalized


def _validate_validation(value) -> dict:
    if not isinstance(value, dict):
        raise OutcomeError("'validation' must be an object with a 'passed' boolean")
    unknown = sorted(set(value) - {"passed", "levels", "notes"})
    if unknown:
        raise OutcomeError(
            f"'validation' has unknown keys: {', '.join(unknown)}. "
            f"Allowed: passed, levels, notes"
        )
    if not isinstance(value.get("passed"), bool):
        raise OutcomeError("'validation.passed' must be true or false")
    normalized = {"passed": value["passed"]}

    if "levels" in value:
        levels = value["levels"]
        if not isinstance(levels, dict):
            raise OutcomeError("'validation.levels' must be an object of L0-L4 booleans")
        unknown_levels = sorted(set(levels) - set(VALIDATION_LEVELS))
        if unknown_levels:
            raise OutcomeError(
                f"'validation.levels' has unknown levels: {', '.join(unknown_levels)}"
            )
        for name, passed in levels.items():
            if not isinstance(passed, bool):
                raise OutcomeError(f"'validation.levels.{name}' must be true or false")
        normalized["levels"] = dict(levels)

    if "notes" in value:
        if not isinstance(value["notes"], str):
            raise OutcomeError("'validation.notes' must be a string")
        normalized["notes"] = value["notes"].strip()

    return normalized


def _validate_blockers(value) -> list[str]:
    if not isinstance(value, list):
        raise OutcomeError("'blockers' must be an array of strings")
    blockers = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise OutcomeError("'blockers' entries must be non-empty strings")
        blockers.append(item.strip())
    return blockers


def validate_outcome(payload: dict) -> dict:
    """Validate and normalize one outcome payload. Raises OutcomeError."""
    if not isinstance(payload, dict):
        raise OutcomeError("outcome block must be a JSON object")

    unknown = sorted(set(payload) - set(TOP_LEVEL_KEYS))
    if unknown:
        raise OutcomeError(
            f"outcome block has unknown fields: {', '.join(unknown)}. "
            f"Allowed: {', '.join(TOP_LEVEL_KEYS)}"
        )
    missing = [key for key in TOP_LEVEL_KEYS if key not in payload]
    if missing:
        raise OutcomeError(f"outcome block is missing fields: {', '.join(missing)}")

    if payload[OUTCOME_VERSION_KEY] != OUTCOME_VERSION:
        raise OutcomeError(
            f"'{OUTCOME_VERSION_KEY}' must be {OUTCOME_VERSION}, "
            f"got {payload[OUTCOME_VERSION_KEY]!r}"
        )

    report_type = _require_non_empty_str(payload["report_type"], "report_type")
    if report_type not in KNOWN_ROLES:
        raise OutcomeError(
            f"'report_type' must be one of: {', '.join(sorted(KNOWN_ROLES))}"
        )

    status_raw = payload["status"]
    if not isinstance(status_raw, str):
        raise OutcomeError(f"'status' must be one of: {', '.join(TERMINAL_STATUSES)}")
    status = status_raw.strip().upper()
    if status not in TERMINAL_STATUSES:
        raise OutcomeError(f"'status' must be one of: {', '.join(TERMINAL_STATUSES)}")

    unit_id = _require_non_empty_str(payload["unit_id"], "unit_id")
    outputs = _validate_outputs(payload["outputs"])
    validation = _validate_validation(payload["validation"])
    blockers = _validate_blockers(payload["blockers"])

    # Cross-field rules keep the terminal record unambiguous: DONE is the only
    # status that claims success, and a non-DONE run must say why.
    if status == "DONE":
        if not validation["passed"]:
            raise OutcomeError(
                "'status' DONE requires 'validation.passed' true; "
                "report PARTIAL or FAILED instead"
            )
        if blockers:
            raise OutcomeError(
                "'status' DONE requires an empty 'blockers' array; "
                "report PARTIAL or FAILED instead"
            )
    elif not blockers:
        raise OutcomeError(
            f"'status' {status} requires at least one entry in 'blockers'"
        )

    return {
        OUTCOME_VERSION_KEY: OUTCOME_VERSION,
        "report_type": report_type,
        "status": status,
        "unit_id": unit_id,
        "outputs": outputs,
        "validation": validation,
        "blockers": blockers,
    }


def normalize_report(message: str) -> NormalizedReport:
    """The single parse/normalize entry point every consumer shares."""
    message = message or ""
    md_type = detect_report_type(message) or ROLE_UNKNOWN
    md_status = extract_markdown_status(message)

    payloads, errors = find_outcome_payloads(message)

    if not payloads and not errors:
        return NormalizedReport(md_type, md_status, None, None, False)

    if errors:
        return NormalizedReport(md_type, md_status, None, "; ".join(errors), True)

    if len(payloads) > 1:
        return NormalizedReport(
            md_type, md_status, None,
            f"report carries {len(payloads)} outcome blocks; exactly one is allowed",
            True,
        )

    try:
        outcome = validate_outcome(payloads[0])
    except OutcomeError as exc:
        return NormalizedReport(md_type, md_status, None, str(exc), True)

    return NormalizedReport(
        outcome["report_type"], outcome["status"], outcome, None, True
    )
