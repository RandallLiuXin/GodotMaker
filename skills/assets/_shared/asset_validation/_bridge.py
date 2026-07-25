"""Import bridge to the repository modules the readiness ladder validates against.

The ladder must judge an asset against exactly the contracts the rest of the
pipeline enforces, so it imports them instead of restating them:

- ``tools/asset_stable_entry.py`` owns the entry schema (L0) and the stable
  output-path relation the on-disk checks (L1, L2) resolve against;
- ``asset_compiler`` next to this package owns the ``(source_layout, artifact
  type)`` routing relation L2 requires a registered compiler for;
- ``tools/agent_runtime.py`` owns the Windows console-binary preference the
  Godot probe needs to capture output.

Neither ``tools/`` nor ``_shared/`` is an installed package. The bridge
supports both the source checkout and the published
``.godotmaker/asset-runtime`` layout, where the runtime sits beside the
project's published ``tools/`` directory.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SHARED_DIR = Path(__file__).resolve().parents[1]
_TOOLS_CANDIDATES = (
    _SHARED_DIR.parents[2] / "tools",  # source: skills/assets/_shared/
    _SHARED_DIR.parents[1] / "tools",  # published: .godotmaker/asset-runtime/
)
_TOOLS_DIR = next((path for path in _TOOLS_CANDIDATES if path.is_dir()), None)

if _TOOLS_DIR is None or not _SHARED_DIR.is_dir():
    raise ImportError(
        "the shared asset validation ladder needs its asset runtime and a "
        "tools/ directory beside the source checkout or published project; "
        "checked " + ", ".join(str(path) for path in _TOOLS_CANDIDATES)
    )

# Appended, never inserted: both are flat directories of scripts and packages,
# and putting either ahead of the standard library would let a same-named module
# shadow a real one for every later import in the process.
for _directory in (_TOOLS_DIR, _SHARED_DIR):
    if str(_directory) not in sys.path:
        sys.path.append(str(_directory))

from agent_runtime import prefer_console_godot_path  # noqa: E402
from asset_compiler import (  # noqa: E402
    CompileReceipt,
    CompilerError,
    CompilerRegistry,
    build_default_registry,
)
from asset_compiler.registry import is_same_file  # noqa: E402
from asset_stable_entry import (  # noqa: E402
    LAYOUT_ARTIFACT_TYPES,
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    StableEntryError,
    assert_within_output_dir,
    validate_entry,
)
from asset_compiler._stable_entry import resolve_res_path  # noqa: E402

__all__ = [
    "LAYOUT_ARTIFACT_TYPES",
    "REFERENCE_FAMILIES",
    "REFERENCE_LAYOUTS",
    "CompileReceipt",
    "CompilerError",
    "CompilerRegistry",
    "StableEntryError",
    "assert_within_output_dir",
    "build_default_registry",
    "is_same_file",
    "prefer_console_godot_path",
    "resolve_res_path",
    "validate_entry",
]
