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


def runtime_candidates() -> tuple[Path, ...]:
    """Return the runtime locations to try, in layout-correct order.

    The order is decided by which layout this file is actually sitting in, not
    by a fixed preference. In a framework checkout the source runtime is the
    authority: a `.godotmaker/asset-runtime/` left behind by publishing the repo
    onto itself is a frozen copy, and preferring it would silently import stale
    compilers while edits to `skills/assets/_shared/` did nothing. A published
    project has no source runtime at all, so the published one is the only
    candidate that exists.
    """
    tools_root = Path(__file__).resolve().parents[1]
    source = tools_root / SOURCE_RUNTIME
    published = tools_root / PUBLISHED_RUNTIME
    return (source, published) if source.is_dir() else (published, source)


def asset_runtime_root() -> Path:
    """Return the shared asset runtime directory for this layout."""
    candidates = runtime_candidates()
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise AssetRuntimePathError(
        "asset runtime is missing; checked "
        + ", ".join(str(candidate) for candidate in candidates)
    )


def ensure_asset_runtime_on_path() -> Path:
    """Put the shared asset runtime on ``sys.path`` and return it."""
    runtime = asset_runtime_root()
    entry = str(runtime)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return runtime
