"""Shared direct-output validation utilities for asset skills.

See ``asset-validation-ladder.md`` next to this package for the contract this
code implements. Standalone family validators apply these checks to their public
request, result, and selected output before registration. No persisted entry
schema or processing-status record is part of this package.

As with the compiler registry, there is deliberately no module-level default
ladder or structure registry. A caller builds them per run with
:func:`build_default_structures`, so one caller's
family registrations can never be invisible to -- or collide with -- another's.
"""
from __future__ import annotations

from .errors import ValidationError
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
from .structure import (
    KNOWN_ARTIFACT_TYPES,
    ATLAS_TEXTURE_CHECKS,
    ATLAS_TEXTURE_VALIDATOR_ID,
    STYLEBOX_TEXTURE_CHECKS,
    STYLEBOX_TEXTURE_VALIDATOR_ID,
    TEXTURE2D_CHECKS,
    TEXTURE2D_VALIDATOR_ID,
    StructureRequest,
    StructureRoute,
    StructureValidator,
    StructureValidatorRegistry,
    build_default_structures,
    validate_texture2d,
    validate_atlas_texture,
    validate_stylebox_texture,
)

__all__ = [
    "KNOWN_ARTIFACT_TYPES",
    "ATLAS_TEXTURE_CHECKS",
    "ATLAS_TEXTURE_VALIDATOR_ID",
    "STYLEBOX_TEXTURE_CHECKS",
    "STYLEBOX_TEXTURE_VALIDATOR_ID",
    "PROBE_CHECKS",
    "PROBE_SCRIPT",
    "TEXTURE2D_CHECKS",
    "TEXTURE2D_VALIDATOR_ID",
    "GodotProbe",
    "GodotProbeError",
    "ProbeReport",
    "ProbeRequest",
    "ProbeResult",
    "StructureRequest",
    "StructureRoute",
    "StructureValidator",
    "StructureValidatorRegistry",
    "ValidationError",
    "build_default_structures",
    "find_godot",
    "validate_texture2d",
    "validate_atlas_texture",
    "validate_stylebox_texture",
]
