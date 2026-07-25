"""Routing, fail-closed, and boundary tests for the shared compiler registry."""
import os
import pickle
import subprocess
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import (  # noqa: E402
    SOURCE_IS_ARTIFACT_TYPES,
    CompileReceipt,
    CompileRequest,
    CompilerError,
    CompilerRegistry,
    build_default_registry,
    texture2d,
)
from asset_compiler._stable_entry import StableEntryError, resolve_res_path  # noqa: E402
from asset_stable_entry import (  # noqa: E402
    GODOT_ARTIFACT_KEYS,
    LAYOUT_ARTIFACT_TYPES,
    validate_entry,
)


def _writer(payload=b"artifact"):
    """Return a compiler that writes its artifact and receipts what it wrote."""

    def compiler(request):
        target = request.artifact_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return {"bytes": len(payload)}

    return compiler


def _register(registry, layout, artifact_type, compiler=None, compiler_id=None):
    return registry.register(
        source_layout_type=layout,
        artifact_type=artifact_type,
        compiler_id=compiler_id or f"{layout}_{artifact_type}".lower(),
        compiler_version=1,
        compiler=compiler or _writer(),
    )


def _replace(request, field, value):
    return replace(request, **{field: value})


def _make_request(project_root, *, layout, artifact_type, family="ui-kit", asset_id="panel"):
    stable = f"res://assets/generated/{family}/{asset_id}"
    return CompileRequest(
        production_family=family,
        asset_id=asset_id,
        source_layout_type=layout,
        source_path=f"{stable}/{asset_id}.png",
        artifact_type=artifact_type,
        artifact_path=f"{stable}/{asset_id}.tres",
        project_root=project_root,
    )


@pytest.fixture
def project(tmp_path):
    """A project root with the ui-kit/panel source image already generated."""
    source = tmp_path / "assets" / "generated" / "ui-kit" / "panel" / "panel.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")
    return tmp_path


# --- routing ---------------------------------------------------------------


def test_routes_on_the_layout_and_artifact_pair(project):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler_id="single_box")
    _register(registry, "region_atlas", "StyleBoxTexture", compiler_id="atlas_box")

    # A one-to-one layout map would have refused the second registration; both
    # legal StyleBoxTexture routes must coexist and resolve independently.
    assert registry.resolve("single", "StyleBoxTexture").compiler_id == "single_box"
    assert registry.resolve("region_atlas", "StyleBoxTexture").compiler_id == "atlas_box"
    assert [route.key for route in registry.routes()] == [
        ("region_atlas", "StyleBoxTexture"),
        ("single", "StyleBoxTexture"),
    ]


def test_single_also_routes_to_texture2d_alongside_stylebox(project):
    registry = CompilerRegistry()
    _register(registry, "single", "Texture2D", compiler_id="tex")
    _register(registry, "single", "StyleBoxTexture", compiler_id="box")

    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )
    assert result.receipt.compiler_id == "box"


def test_every_frozen_compatible_pair_is_registrable():
    registry = CompilerRegistry()
    for layout, artifact_types in LAYOUT_ARTIFACT_TYPES.items():
        for artifact_type in artifact_types:
            _register(registry, layout, artifact_type)
    assert len(registry.routes()) == sum(
        len(types) for types in LAYOUT_ARTIFACT_TYPES.values()
    )


def test_compile_returns_the_routed_compilers_receipt(project):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=_writer(b"12345"))

    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )
    assert result.godot_artifact.type == "StyleBoxTexture"
    assert result.godot_artifact.path.endswith("/panel.tres")
    assert result.receipt.compiler_id == "single_styleboxtexture"
    assert result.receipt.compiler_version == 1
    assert result.receipt.details == {"bytes": 5}
    assert (project / "assets/generated/ui-kit/panel/panel.tres").is_file()


# --- registration failures -------------------------------------------------


def test_duplicate_registration_is_rejected():
    registry = CompilerRegistry()
    _register(registry, "grid_sheet", "SpriteFrames", compiler_id="first")
    with pytest.raises(CompilerError, match="already registered to first"):
        _register(registry, "grid_sheet", "SpriteFrames", compiler_id="second")


def test_registering_an_incompatible_pair_is_rejected():
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="may not compile to"):
        _register(registry, "grid_sheet", "Texture2D")


def test_registering_an_unknown_layout_is_rejected():
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="compiles no Godot artifact"):
        _register(registry, "mosaic", "Texture2D")


def test_registering_a_reference_layout_is_rejected():
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="compiles no Godot artifact"):
        _register(registry, "reference", "Texture2D")


@pytest.mark.parametrize("version", [0, -1, True, 1.0, "1"])
def test_registering_a_non_positive_integer_version_is_rejected(version):
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="compiler_version"):
        registry.register(
            source_layout_type="tile_atlas",
            artifact_type="TileSet",
            compiler_id="tiles",
            compiler_version=version,
            compiler=_writer(),
        )


def test_registering_a_non_callable_is_rejected():
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="callable"):
        registry.register(
            source_layout_type="theme_recipe",
            artifact_type="Theme",
            compiler_id="theme",
            compiler_version=1,
            compiler="not a compiler",
        )


# --- unknown / mismatched compile requests ---------------------------------


def test_unregistered_pair_fails_closed(project):
    registry = CompilerRegistry()
    _register(registry, "single", "Texture2D")
    with pytest.raises(CompilerError, match="no compiler is registered"):
        registry.compile(
            _make_request(project, layout="grid_sheet", artifact_type="SpriteFrames")
        )


def test_empty_registry_names_no_routes(project):
    with pytest.raises(CompilerError, match="registered: none"):
        CompilerRegistry().compile(
            _make_request(project, layout="single", artifact_type="Texture2D")
        )


def test_type_mismatch_fails_before_routing(project):
    registry = CompilerRegistry()
    # Registered under its legal pair; the request still asks for the wrong type.
    _register(registry, "grid_sheet", "SpriteFrames")
    with pytest.raises(CompilerError, match="must be one of: SpriteFrames"):
        registry.compile(
            _make_request(project, layout="grid_sheet", artifact_type="Texture2D")
        )


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("production_family", "sprites", "production_family is not allowed"),
        ("production_family", "screen-reference", "reference-only"),
        ("source_layout_type", "mosaic", "source_layout_type is not allowed"),
        ("source_layout_type", "reference", "compiles no Godot artifact"),
        ("artifact_type", "Resource", "must be one of"),
        ("asset_id", "", "asset_id must be a non-empty string"),
    ],
)
def test_unknown_or_reference_inputs_fail_closed(project, field, value, message):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    request = _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    with pytest.raises(CompilerError, match=message):
        registry.compile(_replace(request, field, value))


@pytest.mark.parametrize(
    "path",
    [
        "res://assets/generated/ui-kit/other/panel.tres",
        "res://.godotmaker/asset-generation/work/panel.tres",
        "res://panel.tres",
        "assets/generated/ui-kit/panel/panel.tres",
    ],
)
def test_artifact_outside_the_stable_directory_is_rejected(project, path):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    request = _replace(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture"),
        "artifact_path",
        path,
    )
    with pytest.raises(CompilerError):
        registry.compile(request)


def test_missing_source_fails_before_the_compiler_runs(tmp_path):
    registry = CompilerRegistry()
    ran = []
    _register(
        registry,
        "single",
        "StyleBoxTexture",
        compiler=lambda request: ran.append(request) or {},
    )
    with pytest.raises(CompilerError, match="source_path not found"):
        registry.compile(
            _make_request(tmp_path, layout="single", artifact_type="StyleBoxTexture")
        )
    assert ran == []


# --- error propagation -----------------------------------------------------


def test_compiler_error_propagates_unchanged(project):
    registry = CompilerRegistry()

    def failing(request):
        raise CompilerError("nine-slice margins exceed the source rect")

    _register(registry, "single", "StyleBoxTexture", compiler=failing)
    with pytest.raises(CompilerError, match="nine-slice margins exceed"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )


def test_unexpected_compiler_exception_is_wrapped_with_the_compiler_id(project):
    registry = CompilerRegistry()

    def exploding(request):
        raise ValueError("bad frame index")

    _register(
        registry, "single", "StyleBoxTexture", compiler=exploding, compiler_id="boxes"
    )
    with pytest.raises(CompilerError, match="boxes failed: bad frame index"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )


def test_compiler_returning_a_non_mapping_is_rejected(project):
    def returns_a_string(request):
        _writer()(request)
        return "done"

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=returns_a_string)
    with pytest.raises(CompilerError, match="must return a mapping"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )


def test_compiler_that_writes_nothing_is_rejected(project):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=lambda request: {})
    with pytest.raises(CompilerError, match="returned without writing"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )


# --- the artifact must actually be rebuilt this run ------------------------


def test_no_op_compiler_cannot_pass_off_a_previous_runs_artifact(project):
    # A no-op compiler must not pass off last run's bytes as this run's result,
    # nor may it remove the already-ready stable artifact.
    stale = project / "assets/generated/ui-kit/panel/panel.tres"
    stale.write_bytes(b"STALE-FROM-RUN-1")

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=lambda request: {})
    with pytest.raises(CompilerError, match="returned without writing"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )
    assert stale.read_bytes() == b"STALE-FROM-RUN-1"


@pytest.mark.parametrize(
    "compiler",
    [
        pytest.param(lambda request: (_writer()(request), "not details")[1], id="bad-details"),
        pytest.param(lambda request: {}, id="no-output"),
    ],
)
def test_failed_compile_keeps_the_previous_artifact(project, compiler):
    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    stable.write_bytes(b"STABLE-OLD-CONTENT")

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=compiler)
    with pytest.raises(CompilerError):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )

    assert stable.read_bytes() == b"STABLE-OLD-CONTENT"
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_raised_compiler_error_keeps_the_previous_artifact(project):
    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    stable.write_bytes(b"STABLE-OLD-CONTENT")

    registry = CompilerRegistry()
    _register(
        registry,
        "single",
        "StyleBoxTexture",
        compiler=lambda request: (_ for _ in ()).throw(CompilerError("failed")),
    )
    with pytest.raises(CompilerError, match="failed"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )

    assert stable.read_bytes() == b"STABLE-OLD-CONTENT"
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_first_failed_compile_leaves_no_stable_or_staging_artifact(project):
    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=lambda request: {})

    with pytest.raises(CompilerError, match="returned without writing"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )

    assert not stable.exists()
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_rebuilding_over_an_existing_artifact_is_accepted(project):
    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    stable.write_bytes(b"OLD")

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=_writer(b"NEW-CONTENT"))
    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )
    assert result.receipt.details == {"bytes": 11}
    assert stable.read_bytes() == b"NEW-CONTENT"
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_same_size_rewrite_is_accepted(project):
    # Replacing the old path before compilation makes this independent of the
    # filesystem timestamp resolution.
    (project / "assets/generated/ui-kit/panel/panel.tres").write_bytes(b"AAA")

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=_writer(b"BBB"))
    registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )
    assert (project / "assets/generated/ui-kit/panel/panel.tres").read_bytes() == b"BBB"


# --- the source image may not be published as the artifact -----------------


def test_a_writing_route_may_not_hand_back_its_source_image(project):
    # tools/asset_stable_entry.py calls this out by name: declaring the source
    # image as the artifact is the shortcut LAYOUT_ARTIFACT_TYPES exists to
    # reject. A worker binding that PNG as SpriteFrames gets a frozen sprite.
    source = project / "assets/generated/character-bundle/hero/hero.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")

    registry = CompilerRegistry()
    _register(registry, "grid_sheet", "SpriteFrames", compiler=lambda request: {})
    request = CompileRequest(
        production_family="character-bundle",
        asset_id="hero",
        source_layout_type="grid_sheet",
        source_path="res://assets/generated/character-bundle/hero/hero.png",
        artifact_type="SpriteFrames",
        artifact_path="res://assets/generated/character-bundle/hero/hero.png",
        project_root=project,
    )
    with pytest.raises(CompilerError, match="must compile a new file"):
        registry.compile(request)


def test_a_writing_route_may_not_hard_link_its_source_as_the_artifact(project):
    def links_the_source(request):
        os.link(request.source_file(), request.artifact_file())
        return {}

    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    stable.write_bytes(b"STABLE-OLD-CONTENT")
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=links_the_source)
    with pytest.raises(CompilerError, match="may not publish source_path"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )
    assert stable.read_bytes() == b"STABLE-OLD-CONTENT"
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_a_writing_route_may_not_symlink_its_source_as_the_artifact(project):
    def symlinks_the_source(request):
        try:
            request.artifact_file().symlink_to(request.source_file())
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")
        return {}

    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    stable.write_bytes(b"STABLE-OLD-CONTENT")
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=symlinks_the_source)
    with pytest.raises(CompilerError, match="may not publish source_path"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )
    assert stable.read_bytes() == b"STABLE-OLD-CONTENT"
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_post_compile_source_validation_failure_keeps_previous_artifact(project):
    def deletes_source_after_writing(request):
        _writer()(request)
        request.source_file().unlink()
        return {}

    stable = project / "assets/generated/ui-kit/panel/panel.tres"
    stable.write_bytes(b"STABLE-OLD-CONTENT")
    registry = CompilerRegistry()
    _register(
        registry,
        "single",
        "StyleBoxTexture",
        compiler=deletes_source_after_writing,
    )
    with pytest.raises(CompilerError, match="source_path not found after compilation"):
        registry.compile(
            _make_request(project, layout="single", artifact_type="StyleBoxTexture")
        )
    assert stable.read_bytes() == b"STABLE-OLD-CONTENT"
    assert not list(stable.parent.glob("panel.tres.staging-*"))


def test_a_non_writing_route_may_not_modify_its_source(project):
    def clobbers_the_source(request):
        request.source_file().write_bytes(b"CLOBBERED")
        return {}

    registry = CompilerRegistry()
    registry.register(
        source_layout_type="single",
        artifact_type="Texture2D",
        compiler_id="unsafe_default_import",
        compiler_version=1,
        compiler=clobbers_the_source,
        writes_artifact=False,
    )
    request = CompileRequest(
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path="res://assets/generated/ui-kit/panel/panel.png",
        artifact_type="Texture2D",
        artifact_path="res://assets/generated/ui-kit/panel/panel.png",
        project_root=project,
    )
    with pytest.raises(CompilerError, match="must not modify source_path"):
        registry.compile(request)


@pytest.mark.parametrize(
    "layout,artifact_type",
    [
        (layout, artifact_type)
        for layout, artifact_types in sorted(LAYOUT_ARTIFACT_TYPES.items())
        for artifact_type in artifact_types
        if artifact_type not in SOURCE_IS_ARTIFACT_TYPES
    ],
)
def test_only_texture2d_may_register_as_a_non_writing_route(layout, artifact_type):
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="must compile a new file"):
        registry.register(
            source_layout_type=layout,
            artifact_type=artifact_type,
            compiler_id="shortcut",
            compiler_version=1,
            compiler=_writer(),
            writes_artifact=False,
        )


def test_writes_artifact_must_be_a_bool():
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="writes_artifact must be a bool"):
        registry.register(
            source_layout_type="single",
            artifact_type="Texture2D",
            compiler_id="tex",
            compiler_version=1,
            compiler=_writer(),
            writes_artifact=0,
        )


# --- worker snapshot boundary ----------------------------------------------


def test_receipt_details_never_widen_the_worker_artifact(project):
    def overreaching(request):
        _writer()(request)
        return {"type": "Resource", "path": "res://elsewhere.tres", "hash": "abc"}

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=overreaching)
    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )

    # The compiler never builds the artifact, so the keys it returns land in the
    # receipt and cannot overwrite or extend the worker-facing object.
    assert set(result.godot_artifact.to_dict()) == GODOT_ARTIFACT_KEYS
    assert result.godot_artifact.to_dict() == {
        "type": "StyleBoxTexture",
        "path": "res://assets/generated/ui-kit/panel/panel.tres",
    }
    assert result.receipt.details["hash"] == "abc"
    assert "hash" not in result.to_dict()["godot_artifact"]


def test_compiled_artifact_is_accepted_by_the_stable_entry_schema(project):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )
    entry = {
        "version": 1,
        "asset_id": "panel",
        "tag": "v0.1.0",
        "production_family": "ui-kit",
        "source_layout": {
            "type": "single",
            "path": "res://assets/generated/ui-kit/panel/panel.png",
        },
        "godot_artifact": result.godot_artifact.to_dict(),
        "processing_status": "compiled",
    }
    assert validate_entry(entry, project_root=project, check_files=True) == entry


# --- Texture2D default import ----------------------------------------------


def test_texture2d_is_served_through_godot_default_import(project):
    request = CompileRequest(
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path="res://assets/generated/ui-kit/panel/panel.png",
        artifact_type="Texture2D",
        artifact_path="res://assets/generated/ui-kit/panel/panel.png",
        project_root=project,
    )
    result = build_default_registry().compile(request)

    assert result.receipt.compiler_id == texture2d.COMPILER_ID
    assert result.receipt.details == {"mode": "godot_default_import"}
    assert result.godot_artifact.to_dict() == {
        "type": "Texture2D",
        "path": "res://assets/generated/ui-kit/panel/panel.png",
    }


def test_texture2d_rejects_a_separate_artifact_path(project):
    with pytest.raises(CompilerError, match="must equal source_path"):
        build_default_registry().compile(
            _make_request(project, layout="single", artifact_type="Texture2D")
        )


def test_texture2d_compiler_rejects_a_separate_artifact_path_directly(project):
    with pytest.raises(CompilerError, match="must equal source_path"):
        texture2d.compile_texture2d(
            _make_request(project, layout="single", artifact_type="Texture2D")
        )


def test_default_registry_ships_only_the_texture2d_route():
    # No concrete AtlasTexture, SpriteFrames, Theme, StyleBoxTexture, or TileSet
    # compiler belongs to the shared layer; each lands with its asset skill.
    assert [route.key for route in build_default_registry().routes()] == [
        ("single", "Texture2D")
    ]


def test_each_build_returns_an_independent_registry():
    # There is no module-level singleton: registering a family compiler must not
    # leak into a registry another caller builds.
    first = build_default_registry()
    _register(first, "grid_sheet", "SpriteFrames")
    assert len(first.routes()) == 2
    assert len(build_default_registry().routes()) == 1


def test_relative_project_root_compiles_without_double_anchoring(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project = Path("myproj")
    source = project / "assets" / "generated" / "ui-kit" / "panel" / "panel.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"png")

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )

    assert result.godot_artifact.path.endswith("/panel.tres")
    assert (project / "assets/generated/ui-kit/panel/panel.tres").is_file()


@pytest.mark.parametrize("path", ["", "assets/generated/ui-kit/panel/panel.png", "/etc/passwd"])
def test_exported_resolver_rejects_non_resource_paths(project, path):
    with pytest.raises(StableEntryError, match="res:// path"):
        resolve_res_path(project, path)


# --- source_path validation ------------------------------------------------


@pytest.mark.parametrize(
    "path,message",
    [
        ("", "source_path must be a non-empty string"),
        ("   ", "source_path must be a non-empty string"),
        ("assets/generated/ui-kit/panel/panel.png", "source_path must be a res:// path"),
        (
            "res://.godotmaker/asset-generation/work/panel.png",
            "source_path must not depend on the generation work/ workspace",
        ),
        (
            "res://assets/generated/ui-kit/other/panel.png",
            "source_path must be a file under",
        ),
        ("res://assets/generated/ui-kit/panel/../x.png", "source_path"),
    ],
)
def test_source_path_is_constrained_like_the_artifact_path(project, path, message):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    request = _replace(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture"),
        "source_path",
        path,
    )
    with pytest.raises(CompilerError, match=message):
        registry.compile(request)


@pytest.mark.parametrize("value", [None, 42, [], {}, b"res://x"])
def test_require_text_rejects_non_strings(project, value):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    request = _replace(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture"),
        "artifact_type",
        value,
    )
    with pytest.raises(CompilerError, match="artifact_type must be a non-empty string"):
        registry.compile(request)


def test_project_root_must_be_a_path(project):
    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    request = _replace(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture"),
        "project_root",
        str(project),
    )
    with pytest.raises(CompilerError, match="project_root must be a Path"):
        registry.compile(request)


@pytest.mark.parametrize("spec", [None, [], "frames", 3])
def test_spec_must_be_a_mapping(project, spec):
    with pytest.raises(CompilerError, match="spec must be a mapping"):
        CompileRequest(
            production_family="ui-kit",
            asset_id="panel",
            source_layout_type="single",
            source_path="res://assets/generated/ui-kit/panel/panel.png",
            artifact_type="StyleBoxTexture",
            artifact_path="res://assets/generated/ui-kit/panel/panel.tres",
            project_root=project,
            spec=spec,
        )


@pytest.mark.parametrize("compiler_id", ["", "   ", None, 7])
def test_registering_a_blank_compiler_id_is_rejected(compiler_id):
    registry = CompilerRegistry()
    with pytest.raises(CompilerError, match="compiler_id must be a non-empty string"):
        registry.register(
            source_layout_type="theme_recipe",
            artifact_type="Theme",
            compiler_id=compiler_id,
            compiler_version=1,
            compiler=_writer(),
        )


def test_symlinked_stable_directory_is_rejected_on_disk(project, tmp_path):
    # The string-level checks all pass here; only the resolve-and-contain guard
    # in assert_within_output_dir can catch a stable dir linked out of the tree.
    outside = tmp_path.parent / "outside-the-project"
    outside.mkdir(exist_ok=True)
    stable = project / "assets" / "generated" / "ui-kit" / "linked"
    try:
        stable.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture")
    with pytest.raises(CompilerError, match="resolves outside the project root"):
        registry.compile(
            _make_request(
                project, layout="single", artifact_type="StyleBoxTexture",
                asset_id="linked",
            )
        )


# --- immutability of the mapping fields ------------------------------------


def test_request_spec_is_snapshotted_hashable_and_standard_library_safe(project):
    spec = {"frames": [1, 2]}
    request = _replace(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture"),
        "spec",
        spec,
    )
    spec["frames"].append(99)

    assert request.spec == {"frames": [1, 2]}
    assert isinstance(hash(request), int)
    assert deepcopy(request).spec == {"frames": [1, 2]}
    assert pickle.loads(pickle.dumps(request)).spec == {"frames": [1, 2]}
    assert asdict(request)["spec"] == {"frames": [1, 2]}


def test_receipt_details_are_snapshotted_hashable_and_standard_library_safe(project):
    details = {"regions": ["a"]}
    receipt = CompileReceipt(
        compiler_id="boxes",
        compiler_version=1,
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path="res://assets/generated/ui-kit/panel/panel.png",
        artifact_type="StyleBoxTexture",
        artifact_path="res://assets/generated/ui-kit/panel/panel.tres",
        details=details,
    )
    details["regions"].append("b")
    receipt.to_dict()["details"]["regions"].append("c")

    assert receipt.details == {"regions": ["a"]}
    assert isinstance(hash(receipt), int)
    assert deepcopy(receipt).details == {"regions": ["a"]}
    assert pickle.loads(pickle.dumps(receipt)).details == {"regions": ["a"]}
    assert asdict(receipt)["details"] == {"regions": ["a"]}


def test_a_compiler_cannot_edit_its_receipt_after_the_fact(project):
    escaped = {}

    def leaky(request):
        _writer()(request)
        escaped["details"] = {"regions": ["a"]}
        return escaped["details"]

    registry = CompilerRegistry()
    _register(registry, "single", "StyleBoxTexture", compiler=leaky)
    result = registry.compile(
        _make_request(project, layout="single", artifact_type="StyleBoxTexture")
    )
    escaped["details"]["regions"].append("b")

    assert result.receipt.details == {"regions": ["a"]}


# --- the tools/ import bridge ----------------------------------------------


def test_bridge_imports_the_package_without_tools_on_the_path(tmp_path):
    # The suite puts tools/ on sys.path before importing asset_compiler, which
    # hides the bridge entirely. Import it in a child process that has neither,
    # so a wrong parents[] index is a failure instead of a silent no-op.
    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(SHARED_DIR)!r})\n"
        "assert 'asset_stable_entry' not in sys.modules\n"
        "import asset_compiler\n"
        "print(asset_compiler.build_default_registry().routes()[0].compiler_id)\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == texture2d.COMPILER_ID


def test_bridge_reports_a_missing_tools_directory_diagnosably(tmp_path):
    # A publish layout that moves the package away from tools/ must say so
    # instead of raising a bare ModuleNotFoundError: asset_stable_entry.
    package = tmp_path / "a" / "b" / "c" / "d" / "asset_compiler"
    package.mkdir(parents=True)
    source = SHARED_DIR / "asset_compiler"
    for name in ("__init__.py", "_stable_entry.py", "contract.py", "registry.py",
                 "texture2d.py"):
        (package / name).write_bytes((source / name).read_bytes())

    code = (
        "import sys\n"
        f"sys.path.insert(0, {str(package.parent)!r})\n"
        "import asset_compiler\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "expects the repository tools/ directory" in completed.stderr
    assert "ModuleNotFoundError" not in completed.stderr
