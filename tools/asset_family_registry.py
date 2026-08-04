#!/usr/bin/env python3
"""The authoritative map from a public Asset Skill family to its registration chain.

Every first-class family advertised by ``/gm-asset`` delivers a generic Asset
Skill result and has to turn that result into a stable entry a worker can
resolve. Which layout it may bind, which Godot artifact it compiles, which
deterministic builder adapts the result, how many entries that produces, and
which ``processing_status`` is its completion state used to be spread across
``tools/asset_stable_entry.py``, ``tools/asset_skill_contract_check.py``, the
``/gm-asset`` routing tables, ``references/asset-runtime-pipeline.md``, and a
hand-maintained tuple in each test. Nothing tied those lists together, so a
family could advertise a runtime delivery, validate it, and still have no
adapter that reaches ``ready``, and the suite stayed green.

This module is that single source of truth. The enums elsewhere derive from it,
and ``tests/tools/test_asset_family_closure.py`` drives every route declared
here from its representative result through registration to a worker snapshot.

**Routes, not families, are the unit.** Several Skills accept more than one
request shape and deliver a different layout and artifact for each:
``platform-strip`` publishes per-segment ``Texture2D`` files for
``kind: "single"`` and cut ``AtlasTexture`` regions for ``kind: "atlas"``, and
``fx-bundle`` compiles a ``Texture2D`` for a static effect and a
``SpriteFrames`` for an animated one. Recording only the union of a family's
layouts and artifacts hides a variant whose adapter is missing, because every
individual assertion still passes against the other variant's fixture. Each
variant therefore carries its own representative result and registration
contract.

Every declared route is complete. ``--check`` fails closed when a declared
family, fixture, or adapter stopped shipping, and ``publish.py`` runs it before
it copies anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTRY_VERSION = 2

# Where a family's Skill, standalone validator, and fixtures live.
SKILLS_ROOT = "skills/assets"

# ``role`` separates a worker-consumable delivery from a reference-only one.
RUNTIME_ROLE = "runtime"
REFERENCE_ROLE = "reference"

# ``entry_shape`` is how one validated delivery becomes stable entries:
#
# - ``one_entry``           one runtime asset, one entry.
# - ``entry_per_output``    one production, several separately bindable
#                           resources out of one shared directory; every entry
#                           carries the shared ``bundle_id``.
# - ``anchor_entry``        several runtime resources, but one entry anchors the
#                           set and the metadata beside it is the inventory.
ONE_ENTRY = "one_entry"
ENTRY_PER_OUTPUT = "entry_per_output"
ANCHOR_ENTRY = "anchor_entry"

# The completion state each role's work stops at.
TERMINAL_STATUS = {RUNTIME_ROLE: "ready", REFERENCE_ROLE: "source_ready"}

# The single request shape a family with no producer variants accepts.
DEFAULT_VARIANT = "default"


@dataclass(frozen=True)
class DeliveryVariant:
    """One request shape a family accepts, and what that shape registers as.

    A family with a single request shape has exactly one of these, named
    ``default``. A family whose request selects between genuinely different
    productions has one per variant, each with its own representative result,
    so a missing adapter on one variant cannot hide behind the other.
    """

    variant: str
    #: The ``source_layout.type`` values this route's entries bind, exactly as
    #: its representative delivery does. This is the driven contract, not the
    #: schema's compatibility superset: which artifact a layout *may* compile to
    #: at all stays in ``asset_stable_entry.LAYOUT_ARTIFACT_TYPES``. Declaring a
    #: layout no representative delivery binds would be an unverifiable claim,
    #: so the closure test asserts equality against the fixture.
    entry_source_layouts: tuple[str, ...]
    #: ``godot_artifact.type`` values its entries bind; empty for reference.
    artifact_types: tuple[str, ...]
    #: How many runtime outputs one validated delivery declares.
    runtime_outputs: str
    #: How that delivery becomes stable entries.
    entry_shape: str
    #: Deterministic ``tools/`` builders that adapt the result into drafts.
    entry_builders: tuple[str, ...]
    #: True when the builder drafts ``compiled`` and promotes it on a later run.
    promotes_from_compiled: bool
    #: Repo-relative representative Asset Skill result for this variant.
    representative_result: str
    #: Repo-relative representative request, when the family ships one.
    representative_request: str | None = None

    def __post_init__(self) -> None:
        label = f"variant {self.variant!r}"
        if not self.variant.strip():
            raise ValueError("a delivery variant needs a non-empty name")
        if self.runtime_outputs not in ("none", "one", "many"):
            raise ValueError(f"{label}: unknown runtime_outputs")
        if not self.entry_builders:
            raise ValueError(f"{label}: a route needs a deterministic entry builder")
        if self.entry_shape not in (ONE_ENTRY, ENTRY_PER_OUTPUT, ANCHOR_ENTRY):
            raise ValueError(f"{label}: unknown entry_shape {self.entry_shape!r}")
        if not self.entry_source_layouts:
            raise ValueError(f"{label}: a variant must name its source layout")

    @property
    def is_reference_only(self) -> bool:
        return not self.artifact_types

    @property
    def uses_bundle_id(self) -> bool:
        """True when each runtime output registers under a shared ``bundle_id``."""
        return self.entry_shape == ENTRY_PER_OUTPUT

    @property
    def terminal_status(self) -> str:
        return TERMINAL_STATUS[
            REFERENCE_ROLE if self.is_reference_only else RUNTIME_ROLE
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "entry_source_layouts": list(self.entry_source_layouts),
            "artifact_types": list(self.artifact_types),
            "runtime_outputs": self.runtime_outputs,
            "entry_shape": self.entry_shape,
            "entry_builders": list(self.entry_builders),
            "terminal_status": self.terminal_status,
            "promotes_from_compiled": self.promotes_from_compiled,
            "uses_bundle_id": self.uses_bundle_id,
            "representative_request": self.representative_request,
            "representative_result": self.representative_result,
        }


@dataclass(frozen=True)
class FamilySpec:
    """One public first-class Asset Skill family and every shape it delivers."""

    family: str
    role: str
    variants: tuple[DeliveryVariant, ...]

    def __post_init__(self) -> None:
        if self.role not in (RUNTIME_ROLE, REFERENCE_ROLE):
            raise ValueError(f"{self.family}: unknown role {self.role!r}")
        if not self.variants:
            raise ValueError(f"{self.family}: a family must declare a delivery")
        names = [item.variant for item in self.variants]
        if len(set(names)) != len(names):
            raise ValueError(f"{self.family}: duplicate variant name")
        for item in self.variants:
            if item.is_reference_only != (self.role == REFERENCE_ROLE):
                raise ValueError(
                    f"{self.family}: variant {item.variant!r} does not match the "
                    f"family role {self.role!r}"
                )

    @property
    def is_reference_only(self) -> bool:
        return self.role == REFERENCE_ROLE

    @property
    def terminal_status(self) -> str:
        return TERMINAL_STATUS[self.role]

    @property
    def entry_source_layouts(self) -> tuple[str, ...]:
        return tuple(
            sorted({item for v in self.variants for item in v.entry_source_layouts})
        )

    @property
    def artifact_types(self) -> tuple[str, ...]:
        return tuple(sorted({item for v in self.variants for item in v.artifact_types}))

    @property
    def entry_builders(self) -> tuple[str, ...]:
        return tuple(sorted({item for v in self.variants for item in v.entry_builders}))

    @property
    def uses_bundle_id(self) -> bool:
        return any(item.uses_bundle_id for item in self.variants)

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
            "role": self.role,
            "terminal_status": self.terminal_status,
            "uses_bundle_id": self.uses_bundle_id,
            "skill_dir": self.skill_dir,
            "variants": [item.to_dict() for item in self.variants],
        }


_SPECS: tuple[FamilySpec, ...] = (
    FamilySpec(
        family="background-map",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="one",
                entry_shape=ONE_ENTRY,
                entry_builders=("asset_finalize_entry_draft.py",),
                promotes_from_compiled=False,
                representative_result=(
                    "skills/assets/background-map/fixtures/representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="card-kit",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas", "theme_recipe"),
                artifact_types=("AtlasTexture", "StyleBoxTexture", "Theme"),
                runtime_outputs="many",
                entry_shape=ENTRY_PER_OUTPUT,
                entry_builders=("asset_ui_card_entry_draft.py",),
                promotes_from_compiled=False,
                representative_request=(
                    "skills/assets/card-kit/fixtures/representative-request.json"
                ),
                representative_result=(
                    "skills/assets/card-kit/fixtures/representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="character-bundle",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("grid_sheet",),
                artifact_types=("SpriteFrames",),
                runtime_outputs="one",
                entry_shape=ONE_ENTRY,
                entry_builders=("asset_action_entry_draft.py",),
                promotes_from_compiled=True,
                representative_request=(
                    "skills/assets/character-bundle/fixtures/valid-request.json"
                ),
                representative_result=(
                    "skills/assets/character-bundle/fixtures/valid-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="compact-prop-pack",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas",),
                artifact_types=("AtlasTexture",),
                runtime_outputs="many",
                entry_shape=ENTRY_PER_OUTPUT,
                entry_builders=("asset_compact_prop_pack_entry_draft.py",),
                promotes_from_compiled=False,
                representative_result=(
                    "skills/assets/compact-prop-pack/fixtures/"
                    "representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="fx-bundle",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant="static",
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="one",
                entry_shape=ONE_ENTRY,
                entry_builders=("asset_curation_entry_draft.py",),
                promotes_from_compiled=True,
                representative_request=(
                    "skills/assets/fx-bundle/fixtures/static-request.json"
                ),
                representative_result=(
                    "skills/assets/fx-bundle/fixtures/static-result.json"
                ),
            ),
            DeliveryVariant(
                variant="animated",
                entry_source_layouts=("grid_sheet",),
                artifact_types=("SpriteFrames",),
                runtime_outputs="one",
                entry_shape=ONE_ENTRY,
                entry_builders=("asset_action_entry_draft.py",),
                promotes_from_compiled=True,
                representative_request=(
                    "skills/assets/fx-bundle/fixtures/animated-request.json"
                ),
                representative_result=(
                    "skills/assets/fx-bundle/fixtures/animated-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="platform-strip",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant="single",
                entry_source_layouts=("single",),
                artifact_types=("Texture2D",),
                runtime_outputs="many",
                entry_shape=ENTRY_PER_OUTPUT,
                entry_builders=("asset_platform_strip_entry_draft.py",),
                promotes_from_compiled=False,
                representative_request=(
                    "skills/assets/platform-strip/fixtures/"
                    "representative-single-request.json"
                ),
                representative_result=(
                    "skills/assets/platform-strip/fixtures/"
                    "representative-single-result.json"
                ),
            ),
            DeliveryVariant(
                variant="atlas",
                entry_source_layouts=("region_atlas",),
                artifact_types=("AtlasTexture",),
                runtime_outputs="many",
                entry_shape=ENTRY_PER_OUTPUT,
                entry_builders=("asset_platform_strip_entry_draft.py",),
                promotes_from_compiled=False,
                representative_request=(
                    "skills/assets/platform-strip/fixtures/"
                    "representative-request.json"
                ),
                representative_result=(
                    "skills/assets/platform-strip/fixtures/"
                    "representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="scene-prop-set",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas",),
                artifact_types=("AtlasTexture",),
                runtime_outputs="many",
                entry_shape=ANCHOR_ENTRY,
                entry_builders=("asset_scene_prop_set_entry_draft.py",),
                promotes_from_compiled=False,
                representative_result=(
                    "skills/assets/scene-prop-set/fixtures/representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="screen-reference",
        role=REFERENCE_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("reference",),
                artifact_types=(),
                runtime_outputs="none",
                entry_shape=ONE_ENTRY,
                entry_builders=("asset_finalize_entry_draft.py",),
                promotes_from_compiled=False,
                representative_request=(
                    "skills/assets/_shared/samples/request/screen-reference.json"
                ),
                representative_result=(
                    "skills/assets/screen-reference/fixtures/representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="tileset",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("tile_atlas",),
                artifact_types=("TileSet",),
                runtime_outputs="one",
                entry_shape=ONE_ENTRY,
                entry_builders=("asset_tileset_entry_draft.py",),
                promotes_from_compiled=False,
                representative_result=(
                    "skills/assets/tileset/fixtures/representative-result.json"
                ),
            ),
        ),
    ),
    FamilySpec(
        family="ui-kit",
        role=RUNTIME_ROLE,
        variants=(
            DeliveryVariant(
                variant=DEFAULT_VARIANT,
                entry_source_layouts=("region_atlas", "theme_recipe"),
                artifact_types=("AtlasTexture", "StyleBoxTexture", "Theme"),
                runtime_outputs="many",
                entry_shape=ENTRY_PER_OUTPUT,
                entry_builders=("asset_ui_card_entry_draft.py",),
                promotes_from_compiled=False,
                representative_request=(
                    "skills/assets/ui-kit/fixtures/representative-request.json"
                ),
                representative_result=(
                    "skills/assets/ui-kit/fixtures/representative-result.json"
                ),
            ),
        ),
    ),
)

FAMILIES: dict[str, FamilySpec] = {spec.family: spec for spec in _SPECS}

# Frozen views the rest of the toolchain imports instead of re-declaring a list.
FAMILY_NAMES: frozenset[str] = frozenset(FAMILIES)
REFERENCE_FAMILY_NAMES: frozenset[str] = frozenset(
    name for name, spec in FAMILIES.items() if spec.is_reference_only
)
RUNTIME_FAMILY_NAMES: frozenset[str] = frozenset(FAMILY_NAMES - REFERENCE_FAMILY_NAMES)
BUNDLE_FAMILY_NAMES: frozenset[str] = frozenset(
    name for name, spec in FAMILIES.items() if spec.uses_bundle_id
)


class FamilyRegistryError(Exception):
    """Raised when the family registry disagrees with what the repo ships."""


def spec(family: str) -> FamilySpec:
    """Return one family's declared contract."""
    try:
        return FAMILIES[family]
    except KeyError:
        raise FamilyRegistryError(f"unknown production family: {family}") from None


def families(*, role: str | None = None) -> list[FamilySpec]:
    """Return the declared families, optionally filtered by role."""
    return [
        item
        for item in FAMILIES.values()
        if role is None or item.role == role
    ]


def routes(*, role: str | None = None) -> list[tuple[FamilySpec, DeliveryVariant]]:
    """Return every ``(family, variant)`` pair, optionally filtered.

    Routes are the unit the closure test enumerates: a family with two request
    shapes has two independent registration chains, and only one of them may be
    closed.
    """
    return [
        (item, variant)
        for item in FAMILIES.values()
        for variant in item.variants
        if role is None or item.role == role
    ]


def to_dict() -> dict[str, Any]:
    """Return the whole registry as plain JSON-serializable data."""
    return {
        "version": REGISTRY_VERSION,
        "families": [item.to_dict() for item in FAMILIES.values()],
    }


def repo_root() -> Path:
    """Return the framework checkout this module lives in."""
    return Path(__file__).resolve().parents[1]


def check_registry(root: Path | None = None) -> list[str]:
    """Return every disagreement between this map and what the repo ships.

    The default pass is structural: an advertised family with no skill
    directory, a declared builder that does not exist, a missing representative
    result, or a family the schema allows but this map never declares all mean
    the registration chain can no longer be reasoned about from one place.
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
        for variant in item.variants:
            label = f"{name}[{variant.variant}]"
            fixtures = (variant.representative_request, variant.representative_result)
            for relative in [entry for entry in fixtures if entry]:
                if not (base / relative).is_file():
                    issues.append(
                        f"{label} declares a fixture that does not exist: {relative}"
                    )
            for builder in variant.entry_builders:
                if not (base / "tools" / builder).is_file():
                    issues.append(
                        f"{label} names a missing entry builder: tools/{builder}"
                    )

    return issues


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Read or verify the authoritative Asset Skill family registry"
    )
    parser.add_argument("--output", choices=["json"], help="Print the registry as JSON")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the registry against the shipped skills, fixtures, and builders",
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
