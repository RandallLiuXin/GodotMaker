"""Disable Godot's default engine file logging in existing projects.

The scaffold `project.godot` template now sets
`[debug] file_logging/enable_file_logging=false` so a generated game does not
write Godot's default `user://logs/godot.log` — which lives on the system drive
and has no per-file size cap. An unattended E2E run that re-raises a GDScript
error every frame could otherwise grow that log without bound and fill the disk.

`project.godot` is target-project state written once at scaffold time (scaffold
is lifetime-once), so re-publishing the framework does not touch it. Existing
projects therefore need this migration to gain the setting.

Policy: only *add* the key when it is absent. If a project already sets
`file_logging/enable_file_logging` to either value, that is an explicit choice
and is preserved — we never flip a value the user (or a prior scaffold) wrote.
"""
from pathlib import Path

_KEY = "file_logging/enable_file_logging"
_LINE = f"{_KEY}=false"


def _has_key(text: str) -> bool:
    """True if the file already sets the key (any value, any spacing).

    The key only belongs under `[debug]`, so a whole-file scan is
    unambiguous — it cannot collide with a same-named key elsewhere.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_KEY) and "=" in stripped:
            return True
    return False


def migrate(target: Path) -> None:
    """target is the absolute path to the game project root.

    Idempotent: the key-presence check makes a re-run a no-op, and an
    explicit existing value is preserved rather than overwritten.
    """
    project_godot = target / "project.godot"
    if not project_godot.exists():
        print("  [skip] project.godot not found")
        return

    text = project_godot.read_text(encoding="utf-8")

    if _has_key(text):
        print(f"  [skip] {_KEY} already set; preserving existing choice")
        return

    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)

    debug_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == "[debug]"), None
    )
    if debug_idx is not None:
        # `[debug]` exists but lacks the key — insert it right after the
        # section header so it lands inside that section.
        lines.insert(debug_idx + 1, _LINE + newline)
        new_text = "".join(lines)
        print(f"  [done] added {_KEY} to existing [debug] section")
    else:
        # No `[debug]` section — append one at the end. Section order is
        # not significant to Godot's ConfigFile parser.
        sep = "" if (text == "" or text.endswith(newline)) else newline
        new_text = f"{text}{sep}{newline}[debug]{newline}{newline}{_LINE}{newline}"
        print("  [done] added [debug] section with default file logging disabled")

    project_godot.write_text(new_text, encoding="utf-8")
