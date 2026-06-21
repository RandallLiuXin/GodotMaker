"""Classify Godot headless output for mechanical gates."""
from __future__ import annotations

from dataclasses import dataclass
import re


_GODOT_DIAGNOSTIC_LINE = re.compile(
    r"^\s*(?P<label>(?:[A-Z_ ]+)?ERROR):\s+(?P<message>.+)$",
    re.MULTILINE,
)
_GD_LOC = re.compile(r"\s+at:\s+[^()]+\((.+):(\d+)\)")

_SHUTDOWN_NOTE_PATTERNS = (
    re.compile(r"\d+\s+resources?\s+still\s+in\s+use\s+at\s+exit", re.IGNORECASE),
    re.compile(r"Found\s+\d+\s+possible\s+orphan\s+nodes?\.?", re.IGNORECASE),
    re.compile(r"ObjectDB\s+instances?\s+leaked\s+at\s+exit", re.IGNORECASE),
    re.compile(r"Screen\s+index\s+\d+\s+is\s+invalid\.?", re.IGNORECASE),
)

_ENGINE_SOURCE_FILE = re.compile(
    r"(?:^|[/\\])(?:core|drivers|editor|main|modules|platform|scene|servers)[/\\].+\.cpp$"
)

@dataclass(frozen=True)
class GodotDiagnostic:
    message: str
    file: str = ""
    line: int = 0


@dataclass(frozen=True)
class GodotOutputClassification:
    blockers: list[GodotDiagnostic]
    shutdown_notes: list[str]


def _next_error_offset(text: str, start: int) -> int:
    match = _GODOT_DIAGNOSTIC_LINE.search(text, start)
    return match.start() if match else len(text)


def _is_shutdown_note(message: str) -> bool:
    return any(pattern.search(message) for pattern in _SHUTDOWN_NOTE_PATTERNS)


def _diagnostic_location(loc_match: re.Match[str] | None) -> tuple[str, int]:
    if not loc_match:
        return "", 0
    file = loc_match.group(1)
    if _ENGINE_SOURCE_FILE.search(file.replace("\\", "/")):
        return "", 0
    return file, int(loc_match.group(2))


def classify_godot_headless_output(
    output: str,
    *,
    returncode: int = 0,
) -> GodotOutputClassification:
    blockers: list[GodotDiagnostic] = []
    shutdown_notes: list[str] = []

    for match in _GODOT_DIAGNOSTIC_LINE.finditer(output):
        message = match.group("message").strip()
        bound = _next_error_offset(output, match.end())
        loc_match = _GD_LOC.search(output, match.end(), bound)

        if _is_shutdown_note(message):
            shutdown_notes.append(message)
            continue

        file, line = _diagnostic_location(loc_match)
        blockers.append(GodotDiagnostic(
            message=message,
            file=file,
            line=line,
        ))

    if returncode != 0 and not blockers:
        blockers.append(GodotDiagnostic(
            message=(
                f"godot exited {returncode} without a recognized blocking "
                "diagnostic"
            ),
        ))

    return GodotOutputClassification(
        blockers=blockers,
        shutdown_notes=shutdown_notes,
    )
