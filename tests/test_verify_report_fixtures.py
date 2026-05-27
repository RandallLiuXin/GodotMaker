"""Schema-level fixtures for `.godotmaker/verify_report.json`.

These tests do NOT run any pipeline. They are hand-written golden fixtures
that pin the protocol shape documented in:

- `skills/core/gm-verify/SKILL.md` Output Format Section B (the schema)
- `skills/core/gm-build/SKILL.md` Step 0 (consumer rules)
- `skills/core/gm-fixgap/SKILL.md` Step 1b (consumer rules)

Why fixtures + a tiny hand-rolled validator instead of a full JSON Schema:

- The actual producer and consumers are LLMs reading SKILL.md prose. The
  Python side only sees this file go past during stage-completion gating.
- Pinning the *shape* lets us fail noisily when SKILL.md documentation
  drifts from what the consumers actually need (e.g. a future PR removing
  the `narrowed_command` operand without updating the fallback table).
- Pinning the *invariants* (required-operand rule, escalate degrade)
  catches accidental schema regressions in the same commit.

When the schema legitimately evolves, update both the SKILL.md and the
constants/fixtures here in the same commit.
"""
import json

import pytest


# ---------------------------------------------------------------------------
# Constants — mirror skills/core/gm-verify/SKILL.md Field rules
# ---------------------------------------------------------------------------

REQUIRED_TOP = {"result", "ts", "checks", "tooling_notes"}
TOP_RESULT_VALUES = {"pass", "fail"}
PER_CHECK_RESULT_VALUES = {"pass", "warn", "fail", "error"}
REQUIRED_CHECKS = {"build", "unit_tests", "lint", "static_check"}

# `warn` is reserved for non-blocking checks: lint style noise and gdUnit
# warnings such as orphan-node reports when every assertion passed.
WARN_ALLOWED_CHECKS = {"lint", "unit_tests"}

# Producer rule: each non-escalate suggested_fallback REQUIRES the named
# operand to be present and non-empty. Mirrors the table in
# gm-verify/SKILL.md → suggested_fallback.
SHIPPED_FALLBACKS = {
    "exclude_file": "crashed_on",       # crashed_on is already top-required for every note
    "scope_narrow": "narrowed_command",
    "add_gdlintrc_rule": "rule_name",
    "skip_check": "check_name",
    "escalate": None,                   # no operand required
}

# Sentinel: distinguishes "key absent" from "key present with value None".
_MISSING = object()

REQUIRED_NOTE_FIELDS = ("tool", "crashed_on", "error", "suggested_fallback")

# Per-check required arrays. Mirrors gm-verify SKILL.md "All array fields are
# required, possibly empty (`[]`). Do not omit them." Consumers iterate these
# without presence checks, so missing arrays are a hard producer-rule break.
REQUIRED_CHECK_ARRAYS = {
    "build": ("errors",),
    "unit_tests": ("failures",),
    "lint": ("issues",),
    "static_check": ("issues",),
}

# unit_tests carries integer counters in addition to its arrays.
UNIT_TESTS_INT_FIELDS = ("passed", "failed")


# ---------------------------------------------------------------------------
# Validator — minimal, hand-rolled, intentionally not a full JSON Schema
# ---------------------------------------------------------------------------

def validate_report(report: dict) -> list[str]:
    """Return a list of issues. Empty list = report is schema-valid.

    Validates the contract the consumers actually depend on, not every
    detail. We deliberately don't enforce things like ts format — the
    consumer's freshness check works on string compare.
    """
    issues: list[str] = []

    missing_top = REQUIRED_TOP - set(report)
    if missing_top:
        issues.append(f"missing top-level keys: {sorted(missing_top)}")
        return issues  # downstream checks would just cascade

    if report["result"] not in TOP_RESULT_VALUES:
        issues.append(
            f"top-level result must be in {sorted(TOP_RESULT_VALUES)}, "
            f"got {report['result']!r}"
        )

    checks = report.get("checks", {})
    if not isinstance(checks, dict):
        issues.append("checks must be an object")
        return issues
    missing_checks = REQUIRED_CHECKS - set(checks)
    if missing_checks:
        issues.append(f"missing checks: {sorted(missing_checks)}")

    for name, body in checks.items():
        if name not in REQUIRED_CHECKS:
            continue
        r = body.get("result")
        if r not in PER_CHECK_RESULT_VALUES:
            issues.append(
                f"checks.{name}.result must be in {sorted(PER_CHECK_RESULT_VALUES)}, "
                f"got {r!r}"
            )
        if r == "warn" and name not in WARN_ALLOWED_CHECKS:
            issues.append(
                f"checks.{name}.result == 'warn' but warn is only allowed for "
                f"{sorted(WARN_ALLOWED_CHECKS)}"
            )
        # Required per-check arrays (must exist, may be empty).
        for arr in REQUIRED_CHECK_ARRAYS.get(name, ()):
            value = body.get(arr, _MISSING)
            if value is _MISSING:
                issues.append(f"checks.{name}.{arr} is required (may be empty list)")
            elif not isinstance(value, list):
                issues.append(f"checks.{name}.{arr} must be a list, got {type(value).__name__}")
        # unit_tests carries int counters that consumers read without guards.
        if name == "unit_tests":
            for f in UNIT_TESTS_INT_FIELDS:
                v = body.get(f, _MISSING)
                if v is _MISSING:
                    issues.append(f"checks.unit_tests.{f} is required (int)")
                elif not isinstance(v, int) or isinstance(v, bool):
                    issues.append(f"checks.unit_tests.{f} must be int, got {type(v).__name__}")

    notes = report.get("tooling_notes", [])
    if not isinstance(notes, list):
        issues.append("tooling_notes must be an array")
        return issues

    # Producer invariant: result == "pass" forbids non-empty tooling_notes.
    # A note pairs with a checks.<name>.result == "error", which by definition
    # forces top-level result: "fail". The two cannot coexist with PASS.
    if report.get("result") == "pass" and notes:
        issues.append(
            "result=='pass' requires tooling_notes==[]; a non-empty array implies "
            "at least one checks.*.result=='error', which forces result=='fail'"
        )

    for i, note in enumerate(notes):
        if not isinstance(note, dict):
            issues.append(f"tooling_notes[{i}] must be an object")
            continue
        for field in REQUIRED_NOTE_FIELDS:
            if not note.get(field):
                issues.append(f"tooling_notes[{i}] missing required field {field!r}")
        fb = note.get("suggested_fallback")
        if fb in SHIPPED_FALLBACKS:
            operand_field = SHIPPED_FALLBACKS[fb]
            if operand_field is not None and not note.get(operand_field):
                # Producer rule violation: must emit "escalate" instead.
                issues.append(
                    f"tooling_notes[{i}] suggested_fallback={fb!r} requires "
                    f"non-empty {operand_field!r}; producer should emit "
                    f"'escalate' when it cannot fill the operand"
                )

    return issues


# ---------------------------------------------------------------------------
# Fixture builders — golden samples. Used by tests AND importable from
# tests/test_pipeline_e2e.py-style harnesses if needed.
# ---------------------------------------------------------------------------

def report_pass() -> dict:
    """All-pass report. Used by stage-completion-gate fixtures."""
    return {
        "result": "pass",
        "ts": "2026-05-07T14:23:00Z",
        "checks": {
            "build": {"result": "pass", "errors": []},
            "unit_tests": {"result": "pass", "passed": 0, "failed": 0, "failures": []},
            "lint": {"result": "pass", "issues": [], "format_drift": None},
            "static_check": {"result": "pass", "issues": []},
        },
        "tooling_notes": [],
    }


def report_fail_compile_errors() -> dict:
    """build.result == fail with concrete errors[]. Triggers consumer's
    project-code task path."""
    r = report_pass()
    r["result"] = "fail"
    r["checks"]["build"] = {
        "result": "fail",
        "errors": [{"file": "src/foo.gd", "line": 42, "message": "Identifier 'bar' not declared"}],
    }
    return r


def report_fail_with_routable_fallback() -> dict:
    """lint.result == error + tooling_note with add_gdlintrc_rule + rule_name.
    Triggers consumer's auto-fix branch."""
    r = report_pass()
    r["result"] = "fail"
    r["checks"]["lint"] = {"result": "error", "issues": [], "format_drift": None}
    r["tooling_notes"] = [{
        "tool": "gdlint",
        "crashed_on": "src/foo.gd",
        "error": "NotImplementedError at gdtoolkit/linter/class_checks.py:144",
        "suggested_fallback": "add_gdlintrc_rule",
        "narrowed_command": None,
        "rule_name": "class-name",
        "check_name": None,
    }]
    return r


def report_fail_with_escalate() -> dict:
    """build.result == error + tooling_note with escalate. Triggers
    consumer's halt-and-surface branch (non-lint tool crash)."""
    r = report_pass()
    r["result"] = "fail"
    r["checks"]["build"] = {"result": "error", "errors": []}
    r["tooling_notes"] = [{
        "tool": "godot",
        "crashed_on": "<headless-run>",
        "error": "Segmentation fault loading scene main.tscn",
        "suggested_fallback": "escalate",
        "narrowed_command": None,
        "rule_name": None,
        "check_name": None,
    }]
    return r


# ---------------------------------------------------------------------------
# Tests — assert the validator agrees with SKILL.md documentation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("builder", [
    report_pass,
    report_fail_compile_errors,
    report_fail_with_routable_fallback,
    report_fail_with_escalate,
])
def test_fixture_is_schema_valid(builder):
    """All shipped fixtures must pass the in-tree validator."""
    report = builder()
    issues = validate_report(report)
    assert issues == [], f"{builder.__name__} produced invalid report: {issues}"


def test_fixture_round_trips_through_json():
    """Every fixture must round-trip through json.dumps/loads — no NaN,
    no datetime, no custom types. Producer/consumer use json only."""
    for builder in (report_pass, report_fail_compile_errors,
                    report_fail_with_routable_fallback,
                    report_fail_with_escalate):
        before = builder()
        after = json.loads(json.dumps(before))
        assert before == after, f"{builder.__name__} did not round-trip"


def test_routable_fallback_without_operand_is_invalid():
    """Producer rule: emitting `add_gdlintrc_rule` without a non-empty
    `rule_name` is a schema violation. The producer must emit `escalate`
    instead. This pins the SKILL.md producer-rule contract."""
    r = report_pass()
    r["result"] = "fail"
    r["checks"]["lint"] = {"result": "error", "issues": [], "format_drift": None}
    r["tooling_notes"] = [{
        "tool": "gdlint",
        "crashed_on": "src/foo.gd",
        "error": "...",
        "suggested_fallback": "add_gdlintrc_rule",
        "narrowed_command": None,
        "rule_name": None,
        "check_name": None,
    }]
    issues = validate_report(r)
    assert any("rule_name" in i and "escalate" in i for i in issues), (
        f"validator must reject add_gdlintrc_rule with empty rule_name: {issues}"
    )


def test_each_routable_fallback_requires_its_operand():
    """All four routable fallbacks share the same producer-rule shape —
    one parametrised test pins them together so a future regression can't
    silently relax one of them."""
    cases = [
        ("scope_narrow", "narrowed_command"),
        ("add_gdlintrc_rule", "rule_name"),
        ("skip_check", "check_name"),
    ]
    for fallback, operand in cases:
        r = report_pass()
        r["result"] = "fail"
        r["checks"]["lint"] = {"result": "error", "issues": [], "format_drift": None}
        r["tooling_notes"] = [{
            "tool": "gdlint",
            "crashed_on": "x",
            "error": "...",
            "suggested_fallback": fallback,
            "narrowed_command": None,
            "rule_name": None,
            "check_name": None,
        }]
        issues = validate_report(r)
        assert any(operand in i for i in issues), (
            f"{fallback} should require non-empty {operand!r}: {issues}"
        )


def test_escalate_does_not_require_any_operand():
    """`escalate` is the catch-all that intentionally needs no operand —
    the consumer halts and surfaces tool/error/crashed_on to the user."""
    r = report_fail_with_escalate()
    assert validate_report(r) == []


def test_warn_outside_allowed_checks_is_invalid():
    """`warn` is allowed only for checks with non-blocking warning semantics."""
    r = report_pass()
    r["checks"]["build"]["result"] = "warn"
    issues = validate_report(r)
    assert any("warn" in i and "build" in i for i in issues), issues


def test_unit_tests_warn_is_valid():
    r = report_pass()
    r["checks"]["unit_tests"]["result"] = "warn"
    r["checks"]["unit_tests"]["warnings"] = ["Found 4 possible orphan nodes."]
    assert validate_report(r) == []


def test_missing_top_level_key_is_caught():
    r = report_pass()
    del r["tooling_notes"]
    issues = validate_report(r)
    assert any("tooling_notes" in i for i in issues), issues


def test_pass_with_non_empty_tooling_notes_is_invalid():
    """Producer invariant: result=='pass' MUST have tooling_notes==[]. A non-
    empty array implies at least one check.result=='error', which forces
    result=='fail'. This pins the SKILL.md "When Done" rule."""
    r = report_pass()
    r["tooling_notes"] = [{
        "tool": "gdlint",
        "crashed_on": "x.gd",
        "error": "...",
        "suggested_fallback": "escalate",
        "narrowed_command": None,
        "rule_name": None,
        "check_name": None,
    }]
    issues = validate_report(r)
    assert any("pass" in i and "tooling_notes" in i for i in issues), (
        f"validator must reject pass with non-empty tooling_notes: {issues}"
    )


@pytest.mark.parametrize("check_name,arr_field", [
    ("build", "errors"),
    ("unit_tests", "failures"),
    ("lint", "issues"),
    ("static_check", "issues"),
])
def test_per_check_array_is_required(check_name, arr_field):
    """SKILL.md says all array fields are required (possibly empty).
    Consumers iterate them without presence checks, so a producer dropping
    one is a hard contract break."""
    r = report_pass()
    del r["checks"][check_name][arr_field]
    issues = validate_report(r)
    assert any(check_name in i and arr_field in i for i in issues), (
        f"validator must reject missing checks.{check_name}.{arr_field}: {issues}"
    )


@pytest.mark.parametrize("field", ["passed", "failed"])
def test_unit_tests_int_counters_are_required(field):
    """unit_tests carries `passed` and `failed` int counters that consumers
    read directly. Missing → schema break. Wrong type (e.g. str) → same."""
    r = report_pass()
    del r["checks"]["unit_tests"][field]
    issues = validate_report(r)
    assert any("unit_tests" in i and field in i for i in issues), (
        f"validator must reject missing unit_tests.{field}: {issues}"
    )

    r2 = report_pass()
    r2["checks"]["unit_tests"][field] = "0"  # wrong type
    issues2 = validate_report(r2)
    assert any("unit_tests" in i and field in i and "int" in i for i in issues2), (
        f"validator must reject string unit_tests.{field}: {issues2}"
    )


def test_per_check_array_must_be_list_not_other_type():
    """An array field that exists but is not actually a list (e.g. dict, str)
    should fail — consumers iterate it expecting list semantics."""
    r = report_pass()
    r["checks"]["build"]["errors"] = "not a list"
    issues = validate_report(r)
    assert any("errors" in i and "list" in i for i in issues), issues
