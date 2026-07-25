"""Routing, fail-closed, and boundary tests for the shared compiler registry."""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import (  # noqa: E402
    DEFAULT_REGISTRY,
    CompileRequest,
    CompilerError,
    CompilerRegistry,
    build_default_registry,
    texture2d,
)
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


def test_default_registry_serves_texture2d_through_godot_default_import(project):
    request = CompileRequest(
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path="res://assets/generated/ui-kit/panel/panel.png",
        artifact_type="Texture2D",
        artifact_path="res://assets/generated/ui-kit/panel/panel.png",
        project_root=project,
    )
    result = DEFAULT_REGISTRY.compile(request)

    assert result.receipt.compiler_id == texture2d.COMPILER_ID
    assert result.receipt.details == {"mode": "godot_default_import"}
    assert result.godot_artifact.to_dict() == {
        "type": "Texture2D",
        "path": "res://assets/generated/ui-kit/panel/panel.png",
    }


def test_texture2d_rejects_a_separate_artifact_path(project):
    with pytest.raises(CompilerError, match="must equal source_path"):
        DEFAULT_REGISTRY.compile(
            _make_request(project, layout="single", artifact_type="Texture2D")
        )


def test_default_registry_ships_only_the_texture2d_route():
    # No concrete AtlasTexture, SpriteFrames, Theme, StyleBoxTexture, or TileSet
    # compiler belongs to the shared layer; each lands with its asset skill.
    assert [route.key for route in build_default_registry().routes()] == [
        ("single", "Texture2D")
    ]
