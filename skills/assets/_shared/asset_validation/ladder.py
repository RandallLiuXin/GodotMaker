"""The L0-L4 readiness ladder: five ordered levels, one ``ready`` verdict.

The ladder verifies; it does not produce. Source generation (L1) and Godot
resource compilation (L2) have already run by the time it is called, and each
level's job is to prove that step's result is real and belongs to this entry.
That ordering comes straight from the pipeline the architecture defines:
generate, process, compile, *then* validate, then register.

Levels run in order and stop at the first failure, because every later level
depends on the earlier one's output: there is no artifact to load when nothing
compiled, and no structure to check when nothing loaded. Skipped levels are
reported as ``not_run`` so a caller can tell "did not pass" from "was never
asked".

A reference asset has no rung on this ladder at all. It is never handed to a
worker as a runtime game asset, compiles no Godot artifact, and completes at
``source_ready``; asking whether it is ``ready`` is a category error, so L0
rejects it rather than inventing a pass.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._bridge import (
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    CompileReceipt,
    CompilerError,
    CompilerRegistry,
    StableEntryError,
    assert_within_output_dir,
    build_default_registry,
    is_same_file,
    resolve_res_path,
    validate_entry,
)
from .contract import (
    FAILED,
    LEVELS,
    NOT_RUN,
    PASSED,
    LadderResult,
    LevelResult,
    ValidationError,
)
from .godot_probe import GodotProbe, ProbeRequest, ProbeResult
from .structure import (
    StructureRequest,
    StructureValidatorRegistry,
    build_default_structures,
)


@dataclass
class _Run:
    """What each level hands to the next. Populated in order, never rewound."""

    # Held exactly as the caller passed it: normalizing a malformed entry to an
    # empty object here would replace L0's real complaint with a missing-field
    # one, and the caller would go looking for the wrong problem.
    entry: Any
    project_root: Path
    spec: Mapping[str, Any]
    receipt: CompileReceipt | None = None
    production_family: str = ""
    asset_id: str = ""
    source_layout_type: str = ""
    source_path: str = ""
    artifact_type: str = ""
    artifact_path: str = ""
    source_file: Path | None = None
    artifact_file: Path | None = None
    writes_artifact: bool = True
    probe: ProbeResult | None = None


class ValidationLadder:
    """Runs L0-L4 over one stable entry and returns the readiness verdict.

    The ladder never raises for a bad asset -- a failure is a result, because the
    caller has to record which level failed and why. It raises only when it is
    itself misconfigured, at construction.
    """

    def __init__(
        self,
        *,
        registry: CompilerRegistry,
        structures: StructureValidatorRegistry,
        probe: GodotProbe,
    ) -> None:
        if not isinstance(registry, CompilerRegistry):
            raise ValidationError("registry must be a CompilerRegistry")
        if not isinstance(structures, StructureValidatorRegistry):
            raise ValidationError("structures must be a StructureValidatorRegistry")
        if not isinstance(probe, GodotProbe):
            raise ValidationError("probe must be a GodotProbe")
        self._registry = registry
        self._structures = structures
        self._probe = probe

    def run(
        self,
        entry: Any,
        *,
        project_root: Path,
        spec: Mapping[str, Any] | None = None,
        receipt: CompileReceipt | None = None,
    ) -> LadderResult:
        """Validate one stable entry and return every level's outcome."""
        if not isinstance(project_root, (str, Path)):
            return self._verdict(
                _Run(entry=entry, project_root=Path("."), spec={}),
                [
                    LevelResult(
                        level=LEVELS[0].level,
                        name=LEVELS[0].name,
                        status=FAILED,
                        error="project_root must be a path",
                    )
                ],
            )
        run = _Run(
            entry=entry,
            project_root=Path(project_root),
            spec=dict(spec or {}),
            receipt=receipt,
        )

        steps = (self._l0, self._l1, self._l2, self._l3, self._l4)
        results: list[LevelResult] = []
        for spec_row, step in zip(LEVELS, steps):
            try:
                details = step(run)
            except (ValidationError, StableEntryError, CompilerError) as exc:
                results.append(
                    LevelResult(
                        level=spec_row.level,
                        name=spec_row.name,
                        status=FAILED,
                        error=str(exc),
                    )
                )
                break
            results.append(
                LevelResult(
                    level=spec_row.level,
                    name=spec_row.name,
                    status=PASSED,
                    details=details,
                )
            )
        return self._verdict(run, results)

    @staticmethod
    def _verdict(run: _Run, results: list[LevelResult]) -> LadderResult:
        """Pad the levels that never ran and assemble the result."""
        filled = list(results)
        for spec_row in LEVELS[len(filled):]:
            filled.append(
                LevelResult(level=spec_row.level, name=spec_row.name, status=NOT_RUN)
            )
        declared = run.entry if isinstance(run.entry, Mapping) else {}
        return LadderResult(
            asset_id=run.asset_id or str(declared.get("asset_id") or ""),
            production_family=run.production_family
            or str(declared.get("production_family") or ""),
            levels=tuple(filled),
        )

    # ------------------------------------------------------------------ L0
    def _l0(self, run: _Run) -> dict[str, Any]:
        """The entry itself must satisfy the v1 stable-entry contract."""
        validated = validate_entry(run.entry, project_root=run.project_root)

        family = validated["production_family"]
        layout = validated["source_layout"]
        layout_type = layout["type"]
        if layout_type in REFERENCE_LAYOUTS or family in REFERENCE_FAMILIES:
            raise ValidationError(
                "a reference asset is never handed to a worker as a runtime game "
                "asset and has no L0-L4 readiness ladder; it completes at "
                "source_ready"
            )

        run.production_family = family
        run.asset_id = validated["asset_id"]
        run.source_layout_type = layout_type
        run.source_path = layout["path"]
        artifact = validated.get("godot_artifact")
        if isinstance(artifact, Mapping):
            run.artifact_type = artifact["type"]
            run.artifact_path = artifact["path"]
        return {
            "production_family": family,
            "asset_id": run.asset_id,
            "source_layout_type": layout_type,
            "processing_status": validated["processing_status"],
        }

    # ------------------------------------------------------------------ L1
    def _l1(self, run: _Run) -> dict[str, Any]:
        """Deterministic processing must have left a real file behind."""
        run.source_file = self._resolve(run, run.source_path, "source_layout.path")
        size = self._require_file(run.source_file, run.source_path, "source_layout.path")
        return {"source_path": run.source_path, "bytes": size}

    # ------------------------------------------------------------------ L2
    def _l2(self, run: _Run) -> dict[str, Any]:
        """A registered compiler route must have produced the artifact."""
        if not run.artifact_path:
            raise ValidationError(
                "the entry declares no godot_artifact, so no native Godot resource "
                "was compiled for it"
            )
        route = self._registry.resolve(run.source_layout_type, run.artifact_type)
        run.writes_artifact = route.writes_artifact
        run.artifact_file = self._resolve(run, run.artifact_path, "godot_artifact.path")
        size = self._require_file(
            run.artifact_file, run.artifact_path, "godot_artifact.path"
        )

        # The same rule the registry enforces at compile time, re-checked here
        # because the ladder also runs on entries it did not compile: a writing
        # route that names its source is publishing the source image as the
        # resource a worker was promised.
        if run.source_file is None:
            raise ValidationError("L2 ran without a source file resolved by L1")
        paths_match = run.artifact_path == run.source_path
        if route.writes_artifact:
            if paths_match or is_same_file(run.source_file, run.artifact_file):
                raise ValidationError(
                    f"{route.compiler_id} compiles a new file, so "
                    f"godot_artifact.path may not be the source image itself "
                    f"({run.artifact_path})"
                )
        elif not paths_match:
            raise ValidationError(
                f"{route.compiler_id} writes no file, so godot_artifact.path must "
                f"equal source_layout.path; got {run.artifact_path} instead of "
                f"{run.source_path}"
            )

        details: dict[str, Any] = {
            "compiler_id": route.compiler_id,
            "compiler_version": route.compiler_version,
            "writes_artifact": route.writes_artifact,
            "artifact_path": run.artifact_path,
            "bytes": size,
        }
        if run.receipt is not None:
            details["receipt"] = self._check_receipt(run, route)
        return details

    @staticmethod
    def _check_receipt(run: _Run, route: Any) -> dict[str, Any]:
        """Bind an optional compile receipt to the entry it claims to describe.

        The receipt is optional because re-validating a registered asset has none
        to offer. When one is supplied it must be this asset's: a receipt for a
        different asset, layout, or artifact would otherwise be accepted as
        evidence that this entry was compiled.
        """
        receipt = run.receipt
        if not isinstance(receipt, CompileReceipt):
            raise ValidationError(
                "receipt must be a CompileReceipt returned by the compiler registry"
            )
        expected = {
            "compiler_id": route.compiler_id,
            "production_family": run.production_family,
            "asset_id": run.asset_id,
            "source_layout_type": run.source_layout_type,
            "source_path": run.source_path,
            "artifact_type": run.artifact_type,
            "artifact_path": run.artifact_path,
        }
        for name, value in expected.items():
            actual = getattr(receipt, name, None)
            if actual != value:
                raise ValidationError(
                    f"the supplied compile receipt describes {name} {actual!r}, not "
                    f"this entry's {value!r}"
                )
        return {
            "compiler_id": receipt.compiler_id,
            "compiler_version": receipt.compiler_version,
        }

    # ------------------------------------------------------------------ L3
    def _l3(self, run: _Run) -> dict[str, Any]:
        """Godot must import the project, load the artifact, and agree on its type."""
        request = ProbeRequest(
            res_path=run.artifact_path,
            expected_type=run.artifact_type,
            checks=self._structures.checks_for(run.artifact_type),
        )
        report = self._probe.probe(run.project_root, [request])
        probe = report.resources[0]
        run.probe = probe
        if not probe.loaded:
            raise ValidationError(
                probe.error
                or f"Godot could not load {run.artifact_path}"
            )
        if not probe.type_matches:
            raise ValidationError(
                f"Godot loaded {run.artifact_path} as {probe.godot_class}, which is "
                f"not a {run.artifact_type}"
            )
        return {
            "godot_version": report.godot_version,
            "godot_class": probe.godot_class,
            "expected_type": run.artifact_type,
            "structure": dict(probe.structure),
        }

    # ------------------------------------------------------------------ L4
    def _l4(self, run: _Run) -> dict[str, Any]:
        """The loaded resource must satisfy its type-specific structural contract."""
        if run.probe is None:
            raise ValidationError("L4 ran without a Godot probe result from L3")
        request = StructureRequest(
            production_family=run.production_family,
            asset_id=run.asset_id,
            source_layout_type=run.source_layout_type,
            source_path=run.source_path,
            artifact_type=run.artifact_type,
            artifact_path=run.artifact_path,
            project_root=run.project_root,
            probe=run.probe,
            spec=run.spec,
        )
        details = dict(self._structures.validate(request))
        details["validator_id"] = self._structures.resolve(run.artifact_type).validator_id
        return details

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _resolve(run: _Run, res_path: str, label: str) -> Path:
        """Resolve a ``res://`` path and re-assert it lands in the stable directory.

        L0 checked the path string. This checks where it actually points, so a
        symlink inside the stable directory cannot aim the ladder at a file it
        was never allowed to accept.
        """
        try:
            return assert_within_output_dir(
                run.project_root,
                resolve_res_path(run.project_root, res_path, label=label),
                production_family=run.production_family,
                asset_id=run.asset_id,
                label=label,
            )
        except OSError as exc:
            # Resolution itself can fail on a path the filesystem rejects; that
            # is still an unusable asset, not a crash for the caller to handle.
            raise ValidationError(f"{label} cannot be resolved: {res_path} ({exc})") from exc

    @staticmethod
    def _require_file(resolved: Path, res_path: str, label: str) -> int:
        """Require a non-empty regular file and return its size."""
        if not resolved.is_file():
            raise ValidationError(f"{label} is not a file on disk: {res_path}")
        try:
            size = resolved.stat().st_size
        except OSError as exc:
            raise ValidationError(f"{label} cannot be read: {res_path} ({exc})") from exc
        if size <= 0:
            raise ValidationError(f"{label} is an empty file: {res_path}")
        return size


def build_default_ladder(
    godot_path: str,
    *,
    registry: CompilerRegistry | None = None,
    structures: StructureValidatorRegistry | None = None,
) -> ValidationLadder:
    """Return a ladder wired to the compilers and validators the shared layer ships.

    A family skill that registers its own compiler and structure validator builds
    both registries itself and constructs :class:`ValidationLadder` directly;
    this is the shortest path for a caller that only needs the shared routes.
    """
    return ValidationLadder(
        registry=registry if registry is not None else build_default_registry(),
        structures=structures if structures is not None else build_default_structures(),
        probe=GodotProbe(godot_path),
    )
