"""Every public Asset Skill route, from result to worker snapshot.

`tests/tools/test_asset_registration_closure.py` proves the chain in depth for
the artifact types that had one. It enumerates nothing, so a family could
advertise a runtime delivery, ship a Skill, validate that delivery, and still
have no adapter that ever reaches `ready` — and nothing failed.

This module closes that hole. It enumerates `tools/asset_family_registry.py`,
the single authoritative map of delivery and registration semantics, and for
each **route** — one `(family, request variant)` pair — asserts the whole chain
is really there:

1. the Skill, its standalone validator, and the route's representative result
   exist;
2. that result passes the generic result checker and delivers exactly the
   layout and artifact the route declares, not merely something inside the
   family's union of them;
3. the layout/artifact pair is a compilable route, not a type the stable-entry
   schema would refuse;
4. the route's deterministic entry-draft builder exists and is what drafts;
5. the drafted entries register, gate, complete their ASSETS.md rows, and come
   back out of the runtime resolver as the artifact the route promised.

Routes, not families, are the unit on purpose. `platform-strip` and `fx-bundle`
each accept two request shapes that deliver a different layout and artifact, so
family-level assertions ("the type is in the family's set", "some source layout
matches") pass against one variant's fixture while the other variant's adapter
is missing entirely.

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
    RUNTIME_ROLE,
    check_registry,
    routes,
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
    planning_table,
    representative_result,
)


def _keys(**filters) -> list[tuple[str, str]]:
    """Return `(family, variant)` route keys, sorted for stable test ids."""
    return sorted(
        (spec.family, variant.variant) for spec, variant in routes(**filters)
    )


ALL_FAMILIES = sorted(FAMILIES)
ALL_ROUTES = _keys()
RUNTIME_ROUTES = _keys(role=RUNTIME_ROLE)
REFERENCE_FAMILIES = sorted(
    name for name, spec in FAMILIES.items() if spec.is_reference_only
)
BUNDLE_ROUTES = sorted(
    (spec.family, variant.variant)
    for spec, variant in routes()
    if variant.uses_bundle_id
)
SINGLE_ENTRY_ROUTES = sorted(set(ALL_ROUTES) - set(BUNDLE_ROUTES))


def _variant(key: tuple[str, str]):
    family, name = key
    return FAMILIES[family].variant(name)


def _route_id(key: tuple[str, str]) -> str:
    """Name the route in the test id, so a failure says which shape broke."""
    return f"{key[0]}[{key[1]}]"


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
        for variant in spec.variants:
            fixtures = (variant.representative_request, variant.representative_result)
            for relative in [item for item in fixtures if item]:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            for builder in variant.entry_builders:
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


def test_publish_fails_closed_when_the_registry_disagrees_with_the_checkout():
    source = (REPO_ROOT / "tools" / "publish.py").read_text(encoding="utf-8")
    body = source.split("\ndef main():", 1)[1]

    assert "from asset_family_registry import" in source
    gate = body.index("check_registry(repo_root)")
    assert gate < body.index("publish_skills(repo_root")
    assert gate < body.index('publish_directory(repo_root / "tools"')


def test_every_declared_route_has_a_delivery_that_is_actually_driven():
    """A route with no driver would silently prove nothing.

    Keyed by `(family, variant)`: adding a second request shape to a Skill
    without a delivery for it fails here instead of riding along on the shape
    that already had one.
    """
    assert sorted(DELIVERIES) == ALL_ROUTES


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
    """Every layout a route may bind has to be one the entry schema accepts."""
    declared = {
        layout for _, variant in routes() for layout in variant.entry_source_layouts
    }

    assert declared <= SOURCE_LAYOUT_TYPES
    assert set(REFERENCE_LAYOUTS) <= declared


# --------------------------------------------------------------------------
# the declared delivery
# --------------------------------------------------------------------------


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_family_ships_its_skill_and_standalone_validator(family):
    spec = FAMILIES[family]
    skill_dir = REPO_ROOT / spec.skill_dir

    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "standalone_validation.py").is_file()
    assert spec.terminal_status == (
        "source_ready" if spec.is_reference_only else "ready"
    )


@pytest.mark.parametrize("key", ALL_ROUTES, ids=_route_id)
def test_route_representative_result_passes_the_generic_validator(key):
    family, name = key
    result = representative_result(family, name)

    assert (REPO_ROOT / _variant(key).representative_result).is_file()
    assert check_result(result)["ok"] is True
    assert result["asset_type"] == family


@pytest.mark.parametrize("key", ALL_ROUTES, ids=_route_id)
def test_route_result_delivers_exactly_the_layout_and_artifact_it_declares(key):
    """Exact per-route equality, not membership in the family's union.

    Checking `godot_type in family.artifact_types` and "some source layout
    intersects" is what let `platform-strip`'s `single -> Texture2D` shape go
    unrecorded: its atlas fixture satisfied both assertions on its own.
    """
    family, name = key
    variant = _variant(key)
    result = representative_result(family, name)
    runtime = [item for item in result["outputs"] if item["role"] == "runtime"]

    expected = {"none": 0, "one": 1}.get(variant.runtime_outputs)
    if expected is None:
        assert variant.runtime_outputs == "many"
        assert len(runtime) > 1, f"{family}[{name}] declares many outputs, ships one"
    else:
        assert len(runtime) == expected

    if variant.is_reference_only:
        assert not runtime
        assert not variant.artifact_types
        return

    delivered = {item["godot_type"] for item in runtime}
    assert delivered == set(variant.artifact_types), (
        f"{family}[{name}] delivers {sorted(delivered)} but declares "
        f"{sorted(variant.artifact_types)}"
    )
    layouts = {
        item["layout"] for item in result["sources"] if item.get("layout") is not None
    }
    # A delivery may carry extra source material (plans, reports, intermediate
    # sheets); every layout the entry can bind must be among what it delivers.
    assert set(variant.entry_source_layouts) <= layouts, (
        f"{family}[{name}] declares {sorted(variant.entry_source_layouts)} but "
        f"delivers {sorted(layouts)}"
    )


@pytest.mark.parametrize("key", RUNTIME_ROUTES, ids=_route_id)
def test_every_route_layout_artifact_pair_is_a_legal_compiler_route(key):
    """A route may not advertise an artifact the schema would refuse to hold."""
    family, name = key
    variant = _variant(key)
    compilable = {
        artifact
        for layout in variant.entry_source_layouts
        for artifact in LAYOUT_ARTIFACT_TYPES.get(layout, ())
    }

    assert compilable, f"{family}[{name}] names no compilable source layout"
    unroutable = sorted(set(variant.artifact_types) - compilable)
    assert not unroutable, (
        f"{family}[{name}] declares artifacts no declared layout compiles: "
        + ", ".join(unroutable)
    )


@pytest.mark.parametrize("key", ALL_ROUTES, ids=_route_id)
def test_a_closed_route_names_deterministic_builders_that_exist(key):
    variant = _variant(key)

    assert variant.entry_builders
    for builder in variant.entry_builders:
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
    """Run the ASSETS.md update path this route's entry shape requires."""
    variant = _variant((delivery.family, delivery.variant))
    row_type = "reference" if variant.is_reference_only else "runtime"
    assets_md = planning_table(project_root, list(delivery.assets_rows), row_type)
    if variant.entry_shape == ENTRY_PER_OUTPUT:
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


@pytest.mark.parametrize("key", ALL_ROUTES, ids=_route_id)
def test_a_validated_delivery_reaches_a_worker_through_the_real_chain(tmp_path, key):
    family, name = key
    variant = _variant(key)
    delivery = DELIVERIES[key](tmp_path)

    assert delivery.variant == name
    assert delivery.entries, f"{family}[{name}] drafted no stable entry"
    for entry in delivery.entries:
        assert entry["production_family"] == family
        assert entry["processing_status"] == variant.terminal_status
        assert entry["source_layout"]["type"] in variant.entry_source_layouts
        assert (entry.get("bundle_id") is not None) is variant.uses_bundle_id
        if variant.is_reference_only:
            assert "godot_artifact" not in entry
        else:
            assert entry["godot_artifact"]["type"] in variant.artifact_types

    paths = _register(tmp_path, delivery)
    assets_md = _complete_rows(tmp_path, delivery, paths)
    assert "MISSING" not in assets_md.read_text(encoding="utf-8")

    for row in delivery.assets_rows:
        if variant.is_reference_only:
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
            assert item["godot_artifact"]["type"] in variant.artifact_types
            assert (tmp_path / item["godot_artifact"]["path"][len("res://"):]).is_file()


# --------------------------------------------------------------------------
# the negative paths every route shape has to fail closed on
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", SINGLE_ENTRY_ROUTES, ids=_route_id)
def test_an_entry_below_its_terminal_status_never_completes_a_row(tmp_path, key):
    variant = _variant(key)
    delivery = DELIVERIES[key](tmp_path)
    entry = delivery.entries[0]
    entry["processing_status"] = "failed" if variant.is_reference_only else "compiled"
    paths = _register(tmp_path, delivery)
    assets_md = planning_table(
        tmp_path,
        list(delivery.assets_rows),
        "reference" if variant.is_reference_only else "runtime",
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


@pytest.mark.parametrize("key", BUNDLE_ROUTES, ids=_route_id)
def test_a_bundle_publishes_every_declared_child_or_none_of_them(tmp_path, key):
    delivery = DELIVERIES[key](tmp_path)
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


@pytest.mark.parametrize("key", BUNDLE_ROUTES, ids=_route_id)
def test_a_bundle_keeps_its_planning_rows_instead_of_adding_logical_ones(tmp_path, key):
    delivery = DELIVERIES[key](tmp_path)
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
