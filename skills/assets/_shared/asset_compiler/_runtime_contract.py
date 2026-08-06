"""Import bridge to the repository's runtime-contract contract module.

The compiler registry must route on exactly the layout/artifact compatibility
set the runtime-contract validator enforces. Re-declaring that set here would let
the two drift, and an artifact could compile that a runtime record then rejects.
So the registry imports the frozen relation instead of copying it.

``tools/`` is a flat script directory rather than an installed package. The
bridge accepts both supported layouts: the source checkout and the published
``.godotmaker/asset-runtime`` beside the project's ``tools/`` directory.
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

if _TOOLS_DIR is None:
    raise ImportError(
        "the shared Godot artifact compiler expects the repository tools/ "
        "directory beside the source checkout or published project runtime; checked "
        + ", ".join(str(path) for path in _TOOLS_CANDIDATES)
    )

# Appended, never inserted: tools/ is a flat directory of scripts, and putting it
# ahead of the standard library would let a future tools/<stdlib name>.py shadow
# a real module for every later import in the process.
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

from asset_runtime_contract import (  # noqa: E402
    LAYOUT_ARTIFACT_TYPES,
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    SOURCE_LAYOUT_TYPES,
    RuntimeContractError,
    _check_res_path,
    _resolve_res_path,
    _safe_identifier,
    assert_within_output_dir,
    check_output_path,
)


def resolve_res_path(project_root: Path, res_path: str, *, label: str = "path") -> Path:
    """Resolve a ``res://`` path to an absolute file under ``project_root``.

    Both halves of this wrapper exist to make the runtime-contract resolver safe to
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


def safe_identifier(value: str, label: str) -> str:
    """Validate one cross-platform stable-identity segment.

    ``asset_id`` and related names must use the canonical runtime-contract rule so
    a compiler cannot accept an identifier that a later manifest or Windows
    filesystem rejects. The canonical helper is deliberately shared rather than
    copied here; it covers control characters and reserved device names as well
    as path syntax.
    """
    return _safe_identifier(value, label)


__all__ = [
    "LAYOUT_ARTIFACT_TYPES",
    "PRODUCTION_FAMILIES",
    "REFERENCE_FAMILIES",
    "REFERENCE_LAYOUTS",
    "SOURCE_LAYOUT_TYPES",
    "RuntimeContractError",
    "assert_within_output_dir",
    "check_output_path",
    "resolve_res_path",
    "safe_identifier",
]
