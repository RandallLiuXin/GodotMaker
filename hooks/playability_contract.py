"""Playable Unit evaluation contract checks.

The evaluator owns runtime E2E coverage. This module only validates that the
structured evaluation artifact proves coverage for every Playable Unit row in
PLAN.md before the evaluate role can complete.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


PLAYABLE_UNIT_HEADING_RE = re.compile(r"^##\s+Playable Unit\s*$", re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^##\s+", re.MULTILINE)
UNIT_OUTCOME_RE = re.compile(r"^-\s+\*\*Unit outcome:\*\*\s*(.+?)\s*$", re.MULTILINE)
MECHANIC_ID_RE = re.compile(r"^v\d+\.\d+\.\d+-M\d+$")


@dataclass(frozen=True)
class PlayableUnitRow:
    key: str
    expected_effect: str
    visible_content: str


def check_evaluation_playable_unit_complete(
    plan_path: str = "PLAN.md",
    evaluation_path: str = os.path.join(".godotmaker", "evaluation.json"),
) -> list[str]:
    """Return validation issues. Empty list means the contract is satisfied."""
    issues: list[str] = []

    try:
        plan_text = _read_text(plan_path)
    except OSError:
        return [f"{plan_path} not found"]

    rows, row_issues = _parse_playable_unit_table(plan_text)
    issues.extend(row_issues)
    if not rows:
        issues.append("PLAN.md Playable Unit table has no rows to evaluate")

    unit_outcome = parse_unit_outcome(plan_text)

    try:
        evaluation = _read_json(evaluation_path)
    except OSError:
        return issues + [f"{evaluation_path} not found"]
    except (json.JSONDecodeError, ValueError) as exc:
        return issues + [f"{evaluation_path} is not valid JSON: {exc}"]

    if not isinstance(evaluation, dict):
        return issues + [f"{evaluation_path} must contain a JSON object"]

    result = evaluation.get("result")
    if result not in {"approve", "reject"}:
        issues.append('evaluation.json field "result" must be "approve" or "reject"')

    closed_loop = evaluation.get("playable_closed_loop")
    if not isinstance(closed_loop, dict):
        issues.append('evaluation.json field "playable_closed_loop" must be an object')
        closed_loop = {}

    playable_unit = evaluation.get("playable_unit")
    if not isinstance(playable_unit, dict):
        issues.append('evaluation.json field "playable_unit" must be an object')
        playable_unit = {}

    row_results = playable_unit.get("rows")
    if not isinstance(row_results, dict):
        issues.append('evaluation.json field "playable_unit.rows" must be an object')
        row_results = {}

    row_failure_seen = False
    for row in rows:
        row_value = _get_row_result(row_results, row)
        if row_value is None:
            issues.append(
                f"Playable Unit row {row.key} missing from evaluation.json playable_unit.rows"
            )
            continue
        if not isinstance(row_value, dict):
            issues.append(f"Playable Unit row {row.key} result must be an object")
            continue

        row_result = row_value.get("result")
        if row_result not in {"pass", "fail"}:
            issues.append(f"Playable Unit row {row.key} result must be pass or fail")
        elif row_result == "fail":
            row_failure_seen = True

        test_path = row_value.get("test")
        if not isinstance(test_path, str) or not test_path.strip():
            issues.append(f"Playable Unit row {row.key} must record a test path")
        elif not os.path.isfile(test_path):
            issues.append(f"Playable Unit row {row.key} test file not found: {test_path}")

        evidence = row_value.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            issues.append(f"Playable Unit row {row.key} must record non-empty evidence")

    if result == "approve":
        if closed_loop.get("playable_unit_coverage") is not True:
            issues.append(
                "approve requires playable_closed_loop.playable_unit_coverage == true"
            )
        if unit_outcome and closed_loop.get("completion_fail_or_exit_reached") is not True:
            issues.append(
                "approve requires playable_closed_loop.completion_fail_or_exit_reached == true"
            )
        for row in rows:
            row_value = _get_row_result(row_results, row)
            if isinstance(row_value, dict) and row_value.get("result") != "pass":
                issues.append(f"approve requires Playable Unit row {row.key} to pass")

    if result == "reject":
        critical = evaluation.get("critical_issues")
        has_critical = isinstance(critical, list) and bool(critical)
        if not row_failure_seen and not has_critical:
            issues.append(
                "reject requires at least one failed Playable Unit row or critical issue"
            )

    return issues


def parse_playable_unit_rows(plan_text: str) -> list[PlayableUnitRow]:
    rows, _ = _parse_playable_unit_table(plan_text)
    return rows


def _parse_playable_unit_table(plan_text: str) -> tuple[list[PlayableUnitRow], list[str]]:
    section = _extract_playable_unit_section(plan_text)
    if not section:
        return [], []

    lines = [line.strip() for line in section.splitlines()]
    rows: list[PlayableUnitRow] = []
    issues: list[str] = []
    in_table = False
    for line in lines:
        if not line.startswith("|") or not line.endswith("|"):
            if in_table:
                break
            continue
        cells = _split_markdown_row(line)
        if len(cells) < 5:
            continue
        if _is_separator_row(cells):
            in_table = True
            continue
        if cells[0].lower() == "mechanic":
            in_table = True
            continue
        if not in_table:
            continue

        raw_key = cells[0].strip()
        key = normalize_row_key(raw_key)
        if not key:
            issues.append(
                f"Playable Unit table row must use a mechanic id in the Mechanic column: {raw_key}"
            )
            continue
        rows.append(
            PlayableUnitRow(
                key=key,
                expected_effect=cells[2].strip(),
                visible_content=cells[3].strip(),
            )
        )
    return rows, issues


def parse_unit_outcome(plan_text: str) -> str:
    section = _extract_playable_unit_section(plan_text)
    if not section:
        return ""
    match = UNIT_OUTCOME_RE.search(section)
    if not match:
        return ""
    value = match.group(1).strip()
    lowered = value.lower()
    if lowered in {"n/a", "none", "deferred", "not applicable"}:
        return ""
    if value.startswith("{") and value.endswith("}"):
        return ""
    return value


def normalize_row_key(value: str) -> str:
    value = value.strip()
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    value = value.strip()
    return value if MECHANIC_ID_RE.fullmatch(value) else ""


def _extract_playable_unit_section(plan_text: str) -> str:
    match = PLAYABLE_UNIT_HEADING_RE.search(plan_text)
    if not match:
        return ""
    start = match.end()
    next_match = NEXT_HEADING_RE.search(plan_text, start)
    end = next_match.start() if next_match else len(plan_text)
    return plan_text[start:end]


def _split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _get_row_result(row_results: dict[str, Any], row: PlayableUnitRow) -> Any:
    return row_results.get(row.key)


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
