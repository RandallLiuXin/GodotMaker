#!/usr/bin/env python3
"""Run retryable public standalone diagnostics for one UI/card handoff."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path


def _load_skill_validator(skill_path: Path):
    spec = importlib.util.spec_from_file_location("asset_ui_card_skill", skill_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load standalone validator: {skill_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compile_and_validate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--skill", default=".agents/skills/ui-kit/standalone_validation.py")
    parser.add_argument("--godot-path", default=os.environ.get("GODOT_BIN", ""))
    parser.add_argument("--allow-failure", action="store_true", help="Return diagnostics without a nonzero process exit")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    if not args.godot_path:
        raise SystemExit("--godot-path or GODOT_BIN is required")
    request_path = (root / args.request).resolve()
    result_path = (root / args.result).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validated = _load_skill_validator((root / args.skill).resolve())(
        request, result, project_root=root, godot_path=args.godot_path
    )
    result_path.write_text(json.dumps(validated, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(validated))
    return 0 if validated["validation"]["passed"] or args.allow_failure else 1


if __name__ == "__main__":
    raise SystemExit(main())
