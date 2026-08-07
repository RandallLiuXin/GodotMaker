#!/usr/bin/env python3
"""Mechanical /gm-verify runner.

Executes the four checks documented in
`skills/core/gm-verify/SKILL.md` "Verification Checklist" and emits a
JSON document matching the verify_report.json schema documented in the
same SKILL's "Output Format" Section B. The /gm-verify SKILL agent
reads this document, sanity-checks it, and writes the final
`.godotmaker/verify_report.json` plus the human-readable chat summary.

Why a script: verify is non-creative, checklist-driven. Driving four
bash invocations one-by-one through an agent costs $0.45-$1.71 and
1-2 minutes per run (per 2026-05-12 AAR). Bundling them lets the agent
keep its judgement role (escalation, future check additions) while
shedding the per-call LLM friction.

Usage:
    python tools/run_verify.py [--project-path <path>]

Output (stdout):
    JSON matching skills/core/gm-verify/SKILL.md Output Format Section B
    (verify_report.json shape). Per-check pass/fail is encoded in the
    JSON, not in the exit code.

Exit codes:
    0   ran to completion
    1   runtime failure (project state malformed, OS error, JSON encoding
        failure, etc.)
    2   bad CLI usage
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from agent_runtime import (
    godot_log_file,
    godotmaker_yaml,
    prefer_console_godot_path,
    read_godot_path,
)
from godot_output import classify_godot_headless_output

try:
    from verification_backend import BackendSelectionError, select_verification_backend
except ImportError:  # Backward-compatible fallback for older published tools.
    class BackendSelectionError(ValueError):
        """Fallback exception for older published tools without backend selection."""

    def select_verification_backend(project_dir: Path) -> dict[str, str]:
        return {"backend": "gdscript"}


# Same scope as gm-verify's static check, minus --build: build is owned by
# check_build(), including backend-specific C#/.NET compilation.
STATIC_CHECK_FLAGS = ["--git", "--ecs", "--tests", "--plan", "--mcp"]
CSHARP_STATIC_CHECK_FLAGS = ["--git", "--plan", "--mcp"]
CSHARP_STATIC_SKIPS = [
    {"check": "gdscript_gecs", "reason": "not applicable to C#/.NET verification backend"},
    {"check": "gdunit_discovery", "reason": "unit tests handled by dotnet test"},
]

# Per-check timeout (seconds). headless `godot --quit` is normally <10s
# but allow 60s for cold-start + project import. gdUnit4 can take
# minutes on big test suites; bound at 600s.
BUILD_TIMEOUT = 60
UNIT_TIMEOUT = 600
STATIC_TIMEOUT = 60


def _resolve_project_path(arg: str | None) -> Path:
    return Path(arg).resolve() if arg else Path.cwd()


def _now_iso_utc() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tooling_note(tool: str, crashed_on: str, error: str,
                  fallback: str = "escalate") -> dict:
    """Build a tooling_notes entry. We always emit `escalate` here —    this script is the producer and per gm-verify producer rule, when
    we can't fill a routable fallback's operand we MUST emit escalate.
    Routable fallbacks (exclude_file / scope_narrow / add_gdlintrc_rule
    / skip_check) are reserved for cases with a clear remediation; a
    script crash doesn't qualify.
    """
    return {
        "tool": tool,
        "crashed_on": crashed_on,
        "error": error,
        "suggested_fallback": fallback,
        "narrowed_command": None,
        "rule_name": None,
        "check_name": None,
    }


def _backend_value(backend: Any, name: str, default: Any = None) -> Any:
    if backend is None:
        return default
    if isinstance(backend, dict):
        return backend.get(name, default)
    return getattr(backend, name, default)


def _backend_name(backend: Any) -> str:
    raw = (
        _backend_value(backend, "language_backend")
        or _backend_value(backend, "backend")
        or _backend_value(backend, "name")
        or _backend_value(backend, "kind")
        or _backend_value(backend, "language")
        or "gdscript"
    )
    normalized = str(raw).strip().lower()
    if normalized in {"c#", "cs", "csharp", "dotnet", ".net"}:
        return "csharp"
    return normalized or "gdscript"


def _backend_unit_name(backend: Any) -> str:
    raw = (
        _backend_value(backend, "unit_test_backend")
        or _backend_value(backend, "unit_tests")
        or _backend_value(backend, "test_backend")
    )
    if raw is None:
        return "dotnet" if _backend_name(backend) == "csharp" else "gdunit"
    normalized = str(raw).strip().lower()
    if normalized in {"c#", "cs", "csharp", "dotnet", ".net"}:
        return "dotnet"
    return normalized or "gdunit"


def _backend_report_path(backend: Any, name: str) -> str | None:
    value = _backend_value(backend, name)
    if value is None:
        return None
    return str(value).replace("\\", "/")


def _backend_report(backend: Any) -> dict[str, Any]:
    return {
        "language": _backend_name(backend),
        "unit_tests": _backend_unit_name(backend),
        "selection": str(_backend_value(backend, "source", "legacy")),
        "dotnet_target": _backend_report_path(backend, "dotnet_target"),
        "godot_csharp_project": _backend_report_path(backend, "godot_csharp_project"),
    }


def _is_csharp_backend(backend: Any) -> bool:
    return _backend_name(backend) == "csharp"


def _backend_path(project_dir: Path, backend: Any, name: str) -> Path | None:
    value = _backend_value(backend, name)
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else project_dir / path


def _empty_dotnet_result(result: str = "error") -> dict:
    return {
        "result": result,
        "framework": "dotnet",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "failures": [],
    }

# ---------------------------------------------------------------------------
# 1. Build
# ---------------------------------------------------------------------------

def _run_godot_headless_build(godot_path: str, project_dir: Path) -> tuple[dict, dict | None]:
    log_file = godot_log_file(project_dir, "build")
    try:
        proc = subprocess.run(
            [godot_path, "--headless", "--path", str(project_dir),
             "--log-file", log_file, "--quit"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=BUILD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return (
            {"result": "error", "errors": []},
            _tooling_note(
                tool="godot",
                crashed_on="<headless-run>",
                error=f"godot --headless --quit timed out after {BUILD_TIMEOUT}s",
            ),
        )
    except FileNotFoundError as ex:
        return (
            {"result": "error", "errors": []},
            _tooling_note(
                tool="godot",
                crashed_on=godot_path,
                error=(
                    f"godot binary not found: {ex}. Set godot_path in "
                    f"{godotmaker_yaml(project_dir)} or ensure godot is on PATH."
                ),
            ),
        )

    combined = (proc.stdout or "") + (proc.stderr or "")
    classified = classify_godot_headless_output(
        combined,
        returncode=proc.returncode,
    )
    errors = [
        {"file": item.file, "line": item.line, "message": item.message}
        for item in classified.blockers
    ]

    result = "fail" if errors else "pass"
    return ({"result": result, "errors": errors}, None)


def _dotnet_build(target: Path) -> tuple[dict | None, dict | None]:
    try:
        proc = subprocess.run(
            ["dotnet", "build", str(target)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=BUILD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return (
            {"result": "error", "errors": []},
            _tooling_note(
                tool="dotnet",
                crashed_on=str(target),
                error=f"dotnet build timed out after {BUILD_TIMEOUT}s",
            ),
        )
    except FileNotFoundError as ex:
        return (
            {"result": "error", "errors": []},
            _tooling_note(
                tool="dotnet",
                crashed_on="dotnet",
                error=f"dotnet executable not found: {ex}",
            ),
        )

    if proc.returncode == 0:
        return None, None

    combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return (
        {
            "result": "fail",
            "errors": [{
                "file": str(target.name),
                "line": 0,
                "message": combined or f"dotnet build exited with code {proc.returncode}",
            }],
        },
        None,
    )


def _solution_mentions_project(solution: Path, project: Path) -> bool:
    if solution.resolve() == project.resolve():
        return True
    if solution.suffix.lower() != ".sln" or not solution.exists():
        return False
    try:
        text = solution.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    rel = os.path.relpath(project, solution.parent).replace("/", "\\")
    return project.name in text or rel in text or rel.replace("\\", "/") in text


def _check_godot_dotnet_runtime(
    godot_path: str,
) -> tuple[dict | None, dict | None]:
    """Require the configured Godot executable to be the Mono/.NET build."""
    try:
        proc = subprocess.run(
            [godot_path, "--version"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15,
        )
    except FileNotFoundError as ex:
        return (
            {"result": "error", "errors": []},
            _tooling_note(
                tool="godot",
                crashed_on=godot_path,
                error=f"godot executable not found: {ex}",
            ),
        )
    except subprocess.TimeoutExpired:
        return (
            {"result": "error", "errors": []},
            _tooling_note(
                tool="godot",
                crashed_on=godot_path,
                error="godot --version timed out after 15s",
            ),
        )

    combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
    version = combined.splitlines()[-1] if combined else "(no version output)"
    if proc.returncode != 0:
        return (
            {
                "result": "fail",
                "errors": [{
                    "file": Path(godot_path).name,
                    "line": 0,
                    "message": f"could not query Godot Mono/.NET version: {version}",
                }],
            },
            None,
        )
    if "mono" not in combined.lower():
        return (
            {
                "result": "fail",
                "errors": [{
                    "file": Path(godot_path).name,
                    "line": 0,
                    "message": (
                        "C# verification requires Godot Mono/.NET; "
                        f"configured executable reports {version}"
                    ),
                }],
            },
            None,
        )
    return None, None


def check_build(godot_path: str, project_dir: Path,
                backend: Any | None = None) -> tuple[dict, dict | None]:
    """Run backend-specific compile checks, then Godot headless parse."""
    if _is_csharp_backend(backend):
        dotnet_target = _backend_path(project_dir, backend, "dotnet_target")
        godot_project = _backend_path(project_dir, backend, "godot_csharp_project")
        if not dotnet_target:
            return (
                {"result": "error", "errors": []},
                _tooling_note(
                    tool="dotnet",
                    crashed_on="dotnet_target",
                    error="C# verification backend selected but dotnet_target is missing",
                ),
            )

        build_result, note = _dotnet_build(dotnet_target)
        if build_result is not None:
            return build_result, note
        if godot_project and not _solution_mentions_project(dotnet_target, godot_project):
            build_result, note = _dotnet_build(godot_project)
            if build_result is not None:
                return build_result, note

        runtime_result, note = _check_godot_dotnet_runtime(godot_path)
        if runtime_result is not None:
            return runtime_result, note

    return _run_godot_headless_build(godot_path, project_dir)

# ---------------------------------------------------------------------------
# 2. Unit Tests
# ---------------------------------------------------------------------------

# gdUnit4 CmdTool prints a summary line we can pin against. Two shapes
# observed across stream logs:
#   "267 test cases | 0 errors | 0 failures (31 suites, exit 0)"
#   "Tests Passed: 274 | Tests Failed: 0"
_GDUNIT_SUMMARY_CASES = re.compile(
    r"(\d+)\s+test\s*cases?\s*\|\s*(\d+)\s+errors?\s*\|\s*(\d+)\s+failures?",
    re.IGNORECASE,
)
_GDUNIT_OVERALL_SUMMARY_CASES = re.compile(
    r"Overall\s+Summary:.*?"
    r"(\d+)\s+test\s*cases?\s*\|\s*(\d+)\s+errors?\s*\|\s*(\d+)\s+failures?",
    re.IGNORECASE | re.DOTALL,
)
_GDUNIT_SUMMARY_PF = re.compile(
    r"Tests?\s+Passed:\s*(\d+).*?Tests?\s+Failed:\s*(\d+)",
    re.IGNORECASE | re.DOTALL,
)
# Per-failure lines. gdUnit4 prints "FAILED: <test_id> - <message>",
# where <test_id> may contain `::` (suite::test). Lazy-match the id and
# require a space-dash-space separator so the `::` does not split.
_GDUNIT_FAILURE = re.compile(
    r"^\s*FAILED:\s*(.+?)\s+-\s+(.+)$",
    re.MULTILINE,
)
_GDUNIT_ORPHAN_WARNING = re.compile(
    r"Found\s+\d+\s+possible\s+orphan\s+nodes?\.?",
    re.IGNORECASE,
)
_TRX_FAIL_OUTCOMES = {"failed", "error", "timeout", "aborted"}
_TRX_SKIP_OUTCOMES = {
    "notexecuted", "notrunnable", "skipped", "inconclusive",
}


def _gdunit_warning_messages(combined: str, returncode: int) -> list[str]:
    warnings: list[str] = []
    for match in _GDUNIT_ORPHAN_WARNING.finditer(combined):
        warning = match.group(0).strip()
        if warning not in warnings:
            warnings.append(warning)
    if returncode == 101 and not warnings:
        warnings.append("gdUnit exited with warning code 101")
    return warnings


def _int_attr(element: ET.Element, name: str) -> int:
    try:
        return int(element.attrib.get(name, "0"))
    except ValueError:
        return 0


def _strip_xml_text(text: str | None) -> str:
    return " ".join((text or "").split())


def _failure_message(node: ET.Element) -> str:
    message = (node.attrib.get("message") or "").strip()
    detail = _strip_xml_text(node.text)
    if message and detail and detail not in message:
        return f"{message}: {detail}"
    return message or detail or node.tag


def _parse_gdunit_xml(results_xml: Path) -> dict:
    root = ET.parse(results_xml).getroot()
    total = _int_attr(root, "tests")
    failures = _int_attr(root, "failures")
    if "errors" in root.attrib:
        errors = _int_attr(root, "errors")
    else:
        errors = sum(
            _int_attr(suite, "errors")
            for suite in root
            if suite.tag == "testsuite"
        )
    skipped = _int_attr(root, "skipped")
    failed_count = failures + errors
    passed_count = max(total - failed_count - skipped, 0)

    failure_entries: list[dict] = []
    for case in root.iter():
        if case.tag != "testcase":
            continue
        test_name = case.attrib.get("name", "").strip()
        class_name = case.attrib.get("classname", "").strip()
        test_id = f"{class_name}::{test_name}" if class_name else test_name
        for child in list(case):
            if child.tag not in {"failure", "error"}:
                continue
            failure_entries.append({
                "test": test_id,
                "message": _failure_message(child),
            })

    if failed_count > 0 and not failure_entries:
        failure_entries.append({
            "test": "<gdunit>",
            "message": (
                f"gdUnit XML reported {failures} failures and {errors} errors "
                f"without testcase details"
            ),
        })

    return {
        "result": "fail" if failed_count > 0 else "pass",
        "passed": passed_count,
        "failed": failed_count,
        "failures": failure_entries,
    }


def _find_gdunit_results_xml(report_dir: Path) -> Path | None:
    matches = list(report_dir.rglob("results.xml"))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _parse_gdunit_stdout(combined: str, returncode: int) -> dict | None:
    m = _GDUNIT_OVERALL_SUMMARY_CASES.search(combined)
    if not m:
        matches = list(_GDUNIT_SUMMARY_CASES.finditer(combined))
        m = matches[-1] if matches else None

    if m:
        total = int(m.group(1))
        errs = int(m.group(2))
        fails = int(m.group(3))
        failed_count = errs + fails
        passed_count = max(total - failed_count, 0)
    else:
        m2 = _GDUNIT_SUMMARY_PF.search(combined)
        if not m2:
            return None
        passed_count = int(m2.group(1))
        failed_count = int(m2.group(2))

    failures: list[dict] = []
    for fm in _GDUNIT_FAILURE.finditer(combined):
        failures.append({
            "test": fm.group(1).strip(),
            "message": fm.group(2).strip(),
        })

    if returncode == 101 and failed_count == 0:
        return {
            "result": "warn",
            "passed": passed_count,
            "failed": 0,
            "failures": [],
            "warnings": _gdunit_warning_messages(combined, returncode),
        }

    if returncode != 0 and failed_count == 0:
        failed_count = 1
        failures.append({
            "test": "<gdunit>",
            "message": f"gdUnit exited with code {returncode}",
        })

    result = "fail" if failed_count > 0 else "pass"
    return {
        "result": result,
        "passed": passed_count,
        "failed": failed_count,
        "failures": failures,
    }


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if _xml_local_name(child.tag) == name:
            return child
    return None


def _find_trx_files(report_path: Path) -> list[Path]:
    return sorted(report_path.rglob("*.trx"))


def _parse_trx_files(trx_files: list[Path]) -> dict:
    total = passed = failed = skipped = 0
    failures: list[dict] = []
    for trx in trx_files:
        root = ET.parse(trx).getroot()
        counters = _find_child(root, "Counters")
        file_has_counters = counters is not None
        if file_has_counters:
            total += _int_attr(counters, "total")
            passed += _int_attr(counters, "passed")
            failed += (
                _int_attr(counters, "failed")
                + _int_attr(counters, "error")
                + _int_attr(counters, "timeout")
                + _int_attr(counters, "aborted")
            )
            skipped += (
                _int_attr(counters, "notExecuted")
                + _int_attr(counters, "notRunnable")
                + _int_attr(counters, "inconclusive")
            )
        for result in root.iter():
            if _xml_local_name(result.tag) != "UnitTestResult":
                continue
            outcome = result.attrib.get("outcome", "").strip().lower()
            test_name = result.attrib.get("testName", "").strip() or "<dotnet-test>"
            if not file_has_counters:
                total += 1
                if outcome == "passed":
                    passed += 1
                elif outcome in _TRX_FAIL_OUTCOMES:
                    failed += 1
                elif outcome in _TRX_SKIP_OUTCOMES:
                    skipped += 1
            if outcome in _TRX_FAIL_OUTCOMES:
                msg_node = _find_child(result, "Message")
                stack_node = _find_child(result, "StackTrace")
                message = _strip_xml_text(msg_node.text if msg_node is not None else "")
                stack = _strip_xml_text(stack_node.text if stack_node is not None else "")
                if stack and stack not in message:
                    message = f"{message}: {stack}" if message else stack
                failures.append({
                    "test": test_name,
                    "message": message or f"dotnet test outcome: {outcome}",
                })

    result = "fail" if failed else "pass"
    return {
        "result": result,
        "framework": "dotnet",
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failures": failures,
    }


def _check_dotnet_tests(project_dir: Path, backend: Any) -> tuple[dict, dict | None]:
    dotnet_target = _backend_path(project_dir, backend, "dotnet_target")
    if not dotnet_target:
        return (
            _empty_dotnet_result(),
            _tooling_note(
                tool="dotnet",
                crashed_on="dotnet_target",
                error="C# verification backend selected but dotnet_target is missing",
            ),
        )

    with tempfile.TemporaryDirectory(prefix="godotmaker-dotnet-") as report_dir:
        report_path = Path(report_dir)
        cmd = [
            "dotnet", "test", str(dotnet_target),
            "--no-build", "--no-restore",
            "--logger", "trx",
            "--results-directory", str(report_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=UNIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                _empty_dotnet_result(),
                _tooling_note(
                    tool="dotnet",
                    crashed_on=str(dotnet_target),
                    error=f"dotnet test timed out after {UNIT_TIMEOUT}s",
                ),
            )
        except FileNotFoundError as ex:
            return (
                _empty_dotnet_result(),
                _tooling_note(
                    tool="dotnet",
                    crashed_on="dotnet",
                    error=f"dotnet executable not found: {ex}",
                ),
            )

        trx_files = _find_trx_files(report_path)
        if not trx_files:
            return (
                _empty_dotnet_result(),
                _tooling_note(
                    tool="dotnet",
                    crashed_on=str(report_path),
                    error="dotnet test produced no TRX results",
                ),
            )
        try:
            parsed = _parse_trx_files(trx_files)
        except ET.ParseError as ex:
            return (
                _empty_dotnet_result(),
                _tooling_note(
                    tool="dotnet",
                    crashed_on=str(trx_files[0]),
                    error=f"could not parse dotnet TRX report: {ex}",
                ),
            )
        if parsed["total"] == 0:
            return (
                parsed | {"result": "error"},
                _tooling_note(
                    tool="dotnet",
                    crashed_on=str(report_path),
                    error="dotnet test reported zero tests",
                ),
            )
        if proc.returncode != 0 and parsed["result"] == "pass":
            return (
                parsed | {"result": "error"},
                _tooling_note(
                    tool="dotnet",
                    crashed_on=str(dotnet_target),
                    error=(
                        f"dotnet test exited with code {proc.returncode} "
                        "despite passing TRX results"
                    ),
                ),
            )
        return parsed, None


def _check_gdunit_tests(godot_path: str, project_dir: Path
                        ) -> tuple[dict, dict | None]:
    with tempfile.TemporaryDirectory(prefix="godotmaker-gdunit-") as report_dir:
        report_path = Path(report_dir)
        cmd = [
            godot_path, "--headless",
            "--path", str(project_dir),
            "--log-file", godot_log_file(project_dir, "gdunit"),
            "-s", "res://addons/gdUnit4/bin/GdUnitCmdTool.gd",
            "--ignoreHeadlessMode",
            "--add", "res://test/",
            "--report-directory", str(report_path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=UNIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                {"result": "error", "passed": 0, "failed": 0, "failures": []},
                _tooling_note(
                    tool="gdunit",
                    crashed_on="<headless-run>",
                    error=f"gdUnit4 timed out after {UNIT_TIMEOUT}s",
                ),
            )
        except FileNotFoundError as ex:
            return (
                {"result": "error", "passed": 0, "failed": 0, "failures": []},
                _tooling_note(
                    tool="gdunit",
                    crashed_on=godot_path,
                    error=f"godot binary not found: {ex}",
                ),
            )

        combined = (proc.stdout or "") + (proc.stderr or "")
        results_xml = _find_gdunit_results_xml(report_path)
        if results_xml:
            try:
                parsed_xml = _parse_gdunit_xml(results_xml)
            except ET.ParseError as ex:
                return (
                    {"result": "error", "passed": 0, "failed": 0, "failures": []},
                    _tooling_note(
                        tool="gdunit",
                        crashed_on=str(results_xml),
                        error=f"could not parse gdUnit4 XML report: {ex}",
                    ),
                )
            if proc.returncode != 0 and parsed_xml["result"] == "pass":
                if proc.returncode == 101:
                    parsed_xml["result"] = "warn"
                    parsed_xml["warnings"] = _gdunit_warning_messages(
                        combined,
                        proc.returncode,
                    )
                    return (parsed_xml, None)
                if proc.returncode == 100:
                    parsed_xml["result"] = "fail"
                    parsed_xml["failed"] = 1
                    parsed_xml["failures"] = [{
                        "test": "<gdunit>",
                        "message": (
                            "gdUnit exited with code 100 despite a passing "
                            "XML report"
                        ),
                    }]
                    return (parsed_xml, None)
                return (
                    {"result": "error", "passed": 0, "failed": 0, "failures": []},
                    _tooling_note(
                        tool="gdunit",
                        crashed_on=str(results_xml),
                        error=(
                            f"gdUnit exited with code {proc.returncode} "
                            "despite a passing XML report"
                        ),
                    ),
                )
            return (parsed_xml, None)

        parsed = _parse_gdunit_stdout(combined, proc.returncode)
        if parsed:
            return (parsed, None)

        if proc.returncode == 100:
            return (
                {
                    "result": "fail",
                    "passed": 0,
                    "failed": 1,
                    "failures": [{
                        "test": "<gdunit>",
                        "message": (
                            "gdUnit exited with code 100 but produced no "
                            "parseable XML or stdout summary"
                        ),
                    }],
                },
                None,
            )

        return (
            {"result": "error", "passed": 0, "failed": 0, "failures": []},
            _tooling_note(
                tool="gdunit",
                crashed_on="<headless-run>",
                error=(
                    "could not parse gdUnit4 XML report or summary line; "
                    "runner may have crashed or test/ may be empty"
                ),
            ),
        )

def check_unit_tests(godot_path: str, project_dir: Path,
                     backend: Any | None = None) -> tuple[dict, dict | None]:
    if _is_csharp_backend(backend):
        return _check_dotnet_tests(project_dir, backend)
    return _check_gdunit_tests(godot_path, project_dir)



# ---------------------------------------------------------------------------
# 3. Lint —gdtoolkit currently disabled (gm-verify SKILL Section 3)
# ---------------------------------------------------------------------------

def check_lint() -> dict:
    return {"result": "pass", "issues": [], "format_drift": None}


# ---------------------------------------------------------------------------
# 4. Static check (delegates to tools/check_project.py)
# ---------------------------------------------------------------------------

_STATIC_FAIL_LINE = re.compile(r"^\[FAIL\]\s+(.+)$", re.MULTILINE)
_STATIC_SKIP_LINE = re.compile(r"^\[SKIP\]\s+(.+)$", re.MULTILINE)
_STATIC_ERROR_LINE = re.compile(r"^\[ERROR\]\s+(.+)$", re.MULTILINE)


def _static_line_items(pattern: re.Pattern[str], combined: str,
                       default_name: str) -> list[dict]:
    items: list[dict] = []
    for m in pattern.finditer(combined):
        detail = m.group(1).strip()
        if ":" in detail:
            check_name, _, rest = detail.partition(":")
            items.append({"check": check_name.strip(), "detail": rest.strip()})
        else:
            items.append({"check": default_name, "detail": detail})
    return items


def check_static(project_dir: Path,
                 backend: Any | None = None) -> tuple[dict, dict | None]:
    check_project = Path(__file__).parent / "check_project.py"
    if not check_project.exists():
        return (
            {"result": "error", "issues": [], "skipped_checks": []},
            _tooling_note(
                tool="check_project",
                crashed_on=str(check_project),
                error="check_project.py not found alongside run_verify.py",
            ),
        )

    skipped_checks = list(CSHARP_STATIC_SKIPS) if _is_csharp_backend(backend) else []
    flags = CSHARP_STATIC_CHECK_FLAGS if _is_csharp_backend(backend) else STATIC_CHECK_FLAGS
    cmd = [sys.executable, str(check_project), str(project_dir)] + flags
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=STATIC_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return (
            {"result": "error", "issues": [], "skipped_checks": skipped_checks},
            _tooling_note(
                tool="check_project",
                crashed_on=str(project_dir),
                error=f"check_project.py timed out after {STATIC_TIMEOUT}s",
            ),
        )

    combined = (proc.stdout or "") + (proc.stderr or "")
    issues = _static_line_items(_STATIC_FAIL_LINE, combined, "static_check")
    skipped_checks.extend(_static_line_items(_STATIC_SKIP_LINE, combined, "static_check"))
    errors = _static_line_items(_STATIC_ERROR_LINE, combined, "static_check")

    if errors:
        return (
            {"result": "error", "issues": issues, "skipped_checks": skipped_checks},
            _tooling_note(
                tool="check_project",
                crashed_on=str(project_dir),
                error="; ".join(f"{e['check']}: {e['detail']}" for e in errors),
            ),
        )

    if proc.returncode != 0 and not issues:
        excerpt = combined.strip()
        if len(excerpt) > 800:
            excerpt = excerpt[:797] + "..."
        if not excerpt:
            excerpt = "no stdout/stderr output"
        return (
            {"result": "error", "issues": [], "skipped_checks": skipped_checks},
            _tooling_note(
                tool="check_project",
                crashed_on=str(project_dir),
                error=(
                    f"check_project.py exited with code {proc.returncode} "
                    f"without [FAIL] output: {excerpt}"
                ),
            ),
        )

    result = "fail" if issues else "pass"
    return ({"result": result, "issues": issues, "skipped_checks": skipped_checks}, None)


# ---------------------------------------------------------------------------
# Compose final report
# ---------------------------------------------------------------------------

def build_report(project_dir: Path) -> dict[str, Any]:
    godot_path = prefer_console_godot_path(
        read_godot_path(project_dir, default="godot")
    )

    try:
        backend = select_verification_backend(project_dir)
    except BackendSelectionError as ex:
        return {
            "result": "fail",
            "backend": {
                "language": "unknown",
                "unit_tests": "unknown",
                "selection": "error",
                "dotnet_target": None,
                "godot_csharp_project": None,
            },
            "ts": _now_iso_utc(),
            "checks": {
                "build": {"result": "error", "errors": []},
                "unit_tests": {
                    "result": "error",
                    "framework": "unknown",
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "failures": [],
                },
                "lint": check_lint(),
                "static_check": {
                    "result": "error",
                    "issues": [],
                    "skipped_checks": [],
                },
            },
            "tooling_notes": [
                _tooling_note(
                    tool="verification_backend",
                    crashed_on=str(project_dir),
                    error=str(ex),
                )
            ],
        }
    backend_name = _backend_name(backend)
    unit_backend_name = _backend_unit_name(backend)

    build_dict, build_note = check_build(godot_path, project_dir, backend=backend)
    unit_dict, unit_note = check_unit_tests(godot_path, project_dir, backend=backend)
    lint_dict = check_lint()
    static_dict, static_note = check_static(project_dir, backend=backend)
    unit_dict.setdefault("framework", unit_backend_name)
    unit_dict.setdefault("passed", 0)
    unit_dict.setdefault("failed", 0)
    unit_dict.setdefault("skipped", 0)
    unit_dict.setdefault(
        "total",
        unit_dict["passed"] + unit_dict["failed"] + unit_dict["skipped"],
    )
    static_dict.setdefault("skipped_checks", [])

    notes: list[dict] = [n for n in (build_note, unit_note, static_note) if n]

    per_check_results = {
        build_dict["result"], unit_dict["result"],
        lint_dict["result"], static_dict["result"],
    }
    # Top-level pass iff every per-check result ∈{pass, warn}.
    overall = "pass" if per_check_results <= {"pass", "warn"} else "fail"

    return {
        "result": overall,
        "backend": _backend_report(backend),
        "ts": _now_iso_utc(),
        "checks": {
            "build": build_dict,
            "unit_tests": unit_dict,
            "lint": lint_dict,
            "static_check": static_dict,
        },
        "tooling_notes": notes,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run /gm-verify checks mechanically and emit the "
            "verify_report.json shape to stdout."
        ),
    )
    parser.add_argument(
        "--project-path", default=None,
        help="project root (default: current working directory)",
    )
    args = parser.parse_args(argv)

    project_dir = _resolve_project_path(args.project_path)
    if not (project_dir / ".godotmaker").is_dir():
        print(
            f"error: {project_dir} is not a godotmaker project "
            f"(.godotmaker/ missing)",
            file=sys.stderr,
        )
        return 1

    try:
        report = build_report(project_dir)
    except OSError as ex:
        print(f"error: build_report failed: {ex}", file=sys.stderr)
        return 1

    try:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    except (UnicodeError, ValueError) as ex:
        print(f"error: failed to encode report as JSON: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
