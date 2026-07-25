"""The stable input, output, error, and receipt boundary of a Godot compiler.

Every deterministic Godot artifact compiler an asset skill runs takes a
:class:`CompileRequest`, raises :class:`CompilerError` when it cannot produce a
legal artifact, and returns receipt details. The registry — not the compiler —
assembles the :class:`CompileResult`, so the worker-facing
:class:`GodotArtifact` can only ever hold the requested type and path.

That asymmetry is deliberate. Compiler identity, versions, hashes, and internal
findings belong in :class:`CompileReceipt`; they are useful for debugging a
generation run and must never reach the worker snapshot, which stays exactly
``{type, path}``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._stable_entry import (
    LAYOUT_ARTIFACT_TYPES,
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    SOURCE_LAYOUT_TYPES,
    StableEntryError,
    assert_within_output_dir,
    check_output_path,
)

RES_PREFIX = "res://"


class CompilerError(Exception):
    """Raised when a Godot artifact cannot be compiled."""


def require_text(value: Any, label: str) -> str:
    """Return ``value`` when it is a non-empty string, else fail closed."""
    if not isinstance(value, str) or not value.strip():
        raise CompilerError(f"{label} must be a non-empty string")
    return value


@dataclass(frozen=True)
class GodotArtifact:
    """The worker-facing result of a compile: exactly a type and a path."""

    type: str
    path: str

    def to_dict(self) -> dict[str, str]:
        """Return the ``godot_artifact`` object of a stable entry, nothing more."""
        return {"type": self.type, "path": self.path}


@dataclass(frozen=True)
class CompileRequest:
    """Everything a compiler is allowed to know about one artifact to build.

    ``spec`` carries family-specific parameters (animation timing, nine-slice
    margins, tile semantics). Its inner shape is owned by the concrete compiler;
    the registry only requires that it is a mapping.
    """

    production_family: str
    asset_id: str
    source_layout_type: str
    source_path: str
    artifact_type: str
    artifact_path: str
    project_root: Path
    spec: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Fail closed on anything the frozen compatibility contract forbids."""
        family = require_text(self.production_family, "production_family")
        if family not in PRODUCTION_FAMILIES:
            raise CompilerError(f"production_family is not allowed: {family}")
        if family in REFERENCE_FAMILIES:
            raise CompilerError(
                f"production_family {family} is reference-only and compiles no "
                "Godot artifact"
            )
        require_text(self.asset_id, "asset_id")

        layout = require_text(self.source_layout_type, "source_layout_type")
        if layout not in SOURCE_LAYOUT_TYPES:
            raise CompilerError(f"source_layout_type is not allowed: {layout}")
        if layout in REFERENCE_LAYOUTS:
            raise CompilerError(
                "a reference source_layout is never handed to a worker as a "
                "runtime game asset and compiles no Godot artifact"
            )

        artifact_type = require_text(self.artifact_type, "artifact_type")
        allowed = LAYOUT_ARTIFACT_TYPES[layout]
        if artifact_type not in allowed:
            raise CompilerError(
                f"artifact_type for a {layout} source_layout must be one of: "
                f"{', '.join(allowed)}; not {artifact_type}"
            )

        if not isinstance(self.project_root, Path):
            raise CompilerError("project_root must be a Path")
        if not isinstance(self.spec, Mapping):
            raise CompilerError("spec must be a mapping")

        for label, value in (
            ("source_path", self.source_path),
            ("artifact_path", self.artifact_path),
        ):
            require_text(value, label)
            try:
                check_output_path(
                    value,
                    production_family=family,
                    asset_id=self.asset_id,
                    label=label,
                )
            except StableEntryError as exc:
                raise CompilerError(str(exc)) from exc

    def _resolve(self, res_path: str, label: str) -> Path:
        try:
            return assert_within_output_dir(
                self.project_root,
                res_path[len(RES_PREFIX):],
                production_family=self.production_family,
                asset_id=self.asset_id,
                label=label,
            )
        except StableEntryError as exc:
            raise CompilerError(str(exc)) from exc

    def source_file(self) -> Path:
        """Resolve ``source_path`` on disk. Call only after :meth:`validate`."""
        return self._resolve(self.source_path, "source_path")

    def artifact_file(self) -> Path:
        """Resolve ``artifact_path`` on disk. Call only after :meth:`validate`."""
        return self._resolve(self.artifact_path, "artifact_path")


@dataclass(frozen=True)
class CompileReceipt:
    """Internal record of one compile. Never part of the worker snapshot."""

    compiler_id: str
    compiler_version: int
    production_family: str
    asset_id: str
    source_layout_type: str
    source_path: str
    artifact_type: str
    artifact_path: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiler_id": self.compiler_id,
            "compiler_version": self.compiler_version,
            "production_family": self.production_family,
            "asset_id": self.asset_id,
            "source_layout_type": self.source_layout_type,
            "source_path": self.source_path,
            "artifact_type": self.artifact_type,
            "artifact_path": self.artifact_path,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class CompileResult:
    """A compiled artifact plus the receipt that stays behind it."""

    godot_artifact: GodotArtifact
    receipt: CompileReceipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "godot_artifact": self.godot_artifact.to_dict(),
            "receipt": self.receipt.to_dict(),
        }
