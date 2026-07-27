"""Standalone Card Kit validation entry point."""
from __future__ import annotations

import sys
from pathlib import Path


def _configure_runtime_imports() -> None:
    """Add the source or published shared runtime to the import path."""
    runner = Path(__file__).resolve()
    project_root = runner.parents[3]
    source_runtime = runner.parents[1] / "_shared"
    runtime_candidates = (
        project_root / ".godotmaker" / "asset-runtime",
        source_runtime,
    )
    source_layout = (
        runner.parents[1].name == "assets"
        and runner.parents[2].name == "skills"
    )
    runtime = next(
        (
            path for path in runtime_candidates
            if path.is_dir() and (path != source_runtime or source_layout)
        ),
        None,
    )
    tools = project_root / "tools"
    if runtime is None:
        raise ImportError(
            "GodotMaker asset runtime is missing for standalone card-kit validation: "
            "checked " + ", ".join(str(path) for path in runtime_candidates)
        )
    if not tools.is_dir():
        raise ImportError(
            "GodotMaker tools directory is missing for standalone card-kit validation: "
            f"expected {tools}"
        )
    # Appended, never inserted: these flat directories must not shadow the
    # standard library or installed packages for the rest of the process.
    for path in (str(runtime), str(tools)):
        if path not in sys.path:
            sys.path.append(path)


_configure_runtime_imports()

from ui_card_standalone_validation import UICardSkillError, compile_and_validate  # noqa: E402

__all__ = ["UICardSkillError", "compile_and_validate"]
