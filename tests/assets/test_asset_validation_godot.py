"""L3 against a real engine: import the project, load the resource, match the type.

These are the tests the unit suite cannot stand in for. A stubbed probe proves
the ladder reacts correctly to an answer; only Godot proves the answer. They skip
when no engine is reachable -- CI installs pytest and pillow only -- so a
contributor with Godot 4.4+ installed runs them and CI does not.
"""
import struct
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import build_default_registry  # noqa: E402
from asset_validation import (  # noqa: E402
    NOT_RUN,
    PASSED,
    GodotProbe,
    ProbeRequest,
    ValidationLadder,
    build_default_ladder,
    build_default_structures,
)

# A Theme with no content: it loads cleanly, which is what makes it a useful
# stand-in for a resource of the wrong type.
THEME_TRES = '[gd_resource type="Theme" format=3]\n\n[resource]\n'


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
    """A ladder with one writing route, so a compiled ``.tres`` can reach L3."""
    registry = build_default_registry()
    registry.register(
        source_layout_type="single",
        artifact_type="StyleBoxTexture",
        compiler_id="test_stylebox",
        compiler_version=1,
        compiler=lambda request: {},
    )
    return ValidationLadder(
        registry=registry,
        structures=build_default_structures(),
        probe=GodotProbe(godot_bin),
    )


def test_a_generated_texture_reaches_ready_through_real_godot(godot_bin, godot_project):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(24, 16))
    result = build_default_ladder(godot_bin).run(_entry(), project_root=godot_project)

    assert result.ready is True, result.to_dict()
    assert result.processing_status == "ready"
    # Godot imports a PNG as a CompressedTexture2D; the declared Texture2D must
    # still match, because is_class covers the whole inheritance chain.
    assert result.levels[3].details["godot_class"] == "CompressedTexture2D"
    assert result.levels[3].details["godot_version"].startswith("4.")
    # L4 reads the dimensions of the resource Godot loaded, not of the file.
    assert result.levels[4].details["width"] == 24
    assert result.levels[4].details["height"] == 16


def test_headless_godot_rejects_a_corrupt_resource(godot_bin, godot_project):
    _write(godot_project, "res://assets/generated/ui-kit/panel/panel.png", _png(8, 8))
    _write(
        godot_project,
        "res://assets/generated/ui-kit/panel/panel.tres",
        b"this is not a Godot resource\n",
    )
    entry = _entry(
        godot_artifact={
            "type": "StyleBoxTexture",
            "path": "res://assets/generated/ui-kit/panel/panel.tres",
        }
    )
    result = _stylebox_ladder(godot_bin).run(entry, project_root=godot_project)

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
        godot_artifact={
            "type": "StyleBoxTexture",
            "path": "res://assets/generated/ui-kit/panel/panel.tres",
        }
    )
    result = _stylebox_ladder(godot_bin).run(entry, project_root=godot_project)

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
    result = ladder.run(entry, project_root=godot_project)

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
    result = build_default_ladder(godot_bin).run(_entry(), project_root=godot_project)

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
