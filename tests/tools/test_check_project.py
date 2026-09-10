"""Tests for check_project.py."""
import os
import subprocess
import sys
import pytest
import tempfile

# tests/tools/ → project_root/tools/
CHECK_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools", "check_project.py"
)


def run_check(project_dir: str, *flags: str) -> tuple[str, int]:
    """Run check_project.py and return (stdout, exit_code)."""
    result = subprocess.run(
        [sys.executable, CHECK_SCRIPT, project_dir, *flags],
        capture_output=True, text=True, timeout=90,
    )
    return result.stdout, result.returncode


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _seed_scaffolded_project(project_dir: str):
    """Build a directory tree that satisfies every static --build check.
    Deliberately omits `.claude/godotmaker.yaml` so the headless step
    can be tested explicitly by each caller.
    """
    # project.godot with [application] + godot-e2e plugin enabled
    with open(os.path.join(project_dir, "project.godot"), "w", encoding="utf-8") as f:
        f.write(
            'config_version=5\n\n'
            '[application]\n'
            'config/name="Test"\n\n'
            '[autoload]\n'
            'AutomationServer="*res://addons/godot_e2e/automation_server.gd"\n\n'
            '[editor_plugins]\n'
            'enabled=PackedStringArray('
            '"res://addons/gecs/plugin.cfg",'
            '"res://addons/gdUnit4/plugin.cfg",'
            '"res://addons/godot_e2e/plugin.cfg"'
            ')\n'
        )
    # Required addon dirs with minimal addon-only shape.
    required_files = {
        "gecs": ("plugin.cfg",),
        "gdUnit4": (
            "plugin.cfg",
            os.path.join("bin", "GdUnitCmdTool.gd"),
            os.path.join("src", "core", "runners", "GdUnitTestCIRunner.gd"),
        ),
        "godot_e2e": ("plugin.cfg", "automation_server.gd"),
    }
    for addon, files in required_files.items():
        addon_dir = os.path.join(project_dir, "addons", addon)
        os.makedirs(addon_dir, exist_ok=True)
        for rel_path in files:
            path = os.path.join(addon_dir, rel_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("# fixture\n")
    # e2e/conftest.py with GodotE2E import
    e2e_dir = os.path.join(project_dir, "e2e")
    os.makedirs(e2e_dir, exist_ok=True)
    with open(os.path.join(e2e_dir, "conftest.py"), "w", encoding="utf-8") as f:
        f.write("from godot_e2e import GodotE2E\n")
    # git repo with one commit
    subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True)
    subprocess.run(["git", "-C", project_dir, "config", "user.email", "x@y.z"], check=True)
    subprocess.run(["git", "-C", project_dir, "config", "user.name", "x"], check=True)
    subprocess.run(["git", "-C", project_dir, "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", project_dir, "commit", "-q", "-m", "init"],
        check=True,
    )


def _write_fake_godot(
    project_dir: str,
    *,
    name: str = "fake-godot",
    output: str = "",
    returncode: int = 0,
) -> str:
    if os.name == "nt":
        path = os.path.join(project_dir, f"{name}.cmd")
        with open(path, "w", encoding="utf-8") as f:
            lines = ["@echo off"]
            if output:
                for line in output.splitlines():
                    lines.append(f"echo {line}")
            lines.append(f"exit /B {returncode}")
            f.write("\n".join(lines) + "\n")
    else:
        path = os.path.join(project_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            lines = ["#!/bin/sh"]
            if output:
                for line in output.splitlines():
                    escaped = line.replace("'", "'\"'\"'")
                    lines.append(f"printf '%s\\n' '{escaped}'")
            lines.append(f"exit {returncode}")
            f.write("\n".join(lines) + "\n")
        os.chmod(path, 0o755)
    return path


def _write_godot_config(project_dir: str, godot_path: str):
    os.makedirs(os.path.join(project_dir, ".claude"), exist_ok=True)
    with open(os.path.join(project_dir, ".claude", "godotmaker.yaml"), "w", encoding="utf-8") as f:
        f.write(f'godot_path: "{godot_path}"\n')


class TestBuildCheck:
    """`--build` is the gm-scaffold readiness check — verifies all of
    Step 4 (project.godot, addons, plugin, conftest, git, headless).
    Successful cases use a fake Godot executable so headless remains a
    real gate without depending on a developer machine install."""

    def test_no_project_godot(self, project_dir):
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "[FAIL]" in stdout
        assert "project.godot" in stdout

    def test_full_scaffold_passes_static(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        stdout, code = run_check(project_dir, "--build")
        assert code == 0, f"expected pass, got:\n{stdout}"
        assert "project.godot exists" in stdout
        assert "[application] section" in stdout
        for addon in ("gecs", "gdUnit4", "godot_e2e"):
            assert f"addons/{addon}/ present" in stdout
            assert f"addons/{addon}/plugin.cfg present" in stdout
        assert "godot-e2e plugin enabled" in stdout
        assert "AutomationServer autoload registered" in stdout
        assert "e2e/conftest.py imports GodotE2E" in stdout
        assert "git HEAD resolves" in stdout

    def test_missing_application_section(self, project_dir):
        with open(os.path.join(project_dir, "project.godot"), "w") as f:
            f.write("[rendering]\n")
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "[FAIL]" in stdout
        assert "[application]" in stdout

    def test_missing_addon_directory_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        # remove gecs to simulate forgotten addon install
        import shutil
        shutil.rmtree(os.path.join(project_dir, "addons", "gecs"))
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "addons/gecs/ missing" in stdout

    def test_addon_without_plugin_cfg_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        os.remove(os.path.join(project_dir, "addons", "gecs", "plugin.cfg"))

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "addons/gecs/plugin.cfg missing" in stdout

    @pytest.mark.parametrize("addon", ("gecs", "gdUnit4", "godot_e2e"))
    def test_full_repo_addon_with_nested_project_godot_fails(self, project_dir, addon):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        with open(
            os.path.join(project_dir, "addons", addon, "project.godot"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("[application]\nconfig/name=\"Nested\"\n")

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert f"addons/{addon}/ contains nested project.godot" in stdout

    def test_gdunit_without_cmd_tool_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        os.remove(
            os.path.join(
                project_dir,
                "addons",
                "gdUnit4",
                "bin",
                "GdUnitCmdTool.gd",
            )
        )

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "addons/gdUnit4/bin/GdUnitCmdTool.gd missing" in stdout

    def test_gdunit_without_cmd_runner_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        os.remove(
            os.path.join(
                project_dir,
                "addons",
                "gdUnit4",
                "src",
                "core",
                "runners",
                "GdUnitTestCIRunner.gd",
            )
        )

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "addons/gdUnit4/src/core/runners/GdUnitTestCIRunner.gd missing" in stdout

    def test_godot_e2e_plugin_not_enabled_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        # rewrite project.godot without the godot_e2e plugin entry
        with open(os.path.join(project_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write(
                'config_version=5\n[application]\nconfig/name="Test"\n\n'
                '[editor_plugins]\nenabled=PackedStringArray("res://addons/gecs/plugin.cfg")\n'
            )
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "godot-e2e plugin not enabled" in stdout

    def test_godot_e2e_autoload_missing_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        # rewrite project.godot without the AutomationServer autoload entry
        with open(os.path.join(project_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write(
                'config_version=5\n[application]\nconfig/name="Test"\n\n'
                '[editor_plugins]\nenabled=PackedStringArray('
                '"res://addons/godot_e2e/plugin.cfg")\n'
            )
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "AutomationServer autoload missing" in stdout

    def test_godot_e2e_autoload_duplicate_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        with open(os.path.join(project_dir, "project.godot"), "a", encoding="utf-8") as f:
            f.write(
                '\n[autoload]\n'
                'AutomationServer="*res://addons/godot_e2e/automation_server.gd"\n'
            )
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "AutomationServer autoload duplicated" in stdout

    def test_conftest_without_godote2e_import_fails(self, project_dir):
        _seed_scaffolded_project(project_dir)
        _write_godot_config(project_dir, _write_fake_godot(project_dir))
        with open(os.path.join(project_dir, "e2e", "conftest.py"), "w", encoding="utf-8") as f:
            f.write("# empty\n")
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "does not import GodotE2E" in stdout

    def test_git_dir_missing_fails(self, project_dir):
        """No .git/ at all — fail with 'missing' message."""
        # Seed enough static state to reach the git check (project.godot
        # exists; addon / plugin / conftest checks fail noisily but don't
        # short-circuit, so the git fail message is still emitted).
        with open(os.path.join(project_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write('[application]\nconfig/name="Test"\n')
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert ".git/ missing" in stdout

    def test_git_without_head_fails(self, project_dir):
        """`.git/` exists but no commits → HEAD doesn't resolve. Build a
        fresh project (no _seed_scaffolded_project) so we never have to
        rmtree a git-managed `.git/` (Windows holds file handles open
        and rmtree fails with PermissionError)."""
        with open(os.path.join(project_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write('[application]\nconfig/name="Test"\n')
        subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True)
        stdout, code = run_check(project_dir, "--build")
        assert code == 1
        assert "HEAD does not resolve" in stdout

    def test_headless_fails_when_godot_path_missing(self, project_dir):
        _seed_scaffolded_project(project_dir)
        # No .claude/godotmaker.yaml means the build gate cannot run
        # headless parse, so --build must fail.
        stdout, code = run_check(project_dir, "--build")
        assert "godot_path missing" in stdout
        assert "[FAIL]" in stdout
        assert code == 1

    def test_codex_build_check_uses_agents_godotmaker_yaml(self, project_dir):
        _seed_scaffolded_project(project_dir)
        os.makedirs(os.path.join(project_dir, ".godotmaker"), exist_ok=True)
        os.makedirs(os.path.join(project_dir, ".agents"), exist_ok=True)
        with open(os.path.join(project_dir, ".godotmaker", "config.yaml"), "w", encoding="utf-8") as f:
            f.write("agent: codex\n")
        with open(os.path.join(project_dir, ".agents", "godotmaker.yaml"), "w", encoding="utf-8") as f:
            f.write("godot_path: definitely-missing-godot-exe\n")

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "godot executable not found" in stdout
        assert ".agents" in stdout

    def test_headless_shutdown_note_does_not_block_headless_parse(self, project_dir):
        _seed_scaffolded_project(project_dir)
        fake_godot = _write_fake_godot(
            project_dir,
            output="ERROR: 7 resources still in use at exit (run with --verbose for details).",
        )
        _write_godot_config(project_dir, fake_godot)

        stdout, code = run_check(project_dir, "--build")

        assert code == 0, stdout
        assert "no blocking diagnostics" in stdout
        assert "shutdown notes" in stdout

    def test_headless_build_redirects_log_into_godotmaker_logs(self, project_dir):
        _seed_scaffolded_project(project_dir)
        os.makedirs(os.path.join(project_dir, ".godotmaker"), exist_ok=True)
        argv_file = os.path.join(project_dir, "godot_argv.txt")
        if os.name == "nt":
            godot = os.path.join(project_dir, "record-godot.cmd")
            with open(godot, "w", encoding="utf-8") as f:
                f.write(f'@echo off\r\necho %* > "{argv_file}"\r\nexit /B 0\r\n')
        else:
            godot = os.path.join(project_dir, "record-godot")
            with open(godot, "w", encoding="utf-8") as f:
                f.write(
                    '#!/bin/sh\n'
                    f'printf "%s\\n" "$@" > "{argv_file}"\n'
                    'exit 0\n'
                )
            os.chmod(godot, 0o755)
        _write_godot_config(project_dir, godot)

        stdout, code = run_check(project_dir, "--build")
        assert code == 0, stdout

        with open(argv_file, encoding="utf-8") as f:
            recorded = f.read()
        assert "--log-file" in recorded
        assert ".godotmaker" in recorded
        assert "godot-static-" in recorded

    def test_headless_display_and_objectdb_noise_does_not_block_headless_parse(
        self, project_dir
    ):
        _seed_scaffolded_project(project_dir)
        fake_godot = _write_fake_godot(
            project_dir,
            output=(
                "ERROR: Screen index 0 is invalid.\n"
                "ERROR: ObjectDB instances leaked at exit (run with --verbose for details)."
            ),
        )
        _write_godot_config(project_dir, fake_godot)

        stdout, code = run_check(project_dir, "--build")

        assert code == 0, stdout
        assert "no blocking diagnostics" in stdout
        assert "shutdown notes" in stdout

    def test_headless_script_error_is_blocking(self, project_dir):
        _seed_scaffolded_project(project_dir)
        fake_godot = _write_fake_godot(
            project_dir,
            output="SCRIPT ERROR: Parse Error: Identifier 'BirdController' not declared.",
        )
        _write_godot_config(project_dir, fake_godot)

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "blocking diagnostic" in stdout
        assert "BirdController" in stdout

    def test_headless_unknown_error_is_blocking_even_with_zero_exit(self, project_dir):
        _seed_scaffolded_project(project_dir)
        fake_godot = _write_fake_godot(
            project_dir,
            output="ERROR: Provider emitted an uncategorized runtime diagnostic.",
        )
        _write_godot_config(project_dir, fake_godot)

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "blocking diagnostic" in stdout
        assert "uncategorized runtime diagnostic" in stdout

    def test_headless_shader_error_is_blocking_even_with_zero_exit(self, project_dir):
        _seed_scaffolded_project(project_dir)
        fake_godot = _write_fake_godot(
            project_dir,
            output="SHADER ERROR: Invalid shader code.",
        )
        _write_godot_config(project_dir, fake_godot)

        stdout, code = run_check(project_dir, "--build")

        assert code == 1
        assert "blocking diagnostic" in stdout
        assert "Invalid shader code" in stdout


class TestEcsCheck:
    def test_no_gecs_addon(self, project_dir):
        stdout, code = run_check(project_dir, "--ecs")
        assert code == 1
        assert "[FAIL]" in stdout
        assert "gecs" in stdout

    def test_with_gecs_and_components(self, project_dir):
        os.makedirs(os.path.join(project_dir, "addons", "gecs"))
        comp_dir = os.path.join(project_dir, "components")
        os.makedirs(comp_dir)
        with open(os.path.join(comp_dir, "health.gd"), "w") as f:
            f.write("extends Component\nvar current: int = 100\n")
        sys_dir = os.path.join(project_dir, "systems")
        os.makedirs(sys_dir)
        with open(os.path.join(sys_dir, "movement_system.gd"), "w") as f:
            f.write("extends System\nfunc _process(delta):\n\tpass\n")

        stdout, code = run_check(project_dir, "--ecs")
        assert code == 0
        assert "[PASS]" in stdout


class TestTestsCheck:
    def test_no_gdunit(self, project_dir):
        stdout, code = run_check(project_dir, "--tests")
        assert code == 1
        assert "gdUnit4" in stdout

    def test_system_without_test(self, project_dir):
        os.makedirs(os.path.join(project_dir, "addons", "gdUnit4"))
        sys_dir = os.path.join(project_dir, "systems")
        os.makedirs(sys_dir)
        with open(os.path.join(sys_dir, "move.gd"), "w") as f:
            f.write("extends System\n")

        stdout, code = run_check(project_dir, "--tests")
        assert code == 1
        assert "[FAIL]" in stdout
        assert "test" in stdout.lower()

    def test_system_with_test(self, project_dir):
        os.makedirs(os.path.join(project_dir, "addons", "gdUnit4"))
        sys_dir = os.path.join(project_dir, "systems")
        os.makedirs(sys_dir)
        with open(os.path.join(sys_dir, "move.gd"), "w") as f:
            f.write("extends System\n")
        test_dir = os.path.join(project_dir, "test")
        os.makedirs(test_dir)
        with open(os.path.join(test_dir, "test_move.gd"), "w") as f:
            f.write("extends GdUnitTestSuite\n")

        stdout, code = run_check(project_dir, "--tests")
        assert code == 0


class TestPlanCheck:
    def test_no_plan(self, project_dir):
        stdout, code = run_check(project_dir, "--plan")
        assert code == 1
        assert "PLAN.md" in stdout

    def test_with_plan_and_structure(self, project_dir):
        with open(os.path.join(project_dir, "PLAN.md"), "w") as f:
            f.write("# Plan\n## Task Status\n| 1 | Move | completed | done |\n")
        with open(os.path.join(project_dir, "STRUCTURE.md"), "w") as f:
            f.write("# Structure\n## Component Registry\n## System Schedule\n")

        stdout, code = run_check(project_dir, "--plan")
        assert code == 0
        assert "[PASS]" in stdout


class TestE2eCheckFallback:
    """`check_e2e()` falls back to scanning the project for files whose
    path contains "e2e" / "end_to_end" / "integration_test" when
    `e2e/test_*.py` is empty (legacy projects that put e2e tests
    elsewhere). Two filters layered on top of the path match: skip
    pytest infrastructure (`conftest.py` / `__init__.py`), and require
    `test_*.py` / `*_test.py` naming so helper modules sharing the path
    aren't reported as e2e tests with "no test functions".

    Fallback fires only when `e2e/test_*.py` is empty — every test here
    creates `e2e/conftest.py` (so the standard-location-conftest check
    passes) but leaves `e2e/` without `test_*.py`, then plants a decoy
    elsewhere to exercise the filters."""

    def _seed_e2e_capable_project(self, project_dir: str):
        """Minimal project.godot + addons/godot_e2e/ + e2e/conftest.py
        so check_e2e()'s plugin / standard-conftest checks pass and the
        fallback runs."""
        with open(os.path.join(project_dir, "project.godot"), "w", encoding="utf-8") as f:
            f.write(
                'config_version=5\n[application]\nconfig/name="Test"\n\n'
                '[editor_plugins]\nenabled=PackedStringArray('
                '"res://addons/godot_e2e/plugin.cfg")\n'
            )
        os.makedirs(os.path.join(project_dir, "addons", "godot_e2e"))
        os.makedirs(os.path.join(project_dir, "e2e"))
        with open(os.path.join(project_dir, "e2e", "conftest.py"), "w", encoding="utf-8") as f:
            f.write("from godot_e2e import GodotE2E\n")

    def test_conftest_in_legacy_e2e_path_no_phantom_fail(self, project_dir):
        """`e2e/conftest.py` (a pytest infrastructure file) must not be
        misclassified as an e2e test and then failed for "no test
        functions" — the historical regression that motivated this guard.
        The legitimate "No e2e test files found in e2e/" FAIL is still
        emitted; only the phantom conftest FAIL is gone."""
        self._seed_e2e_capable_project(project_dir)
        # Decoy: a SECOND conftest.py at a legacy e2e location. The
        # standard-location one (e2e/conftest.py) is also a candidate
        # but the dual-path planting hardens the test against rglob
        # ordering quirks.
        legacy = os.path.join(project_dir, "tests", "e2e")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "conftest.py"), "w", encoding="utf-8") as f:
            f.write("# legacy conftest\n")

        stdout, _ = run_check(project_dir, "--e2e")
        assert "conftest.py has no test functions" not in stdout
        assert "conftest.py is too short" not in stdout

    def test_init_py_in_legacy_e2e_path_not_misclassified(self, project_dir):
        """`__init__.py` is package metadata, not a test — must be skipped
        by the fallback."""
        self._seed_e2e_capable_project(project_dir)
        legacy = os.path.join(project_dir, "tests", "e2e")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "__init__.py"), "w", encoding="utf-8") as f:
            f.write("")

        stdout, _ = run_check(project_dir, "--e2e")
        assert "__init__.py has no test functions" not in stdout
        assert "__init__.py is too short" not in stdout

    def test_helper_module_in_legacy_e2e_path_not_misclassified(self, project_dir):
        """A helper module (fixtures.py / utils.py / …) sharing the path
        with "e2e" must not be misclassified as an e2e test by the
        fallback — it lacks the `test_*` / `*_test` naming and stays out
        of `e2e_files`."""
        self._seed_e2e_capable_project(project_dir)
        legacy = os.path.join(project_dir, "tests", "e2e")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "fixtures.py"), "w", encoding="utf-8") as f:
            f.write(
                "# Substantial enough that the 'too short' rule wouldn't\n"
                "# fire if this were misclassified — the assertion below\n"
                "# guards specifically against the misclassification.\n"
                "def make_player():\n"
                "    return {'hp': 100}\n"
            )

        stdout, _ = run_check(project_dir, "--e2e")
        assert "fixtures.py has no test functions" not in stdout
        assert "fixtures.py is too short" not in stdout

    def test_legacy_test_file_still_picked_up(self, project_dir):
        """Regression guard for the positive path: a properly-named legacy
        e2e test (`test_*.py` under a path containing "e2e") is still
        matched by the fallback after the filter additions."""
        self._seed_e2e_capable_project(project_dir)
        legacy = os.path.join(project_dir, "tests", "e2e")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "test_smoke.py"), "w", encoding="utf-8") as f:
            f.write(
                "from godot_e2e import GodotE2E\n"
                "def test_smoke(game):\n"
                "    assert game is not None\n"
            )

        stdout, _ = run_check(project_dir, "--e2e")
        assert "test_smoke.py" in stdout
        assert "No e2e test files found in e2e/" not in stdout


class TestAllCheck:
    def test_empty_project_fails(self, project_dir):
        stdout, code = run_check(project_dir, "--all")
        assert code == 1
        assert "[FAIL]" in stdout
        assert "Result: CHECKS FAILED" in stdout

    def test_summary_counts(self, project_dir):
        stdout, code = run_check(project_dir, "--all")
        assert "Total:" in stdout
        assert "PASS:" in stdout
        assert "FAIL:" in stdout
