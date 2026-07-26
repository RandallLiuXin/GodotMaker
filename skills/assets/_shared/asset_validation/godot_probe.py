"""Run L3 inside a real headless Godot: import the project, then load and type-check.

Parsing a ``.tres`` in Python would only prove the text is well formed. It would
not prove Godot can import the project, that ``ResourceLoader.load`` returns an
object, or that the object is the declared ClassDB type -- and those are exactly
the failures that reach a worker as an unusable resource. So this level shells
out to Godot and asks it.

Two runs, because they answer different questions:

1. ``--import`` builds ``.godot/imported``. Without it a fresh checkout cannot
   load a texture at all, and its absence is a real L3 failure rather than a
   test-environment quirk.
2. ``--script`` runs ``probe.gd``, which loads each resource and writes a JSON
   report.

The verdict comes from the report file, never from the exit code or the console.
Godot 4.4 headless prints editor progress-dialog errors during ``--import`` and
resource errors during a failed load, and it exits ``0`` through both, so the
streams are captured for diagnostics only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._bridge import prefer_console_godot_path
from .contract import ValidationError

PROBE_SCRIPT = Path(__file__).resolve().parent / "probe.gd"

# The structural checks ``probe.gd`` implements, mirroring its ``KNOWN_CHECKS``;
# tests/assets/ asserts the two agree so neither can drift. Declaring it here as
# well is what lets a structure validator that asks for a check nobody wrote fail
# at registration, instead of failing every asset of that type at L4 -- or, worse,
# passing them, if the validator does not read the error the probe reported.
# A family adds its name to both lists together with the GDScript branch.
PROBE_CHECKS = ("texture2d", "atlas_texture", "spriteframes", "stylebox_texture")

# Godot's own import and script runs; generous because a first import of a
# project with many textures is not fast, and a hang must still end as a
# diagnosable failure rather than a stuck pipeline.
IMPORT_TIMEOUT = 300
SCRIPT_TIMEOUT = 300


class GodotProbeError(ValidationError):
    """Raised when Godot could not be asked, or did not answer."""


@dataclass(frozen=True)
class ProbeRequest:
    """One resource to load, the type it must be, and the L4 facts to collect."""

    res_path: str
    expected_type: str
    checks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.res_path,
            "expected_type": self.expected_type,
            "checks": list(self.checks),
        }


@dataclass(frozen=True)
class ProbeResult:
    """What Godot reported about one resource."""

    res_path: str
    expected_type: str
    loaded: bool
    godot_class: str
    type_matches: bool
    error: str | None = None
    structure: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.res_path,
            "expected_type": self.expected_type,
            "loaded": self.loaded,
            "class": self.godot_class,
            "type_matches": self.type_matches,
            "error": self.error,
            "structure": dict(self.structure),
        }


@dataclass(frozen=True)
class ProbeReport:
    """One Godot run: which engine answered, and what it said about each resource.

    The engine version travels with the answers because L3's verdict is only as
    good as the build that produced it, and "ready here, broken there" is exactly
    the report that needs it.
    """

    godot_version: str
    resources: tuple[ProbeResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "godot_version": self.godot_version,
            "resources": [result.to_dict() for result in self.resources],
        }


def _tail(text: str, limit: int = 2000) -> str:
    """Return the end of a Godot stream, which is where its errors are."""
    collapsed = (text or "").strip()
    if len(collapsed) <= limit:
        return collapsed
    return "..." + collapsed[-limit:]


class GodotProbe:
    """Loads generated artifacts through a headless Godot binary.

    ``godot_path`` is supplied by the caller rather than discovered here: a
    project already resolves it through ``tools/agent_runtime.read_godot_path``,
    and a validator that silently searched ``PATH`` could verify an asset with a
    different engine build than the project uses.
    """

    def __init__(
        self,
        godot_path: str,
        *,
        import_timeout: int = IMPORT_TIMEOUT,
        script_timeout: int = SCRIPT_TIMEOUT,
    ) -> None:
        if not isinstance(godot_path, str) or not godot_path.strip():
            raise GodotProbeError("godot_path must be a non-empty string")
        self._godot_path = prefer_console_godot_path(godot_path)
        self._import_timeout = import_timeout
        self._script_timeout = script_timeout

    @property
    def godot_path(self) -> str:
        return self._godot_path

    def _run(self, argv: list[str], *, timeout: int) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GodotProbeError(
                f"godot binary not found at {self._godot_path}: {exc}"
            ) from exc
        except OSError as exc:
            raise GodotProbeError(
                f"godot binary at {self._godot_path} could not be run: {exc}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise GodotProbeError(
                f"godot did not finish within {timeout}s: {' '.join(argv[1:])}"
            ) from exc

    def probe(
        self,
        project_root: Path,
        requests: Sequence[ProbeRequest],
    ) -> ProbeReport:
        """Import ``project_root`` and load every requested resource in one run."""
        if not requests:
            raise GodotProbeError("probe needs at least one resource request")
        root = Path(project_root)
        if not (root / "project.godot").is_file():
            raise GodotProbeError(
                f"{root} is not a Godot project: no project.godot"
            )
        if not PROBE_SCRIPT.is_file():
            raise GodotProbeError(f"the probe script is missing: {PROBE_SCRIPT}")

        with tempfile.TemporaryDirectory(prefix="godotmaker-l3-") as workspace:
            work = Path(workspace)
            request_file = work / "request.json"
            report_file = work / "report.json"
            request_file.write_text(
                json.dumps({"resources": [item.to_dict() for item in requests]}),
                encoding="utf-8",
            )

            imported = self._run(
                [self._godot_path, "--headless", "--path", str(root), "--import"],
                timeout=self._import_timeout,
            )
            if imported.returncode != 0:
                raise GodotProbeError(
                    f"godot --import failed with exit code {imported.returncode}: "
                    f"{_tail(imported.stderr or imported.stdout)}"
                )

            ran = self._run(
                [
                    self._godot_path,
                    "--headless",
                    "--path",
                    str(root),
                    "--script",
                    str(PROBE_SCRIPT),
                    "--",
                    "--request",
                    str(request_file),
                    "--report",
                    str(report_file),
                ],
                timeout=self._script_timeout,
            )
            if not report_file.is_file():
                raise GodotProbeError(
                    f"the Godot probe wrote no report (exit code {ran.returncode}): "
                    f"{_tail(ran.stderr or ran.stdout)}"
                )
            try:
                report = json.loads(report_file.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise GodotProbeError(f"the Godot probe report is not JSON: {exc}") from exc

        return self._parse(report, requests)

    @staticmethod
    def _parse(report: Any, requests: Sequence[ProbeRequest]) -> ProbeReport:
        if not isinstance(report, Mapping):
            raise GodotProbeError("the Godot probe report is not a JSON object")
        entries = report.get("resources")
        if not isinstance(entries, list) or len(entries) != len(requests):
            raise GodotProbeError(
                f"the Godot probe reported {len(entries) if isinstance(entries, list) else 0} "
                f"resources for {len(requests)} requests"
            )
        results: list[ProbeResult] = []
        for request, entry in zip(requests, entries):
            if not isinstance(entry, Mapping):
                raise GodotProbeError("every Godot probe report entry must be an object")
            # Pair by position and re-assert identity: a report whose rows do not
            # line up with the requests would silently answer for another asset.
            if entry.get("path") != request.res_path:
                raise GodotProbeError(
                    f"the Godot probe answered for {entry.get('path')!r} where "
                    f"{request.res_path!r} was requested"
                )
            structure = entry.get("structure")
            results.append(
                ProbeResult(
                    res_path=request.res_path,
                    expected_type=request.expected_type,
                    loaded=entry.get("loaded") is True,
                    godot_class=str(entry.get("class") or ""),
                    type_matches=entry.get("type_matches") is True,
                    error=entry.get("error") or None,
                    structure=dict(structure) if isinstance(structure, Mapping) else {},
                )
            )
        return ProbeReport(
            godot_version=str(report.get("godot_version") or ""),
            resources=tuple(results),
        )


def find_godot(explicit: str | None = None) -> str | None:
    """Return a usable godot command, or ``None``.

    A convenience for callers that have no project configuration to read, such
    as this repository's own integration tests. Production callers resolve
    ``godot_path`` from the project instead.
    """
    if explicit and explicit.strip():
        candidate = explicit.strip()
        if Path(candidate).is_file():
            return candidate
        return shutil.which(candidate)
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    return None
