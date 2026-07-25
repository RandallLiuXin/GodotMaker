"""Import bridge to the repository's stable-entry contract module.

The compiler registry must route on exactly the layout/artifact compatibility
set the stable-entry validator enforces. Re-declaring that set here would let
the two drift, and an artifact could compile that a stable entry then rejects.
So the registry imports the frozen relation instead of copying it.

``tools/`` is a flat script directory rather than an installed package, so it is
resolved relative to this file the same way the repository's tests do. That
makes this package importable from a source checkout only: ``skills/assets/`` is
not part of the publish layout yet, so the location is asserted with a
diagnosable message instead of failing as a bare ``ModuleNotFoundError``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[4] / "tools"

if not _TOOLS_DIR.is_dir():
    raise ImportError(
        "the shared Godot artifact compiler expects the repository tools/ "
        f"directory at {_TOOLS_DIR}, resolved from {__file__}. It is importable "
        "from a source checkout only; skills/assets/ is not deployed by "
        "tools/publish.py yet."
    )

# Appended, never inserted: tools/ is a flat directory of scripts, and putting it
# ahead of the standard library would let a future tools/<stdlib name>.py shadow
# a real module for every later import in the process.
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

from asset_stable_entry import (  # noqa: E402
    LAYOUT_ARTIFACT_TYPES,
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    SOURCE_LAYOUT_TYPES,
    StableEntryError,
    _check_res_path,
    _resolve_res_path,
    assert_within_output_dir,
    check_output_path,
)


def resolve_res_path(project_root: Path, res_path: str, *, label: str = "path") -> Path:
    """Resolve a ``res://`` path to an absolute file under ``project_root``.

    Both halves of this wrapper exist to make the stable-entry resolver safe to
    share rather than to copy:

    - it slices the prefix without checking it, so a path that carries none is
      silently corrupted (``/etc/passwd`` becomes ``<root>/asswd``). That is
      sound where it lives, because every caller validates first, but not as an
      exported "turn a res:// path into a file" helper. The prefix is checked
      here with the same checker the validator uses.
    - the root is resolved first so the result is absolute.
      ``assert_within_output_dir`` re-anchors a relative target against the
      project root, so handing it a relative root joined path would join the
      root twice.
    """
    _check_res_path(res_path, label)
    return _resolve_res_path(Path(project_root).resolve(), res_path)


__all__ = [
    "LAYOUT_ARTIFACT_TYPES",
    "PRODUCTION_FAMILIES",
    "REFERENCE_FAMILIES",
    "REFERENCE_LAYOUTS",
    "SOURCE_LAYOUT_TYPES",
    "StableEntryError",
    "assert_within_output_dir",
    "check_output_path",
    "resolve_res_path",
]
