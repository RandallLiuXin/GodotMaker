"""Side-effect-free stage completion validation.

The stage event append tool is the enforcement point for these checks. Keep
this module free of metrics, archive, and stage-log writes so callers can run
it before committing any completion side effect.
"""
from __future__ import annotations

import json
import os
import re

from check_completion import get_diligence_failure
from metrics import (
    WORKER_DISPATCH_ROLES,
    load_stage_schemas,
    read_current_events,
    validate_schema_files,
)
from playability_contract import check_evaluation_playable_unit_complete


def check_plan_all_verified(_event: dict | None = None) -> str | None:
    return _check_task_table_all_verified("PLAN.md")


def check_gap_archived(event: dict | None = None) -> str | None:
    if event and event.get("outcome") == "handoff":
        return None
    if os.path.isfile("GAP.md"):
        return (
            "GAP.md is still at project root — it must be archived to "
            ".godotmaker/gaps/<iteration>/GAP.md before completing fixgap."
        )
    return None


def check_evaluation_playable_unit(_event: dict | None = None) -> str | None:
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
    "DESIGN.md",
    "SCENES.md",
    "evaluation-final.json",
    "CHANGELOG.md",
    "README.md",
    "SUMMARY.md",
)

_SEAL_HINT = "run `python tools/seal_tag.py index {tag}` to seal the archive"
_REINDEX_HINT = "run `python tools/seal_tag.py reindex` to rebuild it"


def check_tag_archived(_event: dict | None = None) -> str | None:
    from metrics import get_current_tag

    tag = get_current_tag()
    if not tag:
        return (
            "PLAN.md missing or has no `**Tag:** vX.Y.Z` header — finalize "
            "needs this to know which docs/tags/<Tag>/ directory to verify."
        )
    archive = os.path.join("docs", "tags", tag)
    if not os.path.isdir(archive):
        return (
            f"docs/tags/{tag}/ not created — finalize must archive the tag's "
            "working docs there."
        )
    missing = [
        name for name in _TAG_ARCHIVE_FILES
        if not os.path.isfile(os.path.join(archive, name))
    ]
    if missing:
        return f"docs/tags/{tag}/ missing required files: {', '.join(missing)}"

    manifest_path = os.path.join(archive, "evidence", "manifest.json")
    if not os.path.isfile(manifest_path):
        return (
            f"docs/tags/{tag}/evidence/manifest.json not found — the archive was "
            f"never sealed; {_SEAL_HINT.format(tag=tag)}."
        )
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        return (
            f"docs/tags/{tag}/evidence/manifest.json is unreadable or not valid "
            f"JSON ({exc}) — {_SEAL_HINT.format(tag=tag)}."
        )
    if not isinstance(manifest, dict) or manifest.get("sealed") is not True:
        return (
            f'docs/tags/{tag}/evidence/manifest.json does not say `"sealed": true` '
            f"— the archive is a partial finalize; {_SEAL_HINT.format(tag=tag)}."
        )

    parent_index = os.path.join("docs", "tags", "README.md")
    if not os.path.isfile(parent_index):
        return (
            f"docs/tags/README.md not found — {tag} is sealed but the parent tag "
            f"index was never written; {_REINDEX_HINT}."
        )
    try:
        with open(parent_index, encoding="utf-8", errors="replace") as handle:
            parent_text = handle.read()
    except OSError as exc:
        return f"docs/tags/README.md is unreadable ({exc})."
    if f"({tag}/)" not in parent_text:
        return (
            f"docs/tags/README.md does not list {tag} — the parent index is stale; "
            f"{_REINDEX_HINT}."
        )
    return None


def _check_task_table_all_verified(path: str) -> str | None:
    if not os.path.isfile(path):
        return f"{path} not found"
    with open(path, encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    statuses = (
        ("pending", "pending"),
        ("in_progress", "in_progress"),
        ("completed", "completed (not yet verified)"),
    )
    leftovers = []
    for status, label in statuses:
        count = len(re.findall(rf"\|\s*{status}\s*\|", content, re.IGNORECASE))
        if count:
            leftovers.append(f"{count} {label}")
    if leftovers:
        return f"{path} has tasks not yet verified: {', '.join(leftovers)}"
    return None


PROGRAMMATIC_CHECKS = {
    "plan_all_verified": check_plan_all_verified,
    "evaluation_playable_unit": check_evaluation_playable_unit,
    "gap_archived_unless_handoff": check_gap_archived,
    "tag_archived": check_tag_archived,
}


def get_completion_failure(event: dict[str, object]) -> dict | None:
    """Return a structured failure for ``event`` without writing any state."""
    role = str(event.get("role") or "")
    schemas = load_stage_schemas()
    if schemas is None:
        issues = [".godotmaker/stage_schemas.json is missing or invalid"]
    else:
        role_schema = schemas.get(role, {})
        issues = validate_schema_files(role_schema)
        for check_name in role_schema.get("checks", []):
            check_fn = PROGRAMMATIC_CHECKS.get(check_name)
            if check_fn:
                result = check_fn(event)
                if result:
                    issues.append(result)

    if role in WORKER_DISPATCH_ROLES:
        try:
            current_events = read_current_events()
        except ValueError as exc:
            issues.append(
                ".godotmaker/metrics_current.jsonl is not valid JSONL "
                f"({exc})"
            )
        else:
            diligence = get_diligence_failure(role, current_events)
            if diligence:
                issues.extend(diligence["issues"])

    if not issues:
        return None
    return {
        "decision": "block",
        "role": role,
        "issues": issues,
        "reason": (
            f"Cannot mark role '{role}' as complete — validation failed:\n"
            + "\n".join(f"  - {issue}" for issue in issues)
        ),
    }
