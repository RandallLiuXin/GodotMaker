#!/usr/bin/env python3
"""Run and persist the scene-prop-set L0-L4 validation result.

The scene-prop-set Skill produces a shared generic result document. Its family
validator owns the actual compile/load/structure checks. This command is the
production boundary: it invokes that validator and atomically writes the exact
returned result to both the handoff file and the production diagnostic report.
It is deliberately independent of any private Eval environment variables.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from agent_runtime import read_godot_path


class ScenePropSetValidationError(Exception):
    """Raised when the controlled validation command cannot run."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScenePropSetValidationError(f"{label} file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ScenePropSetValidationError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ScenePropSetValidationError(f"{label} must be a JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(path.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, indent=2)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validator() -> Callable[..., dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    source = root / "skills" / "assets" / "scene-prop-set" / "standalone_validation.py"
    spec = importlib.util.spec_from_file_location("scene_prop_set_validation", source)
    if spec is None or spec.loader is None:
        raise ScenePropSetValidationError(f"Could not load scene-prop-set validator: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    callback = getattr(module, "compile_and_validate", None)
    if not callable(callback):
        raise ScenePropSetValidationError("scene-prop-set validator has no compile_and_validate")
    return callback


def validate_scene_prop_set(
    request_path: Path,
    result_path: Path,
    report_path: Path,
    *,
    project_root: Path,
    godot_path: str,
) -> dict[str, Any]:
    """Validate one handoff and retain the exact returned generic result."""
    request = _load_object(request_path, "request")
    result = _load_object(result_path, "result")
    if request.get("asset_type") != "scene-prop-set":
        raise ScenePropSetValidationError("request.asset_type must be scene-prop-set")
    if result.get("asset_type") != "scene-prop-set":
        raise ScenePropSetValidationError("result.asset_type must be scene-prop-set")
    if not godot_path.strip():
        raise ScenePropSetValidationError("A configured Godot path is required")

    actual = _validator()(request, result, project_root=Path(project_root), godot_path=godot_path)
    if not isinstance(actual, dict):
        raise ScenePropSetValidationError("scene-prop-set validator returned a non-object")
    _write_object(result_path, actual)
    _write_object(report_path, actual)
    return actual


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate and persist a scene-prop-set L0-L4 result")
    parser.add_argument("--request", required=True, help="Asset request JSON path")
    parser.add_argument("--result", required=True, help="Generic result JSON path to update")
    parser.add_argument("--report", required=True, help="Validator report JSON path")
    parser.add_argument("--project-root", default=".", help="Godot project root")
    parser.add_argument("--godot-path", default=None, help="Explicit production Godot binary override")
    args = parser.parse_args()
    project_root = Path(args.project_root).resolve()
    godot_path = args.godot_path or read_godot_path(project_root)
    try:
        actual = validate_scene_prop_set(
            Path(args.request),
            Path(args.result),
            Path(args.report),
            project_root=project_root,
            godot_path=godot_path or "",
        )
    except (OSError, ScenePropSetValidationError, ImportError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    passed = actual.get("validation", {}).get("passed") is True
    print(json.dumps({"ok": passed, "report": str(args.report), "validation": actual.get("validation")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(_main())
