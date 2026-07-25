"""Import bridge to the repository's stable-entry contract module.

The compiler registry must route on exactly the layout/artifact compatibility
set the stable-entry validator enforces. Re-declaring that set here would let
the two drift, and an artifact could compile that a stable entry then rejects.
So the registry imports the frozen relation instead of copying it.

``tools/`` is a flat script directory rather than an installed package, so it is
resolved relative to this file the same way the repository's tests do.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parents[4] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from asset_stable_entry import (  # noqa: E402
    LAYOUT_ARTIFACT_TYPES,
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    SOURCE_LAYOUT_TYPES,
    StableEntryError,
    assert_within_output_dir,
    check_output_path,
)

__all__ = [
    "LAYOUT_ARTIFACT_TYPES",
    "PRODUCTION_FAMILIES",
    "REFERENCE_FAMILIES",
    "REFERENCE_LAYOUTS",
    "SOURCE_LAYOUT_TYPES",
    "StableEntryError",
    "assert_within_output_dir",
    "check_output_path",
]
