"""L4: the type-specific structural contract, and the registry families extend.

L3 proves Godot produced *a* resource of the declared type. It cannot prove the
resource says anything useful: a ``SpriteFrames`` with no animations, a ``Theme``
with no type overrides, and a ``TileSet`` with no sources all load fine and are
all unusable. What "useful" means is per type, so L4 is an extension point, not
a fixed check.

A family skill registers one validator for the artifact type it compiles,
together with the structural facts its validator needs ``probe.gd`` to collect.
The registry fails closed on an unregistered type: an artifact nobody can check
must not reach ``ready`` just because no one wrote the check yet.

The shared layer ships exactly one validator, for the one artifact type it
compiles -- ``Texture2D``, through ``asset_compiler/texture2d.py``. Every other
type lands with its family skill.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ._bridge import LAYOUT_ARTIFACT_TYPES
from .contract import ValidationError
from .godot_probe import ProbeResult

# Every artifact type the frozen stable-entry relation allows. A validator for a
# type outside it could never run, so registering one is a mistake, not a
# forward-compatible extension.
KNOWN_ARTIFACT_TYPES = frozenset(
    artifact_type
    for artifact_types in LAYOUT_ARTIFACT_TYPES.values()
    for artifact_type in artifact_types
)


@dataclass(frozen=True)
class StructureRequest:
    """Everything a structure validator is allowed to know about one artifact."""

    production_family: str
    asset_id: str
    source_layout_type: str
    source_path: str
    artifact_type: str
    artifact_path: str
    project_root: Path
    probe: ProbeResult
    spec: Mapping[str, Any] = field(default_factory=dict)


# A validator raises ``ValidationError`` when the structure is unusable and
# returns the facts it checked otherwise. Those facts land in the L4 details of
# the ladder result; they are diagnostics, never part of the worker snapshot.
StructureValidator = Callable[[StructureRequest], Mapping[str, Any]]


@dataclass(frozen=True)
class StructureRoute:
    """One artifact type bound to the validator that judges its structure."""

    artifact_type: str
    validator_id: str
    validator: StructureValidator
    checks: tuple[str, ...] = ()


class StructureValidatorRegistry:
    """Holds the L4 validator for each artifact type an asset skill may produce."""

    def __init__(self) -> None:
        self._routes: dict[str, StructureRoute] = {}

    def register(
        self,
        *,
        artifact_type: str,
        validator_id: str,
        validator: StructureValidator,
        checks: tuple[str, ...] = (),
    ) -> StructureRoute:
        """Bind one validator to one artifact type."""
        for label, value in (
            ("artifact_type", artifact_type),
            ("validator_id", validator_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{label} must be a non-empty string")
        if artifact_type not in KNOWN_ARTIFACT_TYPES:
            raise ValidationError(
                f"no source layout compiles to {artifact_type}; allowed: "
                f"{', '.join(sorted(KNOWN_ARTIFACT_TYPES))}"
            )
        if not callable(validator):
            raise ValidationError("validator must be callable")
        if not isinstance(checks, tuple) or not all(
            isinstance(check, str) and check.strip() for check in checks
        ):
            raise ValidationError("checks must be a tuple of non-empty strings")
        existing = self._routes.get(artifact_type)
        if existing is not None:
            raise ValidationError(
                f"{artifact_type} is already validated by {existing.validator_id}"
            )
        route = StructureRoute(
            artifact_type=artifact_type,
            validator_id=validator_id,
            validator=validator,
            checks=checks,
        )
        self._routes[artifact_type] = route
        return route

    def routes(self) -> tuple[StructureRoute, ...]:
        """Return every registered route, ordered by artifact type."""
        return tuple(self._routes[key] for key in sorted(self._routes))

    def resolve(self, artifact_type: str) -> StructureRoute:
        """Return the route for one artifact type, or fail closed."""
        route = self._routes.get(artifact_type)
        if route is None:
            registered = ", ".join(sorted(self._routes))
            raise ValidationError(
                f"no structure validator is registered for {artifact_type}, so its "
                f"structure cannot be verified; registered: {registered or 'none'}"
            )
        return route

    def checks_for(self, artifact_type: str) -> tuple[str, ...]:
        """Return the probe checks L3 must collect for this type.

        An unregistered type returns no checks rather than raising: L3 still runs
        and reports its own verdict, and L4 is where the missing validator is
        reported.
        """
        route = self._routes.get(artifact_type)
        return () if route is None else route.checks

    def validate(self, request: StructureRequest) -> Mapping[str, Any]:
        """Run the registered validator and normalize how it may fail."""
        route = self.resolve(request.artifact_type)
        try:
            details = route.validator(request)
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a validation error
            raise ValidationError(f"{route.validator_id} failed: {exc}") from exc
        if not isinstance(details, Mapping):
            raise ValidationError(
                f"{route.validator_id} must return a mapping of checked facts"
            )
        return dict(details)


TEXTURE2D_VALIDATOR_ID = "texture2d_structure"
TEXTURE2D_CHECKS = ("texture2d",)


def validate_texture2d(request: StructureRequest) -> dict[str, Any]:
    """Require the loaded texture to have real pixels.

    A ``Texture2D`` that imported and loaded can still be a zero-sized image, and
    binding one gives a worker an invisible sprite with no error anywhere. Godot
    reports the dimensions of the loaded resource, not of the file on disk, so
    this is the imported result being checked rather than the source PNG.
    """
    structure = request.probe.structure.get("texture2d")
    if not isinstance(structure, Mapping):
        raise ValidationError(
            "the Godot probe collected no texture2d structure for "
            f"{request.artifact_path}"
        )
    reported = structure.get("error")
    if reported:
        raise ValidationError(str(reported))
    dimensions: dict[str, int] = {}
    for axis in ("width", "height"):
        value = structure.get(axis)
        if type(value) is not int or value <= 0:
            raise ValidationError(
                f"the loaded Texture2D reports {axis} {value!r}; a usable texture "
                "needs a positive width and height"
            )
        dimensions[axis] = value
    return dimensions


def build_default_structures() -> StructureValidatorRegistry:
    """Return a new registry holding every validator the shared layer ships."""
    registry = StructureValidatorRegistry()
    registry.register(
        artifact_type="Texture2D",
        validator_id=TEXTURE2D_VALIDATOR_ID,
        validator=validate_texture2d,
        checks=TEXTURE2D_CHECKS,
    )
    return registry
