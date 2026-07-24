#!/usr/bin/env python3
"""Compute and validate stable generated-asset output paths.

Every worker-consumable generated file for one asset lives under a single,
identity-derived directory::

    assets/generated/<production_family>/<asset_id>/

This tool is the deterministic authority for that constraint. It can:

- print the canonical output directory for a ``(production_family, asset_id)``
  pair (``--family`` + ``--asset-id``);
- validate that a ``res://`` path (source image, native Godot artifact, or
  support file) sits under that directory and does not depend on the temporary
  generation ``work/`` workspace (``--path`` / ``--support-file``);
- validate a whole stable entry file plus its declared support files
  (``--entry``), deriving the identity from the entry itself.

Because the directory is derived from stable identity, regeneration overwrites
the same target in place; a timestamped, ``v2``, or ``final`` drift path, an
out-of-tree escape, an illegal family/asset_id, or a ``work/`` dependency is
rejected. This tool never writes or deletes files.

The path constraint itself is enforced at the schema layer by
``asset_stable_entry.validate_entry``; this tool exposes the same checks as a
standalone command for the registration path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    StableEntryError,
    _load_json,
    check_output_path,
    check_support_files,
    stable_output_dir,
    stable_output_res_path,
    validate_entry,
)


def describe_output_dir(production_family: str, asset_id: str) -> dict[str, Any]:
    """Return the canonical output directory for one asset, both forms."""
    relative = stable_output_dir(production_family, asset_id)
    return {
        "ok": True,
        "production_family": production_family,
        "asset_id": asset_id,
        "dir": relative,
        "res_dir": stable_output_res_path(production_family, asset_id),
    }


def check_paths(
    production_family: str,
    asset_id: str,
    *,
    paths: list[str],
    support_files: list[str],
) -> dict[str, Any]:
    """Validate arbitrary output and support paths against the stable directory."""
    for index, path in enumerate(paths):
        check_output_path(
            path,
            production_family=production_family,
            asset_id=asset_id,
            label=f"path[{index}]",
        )
    check_support_files(
        support_files, production_family=production_family, asset_id=asset_id
    )
    result = describe_output_dir(production_family, asset_id)
    result["checked_paths"] = list(paths)
    result["checked_support_files"] = list(support_files)
    return result


def check_entry_file(
    entry_path: Path,
    *,
    project_root: Path,
    support_files: list[str],
    check_files: bool = False,
) -> dict[str, Any]:
    """Validate a stable entry's paths, then its declared support files."""
    entry = _load_json(Path(entry_path))
    validated = validate_entry(
        entry, project_root=project_root, check_files=check_files
    )
    production_family = validated["production_family"]
    asset_id = validated["asset_id"]
    check_support_files(
        support_files, production_family=production_family, asset_id=asset_id
    )
    result = describe_output_dir(production_family, asset_id)
    result["entry"] = str(entry_path)
    result["checked_support_files"] = list(support_files)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute and validate stable generated-asset output paths"
    )
    parser.add_argument("--family", help="Production family (e.g. character-bundle)")
    parser.add_argument("--asset-id", help="Stable asset identifier")
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="res:// path to validate against the stable directory (repeatable)",
    )
    parser.add_argument(
        "--support-file",
        action="append",
        default=[],
        help="res:// support-file path to validate (repeatable)",
    )
    parser.add_argument(
        "--entry",
        type=Path,
        help="Stable entry JSON file; identity and paths are read from it",
    )
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--check-files",
        action="store_true",
        help="With --entry, verify referenced source/artifact files exist",
    )
    args = parser.parse_args()

    try:
        if args.entry is not None:
            if args.family or args.asset_id or args.path:
                raise StableEntryError(
                    "--entry derives identity from the file; do not pass "
                    "--family/--asset-id/--path"
                )
            result = check_entry_file(
                args.entry,
                project_root=args.project_root,
                support_files=args.support_file,
                check_files=args.check_files,
            )
        else:
            if not args.family or not args.asset_id:
                raise StableEntryError(
                    "--family and --asset-id are required without --entry"
                )
            if args.path or args.support_file:
                result = check_paths(
                    args.family,
                    args.asset_id,
                    paths=args.path,
                    support_files=args.support_file,
                )
            else:
                result = describe_output_dir(args.family, args.asset_id)
    except StableEntryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
