"""Tests for e2e_env.py — interpreter-scoped godot-e2e discovery.

The bug these cover: the pipeline asked PATH for a bare `godot-e2e`
command and reported "missing" without ever naming the Python
environment it consulted, so a package installed into a *different*
interpreter looked absent and the same warning came back after every
"fix". Discovery is therefore pinned to one interpreter, every verdict
names it, and nothing is cached between probes.
"""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

import e2e_env
from e2e_env import (
    STATUS_IMPORT_ERROR,
    STATUS_MISSING,
    STATUS_OK,
    STATUS_OTHER_ENVIRONMENT,
    STATUS_PROBE_FAILED,
    format_command,
    probe_e2e_python_env,
)

TARGET_PYTHON = os.path.join("/opt", "envs", "project", "bin", "python")
TARGET_PREFIX = os.path.join("/opt", "envs", "project")
TARGET_SCRIPTS = os.path.join("/opt", "envs", "project", "bin")
OTHER_SCRIPTS = os.path.join("/opt", "envs", "other", "bin")
OTHER_CLI = os.path.join(OTHER_SCRIPTS, "godot-e2e")


def probe_payload(**overrides) -> dict:
    """A probe result from a healthy target interpreter."""
    payload = {
        "executable": TARGET_PYTHON,
        "prefix": TARGET_PREFIX,
        "base_prefix": os.path.join("/usr"),
        "python_version": "3.11.5",
        "scripts_dirs": [TARGET_SCRIPTS],
        "installed": True,
        "location": os.path.join(
            TARGET_PREFIX, "lib", "python3.11", "site-packages",
            "godot_e2e", "__init__.py",
        ),
        "import_error": None,
        "dist_version": "1.3.0",
        "cli_module": True,
    }
    payload.update(overrides)
    return payload


def missing_payload(**overrides) -> dict:
    """A probe result from an interpreter without the package."""
    return probe_payload(
        installed=False,
        location=None,
        dist_version=None,
        cli_module=False,
        import_error="ModuleNotFoundError: No module named 'godot_e2e'",
        **overrides,
    )


def completed(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(stdout=json.dumps(payload) + "\n", stderr="", returncode=0)


def run_probe(payload, *, cli: str | None = None, env: dict | None = None):
    """Probe with the target interpreter's answer and PATH stubbed."""
    returns = payload if isinstance(payload, list) else [payload]
    with patch.object(e2e_env.subprocess, "run",
                      side_effect=[completed(p) for p in returns]) as run:
        with patch.object(e2e_env, "find_cli", return_value=cli):
            results = [
                probe_e2e_python_env(TARGET_PYTHON, env=env if env is not None else {})
                for _ in returns
            ]
    return (results[0] if not isinstance(payload, list) else results), run


class TestAvailable:
    def test_reports_interpreter_and_version(self):
        info, _ = run_probe(probe_payload())
        assert info.status == STATUS_OK
        assert info.available is True
        assert info.interpreter == TARGET_PYTHON
        assert TARGET_PYTHON in info.summary()
        assert "1.3.0" in info.summary()

    def test_run_command_goes_through_the_verified_interpreter(self):
        """Not a bare `godot-e2e`: PATH is exactly what we do not trust."""
        info, _ = run_probe(probe_payload(), cli=OTHER_CLI)
        assert info.run_command == [TARGET_PYTHON, "-m", "godot_e2e.cli"]
        assert "run the suite with:" in "\n".join(info.diagnostic_lines())

    def test_falls_back_to_the_console_script_inside_the_target_env(self):
        cli = os.path.join(TARGET_SCRIPTS, "godot-e2e")
        info, _ = run_probe(probe_payload(cli_module=False), cli=cli)
        assert info.cli_in_target_env is True
        assert info.run_command == [cli]

    def test_diagnostics_name_the_environment(self):
        lines = "\n".join(run_probe(probe_payload())[0].diagnostic_lines())
        assert TARGET_PYTHON in lines
        assert TARGET_PREFIX in lines
        assert "VIRTUAL_ENV" in lines


class TestMissing:
    def test_names_the_interpreter_and_the_install_command(self):
        info, _ = run_probe(missing_payload())
        assert info.status == STATUS_MISSING
        assert info.available is False
        assert info.run_command is None
        assert TARGET_PYTHON in info.summary()
        assert info.install_command == [
            TARGET_PYTHON, "-m", "pip", "install", "godot-e2e",
        ]
        assert format_command(info.install_command) in "\n".join(
            info.diagnostic_lines()
        )

    def test_console_script_in_this_env_but_package_unimportable(self):
        """A broken install in the right place, not an absent one."""
        cli = os.path.join(TARGET_SCRIPTS, "godot-e2e")
        info, _ = run_probe(missing_payload(), cli=cli)
        assert info.status == STATUS_MISSING
        assert info.cli_in_target_env is True
        assert "reinstall" in "\n".join(info.diagnostic_lines())


class TestOtherEnvironment:
    """The reported symptom: installed, visible on PATH, still 'missing'."""

    def test_is_not_reported_as_a_plain_absence(self):
        info, _ = run_probe(missing_payload(), cli=OTHER_CLI)
        assert info.status == STATUS_OTHER_ENVIRONMENT
        assert info.cli_in_target_env is False
        assert OTHER_CLI in info.summary()
        assert "another Python environment" in info.summary()

    def test_diagnostic_points_at_both_environments(self):
        lines = "\n".join(
            run_probe(missing_payload(), cli=OTHER_CLI)[0].diagnostic_lines()
        )
        assert OTHER_CLI in lines
        assert TARGET_PYTHON in lines
        assert "next: " in lines

    def test_activated_virtualenv_that_does_not_own_the_interpreter(self):
        info, _ = run_probe(
            missing_payload(),
            env={"VIRTUAL_ENV": os.path.join("/opt", "envs", "other")},
        )
        assert info.virtual_env_mismatch is True
        assert "does not contain" in "\n".join(info.diagnostic_lines())

    def test_matching_virtualenv_is_not_flagged(self):
        info, _ = run_probe(missing_payload(), env={"VIRTUAL_ENV": TARGET_PREFIX})
        assert info.virtual_env_mismatch is False


class TestBrokenInstall:
    def test_registered_distribution_that_fails_to_import(self):
        info, _ = run_probe(
            probe_payload(
                installed=False,
                location=None,
                cli_module=False,
                import_error="ModuleNotFoundError: No module named 'pytest'",
            )
        )
        assert info.status == STATUS_IMPORT_ERROR
        assert TARGET_PYTHON in info.summary()
        assert "pytest" in "\n".join(info.diagnostic_lines())


class TestProbeFailure:
    def test_unusable_interpreter_is_reported_not_raised(self):
        with patch.object(e2e_env.subprocess, "run", side_effect=FileNotFoundError()):
            with patch.object(e2e_env, "find_cli", return_value=None):
                info = probe_e2e_python_env(TARGET_PYTHON, env={})
        assert info.status == STATUS_PROBE_FAILED
        assert info.available is False
        assert TARGET_PYTHON in info.summary()

    def test_malformed_probe_output(self):
        with patch.object(
            e2e_env.subprocess, "run",
            return_value=SimpleNamespace(stdout="not json", stderr="", returncode=0),
        ):
            with patch.object(e2e_env, "find_cli", return_value=None):
                info = probe_e2e_python_env(TARGET_PYTHON, env={})
        assert info.status == STATUS_PROBE_FAILED
        assert "malformed" in info.summary()

    def test_trailing_json_line_wins_over_startup_noise(self):
        payload = probe_payload()
        noisy = SimpleNamespace(
            stdout="sitecustomize: hello\n" + json.dumps(payload),
            stderr="", returncode=0,
        )
        with patch.object(e2e_env.subprocess, "run", return_value=noisy):
            with patch.object(e2e_env, "find_cli", return_value=None):
                info = probe_e2e_python_env(TARGET_PYTHON, env={})
        assert info.status == STATUS_OK


class TestRedetection:
    """AC-03 — a corrected environment must not inherit an old verdict."""

    def test_second_probe_sees_the_fixed_environment(self):
        results, run = run_probe([missing_payload(), probe_payload()])
        assert [r.status for r in results] == [STATUS_MISSING, STATUS_OK]
        assert run.call_count == 2, "each probe must re-question the interpreter"

    def test_module_keeps_no_probe_state(self):
        cached = [
            name for name, value in vars(e2e_env).items()
            if isinstance(value, dict) and not name.startswith("__")
        ]
        assert cached == []
        assert not hasattr(probe_e2e_python_env, "cache_clear")


class TestSummaryAlwaysNamesTheInterpreter:
    """AC-01 — no failure message may hide which environment was used."""

    @pytest.mark.parametrize("payload,cli", [
        (probe_payload(), None),
        (missing_payload(), None),
        (missing_payload(), OTHER_CLI),
        (probe_payload(installed=False, import_error="ImportError: boom"), None),
    ])
    def test_interpreter_present(self, payload, cli):
        info, _ = run_probe(payload, cli=cli)
        assert TARGET_PYTHON in info.summary()
        assert TARGET_PYTHON in "\n".join(info.diagnostic_lines())


class TestCliDiscovery:
    def test_windows_and_posix_names_are_both_tried(self):
        tried = []

        def fake_which(name, path=None):
            tried.append(name)
            return OTHER_CLI if name.endswith(".exe") else None

        with patch.object(e2e_env.shutil, "which", side_effect=fake_which):
            found = e2e_env.find_cli({"PATH": OTHER_SCRIPTS})
        assert found == OTHER_CLI
        assert tried[:2] == ["godot-e2e", "godot-e2e.exe"]

    def test_absent_command_is_none(self):
        with patch.object(e2e_env.shutil, "which", return_value=None):
            assert e2e_env.find_cli({"PATH": OTHER_SCRIPTS}) is None


class TestFormatCommand:
    def test_quotes_paths_with_spaces(self):
        assert format_command([r"C:\Program Files\python.exe", "-m", "pip"]) == (
            r'"C:\Program Files\python.exe" -m pip'
        )

    def test_none_for_empty(self):
        assert format_command(None) is None
        assert format_command([]) is None


class TestReportedDict:
    def test_to_dict_is_json_serializable_and_complete(self):
        info, _ = run_probe(missing_payload(), cli=OTHER_CLI)
        data = json.loads(json.dumps(info.to_dict()))
        assert data["status"] == STATUS_OTHER_ENVIRONMENT
        assert data["interpreter"] == TARGET_PYTHON
        assert data["available"] is False
        assert data["run_command"] is None
        assert data["diagnostics"]


class TestNoRunner:
    """Importable is not runnable — and callers gate the E2E run on this.

    `-m godot_e2e.cli` or a console script inside the target environment
    is what actually launches the suite. A partial install that imports
    the package but supplies neither must not report success.
    """

    def _payload(self):
        return probe_payload(cli_module=False)

    def test_no_entry_point_at_all_is_not_ok(self):
        info, _ = run_probe(self._payload(), cli=None)
        assert info.status == e2e_env.STATUS_NO_RUNNER
        assert info.available is False
        assert info.run_command is None

    def test_console_script_in_another_env_does_not_rescue_it(self):
        info, _ = run_probe(self._payload(), cli=OTHER_CLI)
        assert info.status == e2e_env.STATUS_NO_RUNNER
        assert info.available is False
        assert info.run_command is None

    def test_summary_names_interpreter_and_the_missing_entry_point(self):
        info, _ = run_probe(self._payload(), cli=None)
        assert TARGET_PYTHON in info.summary()
        assert "godot_e2e.cli" in info.summary()

    def test_remediation_replaces_the_broken_install(self):
        info, _ = run_probe(self._payload(), cli=None)
        assert info.install_command == [
            TARGET_PYTHON, "-m", "pip", "install", "--force-reinstall", "godot-e2e",
        ]
        lines = "\n".join(info.diagnostic_lines())
        assert "--force-reinstall" in lines
        assert "run the suite with:" not in lines

    def test_cli_import_error_is_surfaced(self):
        info, _ = run_probe(
            probe_payload(
                cli_module=False,
                cli_module_error="ModuleNotFoundError: No module named 'godot_e2e.cli'",
            ),
            cli=None,
        )
        assert "godot_e2e.cli" in "\n".join(info.diagnostic_lines())

    def test_cli_exits_non_zero(self):
        with patch.object(e2e_env, "probe_e2e_python_env",
                          return_value=run_probe(self._payload(), cli=None)[0]):
            assert e2e_env.main([]) == 1

    def test_broken_install_is_reinstalled_not_installed(self):
        info, _ = run_probe(
            probe_payload(installed=False, location=None, cli_module=False,
                          import_error="ModuleNotFoundError: No module named 'pytest'"),
            cli=None,
        )
        assert info.status == STATUS_IMPORT_ERROR
        assert "--force-reinstall" in " ".join(info.install_command)


class TestRunnableStatesExitZero:
    def test_cli_module_present(self):
        with patch.object(e2e_env, "probe_e2e_python_env",
                          return_value=run_probe(probe_payload())[0]):
            assert e2e_env.main([]) == 0

    def test_console_script_inside_target_env(self):
        cli = os.path.join(TARGET_SCRIPTS, "godot-e2e")
        info, _ = run_probe(probe_payload(cli_module=False), cli=cli)
        assert info.status == STATUS_OK
        assert info.run_command == [cli]
