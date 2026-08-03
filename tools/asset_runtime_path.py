#!/usr/bin/env python3
"""Locate the shared asset runtime in both the source tree and a published project.

`skills/assets/_shared/` is the source location of the compiler, validator, and
schema runtime. `publish.py` deploys it once to `.godotmaker/asset-runtime/`,
and flattens each family skill into the adapter's skill root — so in a published
game project `skills/assets/` does not exist at all.

A tool under `tools/` that resolves the runtime as `<parent>/skills/assets/_shared`
therefore imports fine from a framework checkout and dies with
`ModuleNotFoundError` in the project `/gm-asset` actually runs in. Every tool
that needs the runtime resolves it through here instead, published location
first, so the same import works in both layouts.
"""
from __future__ import annotations

import sys
from pathlib import Path

PUBLISHED_RUNTIME = Path(".godotmaker") / "asset-runtime"
SOURCE_RUNTIME = Path("skills") / "assets" / "_shared"


class AssetRuntimePathError(Exception):
    """Raised when the shared asset runtime cannot be located."""


def runtime_candidates(project_root: Path | str | None = None) -> tuple[Path, ...]:
    """Return the runtime locations to try, published layout first."""
    tools_root = Path(__file__).resolve().parents[1]
    candidates: list[Path] = []
    if project_root is not None:
        candidates.append(Path(project_root).resolve() / PUBLISHED_RUNTIME)
    # A published project keeps tools/ at its root, so the runtime sits beside
    # it even when the caller passed no project root.
    candidates.append(tools_root / PUBLISHED_RUNTIME)
    candidates.append(tools_root / SOURCE_RUNTIME)
    seen: set[Path] = set()
    return tuple(
        candidate
        for candidate in candidates
        if not (candidate in seen or seen.add(candidate))
    )


def asset_runtime_root(project_root: Path | str | None = None) -> Path:
    """Return the shared asset runtime directory for this layout."""
    candidates = runtime_candidates(project_root)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise AssetRuntimePathError(
        "asset runtime is missing; checked "
        + ", ".join(str(candidate) for candidate in candidates)
    )


def ensure_asset_runtime_on_path(project_root: Path | str | None = None) -> Path:
    """Put the shared asset runtime on ``sys.path`` and return it."""
    runtime = asset_runtime_root(project_root)
    entry = str(runtime)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return runtime
