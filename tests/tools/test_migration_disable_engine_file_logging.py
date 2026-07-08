"""Tests for migrations/20260708145839_disable_engine_file_logging.py.

The migration injects `[debug] file_logging/enable_file_logging=false` into an
existing project's `project.godot`, so projects scaffolded before the template
change stop writing Godot's uncapped default `user://logs/godot.log` to the
system drive. Every step is idempotent, and an explicit existing value is
preserved.
"""
import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260708145839_disable_engine_file_logging.py"
)


@pytest.fixture
def migration_module():
    spec = importlib.util.spec_from_file_location(
        "disable_engine_file_logging", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _debug_section(text: str) -> str:
    """Return the body of the [debug] section (up to the next header)."""
    lines = text.splitlines()
    out: list[str] = []
    in_debug = False
    for line in lines:
        if line.strip() == "[debug]":
            in_debug = True
            continue
        if in_debug and line.strip().startswith("[") and line.strip().endswith("]"):
            break
        if in_debug:
            out.append(line)
    return "\n".join(out)


_BASE = (
    'config_version=5\n\n'
    '[application]\n\n'
    'config/name="Test"\n'
    'run/main_scene="res://scenes/main.tscn"\n\n'
    '[rendering]\n\n'
    'renderer/rendering_method="gl_compatibility"\n'
)


def test_adds_debug_section_when_absent(migration_module, tmp_path):
    (tmp_path / "project.godot").write_text(_BASE, encoding="utf-8")

    migration_module.migrate(tmp_path)

    text = (tmp_path / "project.godot").read_text(encoding="utf-8")
    assert text.count("[debug]") == 1
    assert "file_logging/enable_file_logging=false" in _debug_section(text)
    # Untouched sections survive.
    assert "[application]" in text
    assert 'renderer/rendering_method="gl_compatibility"' in text


def test_adds_key_to_existing_debug_section(migration_module, tmp_path):
    (tmp_path / "project.godot").write_text(
        _BASE + "\n[debug]\n\nsettings/profiler/max_functions=16384\n",
        encoding="utf-8",
    )

    migration_module.migrate(tmp_path)

    text = (tmp_path / "project.godot").read_text(encoding="utf-8")
    assert text.count("[debug]") == 1  # no duplicate section
    debug = _debug_section(text)
    assert "file_logging/enable_file_logging=false" in debug
    assert "settings/profiler/max_functions=16384" in debug  # sibling key kept


def test_idempotent_on_rerun(migration_module, tmp_path):
    (tmp_path / "project.godot").write_text(_BASE, encoding="utf-8")

    migration_module.migrate(tmp_path)
    first = (tmp_path / "project.godot").read_text(encoding="utf-8")
    migration_module.migrate(tmp_path)
    second = (tmp_path / "project.godot").read_text(encoding="utf-8")

    assert first == second
    assert second.count("file_logging/enable_file_logging") == 1


def test_preserves_explicit_true(migration_module, tmp_path):
    (tmp_path / "project.godot").write_text(
        _BASE + "\n[debug]\n\nfile_logging/enable_file_logging=true\n",
        encoding="utf-8",
    )

    migration_module.migrate(tmp_path)

    text = (tmp_path / "project.godot").read_text(encoding="utf-8")
    assert "file_logging/enable_file_logging=true" in text
    assert "enable_file_logging=false" not in text
    assert text.count("file_logging/enable_file_logging") == 1


def test_preserves_comments(migration_module, tmp_path):
    seeded = "; Engine configuration file.\n; hand-written note\n" + _BASE
    (tmp_path / "project.godot").write_text(seeded, encoding="utf-8")

    migration_module.migrate(tmp_path)

    text = (tmp_path / "project.godot").read_text(encoding="utf-8")
    assert "; Engine configuration file." in text
    assert "; hand-written note" in text
    assert "file_logging/enable_file_logging=false" in text


def test_missing_project_godot_is_noop(migration_module, tmp_path):
    # No project.godot at all — must not raise and must not create one.
    migration_module.migrate(tmp_path)
    assert not (tmp_path / "project.godot").exists()
