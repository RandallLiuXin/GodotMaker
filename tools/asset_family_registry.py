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
and ``tests/tools/test_asset_family_closure.py`` drives every family declared
here from its representative result through registration to a worker snapshot.

A family whose chain is not closed today is declared, not omitted:
``registration_closure="open"`` records the concrete missing link and the
upstream issue that owns it. The closure test then asserts the gap is still
real, so closing it upstream fails here until this map is updated. Silence is
never an option: an undeclared family, or an ``open`` one whose gap has
quietly disappeared, is a test failure either way.

Machine-readable form::

    python tools/asset_family_registry.py --output json
    python tools/asset_family_registry.py --check
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REGISTRY_VERSION = 1

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

# ``registration_closure`` values.
CLOSED = "closed"
OPEN = "open"


@dataclass(frozen=True)
class FamilySpec:
    """The complete delivery and registration semantics of one public family."""

    family: str
    role: str
    #: ``source_layout.type`` values this family's stable entries may bind.
    entry_source_layouts: tuple[str, ...]
    #: ``godot_artifact.type`` values its entries may bind; empty for reference.
    artifact_types: tuple[str, ...]
    #: How many runtime outputs one validated delivery declares.
    runtime_outputs: str
    #: How that delivery becomes stable entries; ``None`` only while open.
    entry_shape: str | None
    #: Deterministic ``tools/`` builders that adapt the result into drafts.
    entry_builders: tuple[str, ...]
    #: The ``processing_status`` that makes this family's work complete.
    terminal_status: str
    #: True when the builder drafts ``compiled`` and promotes it on a later run.
    promotes_from_compiled: bool
    #: Repo-relative representative Asset Skill result for this family.
    representative_result: str
    registration_closure: str = CLOSED
    #: Why the chain is not closed, and who owns it. Required when ``open``.
    open_gap: str | None = None
    #: Repo-relative representative request, when the family ships one.
    representative_request: str | None = None

    def __post_init__(self) -> None:
        if self.role not in (RUNTIME_ROLE, REFERENCE_ROLE):
            raise ValueError(f"{self.family}: unknown role {self.role!r}")
        if self.registration_closure not in (CLOSED, OPEN):
            raise ValueError(
                f"{self.family}: unknown registration_closure "
                f"{self.registration_closure!r}"
            )
        if (self.registration_closure == OPEN) != bool(self.open_gap):
            raise ValueError(
                f"{self.family}: an open registration_closure needs an open_gap, "
                "and a closed one must not carry it"
            )
        if self.role == REFERENCE_ROLE and self.artifact_types:
            raise ValueError(
                f"{self.family}: a reference-only family compiles no artifact"
            )
        if self.role == RUNTIME_ROLE and not self.artifact_types:
            raise ValueError(f"{self.family}: a runtime family must name an artifact")
        if self.registration_closure == CLOSED and not self.entry_builders:
            raise ValueError(
                f"{self.family}: a closed chain needs a deterministic entry builder"
            )
        if self.registration_closure == CLOSED and self.entry_shape is None:
            raise ValueError(f"{self.family}: a closed chain needs an entry_shape")
        if self.entry_shape not in (None, ONE_ENTRY, ENTRY_PER_OUTPUT, ANCHOR_ENTRY):
            raise ValueError(f"{self.family}: unknown entry_shape {self.entry_shape!r}")

    @property
    def is_reference_only(self) -> bool:
        return self.role == REFERENCE_ROLE

    @property
    def uses_bundle_id(self) -> bool:
        """True when each runtime output registers under a shared ``bundle_id``."""
        return self.entry_shape == ENTRY_PER_OUTPUT

    @property
    def skill_dir(self) -> str:
        return f"{SKILLS_ROOT}/{self.family}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "role": self.role,
            "entry_source_layouts": list(self.entry_source_layouts),
            "artifact_types": list(self.artifact_types),
            "runtime_outputs": self.runtime_outputs,
            "entry_shape": self.entry_shape,
            "entry_builders": list(self.entry_builders),
            "terminal_status": self.terminal_status,
            "promotes_from_compiled": self.promotes_from_compiled,
            "uses_bundle_id": self.uses_bundle_id,
            "skill_dir": self.skill_dir,
            "representative_request": self.representative_request,
            "representative_result": self.representative_result,
            "registration_closure": self.registration_closure,
            "open_gap": self.open_gap,
        }


_SPECS: tuple[FamilySpec, ...] = (
    FamilySpec(
        family="background-map",
        role=RUNTIME_ROLE,
        entry_source_layouts=("single",),
        artifact_types=("Texture2D",),
        runtime_outputs="one",
        entry_shape=ONE_ENTRY,
        entry_builders=("asset_finalize_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_result=(
            "skills/assets/background-map/fixtures/representative-result.json"
        ),
        registration_closure=OPEN,
        open_gap=(
            "asset_finalize_entry_draft.py is the only documented adapter and it "
            "always drafts source_ready with no godot_artifact, so a validated "
            "Texture2D delivery never reaches ready and never reaches a worker. "
            "Owned by GodotMaker issue #154."
        ),
    ),
    FamilySpec(
        family="card-kit",
        role=RUNTIME_ROLE,
        entry_source_layouts=("single", "region_atlas", "theme_recipe"),
        artifact_types=("AtlasTexture", "StyleBoxTexture", "Theme"),
        runtime_outputs="many",
        entry_shape=ENTRY_PER_OUTPUT,
        entry_builders=("asset_ui_card_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_request=(
            "skills/assets/card-kit/fixtures/representative-request.json"
        ),
        representative_result=(
            "skills/assets/card-kit/fixtures/representative-result.json"
        ),
    ),
    FamilySpec(
        family="character-bundle",
        role=RUNTIME_ROLE,
        entry_source_layouts=("grid_sheet",),
        artifact_types=("SpriteFrames",),
        runtime_outputs="one",
        entry_shape=ONE_ENTRY,
        entry_builders=("asset_action_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=True,
        representative_request=(
            "skills/assets/character-bundle/fixtures/valid-request.json"
        ),
        representative_result=(
            "skills/assets/character-bundle/fixtures/valid-result.json"
        ),
    ),
    FamilySpec(
        family="compact-prop-pack",
        role=RUNTIME_ROLE,
        entry_source_layouts=("region_atlas",),
        artifact_types=("AtlasTexture",),
        runtime_outputs="many",
        entry_shape=ENTRY_PER_OUTPUT,
        entry_builders=("asset_compact_prop_pack_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_result=(
            "skills/assets/compact-prop-pack/fixtures/representative-result.json"
        ),
    ),
    FamilySpec(
        family="fx-bundle",
        role=RUNTIME_ROLE,
        entry_source_layouts=("single", "grid_sheet"),
        artifact_types=("SpriteFrames", "Texture2D"),
        runtime_outputs="one",
        entry_shape=ONE_ENTRY,
        entry_builders=(
            "asset_action_entry_draft.py",
            "asset_curation_entry_draft.py",
        ),
        terminal_status="ready",
        promotes_from_compiled=True,
        representative_request="skills/assets/fx-bundle/fixtures/static-request.json",
        representative_result="skills/assets/fx-bundle/fixtures/static-result.json",
    ),
    FamilySpec(
        family="platform-strip",
        role=RUNTIME_ROLE,
        entry_source_layouts=("region_atlas",),
        artifact_types=("AtlasTexture",),
        runtime_outputs="many",
        entry_shape=None,
        entry_builders=(),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_result=(
            "skills/assets/platform-strip/fixtures/representative-result.json"
        ),
        registration_closure=OPEN,
        open_gap=(
            "No deterministic entry-draft builder exists for platform-strip. Its "
            "validated delivery is several AtlasTexture segments sharing one "
            "stable directory, which the stable-entry schema only allows through "
            "a bundle_id the family does not have, so none of its runtime "
            "outputs can be registered at all."
        ),
    ),
    FamilySpec(
        family="scene-prop-set",
        role=RUNTIME_ROLE,
        entry_source_layouts=("region_atlas",),
        artifact_types=("AtlasTexture",),
        runtime_outputs="many",
        entry_shape=ANCHOR_ENTRY,
        entry_builders=("asset_scene_prop_set_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_result=(
            "skills/assets/scene-prop-set/fixtures/representative-result.json"
        ),
    ),
    FamilySpec(
        family="screen-reference",
        role=REFERENCE_ROLE,
        entry_source_layouts=("reference",),
        artifact_types=(),
        runtime_outputs="none",
        entry_shape=ONE_ENTRY,
        entry_builders=("asset_finalize_entry_draft.py",),
        terminal_status="source_ready",
        promotes_from_compiled=False,
        representative_request=(
            "skills/assets/_shared/samples/request/screen-reference.json"
        ),
        representative_result=(
            "skills/assets/screen-reference/fixtures/representative-result.json"
        ),
    ),
    FamilySpec(
        family="tileset",
        role=RUNTIME_ROLE,
        entry_source_layouts=("tile_atlas",),
        artifact_types=("TileSet",),
        runtime_outputs="one",
        entry_shape=ONE_ENTRY,
        entry_builders=("asset_tileset_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_result=(
            "skills/assets/tileset/fixtures/representative-result.json"
        ),
    ),
    FamilySpec(
        family="ui-kit",
        role=RUNTIME_ROLE,
        entry_source_layouts=("single", "region_atlas", "theme_recipe"),
        artifact_types=("AtlasTexture", "StyleBoxTexture", "Theme"),
        runtime_outputs="many",
        entry_shape=ENTRY_PER_OUTPUT,
        entry_builders=("asset_ui_card_entry_draft.py",),
        terminal_status="ready",
        promotes_from_compiled=False,
        representative_request=(
            "skills/assets/ui-kit/fixtures/representative-request.json"
        ),
        representative_result=(
            "skills/assets/ui-kit/fixtures/representative-result.json"
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


def families(*, role: str | None = None, closure: str | None = None) -> list[FamilySpec]:
    """Return the declared families, optionally filtered by role or closure."""
    return [
        item
        for item in FAMILIES.values()
        if (role is None or item.role == role)
        and (closure is None or item.registration_closure == closure)
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

    This is the publish- and CI-side gate: an advertised family with no skill
    directory, a declared builder that does not exist, a missing representative
    result, or a family the schema allows but this map never declares all mean
    the registration chain can no longer be reasoned about from one place.
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
        if not (base / item.representative_result).is_file():
            issues.append(
                f"{name} declares a representative result that does not exist: "
                f"{item.representative_result}"
            )
        if item.representative_request and not (
            base / item.representative_request
        ).is_file():
            issues.append(
                f"{name} declares a representative request that does not exist: "
                f"{item.representative_request}"
            )
        for builder in item.entry_builders:
            if not (base / "tools" / builder).is_file():
                issues.append(f"{name} names a missing entry builder: tools/{builder}")

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
        print(json.dumps({"ok": True, "families": len(FAMILIES)}))
        return 0

    print(json.dumps(to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
