"""Published standalone entry for the background-map Asset Skill."""

from __future__ import annotations
import sys
from pathlib import Path


def _runtime() -> None:
    runner = Path(__file__).resolve()
    root = runner.parents[3]
    source = runner.parents[1] / "_shared"
    candidates = (root / ".godotmaker" / "asset-runtime", source)
    path = next(
        (
            item
            for item in candidates
            if item.is_dir()
            and (
                item != source
                or (
                    runner.parents[1].name == "assets"
                    and runner.parents[2].name == "skills"
                )
            )
        ),
        None,
    )
    tools = root / "tools"
    if path is None:
        raise ImportError(
            "GodotMaker asset runtime is missing for standalone validation: checked "
            + ", ".join(str(item) for item in candidates)
        )
    if not tools.is_dir():
        raise ImportError(
            f"GodotMaker tools directory is missing for standalone validation: expected {tools}"
        )
    for item in (str(path), str(tools)):
        if item not in sys.path:
            sys.path.append(item)


_runtime()
from missing_family_standalone_validation import (  # noqa: E402
    MissingFamilySkillError,
    compile_and_validate,
)

__all__ = ("MissingFamilySkillError", "compile_and_validate")
