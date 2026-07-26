"""L4 structural validation for deterministic ``SpriteFrames`` artifacts."""
from __future__ import annotations

from collections.abc import Mapping
from math import isclose
from typing import Any

from .contract import ValidationError
from .structure import StructureRequest, StructureValidatorRegistry

VALIDATOR_ID = "spriteframes_structure"
CHECKS = ("spriteframes",)


def validate_spriteframes(request: StructureRequest) -> dict[str, Any]:
    facts = request.checked_structure("spriteframes")
    actual = facts.get("animations")
    expected = request.spec.get("actions")
    if not isinstance(actual, list) or not isinstance(expected, list) or not expected:
        raise ValidationError("SpriteFrames validation needs non-empty spec.actions and probe animations")
    if len(actual) != len(expected):
        raise ValidationError("SpriteFrames animation count does not match spec.actions")
    actual_by_name = {
        item.get("name"): item for item in actual if isinstance(item, Mapping)
    }
    expected_names = [item.get("name") for item in expected if isinstance(item, Mapping)]
    if len(actual_by_name) != len(actual) or set(actual_by_name) != set(expected_names):
        raise ValidationError("SpriteFrames animation names do not match spec.actions")
    checked: list[str] = []
    for wanted in expected:
        if not isinstance(wanted, Mapping):
            raise ValidationError("SpriteFrames spec.actions must contain objects")
        name = wanted.get("name")
        found = actual_by_name[name]
        if found.get("loop") is not wanted.get("loop"):
            raise ValidationError(f"SpriteFrames animation {name!r} loop state differs from the explicit spec")
        if not isclose(float(found.get("fps", 0)), float(wanted.get("fps", 0)), rel_tol=0, abs_tol=1e-9):
            raise ValidationError(f"SpriteFrames animation {name!r} FPS differs from the explicit spec")
        frames = wanted.get("frame_paths")
        durations = wanted.get("frame_durations")
        if not isinstance(frames, list) or not isinstance(durations, list):
            raise ValidationError(f"SpriteFrames action {name!r} has no explicit frame contract")
        if found.get("frame_paths") != frames or found.get("frame_count") != len(frames):
            raise ValidationError(f"SpriteFrames animation {name!r} frame order or texture binding differs from the spec")
        reported = found.get("frame_durations")
        if not isinstance(reported, list) or len(reported) != len(durations) or any(
            not isclose(float(left), float(right), rel_tol=0, abs_tol=1e-9)
            for left, right in zip(reported, durations)
        ):
            raise ValidationError(f"SpriteFrames animation {name!r} relative frame durations differ from the spec")
        checked.append(str(name))
    return {"animations": checked}


def register_into(registry: StructureValidatorRegistry) -> None:
    """Register the SpriteFrames-specific L4 check for one validation run."""
    registry.register(
        artifact_type="SpriteFrames",
        validator_id=VALIDATOR_ID,
        validator=validate_spriteframes,
        checks=CHECKS,
    )
