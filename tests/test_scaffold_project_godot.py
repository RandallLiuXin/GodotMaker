"""The scaffolded project.godot template must disable Godot's default engine
file logging.

Unattended pipeline / E2E runs can re-raise a GDScript error every frame with
no human to stop them, and Godot's engine log has no per-file size cap, so the
default `user://logs/godot.log` (on the system drive) can grow without bound and
fill the disk. Disabling it at the project level covers every launch of the
generated project — pure-skill, cli, build, verify, and the external E2E
launcher alike — without depending on how Godot is invoked.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "skills/core/project-scaffold/templates/project.godot.tmpl"
SETTINGS_DOC = REPO_ROOT / "skills/core/project-scaffold/references/project_settings.md"


def test_project_godot_template_disables_default_file_logging():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "[debug]" in text
    assert "file_logging/enable_file_logging=false" in text


def test_project_settings_reference_documents_debug_file_logging():
    text = SETTINGS_DOC.read_text(encoding="utf-8")
    assert "### [debug]" in text
    assert "file_logging/enable_file_logging=false" in text
