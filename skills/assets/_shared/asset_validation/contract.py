"""The level, result, and error vocabulary of the L0-L4 readiness ladder.

``ready`` is not a field an asset skill may assert; it is the conclusion of five
ordered levels, each with one input, one outcome, and one error. This module
holds that vocabulary so every level reports the same shape and no caller has to
interpret a level-specific return value.

The ladder never partially succeeds: :attr:`LadderResult.ready` is true only when
all five levels passed, and :attr:`LadderResult.processing_status` collapses to
``failed`` otherwise. Which level failed, and why, stays on the result.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# The runtime-contract processing statuses this layer may conclude. The intermediate
# statuses (``pending``, ``source_ready``, ``compiled``) describe how far
# production got and are written by the producing step; the ladder only decides
# whether that production is worker-consumable.
STATUS_READY = "ready"
STATUS_FAILED = "failed"

PASSED = "passed"
FAILED = "failed"
NOT_RUN = "not_run"


class ValidationError(Exception):
    """Raised when a level cannot conclude that its requirement is met."""


@dataclass(frozen=True)
class LevelSpec:
    """One rung: its identifier, what it consumes, and what it proves."""

    level: str
    name: str
    consumes: str
    proves: str


# The ladder in order. ``asset-validation-ladder.md`` mirrors this table and
# tests/assets/ asserts the two agree, so the document cannot go stale.
LEVELS: tuple[LevelSpec, ...] = (
    LevelSpec(
        level="L0",
        name="contract",
        consumes="the runtime record object and the project root",
        proves="the entry satisfies the v1 runtime-contract schema and path contract",
    ),
    LevelSpec(
        level="L1",
        name="processed_source",
        consumes="source_layout.path",
        proves="deterministic source processing left a real file in the stable directory",
    ),
    LevelSpec(
        level="L2",
        name="compiled_artifact",
        consumes="godot_artifact and the compiler registry",
        proves="a registered compiler route produced the artifact file",
    ),
    LevelSpec(
        level="L3",
        name="godot_load",
        consumes="the artifact path and a headless Godot binary",
        proves="Godot imports the project, ResourceLoader.load succeeds, and the type matches",
    ),
    LevelSpec(
        level="L4",
        name="structure",
        consumes="the L3 probe result and the registered structure validator",
        proves="the loaded resource satisfies its type-specific structural contract",
    ),
)

LEVEL_BY_ID: dict[str, LevelSpec] = {spec.level: spec for spec in LEVELS}


@dataclass(frozen=True)
class LevelResult:
    """The outcome of one level: passed, failed with a reason, or never run."""

    level: str
    name: str
    status: str
    error: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in (PASSED, FAILED, NOT_RUN):
            raise ValidationError(f"unknown level status: {self.status}")
        if self.status == FAILED and not self.error:
            raise ValidationError(f"{self.level} failed without an error message")
        if self.status != FAILED and self.error:
            raise ValidationError(f"{self.level} carries an error but did not fail")

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "status": self.status,
            "error": self.error,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class LadderResult:
    """The verdict on one asset: every level's outcome, and whether it is ready."""

    asset_id: str
    production_family: str
    levels: tuple[LevelResult, ...]

    def __post_init__(self) -> None:
        expected = tuple(spec.level for spec in LEVELS)
        if tuple(result.level for result in self.levels) != expected:
            raise ValidationError(
                "a ladder result must report every level in order: "
                f"{', '.join(expected)}"
            )

    @property
    def failure(self) -> LevelResult | None:
        """The first failed level, or ``None`` when every level passed."""
        for result in self.levels:
            if result.status == FAILED:
                return result
        return None

    @property
    def ready(self) -> bool:
        """True only when all five levels passed."""
        return all(result.status == PASSED for result in self.levels)

    @property
    def processing_status(self) -> str:
        """The runtime-contract status this verdict permits: ``ready`` or ``failed``."""
        return STATUS_READY if self.ready else STATUS_FAILED

    def to_dict(self) -> dict[str, Any]:
        failure = self.failure
        return {
            "asset_id": self.asset_id,
            "production_family": self.production_family,
            "ready": self.ready,
            "processing_status": self.processing_status,
            "failed_level": None if failure is None else failure.level,
            "error": None if failure is None else failure.error,
            "levels": [result.to_dict() for result in self.levels],
        }
