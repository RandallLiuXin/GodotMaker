"""Standalone UI Kit validation entry point."""
from __future__ import annotations

import sys
from pathlib import Path


def _configure_runtime_imports() -> None:
    """Add the source or published shared runtime to the import path."""
    runner = Path(__file__).resolve()
    source_runtime = runner.parents[1] / "_shared"
    if source_runtime.is_dir():
        runtime = source_runtime
        project_root = runner.parents[3]
    else:
        project_root = runner.parents[3]
        runtime = project_root / ".godotmaker" / "asset-runtime"
    tools = project_root / "tools"
    if not runtime.is_dir():
        raise ImportError(
            "GodotMaker asset runtime is missing for standalone ui-kit validation: "
            f"expected {runtime}"
        )
    if not tools.is_dir():
        raise ImportError(
            "GodotMaker tools directory is missing for standalone ui-kit validation: "
            f"expected {tools}"
        )
    for path in (str(runtime), str(tools)):
        if path not in sys.path:
            sys.path.insert(0, path)


_configure_runtime_imports()

from ui_card_standalone_validation import UICardSkillError, compile_and_validate  # noqa: E402

__all__ = ["UICardSkillError", "compile_and_validate"]
