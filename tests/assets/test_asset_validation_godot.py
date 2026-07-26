"""L3 against a real engine: import the project, load the resource, match the type.

These are the tests the unit suite cannot stand in for. A stubbed probe proves
the ladder reacts correctly to an answer; only Godot proves the answer. They skip
when no engine is reachable -- CI installs pytest and pillow only -- so a
contributor with Godot 4.4+ installed runs them and CI does not.
"""
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import (  # noqa: E402
    CompileRequest,
    CompilerError,
    CompilerRegistry,
    build_default_registry,
    theme,
)
from asset_validation import (  # noqa: E402
    NOT_RUN,
    PASSED,
    REVALIDATION,
    GodotProbe,
    ProbeRequest,
    ValidationLadder,
    StructureValidatorRegistry,
    build_default_structures,
)
from asset_validation.godot_probe import SCRIPT_TIMEOUT  # noqa: E402

# A Theme with no content: it loads cleanly, which is what makes it a useful
# stand-in for a resource of the wrong type.
THEME_TRES = '[gd_resource type="Theme" format=3]\n\n[resource]\n'

RESOURCE_SAVER_SCRIPT = """extends SceneTree

func _init() -> void:
    var arguments := OS.get_cmdline_user_args()
    if arguments.size() != 2:
        push_error("expected a resource type and target path")
        quit(2)
        return

    var resource: Resource
    match arguments[0]:
        "StyleBoxTexture":
            resource = StyleBoxTexture.new()
        "Theme":
            resource = Theme.new()
        _:
            push_error("unsupported resource type: " + arguments[0])
            quit(2)
            return

    var error := ResourceSaver.save(resource, arguments[1])
    if error != OK:
        push_error("ResourceSaver.save failed: " + str(error))
        quit(error)
        return
    quit()
"""


def _run_resource_saver(
    probe: GodotProbe,
    project_root: Path,
    script: Path,
    artifact_type: str,
    artifact_path: str,
) -> subprocess.CompletedProcess:
    """Ask the same console Godot binary L3 uses to save one resource."""
    return subprocess.run(
        [
            probe.godot_path,
            "--headless",
            "--path",
            str(project_root),
            "--script",
            str(script),
            "--",
            artifact_type,
            artifact_path,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=SCRIPT_TIMEOUT,
    )


def _png(width: int, height: int) -> bytes:
    """Return a solid RGBA PNG of exactly this size, without a Pillow dependency."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        payload = tag + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    scanlines = b"".join(b"\x00" + b"\x40\x80\xc0\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def _write(root: Path, res_path: str, payload: bytes) -> Path:
    target = root / res_path[len("res://"):]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def _entry(**overrides):
    entry = {
        "version": 1,
        "tag": "v0.1.0",
        "asset_id": "panel",
        "production_family": "ui-kit",
        "source_layout": {
            "type": "single",
            "path": "res://assets/generated/ui-kit/panel/panel.png",
        },
        "godot_artifact": {
            "type": "Texture2D",
            "path": "res://assets/generated/ui-kit/panel/panel.png",
        },
        "processing_status": "compiled",
    }
    entry.update(overrides)
    return entry


def _stylebox_ladder(godot_bin: str) -> ValidationLadder:
    """Return the default ladder, including the shared StyleBoxTexture route."""
    return ValidationLadder(
        registry=build_default_registry(),
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    )


def _default_compile_receipt(registry, root: Path):
    return registry.compile(
        CompileRequest(
            production_family="ui-kit",
            asset_id="panel",
            source_layout_type="single",
            source_path="res://assets/generated/ui-kit/panel/panel.png",
            artifact_type="Texture2D",
            artifact_path="res://assets/generated/ui-kit/panel/panel.png",
            project_root=root,
        )
    ).receipt


@pytest.mark.parametrize(
    ("layout", "artifact_type", "asset_id", "source_name", "artifact_name"),
    [
        ("single", "StyleBoxTexture", "panel", "panel.png", "panel.tres"),
        ("theme_recipe", "Theme", "skin", "skin.json", "skin.res"),
    ],
)
def test_resource_saver_accepts_extension_preserving_staging_artifacts(
    godot_bin,
    godot_project,
    layout,
    artifact_type,
    asset_id,
    source_name,
    artifact_name,
):
    """Exercise Godot's suffix-sensitive ResourceSaver through the registry."""
    base = f"res://assets/generated/ui-kit/{asset_id}"
    _write(godot_project, f"{base}/{source_name}", b"source")
    script = godot_project / "save_staging_resource.gd"
    script.write_text(RESOURCE_SAVER_SCRIPT, encoding="utf-8")
    staging_paths = []
    probe = GodotProbe(godot_bin)

    def save_with_godot(request):
        staging_paths.append(request.artifact_path)
        try:
            completed = _run_resource_saver(
                probe,
                godot_project,
                script,
                artifact_type,
                request.artifact_path,
            )
        except subprocess.TimeoutExpired as exc:
            raise CompilerError(
                f"ResourceSaver.save timed out after {SCRIPT_TIMEOUT}s"
            ) from exc
        if completed.returncode != 0:
            raise CompilerError(
                f"ResourceSaver.save failed for {request.artifact_path}: "
                f"{completed.stderr.strip() or completed.stdout.strip()}"
            )
        return {"writer": "ResourceSaver"}

    # This test substitutes the compiler to exercise ResourceSaver itself, so
    # it must not collide with the shared default StyleBoxTexture route.
    registry = CompilerRegistry()
    registry.register(
        source_layout_type=layout,
        artifact_type=artifact_type,
        compiler_id=f"resource_saver_{artifact_type.lower()}",
        compiler_version=1,
        compiler=save_with_godot,
    )
    result = registry.compile(
        CompileRequest(
            production_family="ui-kit",
            asset_id=asset_id,
            source_layout_type=layout,
            source_path=f"{base}/{source_name}",
            artifact_type=artifact_type,
            artifact_path=f"{base}/{artifact_name}",
            project_root=godot_project,
        )
    )

    (staging_path,) = staging_paths
    assert staging_path.endswith(Path(artifact_name).suffix)
    assert ".staging-" in staging_path
    report = probe.probe(
        godot_project,
        [ProbeRequest(result.godot_artifact.path, artifact_type)],
    )
    (loaded,) = report.resources
    assert loaded.loaded is True, loaded.to_dict()
    assert loaded.type_matches is True, loaded.to_dict()


def test_resource_saver_rejects_a_staging_token_after_the_resource_extension(
    godot_bin, godot_project
):
    """The legacy suffix order must remain a real engine failure."""
    base = "res://assets/generated/ui-kit/panel"
    _write(godot_project, f"{base}/panel.png", b"source")
    script = godot_project / "save_legacy_staging_resource.gd"
    script.write_text(RESOURCE_SAVER_SCRIPT, encoding="utf-8")

    completed = _run_resource_saver(
        GodotProbe(godot_bin),
        godot_project,
        script,
        "StyleBoxTexture",
        f"{base}/panel.tres.staging-legacy",
    )

    assert completed.returncode == 15, completed.stderr or completed.stdout


def test_a_generated_texture_reaches_ready_through_real_godot(godot_bin, godot_project):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(24, 16))
    registry = build_default_registry()
    result = ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    ).run(
        _entry(),
        project_root=godot_project,
        receipt=_default_compile_receipt(registry, godot_project),
    )

    assert result.ready is True, result.to_dict()
    assert result.processing_status == "ready"
    # Godot imports a PNG as a CompressedTexture2D; the declared Texture2D must
    # still match, because is_class covers the whole inheritance chain.
    assert result.levels[3].details["godot_class"] == "CompressedTexture2D"
    assert result.levels[3].details["godot_version"].startswith("4.")
    # L4 reads the dimensions of the resource Godot loaded, not of the file.
    assert result.levels[4].details["width"] == 24
    assert result.levels[4].details["height"] == 16


def test_a_compiled_theme_recipe_reaches_ready_through_real_godot(godot_bin, godot_project):
    """The compiler output must survive real Theme loading and L4 inspection."""
    recipe_path = "res://assets/generated/ui-kit/skin/skin.json"
    _write(
        godot_project,
        recipe_path,
        b'''{"version":1,"colors":[{"type":"Button","name":"font_color","value":"#FFFFFFFF"}],"font_sizes":[],"constants":[],"fonts":[],"icons":[],"styleboxes":{"normal":{"type":"StyleBoxFlat","properties":{"bg_color":"#112233FF","border_width":2}},"focus":{"type":"StyleBoxEmpty","properties":{}}},"styles":[{"type":"Button","name":"normal","stylebox":"normal"},{"type":"Button","name":"focus","stylebox":"focus"}],"variations":[{"name":"PrimaryButton","base_type":"Button"}]}''',
    )
    registry = build_default_registry()
    theme.register_into(registry)
    compiled = registry.compile(
        CompileRequest(
            production_family="ui-kit",
            asset_id="skin",
            source_layout_type="theme_recipe",
            source_path=recipe_path,
            artifact_type="Theme",
            artifact_path="res://assets/generated/ui-kit/skin/skin.tres",
            project_root=godot_project,
        )
    )
    structures = build_default_structures()
    theme.register_structure_into(structures)
    entry = _entry(
        asset_id="skin",
        source_layout={"type": "theme_recipe", "path": recipe_path},
        godot_artifact=compiled.godot_artifact.to_dict(),
    )
    result = ValidationLadder(
        registry=registry, structures=structures, probe=GodotProbe(godot_bin)
    ).run(entry, project_root=godot_project, receipt=compiled.receipt)

    assert result.ready is True, result.to_dict()
    assert result.levels[3].details["godot_class"] == "Theme"
    assert result.levels[4].details["variations"] == ["PrimaryButton"]
    border = result.levels[3].details["structure"]["theme"]["types"]["Button"]["styleboxes"]["normal"]["border_width"]
    assert border == {"left": 2, "top": 2, "right": 2, "bottom": 2}
    assert result.levels[3].details["structure"]["theme"]["types"]["Button"]["styleboxes"]["focus"] == {"class": "StyleBoxEmpty"}
def test_fixed_slot_atlas_texture_reaches_ready_with_its_exact_region(
    godot_bin, godot_project
):
    """L3 and L4 prove Godot loads the compiled AtlasTexture unchanged."""
    base = "res://assets/generated/ui-kit/main_atlas"
    _write(godot_project, f"{base}/main_atlas.png", _png(12, 8))
    _write(
        godot_project,
        f"{base}/main_atlas.json",
        json.dumps(
            {
                "version": 1,
                "atlas_path": f"{base}/main_atlas.png",
                "regions": [
                    {"name": "button", "rect": [0, 0, 4, 4], "pivot": [0.5, 0.5], "nine_slice": None},
                    {"name": "icon", "rect": [6, 2, 2, 3], "pivot": [0.0, 1.0], "nine_slice": None},
                ],
            }
        ).encode(),
    )
    registry = build_default_registry()
    request = CompileRequest(
        production_family="ui-kit",
        asset_id="main_atlas",
        source_layout_type="region_atlas",
        source_path=f"{base}/main_atlas.png",
        artifact_type="AtlasTexture",
        artifact_path=f"{base}/button.tres",
        project_root=godot_project,
        spec={"metadata_path": f"{base}/main_atlas.json", "logical_asset_id": "button"},
    )
    compiled = registry.compile(request)
    entry = _entry(
        asset_id="main_atlas",
        source_layout={"type": "region_atlas", "path": request.source_path},
        godot_artifact=compiled.godot_artifact.to_dict(),
    )
    result = ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    ).run(entry, project_root=godot_project, spec=request.spec, receipt=compiled.receipt)

    assert result.ready is True, result.to_dict()
    assert result.levels[3].details["godot_class"] == "AtlasTexture"
    assert result.levels[4].details["region"] == [0, 0, 4, 4]
    assert result.levels[4].details["margin"] == [0, 0, 0, 0]

    # The same region and zero margin cannot prove that the resource still
    # binds the physical atlas declared by metadata. Tampering only the
    # ExtResource target must therefore reach L3 but fail the L4 path check.
    _write(godot_project, f"{base}/other_atlas.png", _png(12, 8))
    artifact = godot_project / "assets/generated/ui-kit/main_atlas/button.tres"
    artifact.write_text(
        artifact.read_text(encoding="utf-8").replace(
            "main_atlas.png", "other_atlas.png"
        ),
        encoding="utf-8",
    )
    entry["processing_status"] = "ready"
    tampered = ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    ).run(
        entry,
        project_root=godot_project,
        spec=request.spec,
        mode=REVALIDATION,
    )

    assert tampered.ready is False, tampered.to_dict()
    assert tampered.levels[3].status == PASSED
    assert tampered.failure.level == "L4"
    assert "atlas_path" in tampered.failure.error


def test_stylebox_texture_reaches_ready_with_its_exact_nine_slice_recipe(
    godot_bin, godot_project
):
    base = "res://assets/generated/ui-kit/panel"
    _write(godot_project, f"{base}/panel.png", _png(16, 12))
    registry = build_default_registry()
    request = CompileRequest(
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path=f"{base}/panel.png",
        artifact_type="StyleBoxTexture",
        artifact_path=f"{base}/panel.tres",
        project_root=godot_project,
        spec={
            "texture_region": [2, 1, 12, 10],
            "border": [3, 2, 3, 2],
            "expand_margin": [1, 1.5, 2, 0],
            "axis_stretch": {"horizontal": "tile_fit", "vertical": "stretch"},
        },
    )
    compiled = registry.compile(request)
    entry = _entry(godot_artifact=compiled.godot_artifact.to_dict())
    result = ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    ).run(entry, project_root=godot_project, spec=request.spec, receipt=compiled.receipt)

    assert result.ready is True, result.to_dict()
    assert result.levels[3].details["godot_class"] == "StyleBoxTexture"
    assert result.levels[4].details["texture_region"] == [2, 1, 12, 10]
    assert result.levels[4].details["border"] == [3, 2, 3, 2]
    assert result.levels[4].details["axis_stretch"] == {
        "horizontal": "tile_fit",
        "vertical": "stretch",
    }


def test_headless_godot_rejects_a_corrupt_resource(godot_bin, godot_project):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(8, 8))
    _write(
        godot_project,
        "res://assets/generated/ui-kit/panel/panel.tres",
        b"this is not a Godot resource\n",
    )
    entry = _entry(
        processing_status="ready",
        godot_artifact={
            "type": "StyleBoxTexture",
            "path": "res://assets/generated/ui-kit/panel/panel.tres",
        }
    )
    result = _stylebox_ladder(godot_bin).run(
        entry, project_root=godot_project, mode=REVALIDATION
    )

    assert result.ready is False
    assert result.failure.level == "L3"
    assert "ResourceLoader.load returned null" in result.failure.error
    assert result.levels[4].status == NOT_RUN


def test_headless_godot_rejects_a_resource_of_the_wrong_type(godot_bin, godot_project):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(8, 8))
    _write(
        godot_project,
        "res://assets/generated/ui-kit/panel/panel.tres",
        THEME_TRES.encode("utf-8"),
    )
    entry = _entry(
        processing_status="ready",
        godot_artifact={
            "type": "StyleBoxTexture",
            "path": "res://assets/generated/ui-kit/panel/panel.tres",
        }
    )
    result = _stylebox_ladder(godot_bin).run(
        entry, project_root=godot_project, mode=REVALIDATION
    )

    assert result.ready is False
    assert result.failure.level == "L3"
    assert "as Theme, which is not a StyleBoxTexture" in result.failure.error


def test_a_loadable_type_without_a_structure_validator_stops_at_l4(godot_bin, godot_project):
    """L3 passing is not readiness: an unchecked structure still fails closed."""
    registry = build_default_registry()
    registry.register(
        source_layout_type="theme_recipe",
        artifact_type="Theme",
        compiler_id="test_theme",
        compiler_version=1,
        compiler=lambda request: {},
    )
    _write(
        godot_project,
        "res://assets/generated/ui-kit/skin/skin.json",
        b'{"colors": {}}',
    )
    _write(
        godot_project,
        "res://assets/generated/ui-kit/skin/skin.tres",
        THEME_TRES.encode("utf-8"),
    )
    entry = _entry(
        processing_status="ready",
        asset_id="skin",
        source_layout={
            "type": "theme_recipe",
            "path": "res://assets/generated/ui-kit/skin/skin.json",
        },
        godot_artifact={
            "type": "Theme",
            "path": "res://assets/generated/ui-kit/skin/skin.tres",
        },
    )
    ladder = ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    )
    result = ladder.run(entry, project_root=godot_project, mode=REVALIDATION)

    assert result.levels[3].status == PASSED
    assert result.levels[3].details["godot_class"] == "Theme"
    assert result.failure.level == "L4"
    assert "no structure validator is registered for Theme" in result.failure.error


def test_the_probe_reports_a_path_godot_cannot_import(godot_bin, godot_project):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(4, 4))
    report = GodotProbe(godot_bin).probe(
        godot_project,
        [
            ProbeRequest(
                res_path="res://assets/generated/ui-kit/panel/panel.png",
                expected_type="Texture2D",
                checks=("texture2d",),
            ),
            ProbeRequest(
                res_path="res://assets/generated/ui-kit/panel/absent.tres",
                expected_type="Texture2D",
            ),
        ],
    )

    assert report.godot_version.startswith("4.")
    present, absent = report.resources
    assert present.loaded is True
    assert present.type_matches is True
    assert present.structure == {"texture2d": {"width": 4, "height": 4}}
    assert absent.loaded is False
    assert "no importable resource" in absent.error


def test_a_check_godot_cannot_answer_fails_l4_even_if_the_validator_ignores_it(
    godot_bin, godot_project
):
    """Registration cannot catch this one: the check name is implemented.

    ``texture2d`` is a legal check, but the artifact is a ``StyleBoxTexture``, so
    the engine answers with an error instead of dimensions. The validator here
    returns ``{}`` without reading the probe -- L4 must still fail, on Godot's
    answer alone.
    """
    # This test deliberately installs a validator that asks for the wrong
    # probe check; isolate both replacements from the shared defaults.
    registry = CompilerRegistry()
    registry.register(
        source_layout_type="single",
        artifact_type="StyleBoxTexture",
        compiler_id="test_stylebox",
        compiler_version=1,
        compiler=lambda request: {},
    )
    structures = StructureValidatorRegistry()
    structures.register(
        artifact_type="StyleBoxTexture",
        validator_id="ignores_the_probe",
        validator=lambda request: {},
        checks=("texture2d",),
    )
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(8, 8))
    _write(
        godot_project,
        "res://assets/generated/ui-kit/panel/panel.tres",
        b'[gd_resource type="StyleBoxTexture" format=3]\n\n[resource]\n',
    )
    entry = _entry(
        processing_status="ready",
        godot_artifact={
            "type": "StyleBoxTexture",
            "path": "res://assets/generated/ui-kit/panel/panel.tres",
        }
    )
    ladder = ValidationLadder(
        registry=registry, structures=structures, probe=GodotProbe(godot_bin)
    )
    result = ladder.run(entry, project_root=godot_project, mode=REVALIDATION)

    assert result.levels[3].status == PASSED
    assert result.ready is False, result.to_dict()
    assert result.failure.level == "L4"
    assert "could not be performed" in result.failure.error
    assert "not a Texture2D" in result.failure.error


def test_the_probe_reports_an_unknown_structural_check(godot_bin, godot_project):
    """A check name probe.gd does not implement is an error, never a silent pass."""
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(4, 4))
    report = GodotProbe(godot_bin).probe(
        godot_project,
        [
            ProbeRequest(
                res_path="res://assets/generated/ui-kit/panel/panel.png",
                expected_type="Texture2D",
                checks=("nine_slice_margins",),
            )
        ],
    )

    (result,) = report.resources
    assert result.loaded is True
    assert "unknown structural check" in result.structure["nine_slice_margins"]["error"]


def test_the_ladder_leaves_the_project_sources_untouched(godot_bin, godot_project):
    """Godot writes its import cache; the ladder itself writes nothing."""
    source = _write(
        godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(12, 12)
    )
    before = source.read_bytes()
    registry = build_default_registry()
    result = ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    ).run(
        _entry(),
        project_root=godot_project,
        receipt=_default_compile_receipt(registry, godot_project),
    )

    assert result.ready is True
    assert source.read_bytes() == before
    generated = sorted(
        path.relative_to(godot_project).as_posix()
        for path in (godot_project / "assets").rglob("*")
        if path.is_file()
    )
    assert generated == [
        "assets/generated/ui-kit/panel/panel.png",
        "assets/generated/ui-kit/panel/panel.png.import",
    ]


@pytest.mark.parametrize("expected_type", ["SpriteFrames", "AtlasTexture"])
def test_a_declared_type_the_resource_is_not_never_matches(
    godot_bin, godot_project, expected_type
):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(4, 4))
    report = GodotProbe(godot_bin).probe(
        godot_project,
        [
            ProbeRequest(
                res_path="res://assets/generated/ui-kit/panel/panel.png",
                expected_type=expected_type,
            )
        ],
    )

    (result,) = report.resources
    assert result.loaded is True
    assert result.godot_class == "CompressedTexture2D"
    assert result.type_matches is False
