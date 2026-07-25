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
    _resolve_res_path,
    assert_within_output_dir,
    check_output_path,
)

# ``_resolve_res_path`` is private to the stable-entry module, but sharing it is
# the point of this bridge: the compiler must turn a ``res://`` path into a file
# exactly the way the validator that will later accept the entry does.
resolve_res_path = _resolve_res_path

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
