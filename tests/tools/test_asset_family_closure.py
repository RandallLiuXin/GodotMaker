"""Every public first-class Asset Skill family, from result to worker snapshot.

`tests/tools/test_asset_registration_closure.py` proves the chain in depth for
the artifact types that had one. It enumerates nothing, so a family could
advertise a runtime delivery, ship a Skill, validate that delivery, and still
have no adapter that ever reaches `ready` — and nothing failed.

This module closes that hole. It enumerates `tools/asset_family_registry.py`,
the single authoritative map of family delivery and registration semantics, and
for each family asserts the whole chain is really there:

1. the Skill, its standalone validator, and its representative result exist;
2. that result passes the generic result checker and matches what the registry
   says the family delivers;
3. the layout/artifact pairs it declares are compilable routes, not a type the
   stable-entry schema would refuse;
4. its deterministic entry-draft builder exists and is what actually drafts;
5. the drafted entries register, gate, complete their ASSETS.md rows, and come
   back out of the runtime resolver as the artifact the family promised.

A family whose chain is still open is not skipped: the registry records the
missing link, and the test asserts the refusal is still real, so closing the gap
upstream fails here until the registry is updated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_assets_md_update import (  # noqa: E402
    AssetsMdUpdateError,
    update_assets_md,
    update_assets_md_from_bundle,
)
from asset_bundle_manifest import write_bundle_manifest  # noqa: E402
from asset_family_registry import (  # noqa: E402
    ENTRY_PER_OUTPUT,
    FAMILIES,
    check_registry,
)
from asset_generation_index import check_index, update_index  # noqa: E402
from asset_runtime_resolver import (  # noqa: E402
    AssetRuntimeResolverError,
    resolve_assets_row,
)
from asset_skill_contract_check import (  # noqa: E402
    ASSET_TYPES,
    AssetContractError,
    check_result,
)
from asset_stable_entry import (  # noqa: E402
    LAYOUT_ARTIFACT_TYPES,
    PRODUCTION_FAMILIES,
    REFERENCE_LAYOUTS,
    SOURCE_LAYOUT_TYPES,
    entry_relative_path,
    write_entry,
)

from tests.tools.asset_family_deliveries import (  # noqa: E402
    DELIVERIES,
    TAG,
    Delivery,
    RegistrationGap,
    planning_table,
    representative_result,
)

ALL_FAMILIES = sorted(FAMILIES)
RUNTIME_FAMILIES = sorted(
    name for name, spec in FAMILIES.items() if not spec.is_reference_only
)
REFERENCE_FAMILIES = sorted(
    name for name, spec in FAMILIES.items() if spec.is_reference_only
)
CLOSED_FAMILIES = sorted(
    name for name, spec in FAMILIES.items() if spec.registration_closure == "closed"
)
OPEN_FAMILIES = sorted(
    name for name, spec in FAMILIES.items() if spec.registration_closure == "open"
)
BUNDLE_FAMILIES = sorted(name for name, spec in FAMILIES.items() if spec.uses_bundle_id)


# --------------------------------------------------------------------------
# the map itself
# --------------------------------------------------------------------------


def test_the_registry_agrees_with_every_skill_fixture_and_builder_that_ships():
    assert check_registry() == []


def _mirror_registry_inputs(root: Path) -> None:
    """Create the exact files the registry gate looks for, and nothing else."""
    for spec in FAMILIES.values():
        skill = root / spec.skill_dir
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("stub", encoding="utf-8")
        (skill / "standalone_validation.py").write_text("", encoding="utf-8")
        fixtures = (spec.representative_request, spec.representative_result)
        for relative in [item for item in fixtures if item]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        for builder in spec.entry_builders:
            tool = root / "tools" / builder
            tool.parent.mkdir(parents=True, exist_ok=True)
            tool.write_text("", encoding="utf-8")


def test_the_registry_gate_catches_a_family_or_adapter_that_stopped_shipping(tmp_path):
    _mirror_registry_inputs(tmp_path)
    assert check_registry(tmp_path) == []

    (tmp_path / "tools" / "asset_tileset_entry_draft.py").unlink()
    (tmp_path / "skills/assets/ui-kit").rename(tmp_path / "skills/assets/kit-ui")

    issues = check_registry(tmp_path)
    assert any("asset_tileset_entry_draft.py" in issue for issue in issues)
    assert any("kit-ui" in issue and "never declares" in issue for issue in issues)
    assert any("ui-kit" in issue and "ships no Skill" in issue for issue in issues)


def test_publish_runs_the_registry_gate_before_it_copies_anything():
    """A publish that ships an inconsistent family map is the failure mode.

    Inside a game project an advertised family whose adapter is missing looks
    exactly like a working one; the asset simply never reaches a worker. The
    gate has to run before the first copy, not after.
    """
    source = (REPO_ROOT / "tools" / "publish.py").read_text(encoding="utf-8")
    body = source.split("\ndef main():", 1)[1]

    assert "from asset_family_registry import check_registry" in source
    gate = body.index("check_registry(repo_root)")
    assert gate < body.index("publish_skills(repo_root")
    assert gate < body.index('publish_directory(repo_root / "tools"')


def test_every_declared_family_has_a_delivery_that_is_actually_driven():
    """An enumerated family with no driver would silently prove nothing."""
    assert sorted(DELIVERIES) == ALL_FAMILIES


def test_no_surface_keeps_a_second_list_of_public_families():
    """The schema enums and the runtime enums must be the same ten names.

    Each of these used to be typed out independently. A family added to one and
    missed in another is accepted by the schema and refused by the validator (or
    the reverse), and the mismatch only shows up in a real production run.
    """
    assert set(ASSET_TYPES) == set(FAMILIES)
    assert set(PRODUCTION_FAMILIES) == set(FAMILIES)
    for name in ("asset-skill-request.schema.json", "asset-skill-result.schema.json"):
        schema = json.loads(
            (REPO_ROOT / "skills/assets/_shared/schema" / name).read_text(
                encoding="utf-8"
            )
        )
        assert set(schema["properties"]["asset_type"]["enum"]) == set(FAMILIES), name


def test_the_registry_and_the_stable_entry_schema_agree_on_layouts():
    """Every layout a family may bind has to be one the entry schema accepts."""
    declared = {
        layout
        for spec in FAMILIES.values()
        for layout in spec.entry_source_layouts
    }

    assert declared <= SOURCE_LAYOUT_TYPES
    assert set(REFERENCE_LAYOUTS) <= declared


def test_open_families_carry_the_gap_that_keeps_them_out_of_a_release():
    for family in OPEN_FAMILIES:
        assert FAMILIES[family].open_gap, f"{family} is open with no recorded gap"
    assert CLOSED_FAMILIES, "the registry lost every closed family"


# --------------------------------------------------------------------------
# the declared delivery
# --------------------------------------------------------------------------


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_family_ships_its_skill_validator_and_representative_result(family):
    spec = FAMILIES[family]
    skill_dir = REPO_ROOT / spec.skill_dir

    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "standalone_validation.py").is_file()
    assert (REPO_ROOT / spec.representative_result).is_file()
    assert spec.terminal_status == (
        "source_ready" if spec.is_reference_only else "ready"
    )


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_representative_result_passes_the_generic_validator(family):
    result = representative_result(family)

    assert check_result(result)["ok"] is True
    assert result["asset_type"] == family


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_representative_result_delivers_exactly_what_the_registry_declares(family):
    spec = FAMILIES[family]
    result = representative_result(family)
    runtime = [item for item in result["outputs"] if item["role"] == "runtime"]

    expected = {"none": 0, "one": 1}.get(spec.runtime_outputs)
    if expected is None:
        assert spec.runtime_outputs == "many"
        assert len(runtime) > 1, f"{family} declares many runtime outputs but ships one"
    else:
        assert len(runtime) == expected

    for output in runtime:
        assert output["godot_type"] in spec.artifact_types, (
            f"{family} delivers {output['godot_type']}, which its registry entry "
            "does not declare"
        )
    layouts = {
        item["layout"] for item in result["sources"] if item.get("layout") is not None
    }
    if spec.is_reference_only:
        assert not runtime
        assert not spec.artifact_types
    else:
        # The entry binds one of the declared layouts; a delivery may carry more
        # source material than the entry records, never fewer.
        assert layouts & set(spec.entry_source_layouts), (
            f"{family} delivers no source in {spec.entry_source_layouts}"
        )


@pytest.mark.parametrize("family", RUNTIME_FAMILIES)
def test_every_declared_layout_artifact_pair_is_a_legal_compiler_route(family):
    """A family may not advertise an artifact the schema would refuse to hold."""
    spec = FAMILIES[family]
    compilable = {
        artifact
        for layout in spec.entry_source_layouts
        for artifact in LAYOUT_ARTIFACT_TYPES.get(layout, ())
    }

    assert compilable, f"{family} names no compilable source layout"
    unroutable = sorted(set(spec.artifact_types) - compilable)
    assert not unroutable, (
        f"{family} declares artifacts no declared layout compiles: "
        + ", ".join(unroutable)
    )


@pytest.mark.parametrize("family", CLOSED_FAMILIES)
def test_a_closed_family_names_deterministic_builders_that_exist(family):
    spec = FAMILIES[family]

    assert spec.entry_builders
    for builder in spec.entry_builders:
        assert (REPO_ROOT / "tools" / builder).is_file()


# --------------------------------------------------------------------------
# the registration chain
# --------------------------------------------------------------------------


def _register(project_root: Path, delivery: Delivery) -> list[Path]:
    """Write every entry, upsert its pointer, and run the full root-index gate."""
    written: list[Path] = []
    for entry in delivery.entries:
        write_entry(entry, project_root=project_root, check_files=True)
        path = project_root / entry_relative_path(entry["tag"], entry["asset_id"])
        written.append(path)
        update_index(
            project_root / ".godotmaker/asset-generation/manifest.json",
            [path],
            project_root=project_root,
        )
    check_index(
        project_root / ".godotmaker/asset-generation/manifest.json",
        project_root=project_root,
        check_entries=True,
        check_files=True,
    )
    return written


def _complete_rows(project_root: Path, delivery: Delivery, paths: list[Path]) -> Path:
    """Run the ASSETS.md update path this family's entry shape requires."""
    spec = FAMILIES[delivery.family]
    row_type = "reference" if spec.is_reference_only else "runtime"
    assets_md = planning_table(project_root, list(delivery.assets_rows), row_type)
    if spec.entry_shape == ENTRY_PER_OUTPUT:
        manifest = write_bundle_manifest(
            paths,
            asset_ids=list(delivery.assets_rows),
            request_path=delivery.request_path,
            result_path=delivery.result_path,
            project_root=project_root,
        )
        update_assets_md_from_bundle(assets_md, project_root / manifest["path"])
    else:
        update_assets_md(assets_md, paths)
    return assets_md


@pytest.mark.parametrize("family", CLOSED_FAMILIES)
def test_a_validated_delivery_reaches_a_worker_through_the_real_chain(
    tmp_path, family
):
    spec = FAMILIES[family]
    delivery = DELIVERIES[family](tmp_path)

    assert delivery.entries, f"{family} drafted no stable entry"
    for entry in delivery.entries:
        assert entry["production_family"] == family
        assert entry["processing_status"] == spec.terminal_status
        assert entry["source_layout"]["type"] in spec.entry_source_layouts
        assert (entry.get("bundle_id") is not None) is spec.uses_bundle_id
        if spec.is_reference_only:
            assert "godot_artifact" not in entry
        else:
            assert entry["godot_artifact"]["type"] in spec.artifact_types

    paths = _register(tmp_path, delivery)
    assets_md = _complete_rows(tmp_path, delivery, paths)
    assert "MISSING" not in assets_md.read_text(encoding="utf-8")

    for row in delivery.assets_rows:
        if spec.is_reference_only:
            # A reference completes its own row and stops there; it must never
            # become a runtime handoff.
            with pytest.raises(AssetRuntimeResolverError):
                resolve_assets_row(
                    assets_md, tag=TAG, asset_id=row, project_root=tmp_path
                )
            continue
        snapshot = resolve_assets_row(
            assets_md, tag=TAG, asset_id=row, project_root=tmp_path
        )
        items = snapshot if isinstance(snapshot, list) else [snapshot]
        assert items
        for item in items:
            assert list(item) == [
                "asset_id",
                "production_family",
                "source_layout",
                "godot_artifact",
            ]
            assert item["production_family"] == family
            assert item["godot_artifact"]["type"] in spec.artifact_types
            assert (tmp_path / item["godot_artifact"]["path"][len("res://"):]).is_file()


@pytest.mark.parametrize("family", OPEN_FAMILIES)
def test_an_open_family_still_refuses_at_the_link_the_registry_records(
    tmp_path, family
):
    """The gap must stay mechanically real, not just described in prose.

    When the missing adapter lands, this stops raising and the test fails, which
    is the signal to close the family in `tools/asset_family_registry.py`.
    """
    with pytest.raises(RegistrationGap) as refusal:
        DELIVERIES[family](tmp_path)

    assert str(refusal.value)


# --------------------------------------------------------------------------
# the negative paths every family shape has to fail closed on
# --------------------------------------------------------------------------


@pytest.mark.parametrize("family", sorted(set(CLOSED_FAMILIES) - set(BUNDLE_FAMILIES)))
def test_an_entry_below_its_terminal_status_never_completes_a_row(tmp_path, family):
    spec = FAMILIES[family]
    delivery = DELIVERIES[family](tmp_path)
    entry = delivery.entries[0]
    entry["processing_status"] = "failed" if spec.is_reference_only else "compiled"
    paths = _register(tmp_path, delivery)
    assets_md = planning_table(
        tmp_path,
        list(delivery.assets_rows),
        "reference" if spec.is_reference_only else "runtime",
    )

    with pytest.raises(AssetsMdUpdateError):
        update_assets_md(assets_md, paths)
    assert "MISSING" in assets_md.read_text(encoding="utf-8")


@pytest.mark.parametrize("family", REFERENCE_FAMILIES)
def test_a_reference_family_result_never_declares_a_runtime_artifact(family):
    result = representative_result(family)

    assert all(item["role"] == "reference" for item in result["outputs"])
    assert all("godot_type" not in item for item in result["outputs"])
    with pytest.raises(AssetContractError):
        check_result({**result, "outputs": [{"role": "runtime", "path": "x.png"}]})


@pytest.mark.parametrize("family", BUNDLE_FAMILIES)
def test_a_bundle_publishes_every_declared_child_or_none_of_them(tmp_path, family):
    delivery = DELIVERIES[family](tmp_path)
    paths = _register(tmp_path, delivery)
    assets_md = planning_table(tmp_path, list(delivery.assets_rows))
    before = assets_md.read_bytes()

    with pytest.raises(Exception) as refusal:
        write_bundle_manifest(
            paths[:-1],
            asset_ids=list(delivery.assets_rows),
            request_path=delivery.request_path,
            result_path=delivery.result_path,
            project_root=tmp_path,
        )

    assert "child set" in str(refusal.value)
    assert assets_md.read_bytes() == before
    assert not (tmp_path / ".godotmaker/asset-generation/bundles").exists()


@pytest.mark.parametrize("family", BUNDLE_FAMILIES)
def test_a_bundle_keeps_its_planning_rows_instead_of_adding_logical_ones(
    tmp_path, family
):
    delivery = DELIVERIES[family](tmp_path)
    paths = _register(tmp_path, delivery)
    assets_md = planning_table(tmp_path, list(delivery.assets_rows))
    rows_before = len(assets_md.read_text(encoding="utf-8").splitlines())

    manifest = write_bundle_manifest(
        paths,
        asset_ids=list(delivery.assets_rows),
        request_path=delivery.request_path,
        result_path=delivery.result_path,
        project_root=tmp_path,
    )
    update_assets_md_from_bundle(assets_md, tmp_path / manifest["path"])

    assert len(assets_md.read_text(encoding="utf-8").splitlines()) == rows_before
    assert len(delivery.entries) > 1
    manifest_body = json.loads(
        (tmp_path / manifest["path"]).read_text(encoding="utf-8")
    )
    assert len(manifest_body["entries"]) == len(delivery.entries)
