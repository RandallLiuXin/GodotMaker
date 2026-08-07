"""Tests for tools/run_verify.py —the mechanical /gm-verify runner.

Subprocess is mocked at the module-under-test level (`run_verify.subprocess.run`)
to avoid actually launching godot. The composed report is then validated
against `tests/test_verify_report_fixtures.validate_report` so producer
output stays pinned to the schema the build/fixgap consumers expect.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "run_verify.py"
sys.path.insert(0, str(REPO_ROOT / "tools"))


def _load_run_verify():
    spec = importlib.util.spec_from_file_location("run_verify_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_verify = _load_run_verify()

# Reuse the schema validator that pins the producer/consumer contract.
sys.path.insert(0, str(REPO_ROOT / "tests"))
from test_verify_report_fixtures import validate_report  # noqa: E402


def _make_proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    p = MagicMock()
    p.stdout = stdout
    p.stderr = stderr
    p.returncode = returncode
    return p


def _write_gdunit_xml_from_cmd(cmd: list, xml: str) -> Path:
    report_dir = Path(cmd[cmd.index("--report-directory") + 1])
    results_xml = report_dir / "report_1" / "results.xml"
    results_xml.parent.mkdir(parents=True, exist_ok=True)
    results_xml.write_text(xml, encoding="utf-8")
    return results_xml

class _Backend:
    def __init__(
        self,
        backend: str = "gdscript",
        dotnet_target: str | None = None,
        godot_csharp_project: str | None = None,
    ):
        self.backend = backend
        self.language_backend = backend
        self.unit_test_backend = "dotnet" if backend == "csharp" else "gdunit"
        self.source = "test"
        self.dotnet_target = dotnet_target
        self.godot_csharp_project = godot_csharp_project


def _write_trx_from_cmd(cmd: list, xml: str, name: str = "results.trx") -> Path:
    results_dir = Path(cmd[cmd.index("--results-directory") + 1])
    results_dir.mkdir(parents=True, exist_ok=True)
    trx = results_dir / name
    trx.write_text(xml, encoding="utf-8")
    return trx


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    (tmp_path / ".godotmaker").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "godotmaker.yaml").write_text(
        'godot_path: "/usr/bin/godot"\n'
    )
    return tmp_path


# ---------- build ----------

def test_check_build_pass():
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="Setting Up MainLoop...\nDone.\n")
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))
    assert result == {"result": "pass", "errors": []}
    assert note is None


def test_check_build_csharp_runs_dotnet_targets_before_godot(project_dir: Path):
    sln = project_dir / "Game.sln"
    godot_csproj = project_dir / "Game.Godot.csproj"
    sln.write_text(
        'Project("{GUID}") = "Core", "Game.Core.csproj", "{GUID2}"\n'
        "EndProject\n",
        encoding="utf-8",
    )
    godot_csproj.write_text("<Project />", encoding="utf-8")
    backend = _Backend(
        "csharp",
        dotnet_target="Game.sln",
        godot_csharp_project="Game.Godot.csproj",
    )
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd == ["/usr/bin/godot", "--version"]:
            return _make_proc(stdout="4.5.1.stable.mono.official\n")
        return _make_proc(stdout="ok\n")

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_build(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result == {"result": "pass", "errors": []}
    assert note is None
    assert calls[0][:3] == ["dotnet", "build", str(sln)]
    assert calls[1][:3] == ["dotnet", "build", str(godot_csproj)]
    assert calls[2] == ["/usr/bin/godot", "--version"]
    assert calls[3][0:2] == ["/usr/bin/godot", "--headless"]


def test_check_build_csharp_solution_in_subdir_does_not_crash_for_root_godot_project(project_dir: Path):
    solution_dir = project_dir / "core"
    solution_dir.mkdir()
    sln = solution_dir / "Game.sln"
    godot_csproj = project_dir / "Game.Godot.csproj"
    sln.write_text(
        'Project("{GUID}") = "Core", "Game.Core.csproj", "{GUID2}"\n'
        "EndProject\n",
        encoding="utf-8",
    )
    godot_csproj.write_text("<Project />", encoding="utf-8")
    backend = _Backend(
        "csharp",
        dotnet_target="core/Game.sln",
        godot_csharp_project="Game.Godot.csproj",
    )
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd == ["/usr/bin/godot", "--version"]:
            return _make_proc(stdout="4.5.1.stable.mono.official\n")
        return _make_proc(stdout="ok\n")

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_build(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert run_verify._solution_mentions_project(sln, godot_csproj) is False
    assert result == {"result": "pass", "errors": []}
    assert note is None
    assert calls[0][:3] == ["dotnet", "build", str(sln)]
    assert calls[1][:3] == ["dotnet", "build", str(godot_csproj)]
    assert calls[2] == ["/usr/bin/godot", "--version"]
    assert calls[3][0:2] == ["/usr/bin/godot", "--headless"]

def test_check_build_csharp_rejects_non_mono_godot(project_dir: Path):
    backend = _Backend("csharp", dotnet_target="Game.sln")

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["dotnet", "build"]:
            return _make_proc(stdout="build ok\n")
        if cmd == ["/usr/bin/godot", "--version"]:
            return _make_proc(stdout="4.5.1.stable.official\n")
        raise AssertionError(f"unexpected command after non-Mono detection: {cmd}")

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_build(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result["result"] == "fail"
    assert "requires Godot Mono/.NET" in result["errors"][0]["message"]
    assert note is None

def test_check_build_csharp_dotnet_failure_blocks_before_godot(project_dir: Path):
    backend = _Backend("csharp", dotnet_target="Game.sln")

    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(
            stderr="CSC : error CS1002: ; expected\n",
            returncode=1,
        )
        result, note = run_verify.check_build(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result["result"] == "fail"
    assert result["errors"][0]["file"] == "Game.sln"
    assert "error CS1002" in result["errors"][0]["message"]
    assert note is None
    assert run.call_count == 1

def test_check_build_fail_with_errors_and_locations():
    output = (
        "ERROR: Parse Error: Identifier 'bar' not declared.\n"
        "   at: GDScript::reload (src/foo.gd:42)\n"
        "ERROR: Failed loading resource: res://scenes/main.tscn.\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))
    assert result["result"] == "fail"
    assert len(result["errors"]) == 2
    assert result["errors"][0]["file"] == "src/foo.gd"
    assert result["errors"][0]["line"] == 42
    assert "Identifier 'bar'" in result["errors"][0]["message"]
    # Second ERROR has no GDScript location →file empty, line 0
    assert result["errors"][1]["file"] == ""
    assert result["errors"][1]["line"] == 0
    assert note is None


def test_check_build_ignores_headless_shutdown_diagnostics():
    output = "ERROR: 7 resources still in use at exit (run with --verbose for details).\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result == {"result": "pass", "errors": []}
    assert note is None


def test_check_build_ignores_headless_display_and_objectdb_noise():
    output = (
        "ERROR: Screen index 0 is invalid.\n"
        "ERROR: ObjectDB instances leaked at exit (run with --verbose for details).\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result == {"result": "pass", "errors": []}
    assert note is None


def test_check_build_engine_cpp_location_remains_blocking_without_file_pointer():
    output = (
        "ERROR: Cannot open file 'res://bad_scene.tscn'.\n"
        "   at: load (scene/resources/resource_format_text.cpp:123)\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stderr=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "",
        "line": 0,
        "message": "Cannot open file 'res://bad_scene.tscn'.",
    }]
    assert note is None


def test_check_build_shutdown_note_plus_real_error_fails():
    output = (
        "ERROR: 7 resources still in use at exit (run with --verbose for details).\n"
        "ERROR: Failed loading resource: res://scenes/main.tscn.\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "",
        "line": 0,
        "message": "Failed loading resource: res://scenes/main.tscn.",
    }]
    assert note is None


def test_check_build_shutdown_note_plus_nonzero_exit_fails():
    output = "ERROR: 7 resources still in use at exit (run with --verbose for details).\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=1)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "",
        "line": 0,
        "message": "godot exited 1 without a recognized blocking diagnostic",
    }]
    assert note is None


def test_check_build_script_error_still_fails():
    output = (
        "SCRIPT ERROR: Parse Error: Identifier 'BirdController' not declared.\n"
        "   at: GDScript::reload (src/bird.gd:12)\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stderr=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "src/bird.gd",
        "line": 12,
        "message": "Parse Error: Identifier 'BirdController' not declared.",
    }]
    assert note is None


def test_check_build_unknown_error_with_zero_exit_fails():
    output = "ERROR: Provider emitted an uncategorized runtime diagnostic.\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stderr=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "",
        "line": 0,
        "message": "Provider emitted an uncategorized runtime diagnostic.",
    }]
    assert note is None


def test_check_build_shader_error_with_zero_exit_fails():
    output = (
        "SHADER ERROR: Invalid shader code.\n"
        "   at: GDScript::reload (res://shaders/card.gdshader:3)\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stderr=output, returncode=0)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "res://shaders/card.gdshader",
        "line": 3,
        "message": "Invalid shader code.",
    }]
    assert note is None


def test_check_build_unknown_error_with_nonzero_exit_fails():
    output = "ERROR: Provider emitted an uncategorized runtime diagnostic.\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stderr=output, returncode=1)
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["errors"] == [{
        "file": "",
        "line": 0,
        "message": "Provider emitted an uncategorized runtime diagnostic.",
    }]
    assert note is None


def test_check_build_locations_are_scoped_to_each_error():
    """A GDScript location after ERROR_B must not be attributed to ERROR_A."""
    output = (
        "ERROR: Cannot open file 'res://scenes/main.tscn'.\n"
        "ERROR: Parse Error.\n"
        "   at: GDScript::reload (src/bar.gd:7)\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        result, _ = run_verify.check_build("/usr/bin/godot", Path("/x"))
    assert result["errors"][0]["file"] == ""
    assert result["errors"][0]["line"] == 0
    assert result["errors"][1]["file"] == "src/bar.gd"
    assert result["errors"][1]["line"] == 7


def test_check_build_timeout_returns_escalate():
    with patch.object(
        run_verify.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(cmd="godot", timeout=60),
    ):
        result, note = run_verify.check_build("/usr/bin/godot", Path("/x"))
    assert result["result"] == "error"
    assert result["errors"] == []
    assert note["tool"] == "godot"
    assert note["suggested_fallback"] == "escalate"


def test_check_build_missing_binary_returns_escalate():
    with patch.object(
        run_verify.subprocess, "run", side_effect=FileNotFoundError("no godot"),
    ):
        result, note = run_verify.check_build("nope-godot", Path("/x"))
    assert result["result"] == "error"
    assert note["tool"] == "godot"
    assert note["crashed_on"] == "nope-godot"


def test_check_build_redirects_log_into_godotmaker_logs(project_dir: Path):
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="Done.\n")
        run_verify.check_build("/usr/bin/godot", project_dir)
    cmd = run.call_args.args[0]
    assert "--log-file" in cmd
    log_path = Path(cmd[cmd.index("--log-file") + 1])
    assert log_path.parent == project_dir / ".godotmaker" / "logs"
    assert log_path.name.startswith("godot-build-")
    assert log_path.suffix == ".log"


# ---------- unit tests ----------

def test_check_unit_tests_pass_with_cases_summary():
    output = "267 test cases | 0 errors | 0 failures (31 suites, exit 0)\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))
    assert result == {"result": "pass", "passed": 267, "failed": 0, "failures": []}
    assert note is None


def test_check_unit_tests_csharp_parses_namespaced_trx(project_dir: Path):
    trx = """<?xml version="1.0" encoding="utf-8"?>
<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <ResultSummary outcome="Failed">
    <Counters total="3" executed="3" passed="1" failed="1" error="0" timeout="0" aborted="0" inconclusive="0" notExecuted="1" />
  </ResultSummary>
  <Results>
    <UnitTestResult testName="Passes" outcome="Passed" />
    <UnitTestResult testName="Fails" outcome="Failed">
      <Output><ErrorInfo><Message>Expected 2 but got 1</Message></ErrorInfo></Output>
    </UnitTestResult>
    <UnitTestResult testName="Skipped" outcome="NotExecuted" />
  </Results>
</TestRun>
"""
    backend = _Backend("csharp", dotnet_target="Game.sln")

    def fake_run(cmd, *args, **kwargs):
        _write_trx_from_cmd(cmd, trx)
        return _make_proc(stdout="Test run failed.", returncode=1)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result["framework"] == "dotnet"
    assert result["result"] == "fail"
    assert result["total"] == 3
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1
    assert result["failures"] == [
        {"test": "Fails", "message": "Expected 2 but got 1"}
    ]
    assert note is None


def test_parse_trx_files_counts_each_file_without_global_counters(tmp_path: Path):
    with_counters = tmp_path / "with_counters.trx"
    with_counters.write_text(
        """<TestRun><ResultSummary><Counters total="1" passed="1" failed="0" /></ResultSummary></TestRun>""",
        encoding="utf-8",
    )
    without_counters = tmp_path / "without_counters.trx"
    without_counters.write_text(
        """<TestRun><Results><UnitTestResult testName="SecondPass" outcome="Passed" /></Results></TestRun>""",
        encoding="utf-8",
    )

    result = run_verify._parse_trx_files([with_counters, without_counters])

    assert result["result"] == "pass"
    assert result["total"] == 2
    assert result["passed"] == 2
    assert result["failed"] == 0
    assert result["skipped"] == 0

def test_check_unit_tests_csharp_missing_trx_is_error(project_dir: Path):
    backend = _Backend("csharp", dotnet_target="Game.sln")
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="No TRX here", returncode=0)
        result, note = run_verify.check_unit_tests(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result == {
        "result": "error",
        "framework": "dotnet",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "failures": [],
    }
    assert note["tool"] == "dotnet"
    assert "TRX" in note["error"]


def test_check_unit_tests_csharp_zero_tests_is_tooling_error(project_dir: Path):
    trx = (
        "<TestRun><ResultSummary>"
        '<Counters total="0" passed="0" failed="0" notExecuted="0" />'
        "</ResultSummary></TestRun>"
    )
    backend = _Backend("csharp", dotnet_target="Game.sln")

    def fake_run(cmd, *args, **kwargs):
        _write_trx_from_cmd(cmd, trx)
        return _make_proc(stdout="No tests matched.", returncode=0)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result["result"] == "error"
    assert result["total"] == 0
    assert note["tool"] == "dotnet"
    assert "zero tests" in note["error"]


def test_check_unit_tests_csharp_nonzero_exit_with_passing_trx_is_tooling_error(
    project_dir: Path,
):
    trx = (
        "<TestRun><ResultSummary>"
        '<Counters total="1" passed="1" failed="0" notExecuted="0" />'
        "</ResultSummary></TestRun>"
    )
    backend = _Backend("csharp", dotnet_target="Game.sln")

    def fake_run(cmd, *args, **kwargs):
        _write_trx_from_cmd(cmd, trx)
        return _make_proc(stdout="Host failed after tests.", returncode=1)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests(
            "/usr/bin/godot",
            project_dir,
            backend=backend,
        )

    assert result["result"] == "error"
    assert result["total"] == 1
    assert result["passed"] == 1
    assert note["tool"] == "dotnet"
    assert "exited with code 1 despite passing TRX" in note["error"]


def test_check_unit_tests_uses_official_gdunit_cmdtool_args():
    output = "1 test case | 0 errors | 0 failures (1 suite, exit 0)\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    cmd = run.call_args.args[0]
    assert "res://addons/gdUnit4/bin/GdUnitCmdTool.gd" in cmd
    assert "--add" in cmd
    assert "res://test/" in cmd
    assert "--ignoreHeadlessMode" in cmd
    assert "--report-directory" in cmd
    assert "--run-tests" not in cmd
    assert "--test-case" not in cmd


def test_check_unit_tests_redirects_log_into_godotmaker_logs(project_dir: Path):
    output = "1 test case | 0 errors | 0 failures (1 suite, exit 0)\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        run_verify.check_unit_tests("/usr/bin/godot", project_dir)
    cmd = run.call_args.args[0]
    assert "--log-file" in cmd
    log_path = Path(cmd[cmd.index("--log-file") + 1])
    assert log_path.parent == project_dir / ".godotmaker" / "logs"
    assert log_path.name.startswith("godot-gdunit-")


def test_check_unit_tests_prefers_xml_top_level_over_first_suite_summary():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="report_1" tests="76" failures="1" errors="0" skipped="0">
  <testsuite name="test_game_scene" tests="6" failures="0" errors="0" skipped="0">
    <testcase name="test_ok" classname="test_game_scene" />
  </testsuite>
  <testsuite name="test_s_hud_prompt" tests="13" failures="1" errors="0" skipped="0">
    <testcase name="test_game_over_modal_layout_keeps_score_and_button_separate" classname="test_s_hud_prompt">
      <failure message="FAILED: res://test/test_s_hud_prompt.gd:255" type="FAILURE">
        <![CDATA[Expecting to be less than or equal: 100]]>
      </failure>
    </testcase>
  </testsuite>
</testsuites>
"""

    def fake_run(cmd, *args, **kwargs):
        _write_gdunit_xml_from_cmd(cmd, xml)
        return _make_proc(
            stdout="Statistics: 6 test cases | 0 errors | 0 failures | PASSED\n",
            returncode=0,
        )

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["passed"] == 75
    assert result["failed"] == 1
    assert result["failures"] == [{
        "test": (
            "test_s_hud_prompt::"
            "test_game_over_modal_layout_keeps_score_and_button_separate"
        ),
        "message": (
            "FAILED: res://test/test_s_hud_prompt.gd:255: "
            "Expecting to be less than or equal: 100"
        ),
    }]
    assert note is None


def test_check_unit_tests_xml_pass_counts_all_cases():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="report_1" tests="76" failures="0" errors="0" skipped="0">
  <testsuite name="test_game_scene" tests="6" failures="0" errors="0" skipped="0" />
  <testsuite name="test_s_hud_prompt" tests="13" failures="0" errors="0" skipped="0" />
</testsuites>
"""

    def fake_run(cmd, *args, **kwargs):
        _write_gdunit_xml_from_cmd(cmd, xml)
        return _make_proc(stdout="not a summary\n", returncode=0)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result == {"result": "pass", "passed": 76, "failed": 0, "failures": []}
    assert note is None


def test_check_unit_tests_xml_pass_exit_101_is_warn():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="report_1" tests="76" failures="0" errors="0" skipped="0" />
"""

    def fake_run(cmd, *args, **kwargs):
        _write_gdunit_xml_from_cmd(cmd, xml)
        return _make_proc(
            stdout="line 21: WARNING:: Found 4 possible orphan nodes.\n",
            returncode=101,
        )

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result == {
        "result": "warn",
        "passed": 76,
        "failed": 0,
        "failures": [],
        "warnings": ["Found 4 possible orphan nodes."],
    }
    assert note is None


def test_check_unit_tests_xml_suite_errors_count_as_failed():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="report_1" tests="3" failures="0" skipped="0">
  <testsuite name="test_game_scene" tests="1" failures="0" errors="0" skipped="0">
    <testcase name="test_ok" classname="test_game_scene" />
  </testsuite>
  <testsuite name="test_s_hud_prompt" tests="2" failures="0" errors="1" skipped="0">
    <testcase name="test_crashes" classname="test_s_hud_prompt">
      <error message="ERROR: res://test/test_s_hud_prompt.gd:255" type="ERROR">
        <![CDATA[Runtime error]]>
      </error>
    </testcase>
  </testsuite>
</testsuites>
"""

    def fake_run(cmd, *args, **kwargs):
        _write_gdunit_xml_from_cmd(cmd, xml)
        return _make_proc(stdout="not a summary\n", returncode=0)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["failures"] == [{
        "test": "test_s_hud_prompt::test_crashes",
        "message": (
            "ERROR: res://test/test_s_hud_prompt.gd:255: Runtime error"
        ),
    }]
    assert note is None


def test_check_unit_tests_xml_pass_exit_100_is_fail():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="report_1" tests="76" failures="0" errors="0" skipped="0" />
"""

    def fake_run(cmd, *args, **kwargs):
        _write_gdunit_xml_from_cmd(cmd, xml)
        return _make_proc(stdout="Exit code: 100\n", returncode=100)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["failed"] == 1
    assert "code 100" in result["failures"][0]["message"]
    assert note is None


def test_check_unit_tests_xml_pass_other_nonzero_is_error():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="report_1" tests="76" failures="0" errors="0" skipped="0" />
"""

    def fake_run(cmd, *args, **kwargs):
        _write_gdunit_xml_from_cmd(cmd, xml)
        return _make_proc(stdout="Exit code: 103\n", returncode=103)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result == {"result": "error", "passed": 0, "failed": 0, "failures": []}
    assert note["tool"] == "gdunit"
    assert "code 103" in note["error"]


def test_check_unit_tests_missing_xml_exit_100_is_fail():
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="runner output without summary\n", returncode=100)
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["failed"] == 1
    assert "code 100" in result["failures"][0]["message"]
    assert note is None


def test_check_unit_tests_fallback_uses_overall_summary_not_first_suite():
    output = (
        "Statistics: 6 test cases | 0 errors | 0 failures | PASSED\n"
        "Overall Summary: 76 test cases | 0 errors | 1 failures | FAILED\n"
        "Exit code: 100\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=100)
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))

    assert result["result"] == "fail"
    assert result["passed"] == 75
    assert result["failed"] == 1
    assert note is None


def test_check_unit_tests_pass_with_pf_summary():
    output = "Tests Passed: 274 | Tests Failed: 0 (some other text)\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))
    assert result["result"] == "pass"
    assert result["passed"] == 274
    assert result["failed"] == 0
    assert note is None


def test_check_unit_tests_fail_with_failures():
    output = (
        "267 test cases | 0 errors | 2 failures (31 suites, exit 1)\n"
        "FAILED: test_player::test_jump - expected 10, got 0\n"
        "FAILED: test_hud::test_score - expected 100, got 50\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=1)
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))
    assert result["result"] == "fail"
    assert result["passed"] == 265
    assert result["failed"] == 2
    assert len(result["failures"]) == 2
    assert result["failures"][0] == {
        "test": "test_player::test_jump",
        "message": "expected 10, got 0",
    }
    assert note is None


def test_check_unit_tests_errors_count_as_failed():
    """gdUnit4 reports errors separately from failures; both contribute to
    'failed' from the consumer's perspective (test runner result was not
    a clean pass)."""
    output = "100 test cases | 3 errors | 1 failures (10 suites, exit 1)\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        result, _ = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))
    assert result["failed"] == 4
    assert result["passed"] == 96


def test_check_unit_tests_unparseable_output_is_error():
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="??? garbage ???\n")
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))
    assert result["result"] == "error"
    assert note["tool"] == "gdunit"
    assert note["suggested_fallback"] == "escalate"


def test_check_unit_tests_timeout_is_error():
    with patch.object(
        run_verify.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(cmd="godot", timeout=600),
    ):
        result, note = run_verify.check_unit_tests("/usr/bin/godot", Path("/x"))
    assert result["result"] == "error"
    assert result == {"result": "error", "passed": 0, "failed": 0, "failures": []}
    assert note["suggested_fallback"] == "escalate"


# ---------- lint ----------

def test_check_lint_is_always_pass_with_null_format_drift():
    """gdtoolkit is disabled pipeline-wide; lint always emits a stub pass."""
    assert run_verify.check_lint() == {
        "result": "pass", "issues": [], "format_drift": None,
    }


# ---------- static check ----------

def test_check_static_pass():
    output = "[PASS] project.godot exists\n[PASS] tests directory exists\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output)
        result, note = run_verify.check_static(Path("/x"))
    assert result == {"result": "pass", "issues": [], "skipped_checks": []}
    assert note is None


def test_check_static_fail_parses_check_name_prefix():
    output = (
        "[PASS] project.godot exists\n"
        "[FAIL] missing_unit_test: s_hud has no test file\n"
        "[FAIL] orphan_test: test_x.gd refers to deleted system\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=1)
        result, note = run_verify.check_static(Path("/x"))
    assert result["result"] == "fail"
    assert result["issues"] == [
        {"check": "missing_unit_test", "detail": "s_hud has no test file"},
        {"check": "orphan_test", "detail": "test_x.gd refers to deleted system"},
    ]
    assert note is None


def test_check_static_fail_without_check_prefix():
    output = "[FAIL] something generic went wrong\n"
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=1)
        result, _ = run_verify.check_static(Path("/x"))
    assert result["issues"] == [
        {"check": "static_check", "detail": "something generic went wrong"},
    ]


def test_check_static_parses_skip_and_error_lines():
    output = (
        "[PASS] project.godot exists\n"
        "[SKIP] ecs: C# backend skips GDScript ECS scan\n"
        "[ERROR] mcp: config unreadable\n"
    )
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout=output, returncode=1)
        result, note = run_verify.check_static(Path("/x"))

    assert result["result"] == "error"
    assert result["issues"] == []
    assert result["skipped_checks"] == [
        {"check": "ecs", "detail": "C# backend skips GDScript ECS scan"}
    ]
    assert note["tool"] == "check_project"
    assert "mcp: config unreadable" in note["error"]


def test_check_static_gdscript_includes_git_gate_flags(project_dir: Path):
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="[PASS] all good\n")
        result, note = run_verify.check_static(project_dir)

    cmd = run.call_args.args[0]
    assert cmd[-5:] == ["--git", "--ecs", "--tests", "--plan", "--mcp"]
    assert result == {"result": "pass", "issues": [], "skipped_checks": []}
    assert note is None

def test_check_static_csharp_omits_build_ecs_tests_flags(project_dir: Path):
    backend = _Backend("csharp", dotnet_target="Game.sln")
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(stdout="[PASS] plan ok\n")
        result, note = run_verify.check_static(project_dir, backend=backend)

    cmd = run.call_args.args[0]
    assert cmd[-3:] == ["--git", "--plan", "--mcp"]
    assert "--build" not in cmd
    assert "--ecs" not in cmd
    assert "--tests" not in cmd
    assert result["skipped_checks"] == [
        {"check": "gdscript_gecs", "reason": "not applicable to C#/.NET verification backend"},
        {"check": "gdunit_discovery", "reason": "unit tests handled by dotnet test"},
    ]
    assert note is None

def test_check_static_timeout_is_error():
    with patch.object(
        run_verify.subprocess, "run",
        side_effect=subprocess.TimeoutExpired(cmd="check_project", timeout=60),
    ):
        result, note = run_verify.check_static(Path("/x"))
    assert result["result"] == "error"
    assert result["issues"] == []
    assert note["tool"] == "check_project"


def test_check_static_nonzero_without_fail_output_is_error():
    with patch.object(run_verify.subprocess, "run") as run:
        run.return_value = _make_proc(
            stderr="Traceback (most recent call last):\nImportError: broken\n",
            returncode=2,
        )
        result, note = run_verify.check_static(Path("/x"))

    assert result == {"result": "error", "issues": [], "skipped_checks": []}
    assert note["tool"] == "check_project"
    assert note["suggested_fallback"] == "escalate"
    assert "exited with code 2" in note["error"]
    assert "ImportError: broken" in note["error"]


# ---------- godot_path resolution ----------

def test_read_godot_path_returns_configured_value(project_dir: Path):
    assert run_verify.read_godot_path(project_dir, default="godot") == "/usr/bin/godot"


def test_read_godot_path_falls_back_to_godot_when_missing(tmp_path: Path):
    """SKILL says fall back to plain 'godot' when the yaml is absent."""
    (tmp_path / ".godotmaker").mkdir()
    assert run_verify.read_godot_path(tmp_path, default="godot") == "godot"


def test_read_godot_path_falls_back_when_field_empty(tmp_path: Path):
    (tmp_path / ".godotmaker").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "godotmaker.yaml").write_text("godot_path: \n")
    assert run_verify.read_godot_path(tmp_path, default="godot") == "godot"


def test_read_godot_path_uses_codex_runtime_config(tmp_path: Path):
    (tmp_path / ".godotmaker").mkdir()
    (tmp_path / ".godotmaker" / "config.yaml").write_text("agent: codex\n")
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "godotmaker.yaml").write_text(
        "godot_path: /opt/codex-godot\n"
    )
    assert run_verify.read_godot_path(tmp_path, default="godot") == "/opt/codex-godot"


def test_prefer_console_godot_path_uses_existing_sibling(tmp_path: Path):
    gui = tmp_path / "Godot_v4.5-stable_win64.exe"
    console = tmp_path / "Godot_v4.5-stable_win64_console.exe"
    gui.write_text("", encoding="utf-8")
    console.write_text("", encoding="utf-8")

    assert run_verify.prefer_console_godot_path(str(gui)) == str(console)


def test_prefer_console_godot_path_keeps_original_when_missing(tmp_path: Path):
    gui = tmp_path / "Godot_v4.5-stable_win64.exe"
    gui.write_text("", encoding="utf-8")

    assert run_verify.prefer_console_godot_path(str(gui)) == str(gui)


# ---------- build_report composition ----------

def _fake_run_factory(*, build="ok", unit="ok", static="ok"):
    """Build a subprocess.run fake. Each arg selects per-tool behaviour:

    - "ok"      →clean pass output
    - "fail"    →output that parses to a failing result
    - "timeout" →raise TimeoutExpired
    """
    BUILD_OK = "Setting Up MainLoop...\nDone.\n"
    BUILD_FAIL = "ERROR: Cannot open file 'res://x.tscn'.\n"
    UNIT_OK = "100 test cases | 0 errors | 0 failures (10 suites, exit 0)\n"
    UNIT_FAIL = (
        "100 test cases | 0 errors | 1 failures (10 suites, exit 1)\n"
        "FAILED: test_x::test_y - boom\n"
    )
    STATIC_OK = "[PASS] all good\n"
    STATIC_FAIL = "[FAIL] missing_unit_test: s_hud has no test file\n"

    def fake_run(cmd, *args, **kwargs):
        # Identify which check this call is from.
        cmd_str = " ".join(str(c) for c in cmd)
        if "GdUnitCmdTool" in cmd_str:
            if unit == "timeout":
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=600)
            return _make_proc(stdout=UNIT_FAIL if unit == "fail" else UNIT_OK)
        if "check_project.py" in cmd_str:
            if static == "timeout":
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
            return _make_proc(stdout=STATIC_FAIL if static == "fail" else STATIC_OK)
        # Otherwise: godot --headless --quit
        if build == "timeout":
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)
        return _make_proc(stdout=BUILD_FAIL if build == "fail" else BUILD_OK)
    return fake_run


def test_build_report_all_pass_is_schema_valid(project_dir: Path):
    with patch.object(run_verify.subprocess, "run",
                      side_effect=_fake_run_factory()):
        report = run_verify.build_report(project_dir)
    assert report["result"] == "pass"
    assert report["backend"] == {
        "language": "gdscript",
        "unit_tests": "gdunit",
        "selection": "legacy-default",
        "dotnet_target": None,
        "godot_csharp_project": None,
    }
    assert report["tooling_notes"] == []
    assert report["checks"]["lint"]["format_drift"] is None
    assert report["checks"]["unit_tests"]["framework"] == "gdunit"
    assert report["checks"]["unit_tests"]["total"] == 100
    assert report["checks"]["unit_tests"]["skipped"] == 0
    assert report["checks"]["static_check"]["skipped_checks"] == []
    assert validate_report(report) == []


def test_build_report_csharp_uses_selected_backend(project_dir: Path):
    trx = """<TestRun><ResultSummary><Counters total="1" passed="1" failed="0" /></ResultSummary></TestRun>"""
    backend = _Backend("csharp", dotnet_target="Game.sln")

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["/usr/bin/godot", "--version"]:
            return _make_proc(stdout="4.5.1.stable.mono.official\n")
        cmd_str = " ".join(str(c) for c in cmd)
        if " test " in f" {cmd_str} ":
            _write_trx_from_cmd(cmd, trx)
        return _make_proc(stdout="[PASS] ok\n")

    with patch.object(run_verify, "select_verification_backend", return_value=backend):
        with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
            report = run_verify.build_report(project_dir)

    assert report["backend"] == {
        "language": "csharp",
        "unit_tests": "dotnet",
        "selection": "test",
        "dotnet_target": "Game.sln",
        "godot_csharp_project": None,
    }
    assert report["result"] == "pass"
    assert report["checks"]["unit_tests"]["framework"] == "dotnet"
    assert report["checks"]["unit_tests"]["total"] == 1
    assert report["checks"]["unit_tests"]["skipped"] == 0
    assert report["checks"]["static_check"]["skipped_checks"] == [
        {"check": "gdscript_gecs", "reason": "not applicable to C#/.NET verification backend"},
        {"check": "gdunit_discovery", "reason": "unit tests handled by dotnet test"},
    ]
    assert validate_report(report) == []


def test_build_report_shutdown_note_keeps_overall_pass(project_dir: Path):
    base_fake = _fake_run_factory()

    def fake_run(cmd, *args, **kwargs):
        cmd_str = " ".join(str(c) for c in cmd)
        if "GdUnitCmdTool" not in cmd_str and "check_project.py" not in cmd_str:
            return _make_proc(
                stdout=(
                    "ERROR: 7 resources still in use at exit "
                    "(run with --verbose for details).\n"
                ),
                returncode=0,
            )
        return base_fake(cmd, *args, **kwargs)

    with patch.object(run_verify.subprocess, "run", side_effect=fake_run):
        report = run_verify.build_report(project_dir)

    assert report["result"] == "pass"
    assert report["checks"]["build"] == {"result": "pass", "errors": []}
    assert validate_report(report) == []


def test_build_report_unit_fail_makes_overall_fail(project_dir: Path):
    with patch.object(run_verify.subprocess, "run",
                      side_effect=_fake_run_factory(unit="fail")):
        report = run_verify.build_report(project_dir)
    assert report["result"] == "fail"
    assert report["checks"]["unit_tests"]["failed"] == 1
    assert validate_report(report) == []


def test_build_report_build_timeout_pairs_with_tooling_note(project_dir: Path):
    with patch.object(run_verify.subprocess, "run",
                      side_effect=_fake_run_factory(build="timeout")):
        report = run_verify.build_report(project_dir)
    assert report["result"] == "fail"
    assert report["checks"]["build"]["result"] == "error"
    notes = report["tooling_notes"]
    assert len(notes) == 1
    assert notes[0]["tool"] == "godot"
    assert notes[0]["suggested_fallback"] == "escalate"
    assert validate_report(report) == []


def test_build_report_multiple_tool_errors_emit_multiple_notes(project_dir: Path):
    """build + static both timing out →2 entries in tooling_notes."""
    with patch.object(
        run_verify.subprocess, "run",
        side_effect=_fake_run_factory(build="timeout", static="timeout"),
    ):
        report = run_verify.build_report(project_dir)
    assert report["result"] == "fail"
    tools = sorted(n["tool"] for n in report["tooling_notes"])
    assert tools == ["check_project", "godot"]
    assert validate_report(report) == []


def test_build_report_static_fail_is_schema_valid(project_dir: Path):
    with patch.object(run_verify.subprocess, "run",
                      side_effect=_fake_run_factory(static="fail")):
        report = run_verify.build_report(project_dir)
    assert report["result"] == "fail"
    assert report["checks"]["static_check"]["issues"][0]["check"] == "missing_unit_test"
    assert validate_report(report) == []


def test_build_report_backend_selection_error_is_schema_valid(project_dir: Path):
    with patch.object(
        run_verify,
        "select_verification_backend",
        side_effect=run_verify.BackendSelectionError(
            "auto detected mixed language backends"
        ),
    ):
        report = run_verify.build_report(project_dir)

    assert report["result"] == "fail"
    assert report["backend"] == {
        "language": "unknown",
        "unit_tests": "unknown",
        "selection": "error",
        "dotnet_target": None,
        "godot_csharp_project": None,
    }
    assert report["checks"]["build"] == {"result": "error", "errors": []}
    assert report["checks"]["unit_tests"] == {
        "result": "error",
        "framework": "unknown",
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "failures": [],
    }
    assert report["checks"]["static_check"] == {
        "result": "error",
        "issues": [],
        "skipped_checks": [],
    }
    assert report["tooling_notes"][0]["tool"] == "verification_backend"
    assert report["tooling_notes"][0]["crashed_on"] == str(project_dir)
    assert "mixed language" in report["tooling_notes"][0]["error"]
    assert validate_report(report) == []


def test_main_backend_selection_error_emits_fail_json(project_dir: Path, capsys):
    with patch.object(
        run_verify,
        "select_verification_backend",
        side_effect=run_verify.BackendSelectionError(
            "unit_test_backend must be one of: auto, dotnet, gdunit; got 'bogus'"
        ),
    ):
        rc = run_verify.main(["--project-path", str(project_dir)])

    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"] == "fail"
    assert parsed["tooling_notes"][0]["tool"] == "verification_backend"
    assert "unit_test_backend" in parsed["tooling_notes"][0]["error"]
    assert validate_report(parsed) == []

# ---------- main / CLI ----------

def test_main_missing_godotmaker_dir_returns_1(tmp_path: Path, capsys):
    rc = run_verify.main(["--project-path", str(tmp_path)])
    assert rc == 1
    assert "not a godotmaker project" in capsys.readouterr().err


def test_main_emits_json_to_stdout(project_dir: Path, capsys):
    with patch.object(run_verify.subprocess, "run",
                      side_effect=_fake_run_factory()):
        rc = run_verify.main(["--project-path", str(project_dir)])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert validate_report(parsed) == []
    assert parsed["result"] == "pass"
    assert "ts" in parsed and parsed["ts"].endswith("Z")


def test_main_defaults_to_cwd(project_dir: Path, capsys, monkeypatch):
    monkeypatch.chdir(project_dir)
    with patch.object(run_verify.subprocess, "run",
                      side_effect=_fake_run_factory()):
        rc = run_verify.main([])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["result"] == "pass"


def test_main_subprocess_invocation_real(project_dir: Path):
    """End-to-end via real subprocess —godot/gdunit/check_project all fail
    to launch, so we expect rc=0 with a JSON whose checks.* are 'error'.

    Important: this guards against the script breaking at import time
    (syntax errors, missing imports) —the rest of the file mocks at
    module level and would miss those.
    """
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-path", str(project_dir)],
        capture_output=True, text=True, timeout=30,
        # Avoid hitting a real godot on the dev machine: point PATH at an
        # empty dir for this call.
        env={**os.environ, "PATH": str(project_dir)},
    )
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)
    # godot not on PATH →build + unit are 'error'. Lint stub-passes.
    assert parsed["checks"]["build"]["result"] == "error"
    assert parsed["checks"]["unit_tests"]["result"] == "error"
    assert parsed["checks"]["lint"]["result"] == "pass"
    # check_project.py runs (sys.executable is still found) so static_check
    # depends on whether it errors out on the empty project; tolerate
    # either pass or fail/error here —the assertion that matters is that
    # the script ran end-to-end and produced a schema-valid JSON.
    assert validate_report(parsed) == []


# ---------- godot log-file retention ----------

def test_godot_log_file_keeps_five_newest_per_kind(project_dir: Path):
    logs = project_dir / ".godotmaker" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    seeded = []
    for i in range(6):
        p = logs / f"godot-build-seed{i}.log"
        p.write_text("x")
        os.utime(p, (1000 + i, 1000 + i))  # ascending mtime: seed5 newest
        seeded.append(p)
    # A different kind must survive build-kind pruning.
    untouched = logs / "godot-gdunit-seed.log"
    untouched.write_text("x")

    new_path = Path(run_verify.godot_log_file(project_dir, "build"))
    new_path.write_text("new")  # the caller (godot) writes the returned path

    build_logs = list(logs.glob("godot-build-*.log"))
    assert len(build_logs) == 5  # 4 newest seeds + the new one
    assert not seeded[0].exists()
    assert not seeded[1].exists()
    assert seeded[5].exists()
    assert untouched.exists()
