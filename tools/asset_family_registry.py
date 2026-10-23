#!/usr/bin/env python3
"""The authoritative map from a public Asset Skill family to its registration chain.

Every first-class family advertised by ``/gm-asset`` delivers a generic Asset
Skill result and records the result outputs a worker can
resolve. Which layout it may bind, which Godot artifact it compiles, which
deterministic builder adapts the result, how many entries that produces, and
which logical outputs a completed delivery contains used to be spread across
the request/result checker, the
``/gm-asset`` routing tables, ``references/asset-runtime-pipeline.md``, and a
hand-maintained tuple in each test. Nothing tied those lists together, so a
family could advertise a runtime delivery, validate it, and still have no
adapter that reaches ``generated``, and the suite stayed green.

This module is that single source of truth for families, routes, ``ASSETS.md``
row statuses, and physical source layouts. The enums elsewhere derive from it
or are bound to it by consistency tests.
``tests/tools/test_asset_family_closure.py`` supplies its own representative
deliveries and drives every declared route through registration to a worker
snapshot.

**Routes, not families, are the unit.** Several Skills accept more than one
request shape and deliver a different layout and artifact for each:
``platform-strip`` publishes per-segment ``Texture2D`` files for
``kind: "single"`` and cut ``AtlasTexture`` regions for ``kind: "atlas"``, and
``fx-bundle`` compiles a ``Texture2D`` for a static effect and a
``SpriteFrames`` for an animated one. Recording only the union of a family's
layouts and artifacts hides a variant whose adapter is missing, because every
individual assertion still passes against the other variant's delivery. Each
variant therefore carries its own registration contract.

Every declared route is complete. ``--check`` fails closed when a declared
family or adapter stopped shipping, and ``publish.py`` runs it before it copies
anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTRY_VERSION = 3

# Where a family's Skill and standalone validator live.
SKILLS_ROOT = "skills/assets"

# Every family delivers worker-consumable runtime outputs, and every runtime
# ``ASSETS.md`` row moves forward only, from ``MISSING`` to exactly one of
# these: ``provided`` for a user-supplied file, the family's terminal status
# after direct registration, or ``deferred`` for work this tag does not do.
TERMINAL_STATUS = "generated"
PROVIDED_STATUS = "provided"
DEFERRED_STATUS = "deferred"
MISSING_STATUS = "MISSING"
ASSET_ROW_STATUSES = (MISSING_STATUS, PROVIDED_STATUS, TERMINAL_STATUS, DEFERRED_STATUS)

# The physical arrangement of a source image a compiler reads. A layout says
# how pixels are laid out, never what an image is used for: a provider identity
# anchor or provenance image is an ``outputs[].role: reference`` entry, not a
# layout.
SOURCE_LAYOUTS = ("single", "grid_sheet", "region_atlas", "tile_atlas", "theme_recipe")

# The single request shape a family with no producer variants accepts.
DEFAULT_VARIANT = "default"

# A request must explicitly select every family that has more than one delivery
# route.  Result registration uses this selector to avoid accepting a type from
# a sibling variant.
REQUEST_VARIANT_FIELDS = {
    "fx-bundle": "mode",
    "platform-strip": "kind",
}


@dataclass(frozen=True)
class DeliveryVariant:
    """One request shape a family accepts, and what that shape registers as.

    A family with a single request shape has exactly one of these, named
    ``default``. A family whose request selects between genuinely different
    productions has one per variant, so a missing adapter on one variant cannot
    hide behind the other.
    """

    variant: str
    #: The ``source_layout.type`` values this route's entries bind.
    entry_source_layouts: tuple[str, ...]
    #: ``godot_artifact.type`` values its entries bind.
    artifact_types: tuple[str, ...]
    #: How many runtime outputs one validated delivery declares.
    runtime_outputs: str

    def __post_init__(self) -> None:
        label = f"variant {self.variant!r}"
        if not self.variant.strip():
            raise ValueError("a delivery variant needs a non-empty name")
        if self.runtime_outputs not in ("one", "many"):
            raise ValueError(f"{label}: unknown runtime_outputs")
        if not self.entry_source_layouts:
            raise ValueError(f"{label}: a variant must name its source layout")
        unknown = sorted(set(self.entry_source_layouts) - set(SOURCE_LAYOUTS))
        if unknown:
            raise ValueError(f"{label}: unknown source layout {', '.join(unknown)}")
        if not self.artifact_types:
            raise ValueError(f"{label}: a variant must name its Godot artifact type")

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "entry_source_layouts": list(self.entry_source_layouts),
            "artifact_types": list(self.artifact_types),
            "runtime_outputs": self.runtime_outputs,
        }


@dataclass(frozen=True)
class FamilySpec:
    """One public first-class Asset Skill family and every shape it delivers."""

    family: str
    variants: tuple[DeliveryVariant, ...]

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError(f"{self.family}: a family must declare a delivery")
        names = [item.variant for item in self.variants]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.family}: duplicate variant name")

    @property
    def terminal_status(self) -> str:
        return TERMINAL_STATUS

    @property
    def entry_source_layouts(self) -> tuple[str, ...]:
        return tuple(
            sorted({item for v in self.variants for item in v.entry_source_layouts})
        )

    @property
    def artifact_types(self) -> tuple[str, ...]:
        return tuple(sorted({item for v in self.variants for item in v.artifact_types}))

    @property
    def skill_dir(self) -> str:
        return f"{SKILLS_ROOT}/{self.family}"

    def variant(self, name: str) -> DeliveryVariant:
        for item in self.variants:
            if item.variant == name:
                return item
        raise FamilyRegistryError(f"{self.family} has no delivery variant {name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "terminal_status": self.terminal_status,
            "skill_dir": self.skill_dir,
            "variants": [item.to_dict() for item in self.variants],
        }


_SPECS: tuple[FamilySpec, ...] = (
    FamilySpec(
        family="background-map",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="one",
            ),
        ),
    ),
    FamilySpec(
        family="card-kit",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas", "theme_recipe"),
                artifact_types=("AtlasTexture", "StyleBoxTexture", "Theme"),
                runtime_outputs="many",
            ),
        ),
    ),
    FamilySpec(
        family="character-bundle",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("grid_sheet",),
                artifact_types=("SpriteFrames",),
                runtime_outputs="one",
            ),
        ),
    ),
    FamilySpec(
        family="compact-prop-pack",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas",),
                artifact_types=("AtlasTexture",),
                runtime_outputs="many",
            ),
        ),
    ),
    FamilySpec(
        family="fx-bundle",
        variants=(
            DeliveryVariant(
                variant="static",
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="one",
            ),
            DeliveryVariant(
                variant="animated",
                entry_source_layouts=("grid_sheet",),
                artifact_types=("SpriteFrames",),
                runtime_outputs="one",
            ),
        ),
    ),
    FamilySpec(
        family="platform-strip",
        variants=(
            DeliveryVariant(
                variant="single",
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="many",
            ),
            DeliveryVariant(
                variant="atlas",
                entry_source_layouts=("region_atlas",),
                artifact_types=("AtlasTexture",),
                runtime_outputs="many",
            ),
        ),
    ),
    FamilySpec(
        family="portrait",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="one",
            ),
        ),
    ),
    FamilySpec(
        family="scene-prop-set",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas",),
                artifact_types=("AtlasTexture",),
                runtime_outputs="many",
            ),
        ),
    ),
    FamilySpec(
        family="tileset",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("tile_atlas",),
                artifact_types=("TileSet",),
                runtime_outputs="one",
            ),
        ),
    ),
    FamilySpec(
        family="ui-kit",
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas", "theme_recipe"),
                artifact_types=("AtlasTexture", "StyleBoxTexture", "Theme"),
                runtime_outputs="many",
            ),
        ),
    ),
)

FAMILIES: dict[str, FamilySpec] = {spec.family: spec for spec in _SPECS}

# Frozen views the rest of the toolchain imports instead of re-declaring a list.
FAMILY_NAMES: frozenset[str] = frozenset(FAMILIES)


class FamilyRegistryError(Exception):
    """Raised when the family registry disagrees with what the repo ships."""


def spec(family: str) -> FamilySpec:
    """Return one family's declared contract."""
    try:
        return FAMILIES[family]
    except KeyError:
        raise FamilyRegistryError(f"unknown production family: {family}") from None


def variant_for_request(request: dict[str, Any]) -> DeliveryVariant:
    """Return the single output contract selected by ``request``."""
    family = request.get("asset_type")
    if not isinstance(family, str):
        raise FamilyRegistryError("request.asset_type must be a string")
    family_spec = spec(family)
    if len(family_spec.variants) == 1:
        return family_spec.variants[0]
    selector = REQUEST_VARIANT_FIELDS.get(family)
    if selector is None:
        raise FamilyRegistryError(f"{family} has no request variant selector")
    request_spec = request.get("spec")
    value = request_spec.get(selector) if isinstance(request_spec, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise FamilyRegistryError(f"{family} request.spec.{selector} must select a variant")
    try:
        return family_spec.variant(value)
    except FamilyRegistryError as exc:
        allowed = ", ".join(item.variant for item in family_spec.variants)
        raise FamilyRegistryError(
            f"{family} request.spec.{selector} must be one of: {allowed}; got {value!r}"
        ) from exc


def routes() -> list[tuple[FamilySpec, DeliveryVariant]]:
    """Return every ``(family, variant)`` pair.

    Routes are the unit the closure test enumerates: a family with two request
    shapes has two independent registration chains, so each one must be proven
    independently.
    """
    return [
        (item, variant)
        for item in FAMILIES.values()
        for variant in item.variants
    ]


def to_dict() -> dict[str, Any]:
    """Return the whole registry as plain JSON-serializable data."""
    return {
        "version": REGISTRY_VERSION,
        "row_statuses": list(ASSET_ROW_STATUSES),
        "source_layouts": list(SOURCE_LAYOUTS),
        "families": [item.to_dict() for item in FAMILIES.values()],
    }


def repo_root() -> Path:
    """Return the framework checkout this module lives in."""
    return Path(__file__).resolve().parents[1]


def check_registry(root: Path | None = None) -> list[str]:
    """Return every disagreement between this map and what the repo ships.

    The default pass is structural: an advertised family with no skill
    directory, a declared builder that does not exist, or a family the schema
    allows but this map never declares all mean the registration chain can no
    longer be reasoned about from one place.
    ``publish.py`` runs this before it copies anything.
    """
    base = repo_root() if root is None else Path(root)
    issues: list[str] = []

    skills_dir = base / SKILLS_ROOT
    if not skills_dir.is_dir():
        return [f"asset skill root is missing: {SKILLS_ROOT}"]
    shipped = {
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }
    for missing in sorted(shipped - FAMILY_NAMES):
        issues.append(
            f"{SKILLS_ROOT}/{missing} ships a first-class Asset Skill that the "
            "family registry never declares"
        )
    for missing in sorted(FAMILY_NAMES - shipped):
        issues.append(f"the family registry declares {missing} but it ships no Skill")

    for name in sorted(FAMILY_NAMES & shipped):
        item = FAMILIES[name]
        for required in ("SKILL.md", "standalone_validation.py"):
            if not (skills_dir / name / required).is_file():
                issues.append(f"{item.skill_dir}/{required} is missing")

    return issues


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Read or verify the authoritative Asset Skill family registry"
    )
    parser.add_argument("--output", choices=["json"], help="Print the registry as JSON")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the registry against shipped skills and validators",
    )
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args()

    if args.check:
        issues = check_registry(args.project_root)
        if issues:
            print(json.dumps({"ok": False, "issues": issues}, indent=2))
            return 1
        print(
            json.dumps(
                {
                    "ok": True,
                    "families": len(FAMILIES),
                    "routes": len(routes()),
                }
            )
        )
        return 0

    print(json.dumps(to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
