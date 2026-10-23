"""One runtime row status vocabulary and one physical source-layout vocabulary.

The family registry owns both. Every other surface that names a row status or
a source layout -- the checker, the schemas, the compiler relation,
registration, preflight, ``/gm-asset``, and the ``ASSETS.md`` template -- is
bound to it here, so a retired value cannot survive in one place.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools")]

import asset_family_registry as registry  # noqa: E402
import asset_output_paths  # noqa: E402
import asset_result_registration  # noqa: E402
import asset_skill_contract_check  # noqa: E402
import asset_user_preflight  # noqa: E402


RETIRED_STATUSES = ("ready", "source_ready")
RETIRED_LAYOUTS = ("action_frames", "reference")
FORWARD_ONLY = "MISSING -> provided | generated | deferred"

RESULT_SCHEMA = ROOT / "skills/assets/_shared/schema/asset-skill-result.schema.json"
SHARED_CONTRACT = ROOT / "skills/assets/_shared/asset-skill-contract.md"
ASSETS_TEMPLATE = ROOT / "templates/ASSETS.md"
GM_ASSET = ROOT / "skills/core/gm-asset"

# Every surface that states the runtime row lifecycle or a family's terminal
# state. A retired status written as a status (backticked, or as a table cell)
# in any of them is a second vocabulary.
STATUS_SURFACES = (
    ROOT / "tools/asset_family_registry.py",
    ROOT / "tools/asset_result_registration.py",
    ROOT / "tools/asset_user_preflight.py",
    ROOT / "tools/asset_skill_contract_check.py",
    RESULT_SCHEMA,
    SHARED_CONTRACT,
    ASSETS_TEMPLATE,
    *sorted(GM_ASSET.rglob("*.md")),
    ROOT / "docs/wiki/03-skills/asset-skills.md",
    ROOT / "docs/zh/wiki/03-skills/asset-skills.md",
    ROOT / "docs/wiki/03-skills/skill-system.md",
    ROOT / "docs/zh/wiki/03-skills/skill-system.md",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _asset_table_statuses() -> list[str]:
    text = _read(ASSETS_TEMPLATE)
    table = text.split("## Asset Table", 1)[1].split("\n## ", 1)[0]
    statuses = []
    for line in table.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not line.startswith("| ") or len(cells) != 9:
            continue
        if cells[0] in {"#", "..."} or cells[0].startswith("---"):
            continue
        statuses.append(cells[8])
    return statuses


# ---------------------------------------------------------------------------
# AC-01: one terminal status, one forward-only row lifecycle
# ---------------------------------------------------------------------------


def test_registry_declares_the_one_row_lifecycle():
    assert registry.ASSET_ROW_STATUSES == ("MISSING", "provided", "generated", "deferred")
    assert registry.TERMINAL_STATUS == "generated"
    data = registry.to_dict()
    assert data["row_statuses"] == list(registry.ASSET_ROW_STATUSES)


@pytest.mark.parametrize("family", sorted(registry.FAMILIES))
def test_every_family_terminates_at_generated(family):
    spec = registry.FAMILIES[family]
    assert spec.terminal_status == "generated"
    assert spec.to_dict()["terminal_status"] == "generated"


def test_registration_and_preflight_derive_statuses_from_the_registry():
    assert asset_result_registration.RUNTIME_STATUS == registry.TERMINAL_STATUS
    assert asset_user_preflight.DONE_STATUSES == {
        registry.PROVIDED_STATUS, registry.TERMINAL_STATUS
    }
    assert asset_user_preflight.UNFILLED_STATUSES == {
        registry.MISSING_STATUS.lower(), registry.DEFERRED_STATUS
    }


def test_manager_and_template_state_the_same_forward_only_lifecycle():
    assert FORWARD_ONLY in _read(GM_ASSET / "SKILL.md")
    assert FORWARD_ONLY in _read(ASSETS_TEMPLATE)


def test_template_rows_use_only_registry_statuses():
    statuses = _asset_table_statuses()
    assert statuses, "the ASSETS.md template must show example runtime rows"
    assert set(statuses) <= set(registry.ASSET_ROW_STATUSES)


@pytest.mark.parametrize(
    "path", STATUS_SURFACES, ids=lambda path: str(path.relative_to(ROOT))
)
def test_no_surface_names_a_retired_status(path):
    text = _read(path)
    assert "source_ready" not in text
    for status in RETIRED_STATUSES:
        assert f"`{status}`" not in text, f"{path.name} names `{status}` as a status"
        assert f"| {status} |" not in text, f"{path.name} has a `{status}` table cell"
        assert f'"{status}"' not in text, f"{path.name} has a {status!r} literal"


# ---------------------------------------------------------------------------
# AC-02: five physical source layouts, nothing else
# ---------------------------------------------------------------------------


def test_registry_declares_exactly_the_five_physical_layouts():
    assert set(registry.SOURCE_LAYOUTS) == {
        "single", "grid_sheet", "region_atlas", "tile_atlas", "theme_recipe"
    }
    assert len(registry.SOURCE_LAYOUTS) == 5
    assert registry.to_dict()["source_layouts"] == list(registry.SOURCE_LAYOUTS)


def test_every_layout_enum_derives_from_or_matches_the_registry():
    schema = json.loads(_read(RESULT_SCHEMA))
    schema_layouts = schema["properties"]["sources"]["items"]["properties"]["layout"]["enum"]
    expected = set(registry.SOURCE_LAYOUTS)
    assert set(schema_layouts) == expected
    assert len(schema_layouts) == len(expected)
    assert asset_skill_contract_check.SOURCE_LAYOUTS == expected
    assert asset_output_paths.SOURCE_LAYOUT_TYPES == expected
    # Every physical layout compiles to some Godot artifact; none is a
    # purpose label that compiles nothing.
    assert set(asset_output_paths.LAYOUT_ARTIFACT_TYPES) == expected


def test_routes_together_use_every_layout_and_only_registry_layouts():
    used = {
        layout
        for _, variant in registry.routes()
        for layout in variant.entry_source_layouts
    }
    assert used == set(registry.SOURCE_LAYOUTS)


@pytest.mark.parametrize("layout", RETIRED_LAYOUTS)
def test_retired_layouts_are_gone_everywhere(layout):
    assert layout not in registry.SOURCE_LAYOUTS
    assert layout not in asset_skill_contract_check.SOURCE_LAYOUTS
    assert layout not in asset_output_paths.SOURCE_LAYOUT_TYPES
    assert layout not in asset_output_paths.LAYOUT_ARTIFACT_TYPES
    schema = json.loads(_read(RESULT_SCHEMA))
    assert layout not in schema["properties"]["sources"]["items"]["properties"]["layout"]["enum"]


@pytest.mark.parametrize("layout", RETIRED_LAYOUTS)
def test_checker_rejects_a_retired_source_layout(layout):
    result = {
        "asset_type": "background-map",
        "outputs": [{
            "role": "runtime", "name": "sky",
            "path": "res://assets/generated/background-map/sky/sky.png",
            "godot_type": "Texture2D",
        }],
        "sources": [{"path": "res://assets/generated/background-map/sky/sky.png", "layout": layout}],
        "previews": [],
        "validation": {"passed": True},
    }
    with pytest.raises(asset_skill_contract_check.AssetContractError, match="layout is not allowed"):
        asset_skill_contract_check.check_result(result)


def test_registry_refuses_a_route_with_a_non_physical_layout():
    with pytest.raises(ValueError, match="unknown source layout reference"):
        registry.DeliveryVariant(
            variant="default",
            entry_source_layouts=("reference",),
            artifact_types=("Texture2D",),
            runtime_outputs="one",
        )


def test_shared_contract_lists_exactly_the_physical_layouts():
    body = _read(SHARED_CONTRACT).split("### sources", 1)[1].split("### previews", 1)[0]
    listed = body.split("and is one of", 1)[1].split(".", 1)[0]
    named = set(re.findall(r"`([a-z_]+)`", listed))
    assert named == set(registry.SOURCE_LAYOUTS)


def test_reference_outputs_stay_evidence_without_status_or_layout():
    """``outputs[].role: reference`` survives, but only as evidence."""
    assert asset_skill_contract_check.OUTPUT_ROLES == {"runtime", "reference"}
    body = _read(SHARED_CONTRACT).split("### sources", 1)[0]
    assert "have no completion status of their own" in body
    assert "do not create `ASSETS.md` rows" in body
