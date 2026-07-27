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

The registry also owns whether those facts were actually collected. A check name
``probe.gd`` does not implement is rejected at registration, and a declared check
the probe could not answer fails the level before the validator runs -- otherwise
a validator that simply ignores ``request.probe.structure`` would return normally
and carry the ladder to ``ready`` while the L3 details record that the check was
impossible.

The shared layer ships exactly one validator, for the one artifact type it
compiles -- ``Texture2D``, through ``asset_compiler/texture2d.py``. Every other
type lands with its family skill.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Callable

from ._bridge import (
    LAYOUT_ARTIFACT_TYPES,
    StableEntryError,
    assert_within_output_dir,
    check_output_path,
    resolve_res_path,
)
from .contract import ValidationError
from .godot_probe import PROBE_CHECKS, ProbeResult
from asset_compiler.atlas_texture import read_atlas_texture_input
from asset_compiler.stylebox_texture import read_stylebox_texture_input

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

    def source_file(self) -> Path:
        """Resolve the declared source under its stable output directory.

        L4 validators may need to read their source recipe independently of the
        ladder.  Keep that read behind the same ``res://`` and on-disk
        containment checks as compiler input so a direct validator call cannot
        use a traversal, absolute path, or escaping symlink.
        """
        try:
            check_output_path(
                self.source_path,
                production_family=self.production_family,
                asset_id=self.asset_id,
                label="source_path",
            )
            return assert_within_output_dir(
                self.project_root,
                resolve_res_path(self.project_root, self.source_path, label="source_path"),
                production_family=self.production_family,
                asset_id=self.asset_id,
                label="source_path",
            )
        except (OSError, StableEntryError, ValueError) as exc:
            raise ValidationError(
                f"source_path cannot be resolved: {self.source_path!r} ({exc})"
            ) from exc

    def checked_structure(self, check: str) -> Mapping[str, Any]:
        """Return the facts Godot collected for one check, or fail closed.

        The single place that decides whether a structural check was answered.
        The registry calls it for every declared check before the validator runs,
        and a validator reads its own facts through it, so a validator used
        outside the registry gets the same guarantee rather than an attribute
        error on a missing answer.
        """
        answered = self.probe.structure.get(check)
        if not isinstance(answered, Mapping):
            raise ValidationError(
                f"the Godot probe reported no {check!r} structural check for "
                f"{self.artifact_path}"
            )
        reported = answered.get("error")
        if reported:
            raise ValidationError(
                f"the {check!r} structural check could not be performed on "
                f"{self.artifact_path}: {reported}"
            )
        return answered


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
        unknown = tuple(check for check in checks if check not in PROBE_CHECKS)
        if unknown:
            raise ValidationError(
                f"probe.gd implements no structural check named "
                f"{', '.join(unknown)}; implemented: {', '.join(PROBE_CHECKS)}"
            )
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

    @staticmethod
    def _require_answered_checks(route: StructureRoute, request: StructureRequest) -> None:
        """Fail before the validator runs if Godot did not answer a declared check.

        The registry, not the validator, owns this. A validator that never reads
        ``request.probe.structure`` -- or reads only part of it -- would otherwise
        return normally and carry the whole ladder to ``ready`` while the probe
        result sitting in the L3 details says the check could not be performed.
        Making every validator repeat the guard would only mean every family gets
        one chance to forget it.

        ``checks`` are what the validator declared it needs, so a missing or
        errored one is a level that did not run, not an optional extra.
        """
        for check in route.checks:
            request.checked_structure(check)

    def validate(self, request: StructureRequest) -> Mapping[str, Any]:
        """Run the registered validator and normalize how it may fail."""
        route = self.resolve(request.artifact_type)
        self._require_answered_checks(route, request)
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
ATLAS_TEXTURE_VALIDATOR_ID = "atlas_texture_fixed_slot_structure"
ATLAS_TEXTURE_CHECKS = ("atlas_texture",)
STYLEBOX_TEXTURE_VALIDATOR_ID = "stylebox_texture_nine_slice_structure"
STYLEBOX_TEXTURE_CHECKS = ("stylebox_texture",)


def validate_texture2d(request: StructureRequest) -> dict[str, Any]:
    """Require the loaded texture to have real pixels.

    A ``Texture2D`` that imported and loaded can still be a zero-sized image, and
    binding one gives a worker an invisible sprite with no error anywhere. Godot
    reports the dimensions of the loaded resource, not of the file on disk, so
    this is the imported result being checked rather than the source PNG.

    The template for a family validator: read the declared checks through
    :meth:`StructureRequest.checked_structure` and judge only what this type
    means. Whether the probe answered at all is the registry's guarantee, not
    something each validator re-implements.
    """
    structure = request.checked_structure("texture2d")
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


def validate_atlas_texture(request: StructureRequest) -> dict[str, Any]:
    """Require the loaded resource to retain its declared region and zero margin."""
    try:
        expected = read_atlas_texture_input(request)
    except Exception as exc:  # CompilerError is a family-input failure at L4.
        raise ValidationError(str(exc)) from exc
    structure = request.checked_structure("atlas_texture")
    if structure.get("has_atlas") is not True:
        raise ValidationError("the loaded AtlasTexture has no atlas texture")
    actual_atlas_path = structure.get("atlas_path")
    if actual_atlas_path != expected.atlas_path:
        raise ValidationError(
            "the loaded AtlasTexture atlas_path is "
            f"{actual_atlas_path!r}, not {expected.atlas_path!r}"
        )
    for rectangle_name, expected_value in (
        ("region", list(expected.region)),
        ("margin", [0, 0, 0, 0]),
    ):
        actual = structure.get(rectangle_name)
        if not isinstance(actual, list) or len(actual) != 4:
            raise ValidationError(
                f"the loaded AtlasTexture reported no {rectangle_name} rectangle"
            )
        if any(type(value) not in (int, float) or isinstance(value, bool) for value in actual):
            raise ValidationError(
                f"the loaded AtlasTexture reported an invalid {rectangle_name} rectangle"
            )
        if list(actual) != expected_value:
            raise ValidationError(
                f"the loaded AtlasTexture {rectangle_name} is {actual!r}, not "
                f"{expected_value!r}"
            )
    return {
        "logical_asset_id": expected.logical_asset_id,
        "atlas_path": expected.atlas_path,
        "region": list(expected.region),
        "margin": [0, 0, 0, 0],
    }


def _exact_numbers(actual: Any, expected: list[int | float], label: str) -> None:
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValidationError(f"the loaded StyleBoxTexture reported no {label}")
    if any(type(value) not in (int, float) or isinstance(value, bool) for value in actual):
        raise ValidationError(f"the loaded StyleBoxTexture reported an invalid {label}")
    if list(actual) != expected:
        raise ValidationError(
            f"the loaded StyleBoxTexture {label} is {actual!r}, not {expected!r}"
        )


def _float32_numbers(actual: Any, expected: list[int | float], label: str) -> None:
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValidationError(f"the loaded StyleBoxTexture reported no {label}")
    if any(type(value) not in (int, float) or isinstance(value, bool) for value in actual):
        raise ValidationError(f"the loaded StyleBoxTexture reported an invalid {label}")
    if not all(
        math.isfinite(float(value))
        and math.isclose(float(value), float(wanted), rel_tol=1e-6, abs_tol=1e-6)
        for value, wanted in zip(actual, expected)
    ):
        raise ValidationError(
            f"the loaded StyleBoxTexture {label} is {actual!r}, not {expected!r}"
        )


def validate_stylebox_texture(request: StructureRequest) -> dict[str, Any]:
    """Require Godot's loaded StyleBoxTexture to retain every recipe fact."""
    try:
        expected = read_stylebox_texture_input(request)
    except Exception as exc:
        raise ValidationError(str(exc)) from exc
    structure = request.checked_structure("stylebox_texture")
    if structure.get("has_texture") is not True:
        raise ValidationError("the loaded StyleBoxTexture has no texture")
    if structure.get("texture_path") != expected.texture_path:
        raise ValidationError(
            "the loaded StyleBoxTexture texture_path is "
            f"{structure.get('texture_path')!r}, not {expected.texture_path!r}"
        )
    _exact_numbers(structure.get("texture_region"), list(expected.texture_region), "texture_region")
    _exact_numbers(structure.get("border"), list(expected.border), "border")
    _float32_numbers(structure.get("expand_margin"), list(expected.expand_margin), "expand_margin")
    _exact_numbers(
        structure.get("axis_stretch"),
        [
            {"stretch": 0, "tile": 1, "tile_fit": 2}[expected.axis_stretch[0]],
            {"stretch": 0, "tile": 1, "tile_fit": 2}[expected.axis_stretch[1]],
        ],
        "axis_stretch",
    )
    return {
        "texture_path": expected.texture_path,
        "texture_region": list(expected.texture_region),
        "border": list(expected.border),
        "expand_margin": list(expected.expand_margin),
        "axis_stretch": {"horizontal": expected.axis_stretch[0], "vertical": expected.axis_stretch[1]},
    }


def build_default_structures() -> StructureValidatorRegistry:
    """Return a new registry holding every validator the shared layer ships."""
    from . import sprite_frames

    registry = StructureValidatorRegistry()
    registry.register(
        artifact_type="Texture2D",
        validator_id=TEXTURE2D_VALIDATOR_ID,
        validator=validate_texture2d,
        checks=TEXTURE2D_CHECKS,
    )
    registry.register(
        artifact_type="StyleBoxTexture",
        validator_id=STYLEBOX_TEXTURE_VALIDATOR_ID,
        validator=validate_stylebox_texture,
        checks=STYLEBOX_TEXTURE_CHECKS,
    )
    registry.register(
        artifact_type="AtlasTexture",
        validator_id=ATLAS_TEXTURE_VALIDATOR_ID,
        validator=validate_atlas_texture,
        checks=ATLAS_TEXTURE_CHECKS,
    )
    sprite_frames.register_into(registry)
    return registry
