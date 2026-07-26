"""Shared L0-L4 readiness ladder for asset skills.

See ``asset-validation-ladder.md`` next to this package for the contract this
code implements. ``ready`` is the conclusion of five ordered levels: the entry
contract (L0), the processed source (L1), the compiled Godot artifact (L2), a
real headless Godot import and load (L3), and the type-specific structural check
(L4). A failure at any level means the asset is not ready.

As with the compiler registry, there is deliberately no module-level default
ladder or structure registry. A caller builds them per run with
:func:`build_default_ladder` or :func:`build_default_structures`, so one caller's
family registrations can never be invisible to -- or collide with -- another's.
"""
from __future__ import annotations

from .contract import (
    FAILED,
    LEVEL_BY_ID,
    LEVELS,
    NOT_RUN,
    PASSED,
    STATUS_FAILED,
    STATUS_READY,
    LadderResult,
    LevelResult,
    LevelSpec,
    ValidationError,
)
from .godot_probe import (
    PROBE_CHECKS,
    PROBE_SCRIPT,
    GodotProbe,
    GodotProbeError,
    ProbeReport,
    ProbeRequest,
    ProbeResult,
    find_godot,
)
from .ladder import PROMOTION, REVALIDATION, ValidationLadder, build_default_ladder
from .structure import (
    KNOWN_ARTIFACT_TYPES,
    ATLAS_TEXTURE_CHECKS,
    ATLAS_TEXTURE_VALIDATOR_ID,
    TEXTURE2D_CHECKS,
    TEXTURE2D_VALIDATOR_ID,
    StructureRequest,
    StructureRoute,
    StructureValidator,
    StructureValidatorRegistry,
    build_default_structures,
    validate_texture2d,
    validate_atlas_texture,
)

__all__ = [
    "FAILED",
    "KNOWN_ARTIFACT_TYPES",
    "ATLAS_TEXTURE_CHECKS",
    "ATLAS_TEXTURE_VALIDATOR_ID",
    "LEVELS",
    "LEVEL_BY_ID",
    "NOT_RUN",
    "PASSED",
    "PROBE_CHECKS",
    "PROBE_SCRIPT",
    "PROMOTION",
    "REVALIDATION",
    "STATUS_FAILED",
    "STATUS_READY",
    "TEXTURE2D_CHECKS",
    "TEXTURE2D_VALIDATOR_ID",
    "GodotProbe",
    "GodotProbeError",
    "LadderResult",
    "LevelResult",
    "LevelSpec",
    "ProbeReport",
    "ProbeRequest",
    "ProbeResult",
    "StructureRequest",
    "StructureRoute",
    "StructureValidator",
    "StructureValidatorRegistry",
    "ValidationError",
    "ValidationLadder",
    "build_default_ladder",
    "build_default_structures",
    "find_godot",
    "validate_texture2d",
    "validate_atlas_texture",
]
