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
from asset_build_record import write_validation_record  # noqa: E402
from missing_family_standalone_validation import (  # noqa: E402
    MissingFamilySkillError,
    compile_and_validate as _compile_and_validate,
)

_LEVELS = ("L0", "L1", "L2", "L3", "L4")


def compile_and_validate(request, result, *, project_root, godot_path):
    """Run the family ladder and record the PNG a fully passing run examined.

    The stable output path is derived from ``asset_id``, so a regeneration
    overwrites the very file an older passing result names, and comparing paths
    at registration would prove nothing about which bytes are there. The record
    this leaves is what registration recomputes from disk, so only a PNG that
    actually passed L0-L4 can become a ``ready`` entry.
    """
    validated = _compile_and_validate(request, result, project_root=project_root, godot_path=godot_path, expected_family="background-map")
    levels = validated["validation"]["levels"]
    if not all(levels.get(level) is True for level in _LEVELS):
        return validated
    runtime = [item for item in validated["outputs"] if item.get("role") == "runtime"]
    write_validation_record(
        project_root,
        production_family="background-map",
        asset_id=request["asset_id"],
        artifact_path=runtime[0]["path"],
    )
    return validated

__all__ = ("MissingFamilySkillError", "compile_and_validate")
