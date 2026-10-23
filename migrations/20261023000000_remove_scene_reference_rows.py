"""Remove framework-generated scene-reference rows without deleting images."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _is_scene_reference_row(cells: list[str], columns: dict[str, int]) -> bool:
    params = cells[columns["Generation Params"]]
    if "family=screen-reference" in params:
        return True
    path_column = "Runtime Path" if "Runtime Path" in columns else "File Path"
    path = cells[columns[path_column]].replace("\\", "/")
    return (
        cells[columns["Type"]].casefold() == "reference"
        and path.startswith("references/scene_")
        and path.endswith(".png")
    )


def _write_atomic(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def migrate(target: Path) -> None:
    """Delete obsolete catalog rows while preserving every project image."""
    assets = Path(target) / "ASSETS.md"
    if not assets.is_file():
        print("  [skip] ASSETS.md not found")
        return

    lines = assets.read_bytes().decode("utf-8").splitlines(keepends=True)
    columns: dict[str, int] | None = None
    removed = 0
    kept: list[str] = []
    for line in lines:
        cells = _cells(line)
        if cells and {"Name", "Type", "Generation Params"}.issubset(cells):
            candidate = {name: index for index, name in enumerate(cells)}
            if "Runtime Path" in candidate or "File Path" in candidate:
                columns = candidate
            kept.append(line)
            continue
        if columns and cells and len(cells) == len(columns):
            if _is_scene_reference_row(cells, columns):
                removed += 1
                continue
        elif cells is None:
            columns = None
        kept.append(line)

    if removed:
        _write_atomic(assets, "".join(kept))
        print(f"  [done] removed {removed} obsolete scene-reference row(s)")
    else:
        print("  [skip] no obsolete scene-reference rows")
