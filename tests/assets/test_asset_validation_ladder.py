"""Unit coverage for the shared L0-L4 readiness ladder.

Godot is stubbed here so every level's own logic is exercised without an engine;
``test_asset_validation_godot.py`` runs the same ladder against a real binary.
The stub is a ``GodotProbe`` subclass rather than a mock so it cannot drift from
the interface the ladder actually calls.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import (  # noqa: E402
    CompileReceipt,
    CompileRequest,
    CompilerRegistry,
    build_default_registry,
)
from asset_validation import (  # noqa: E402
    FAILED,
    LEVELS,
    NOT_RUN,
    PASSED,
    PROMOTION,
    REVALIDATION,
    STATUS_FAILED,
    STATUS_READY,
    GodotProbe,
    GodotProbeError,
    PROBE_CHECKS,
    LadderResult,
    LevelResult,
    ProbeReport,
    ProbeRequest,
    ProbeResult,
    StructureRequest,
    StructureValidatorRegistry,
    ValidationError,
    ValidationLadder,
    build_default_ladder,
    build_default_structures,
    find_godot,
    validate_texture2d,
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

SOURCE = "res://assets/generated/ui-kit/panel/panel.png"
ARTIFACT = "res://assets/generated/ui-kit/panel/panel.tres"


class StubProbe(GodotProbe):
    """A ``GodotProbe`` that answers from a script instead of running Godot."""

    def __init__(self, *, answers=None, raises=None, structure=None):
        super().__init__("godot")
        self.answers = answers
        self.raises = raises
        self.structure = structure if structure is not None else {"texture2d": {"width": 4, "height": 3}}
        self.calls: list[tuple[Path, tuple[ProbeRequest, ...]]] = []

    def probe(self, project_root, requests):
        self.calls.append((Path(project_root), tuple(requests)))
        if self.raises is not None:
            raise self.raises
        if self.answers is not None:
            return ProbeReport(godot_version="4.4-stable (stub)", resources=tuple(self.answers))
        return ProbeReport(
            godot_version="4.4-stable (stub)",
            resources=tuple(
                ProbeResult(
                    res_path=item.res_path,
                    expected_type=item.expected_type,
                    loaded=True,
                    godot_class=item.expected_type,
                    type_matches=True,
                    structure={
                        name: value
                        for name, value in self.structure.items()
                        if name in item.checks
                    },
                )
                for item in requests
            ),
        )


def _project(tmp_path: Path, *, family: str = "ui-kit", asset_id: str = "panel") -> Path:
    root = tmp_path / "game"
    (root / "assets" / "generated" / family / asset_id).mkdir(parents=True, exist_ok=True)
    (root / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    return root


def _write(root: Path, res_path: str, payload: bytes = PNG) -> Path:
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
        "source_layout": {"type": "single", "path": SOURCE},
        "godot_artifact": {"type": "Texture2D", "path": SOURCE},
        "processing_status": "compiled",
    }
    entry.update(overrides)
    return entry


def _stylebox_registry() -> CompilerRegistry:
    """The shared registry plus one writing route, so L2's writing rules are reachable."""
    registry = build_default_registry()
    registry.register(
        source_layout_type="single",
        artifact_type="StyleBoxTexture",
        compiler_id="test_stylebox",
        compiler_version=2,
        compiler=lambda request: {},
    )
    return registry


def _ladder(*, registry=None, structures=None, probe=None) -> ValidationLadder:
    return ValidationLadder(
        registry=registry if registry is not None else build_default_registry(),
        structures=structures if structures is not None else build_default_structures(),
        probe=probe if probe is not None else StubProbe(),
    )


_DEFAULT_RECEIPT = object()


def _run(tmp_path, entry=None, *, receipt=_DEFAULT_RECEIPT, **kwargs):
    root = _project(tmp_path)
    _write(root, SOURCE)
    registry = kwargs.pop("registry", None)
    if registry is None:
        registry = build_default_registry()
    if receipt is _DEFAULT_RECEIPT:
        receipt = _issued_receipt(root, registry)
    mode = kwargs.pop("mode", PROMOTION)
    return (
        _ladder(registry=registry, **kwargs).run(
            entry or _entry(), project_root=root, receipt=receipt, mode=mode
        ),
        root,
    )


def _failure(result):
    assert result.failure is not None, result.to_dict()
    return result.failure.level, result.failure.error


# --------------------------------------------------------------------- happy


def test_a_fully_valid_texture_entry_reaches_ready(tmp_path):
    result, _ = _run(tmp_path)
    assert result.ready is True
    assert result.processing_status == STATUS_READY
    assert result.failure is None
    assert [level.status for level in result.levels] == [PASSED] * 5
    assert result.asset_id == "panel"
    assert result.production_family == "ui-kit"


def test_every_level_is_reported_in_order_with_its_documented_name(tmp_path):
    result, _ = _run(tmp_path)
    assert [level.level for level in result.levels] == [spec.level for spec in LEVELS]
    assert [level.name for level in result.levels] == [spec.name for spec in LEVELS]


def test_the_verdict_serializes_every_level(tmp_path):
    result, _ = _run(tmp_path)
    payload = result.to_dict()
    assert payload["ready"] is True
    assert payload["processing_status"] == STATUS_READY
    assert payload["failed_level"] is None
    assert len(payload["levels"]) == 5
    assert payload["levels"][3]["details"]["godot_class"] == "Texture2D"
    assert payload["levels"][3]["details"]["godot_version"] == "4.4-stable (stub)"
    assert payload["levels"][4]["details"]["validator_id"] == "texture2d_structure"


def test_the_ladder_never_writes_to_the_project(tmp_path):
    result, root = _run(tmp_path)
    assert result.ready is True
    produced = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert produced == ["assets/generated/ui-kit/panel/panel.png", "project.godot"]


# ------------------------------------------------------------------------ L0


def test_a_non_object_entry_fails_l0(tmp_path):
    root = _project(tmp_path)
    result = _ladder().run(["not", "an", "entry"], project_root=root)
    level, error = _failure(result)
    assert level == "L0"
    assert "JSON object" in error


def test_a_legacy_runtime_artifact_entry_fails_l0(tmp_path):
    result, _ = _run(tmp_path, _entry(runtime_artifact={"type": "grid_sheet"}))
    level, error = _failure(result)
    assert level == "L0"
    assert "Legacy runtime_artifact schema" in error


def test_a_wrong_schema_version_fails_l0(tmp_path):
    result, _ = _run(tmp_path, _entry(version="1"))
    assert _failure(result)[0] == "L0"


def test_an_unknown_production_family_fails_l0(tmp_path):
    result, _ = _run(tmp_path, _entry(production_family="mystery-family"))
    level, error = _failure(result)
    assert level == "L0"
    assert "production_family is not allowed" in error


def test_an_artifact_type_incompatible_with_its_layout_fails_l0(tmp_path):
    result, _ = _run(
        tmp_path,
        _entry(
            source_layout={"type": "grid_sheet", "path": SOURCE},
            godot_artifact={"type": "Texture2D", "path": SOURCE},
        ),
    )
    level, error = _failure(result)
    assert level == "L0"
    assert "must be one of: SpriteFrames" in error


def test_a_source_outside_the_stable_directory_fails_l0(tmp_path):
    result, _ = _run(
        tmp_path,
        _entry(source_layout={"type": "single", "path": "res://assets/generated/ui-kit/other/x.png"}),
    )
    level, error = _failure(result)
    assert level == "L0"
    assert "must be a file under res://assets/generated/ui-kit/panel/" in error


def test_a_path_in_the_generation_workspace_fails_l0(tmp_path):
    work = "res://.godotmaker/asset-generation/work/panel.png"
    result, _ = _run(tmp_path, _entry(source_layout={"type": "single", "path": work}))
    level, error = _failure(result)
    assert level == "L0"
    assert "work/ workspace" in error


@pytest.mark.parametrize(
    "entry",
    [
        _entry(
            production_family="screen-reference",
            asset_id="title",
            source_layout={"type": "reference", "path": "res://assets/refs/title.png"},
            godot_artifact=None,
            processing_status="source_ready",
        ),
    ],
)
def test_a_reference_asset_has_no_rung_on_the_ladder(tmp_path, entry):
    root = _project(tmp_path, family="screen-reference", asset_id="title")
    _write(root, "res://assets/refs/title.png")
    result = _ladder().run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L0"
    assert "no L0-L4 readiness ladder" in error
    assert "source_ready" in error
    assert result.processing_status == STATUS_FAILED


def test_a_non_path_project_root_fails_l0(tmp_path):
    result = _ladder().run(_entry(), project_root=object())
    level, error = _failure(result)
    assert level == "L0"
    assert "project_root must be a path" in error


def test_a_failure_leaves_every_later_level_not_run(tmp_path):
    result, _ = _run(tmp_path, _entry(version=99))
    assert [level.status for level in result.levels] == [FAILED, NOT_RUN, NOT_RUN, NOT_RUN, NOT_RUN]
    assert result.ready is False
    assert result.processing_status == STATUS_FAILED


# ------------------------------------------------------------------------ L1


def test_a_missing_processed_source_fails_l1(tmp_path):
    root = _project(tmp_path)
    result = _ladder().run(_entry(), project_root=root)
    level, error = _failure(result)
    assert level == "L1"
    assert "is not a file on disk" in error


def test_an_empty_processed_source_fails_l1(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE, b"")
    result = _ladder().run(_entry(), project_root=root)
    level, error = _failure(result)
    assert level == "L1"
    assert "empty file" in error


def test_a_directory_where_the_source_should_be_fails_l1(tmp_path):
    root = _project(tmp_path)
    (root / "assets/generated/ui-kit/panel/panel.png").mkdir(parents=True)
    result = _ladder().run(_entry(), project_root=root)
    assert _failure(result)[0] == "L1"


# L0 already resolves both paths and requires them to stay inside the project
# root, so a link aimed out of the project never reaches L1. The escape only L1
# can catch is one that lands inside the project but outside the asset's own
# stable directory -- another asset's files, or a shared directory -- which is
# what both tests below build.
def _elsewhere_in_project(root: Path) -> Path:
    target = root / "assets" / "generated" / "ui-kit" / "borrowed"
    target.mkdir(parents=True, exist_ok=True)
    (target / "panel.png").write_bytes(PNG)
    return target


def test_a_symlinked_source_leaving_the_stable_directory_fails_l1(tmp_path):
    root = _project(tmp_path)
    borrowed = _elsewhere_in_project(root)
    link = root / "assets/generated/ui-kit/panel/panel.png"
    try:
        link.symlink_to(borrowed / "panel.png")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")

    result = _ladder().run(_entry(), project_root=root)
    level, error = _failure(result)
    assert level == "L1"
    assert "must be written under assets/generated/ui-kit/panel/" in error


def _link_directory(link: Path, target: Path) -> None:
    """Link a directory, using a junction where symlinks need a privilege.

    Windows reserves symlink creation for elevated or developer-mode sessions but
    lets any user create a directory junction, and ``Path.resolve`` follows both.
    Without this the on-disk containment guard would be exercised on no platform
    a Windows contributor is likely to run tests on.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if sys.platform != "win32":
        pytest.skip("directory links not permitted on this platform")
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"directory junctions not permitted: {completed.stderr.strip()}")


def test_a_linked_subdirectory_of_the_stable_directory_fails_l1(tmp_path):
    root = _project(tmp_path)
    borrowed = _elsewhere_in_project(root)
    # A directory link *inside* the stable directory. The declared path is a
    # clean res:// file under assets/generated/ui-kit/panel/, so L0 accepts it
    # and it still resolves inside the project -- only the stable-directory
    # containment can see that the bytes come from another asset.
    _link_directory(root / "assets/generated/ui-kit/panel/nested", borrowed)
    nested = "res://assets/generated/ui-kit/panel/nested/panel.png"

    result = _ladder().run(
        _entry(
            source_layout={"type": "single", "path": nested},
            godot_artifact={"type": "Texture2D", "path": nested},
        ),
        project_root=root,
    )
    level, error = _failure(result)
    assert level == "L1"
    assert "must be written under assets/generated/ui-kit/panel/" in error


# ------------------------------------------------------------------------ L2


def test_an_entry_without_a_godot_artifact_fails_l2(tmp_path):
    result, _ = _run(tmp_path, _entry(godot_artifact=None, processing_status="source_ready"))
    level, error = _failure(result)
    assert level == "L0"
    assert "promotion requires an entry with processing_status 'compiled'" in error


def test_an_artifact_type_with_no_registered_compiler_fails_l2(tmp_path):
    root = _project(tmp_path, asset_id="hero")
    entry = _entry(
        asset_id="hero",
        source_layout={"type": "theme_recipe", "path": "res://assets/generated/ui-kit/hero/hero.json"},
        godot_artifact={"type": "Theme", "path": "res://assets/generated/ui-kit/hero/hero.tres"},
    )
    _write(root, "res://assets/generated/ui-kit/hero/hero.json")
    _write(root, "res://assets/generated/ui-kit/hero/hero.tres", b"[gd_resource]\n")
    result = _ladder().run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L2"
    assert "no compiler is registered for theme_recipe -> Theme" in error


def test_a_missing_compiled_artifact_fails_l2(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    entry = _entry(godot_artifact={"type": "StyleBoxTexture", "path": ARTIFACT})
    result = _ladder(registry=_stylebox_registry()).run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L2"
    assert "godot_artifact.path is not a file on disk" in error


def test_an_empty_compiled_artifact_fails_l2(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    _write(root, ARTIFACT, b"")
    entry = _entry(godot_artifact={"type": "StyleBoxTexture", "path": ARTIFACT})
    result = _ladder(registry=_stylebox_registry()).run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L2"
    assert "empty file" in error


def test_a_writing_route_may_not_publish_its_source_image_as_the_artifact(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    entry = _entry(godot_artifact={"type": "StyleBoxTexture", "path": SOURCE})
    result = _ladder(registry=_stylebox_registry()).run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L2"
    assert "may not be the source image itself" in error


def test_a_writing_route_may_not_hard_link_its_source_as_the_artifact(tmp_path):
    root = _project(tmp_path)
    source = _write(root, SOURCE)
    alias = root / ARTIFACT[len("res://"):]
    try:
        os.link(source, alias)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("hard links not permitted on this platform")
    entry = _entry(godot_artifact={"type": "StyleBoxTexture", "path": ARTIFACT})
    result = _ladder(registry=_stylebox_registry()).run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L2"
    assert "may not be the source image itself" in error


def test_a_non_writing_route_must_name_its_source_as_the_artifact(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    _write(root, ARTIFACT, b"[gd_resource]\n")
    entry = _entry(
        source_layout={"type": "single", "path": SOURCE},
        godot_artifact={"type": "Texture2D", "path": ARTIFACT},
    )
    result = _ladder().run(entry, project_root=root)
    level, error = _failure(result)
    assert level == "L2"
    assert "must equal source_layout.path" in error


def test_l2_reports_the_route_that_compiled_the_artifact(tmp_path):
    result, _ = _run(tmp_path)
    details = result.levels[2].details
    assert details["compiler_id"] == "texture2d_default_import"
    assert details["compiler_version"] == 1
    assert details["writes_artifact"] is False
    assert details["bytes"] == len(PNG)


def test_promotion_of_a_compiled_entry_requires_a_compile_receipt(tmp_path):
    result, _ = _run(tmp_path, receipt=None)
    level, error = _failure(result)
    assert level == "L2"
    assert "promotion requires a matching CompileReceipt" in error
    assert result.levels[3].status == NOT_RUN


def _receipt(**overrides):
    fields = {
        "compiler_id": "texture2d_default_import",
        "compiler_version": 1,
        "production_family": "ui-kit",
        "asset_id": "panel",
        "source_layout_type": "single",
        "source_path": SOURCE,
        "artifact_type": "Texture2D",
        "artifact_path": SOURCE,
        "details": {},
    }
    fields.update(overrides)
    return CompileReceipt(**fields)


def _issued_receipt(root: Path, registry: CompilerRegistry) -> CompileReceipt:
    return registry.compile(
        CompileRequest(
            production_family="ui-kit",
            asset_id="panel",
            source_layout_type="single",
            source_path=SOURCE,
            artifact_type="Texture2D",
            artifact_path=SOURCE,
            project_root=root,
        )
    ).receipt


def test_a_matching_compile_receipt_is_recorded_by_l2(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    registry = build_default_registry()
    result = _ladder(registry=registry).run(
        _entry(), project_root=root, receipt=_issued_receipt(root, registry)
    )
    assert result.ready is True
    assert result.levels[2].details["receipt"] == {
        "compiler_id": "texture2d_default_import",
        "compiler_version": 1,
    }


def test_a_hand_built_matching_receipt_is_rejected_as_unissued(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    registry = build_default_registry()
    result = _ladder(registry=registry).run(
        _entry(), project_root=root, receipt=_receipt()
    )
    level, error = _failure(result)
    assert level == "L2"
    assert "was not issued by this compiler registry" in error


def test_a_receipt_with_an_old_compiler_version_fails_l2(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    registry = build_default_registry()
    result = _ladder(registry=registry).run(
        _entry(), project_root=root, receipt=_receipt(compiler_version=999)
    )
    level, error = _failure(result)
    assert level == "L2"
    assert "describes compiler_version 999" in error


def test_an_object_that_is_not_a_compile_receipt_fails_l2(tmp_path):
    class Lookalike:
        compiler_id = "texture2d_default_import"
        compiler_version = 1
        production_family = "ui-kit"
        asset_id = "panel"
        source_layout_type = "single"
        source_path = SOURCE
        artifact_type = "Texture2D"
        artifact_path = SOURCE

    root = _project(tmp_path)
    _write(root, SOURCE)
    result = _ladder().run(_entry(), project_root=root, receipt=Lookalike())
    level, error = _failure(result)
    assert level == "L2"
    assert "must be a CompileReceipt" in error


def test_an_already_ready_entry_can_be_explicitly_revalidated_without_a_receipt(tmp_path):
    result, _ = _run(
        tmp_path,
        _entry(processing_status="ready"),
        receipt=None,
        mode=REVALIDATION,
    )
    assert result.ready is True
    assert [level.status for level in result.levels] == [PASSED] * 5
    assert "receipt" not in result.levels[2].details


@pytest.mark.parametrize("processing_status", ["pending", "source_ready", "compiled"])
def test_revalidation_cannot_promote_an_entry_that_is_not_ready(tmp_path, processing_status):
    result, _ = _run(
        tmp_path,
        _entry(processing_status=processing_status),
        receipt=None,
        mode=REVALIDATION,
    )
    level, error = _failure(result)
    assert level == "L0"
    assert "revalidation requires an entry with processing_status 'ready'" in error


def test_promotion_only_accepts_a_compiled_entry(tmp_path):
    result, _ = _run(tmp_path, _entry(processing_status="ready"), mode=PROMOTION)
    level, error = _failure(result)
    assert level == "L0"
    assert "promotion requires an entry with processing_status 'compiled'" in error


# ------------------------------------------------------------------------ L3


def test_l3_asks_godot_for_the_artifact_and_the_checks_l4_needs(tmp_path):
    probe = StubProbe()
    root = _project(tmp_path)
    _write(root, SOURCE)
    registry = build_default_registry()
    _ladder(registry=registry, probe=probe).run(
        _entry(), project_root=root, receipt=_issued_receipt(root, registry)
    )
    (project_root, requests), = probe.calls
    assert project_root == root
    assert requests == (ProbeRequest(res_path=SOURCE, expected_type="Texture2D", checks=("texture2d",)),)


def test_a_resource_godot_cannot_load_fails_l3(tmp_path):
    probe = StubProbe(
        answers=[
            ProbeResult(
                res_path=SOURCE,
                expected_type="Texture2D",
                loaded=False,
                godot_class="",
                type_matches=False,
                error="ResourceLoader.load returned null for " + SOURCE,
            )
        ]
    )
    result, _ = _run(tmp_path, probe=probe)
    level, error = _failure(result)
    assert level == "L3"
    assert "returned null" in error


def test_a_resource_of_the_wrong_godot_type_fails_l3(tmp_path):
    probe = StubProbe(
        answers=[
            ProbeResult(
                res_path=SOURCE,
                expected_type="Texture2D",
                loaded=True,
                godot_class="Theme",
                type_matches=False,
            )
        ]
    )
    result, _ = _run(tmp_path, probe=probe)
    level, error = _failure(result)
    assert level == "L3"
    assert "loaded" in error and "Theme" in error and "not a Texture2D" in error


def test_an_unavailable_godot_binary_fails_l3_rather_than_skipping_it(tmp_path):
    probe = StubProbe(raises=GodotProbeError("godot binary not found at godot"))
    result, _ = _run(tmp_path, probe=probe)
    level, error = _failure(result)
    assert level == "L3"
    assert "godot binary not found" in error
    assert result.ready is False
    assert result.levels[4].status == NOT_RUN


# ------------------------------------------------------------------------ L4


def test_an_artifact_type_with_no_structure_validator_fails_l4(tmp_path):
    root = _project(tmp_path)
    _write(root, SOURCE)
    _write(root, ARTIFACT, b"[gd_resource]\n")
    entry = _entry(
        godot_artifact={"type": "StyleBoxTexture", "path": ARTIFACT},
        processing_status="ready",
    )
    result = _ladder(registry=_stylebox_registry()).run(
        entry,
        project_root=root,
        mode=REVALIDATION,
    )
    level, error = _failure(result)
    assert level == "L4"
    assert "no structure validator is registered for StyleBoxTexture" in error
    assert result.levels[3].status == PASSED


def test_a_zero_sized_texture_fails_l4(tmp_path):
    probe = StubProbe(structure={"texture2d": {"width": 0, "height": 8}})
    result, _ = _run(tmp_path, probe=probe)
    level, error = _failure(result)
    assert level == "L4"
    assert "positive width and height" in error


def test_a_texture_whose_dimensions_are_not_integers_fails_l4(tmp_path):
    probe = StubProbe(structure={"texture2d": {"width": True, "height": 8}})
    result, _ = _run(tmp_path, probe=probe)
    assert _failure(result)[0] == "L4"


def test_a_probe_that_collected_no_structure_fails_l4(tmp_path):
    probe = StubProbe(structure={})
    result, _ = _run(tmp_path, probe=probe)
    level, error = _failure(result)
    assert level == "L4"
    assert "reported no 'texture2d' structural check" in error


def test_a_structure_check_godot_could_not_answer_fails_l4(tmp_path):
    probe = StubProbe(structure={"texture2d": {"error": "resource is a Theme, not a Texture2D"}})
    result, _ = _run(tmp_path, probe=probe)
    level, error = _failure(result)
    assert level == "L4"
    assert "could not be performed" in error
    assert "resource is a Theme" in error


@pytest.mark.parametrize(
    "structure",
    [
        {},
        {"texture2d": {"error": "unknown structural check: texture2d"}},
        {"texture2d": "not even an object"},
    ],
)
def test_a_validator_that_ignores_the_probe_cannot_pass_an_unanswered_check(
    tmp_path, structure
):
    """The bypass this guard exists for: L4 must fail on the probe's answer alone.

    A validator is free to return ``{}`` without reading anything. If the level
    depended on it noticing, every family would get one chance to forget, and the
    ladder would report ``ready`` beside an L3 detail saying the check was
    impossible.
    """
    structures = StructureValidatorRegistry()
    structures.register(
        artifact_type="Texture2D",
        validator_id="ignores_the_probe",
        validator=lambda request: {},
        checks=("texture2d",),
    )
    result, _ = _run(tmp_path, probe=StubProbe(structure=structure), structures=structures)

    assert result.ready is False
    assert result.processing_status == STATUS_FAILED
    level, error = _failure(result)
    assert level == "L4"
    assert "texture2d" in error


def test_a_validator_declaring_no_checks_still_runs(tmp_path):
    """The guard covers declared checks only; a validator may need none."""
    structures = StructureValidatorRegistry()
    structures.register(
        artifact_type="Texture2D",
        validator_id="needs_nothing",
        validator=lambda request: {"checked": "nothing"},
    )
    result, _ = _run(tmp_path, probe=StubProbe(structure={}), structures=structures)

    assert result.ready is True
    assert result.levels[4].details["checked"] == "nothing"


def test_l4_reports_the_dimensions_it_checked(tmp_path):
    result, _ = _run(tmp_path)
    assert result.levels[4].details == {
        "width": 4,
        "height": 3,
        "validator_id": "texture2d_structure",
    }


def test_a_validator_that_raises_an_unexpected_error_fails_l4(tmp_path):
    structures = StructureValidatorRegistry()

    def explode(request):
        raise RuntimeError("boom")

    structures.register(
        artifact_type="Texture2D", validator_id="exploding", validator=explode
    )
    result, _ = _run(tmp_path, structures=structures)
    level, error = _failure(result)
    assert level == "L4"
    assert "exploding failed: boom" in error


def test_a_validator_that_returns_a_non_mapping_fails_l4(tmp_path):
    structures = StructureValidatorRegistry()
    structures.register(
        artifact_type="Texture2D", validator_id="chatty", validator=lambda request: "fine"
    )
    result, _ = _run(tmp_path, structures=structures)
    level, error = _failure(result)
    assert level == "L4"
    assert "must return a mapping" in error


def test_the_validator_receives_the_entry_identity_and_the_probe_result(tmp_path):
    seen = {}
    structures = StructureValidatorRegistry()

    def capture(request: StructureRequest):
        seen["request"] = request
        return {}

    structures.register(
        artifact_type="Texture2D", validator_id="capturing", validator=capture
    )
    result, root = _run(tmp_path, structures=structures)
    assert result.ready is True
    request = seen["request"]
    assert request.production_family == "ui-kit"
    assert request.asset_id == "panel"
    assert request.source_layout_type == "single"
    assert request.artifact_path == SOURCE
    assert request.project_root == root
    assert request.probe.godot_class == "Texture2D"


# ------------------------------------------------- structure validator registry


def test_a_validator_for_a_type_no_layout_compiles_to_is_rejected():
    structures = StructureValidatorRegistry()
    with pytest.raises(ValidationError, match="no source layout compiles to PackedScene"):
        structures.register(
            artifact_type="PackedScene", validator_id="scenes", validator=lambda r: {}
        )


def test_a_second_validator_for_one_type_is_rejected():
    structures = build_default_structures()
    with pytest.raises(ValidationError, match="already validated by texture2d_structure"):
        structures.register(
            artifact_type="Texture2D", validator_id="second", validator=lambda r: {}
        )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"artifact_type": "", "validator_id": "v"}, "artifact_type must be"),
        ({"artifact_type": "Texture2D", "validator_id": "  "}, "validator_id must be"),
    ],
)
def test_blank_registration_fields_are_rejected(kwargs, message):
    structures = StructureValidatorRegistry()
    with pytest.raises(ValidationError, match=message):
        structures.register(validator=lambda r: {}, **kwargs)


def test_a_non_callable_validator_is_rejected():
    structures = StructureValidatorRegistry()
    with pytest.raises(ValidationError, match="must be callable"):
        structures.register(
            artifact_type="Theme", validator_id="theme", validator="not callable"
        )


@pytest.mark.parametrize("checks", [["texture2d"], ("",), ("texture2d", 3)])
def test_malformed_checks_are_rejected(checks):
    structures = StructureValidatorRegistry()
    with pytest.raises(ValidationError, match="checks must be a tuple"):
        structures.register(
            artifact_type="Theme",
            validator_id="theme",
            validator=lambda r: {},
            checks=checks,
        )


def test_a_check_the_probe_script_does_not_implement_is_rejected_at_registration():
    structures = StructureValidatorRegistry()
    with pytest.raises(ValidationError, match="probe.gd implements no structural check"):
        structures.register(
            artifact_type="StyleBoxTexture",
            validator_id="nine_slice",
            validator=lambda r: {},
            checks=("unknown_structure",),
        )


def test_every_implemented_check_may_be_registered():
    for check in PROBE_CHECKS:
        structures = StructureValidatorRegistry()
        route = structures.register(
            artifact_type="Theme",
            validator_id="theme",
            validator=lambda r: {},
            checks=(check,),
        )
        assert route.checks == (check,)


def test_an_unregistered_type_asks_for_no_probe_checks():
    assert build_default_structures().checks_for("TileSet") == ()
    assert build_default_structures().checks_for("SpriteFrames") == ("spriteframes",)
    assert build_default_structures().checks_for("Texture2D") == ("texture2d",)


def test_routes_are_ordered_by_artifact_type():
    structures = build_default_structures()
    structures.register(
        artifact_type="AtlasTexture", validator_id="atlas", validator=lambda r: {}
    )
    assert [route.artifact_type for route in structures.routes()] == [
        "AtlasTexture",
        "SpriteFrames",
        "Texture2D",
    ]


def test_each_build_returns_an_independent_structure_registry():
    first = build_default_structures()
    first.register(artifact_type="Theme", validator_id="theme", validator=lambda r: {})
    assert [route.artifact_type for route in build_default_structures().routes()] == [
        "SpriteFrames",
        "Texture2D"
    ]


# ------------------------------------------------------------ result vocabulary


def test_a_failed_level_must_carry_an_error():
    with pytest.raises(ValidationError, match="failed without an error message"):
        LevelResult(level="L1", name="processed_source", status=FAILED)


def test_a_passing_level_may_not_carry_an_error():
    with pytest.raises(ValidationError, match="did not fail"):
        LevelResult(level="L1", name="processed_source", status=PASSED, error="hmm")


def test_an_unknown_level_status_is_rejected():
    with pytest.raises(ValidationError, match="unknown level status"):
        LevelResult(level="L1", name="processed_source", status="maybe")


def test_a_verdict_must_report_every_level_in_order():
    with pytest.raises(ValidationError, match="every level in order"):
        LadderResult(
            asset_id="panel",
            production_family="ui-kit",
            levels=(LevelResult(level="L0", name="contract", status=PASSED),),
        )


def test_ready_requires_every_level_to_pass():
    levels = tuple(
        LevelResult(level=spec.level, name=spec.name, status=PASSED) for spec in LEVELS
    )
    assert LadderResult(asset_id="a", production_family="ui-kit", levels=levels).ready
    degraded = levels[:4] + (
        LevelResult(level="L4", name="structure", status=NOT_RUN),
    )
    verdict = LadderResult(asset_id="a", production_family="ui-kit", levels=degraded)
    assert verdict.ready is False
    assert verdict.processing_status == STATUS_FAILED
    assert verdict.failure is None


# ------------------------------------------------------------------ construction


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"registry": object()}, "registry must be a CompilerRegistry"),
        ({"structures": object()}, "structures must be a StructureValidatorRegistry"),
        ({"probe": object()}, "probe must be a GodotProbe"),
    ],
)
def test_a_misconfigured_ladder_is_rejected_at_construction(kwargs, message):
    arguments = {
        "registry": build_default_registry(),
        "structures": build_default_structures(),
        "probe": StubProbe(),
    }
    arguments.update(kwargs)
    with pytest.raises(ValidationError, match=message):
        ValidationLadder(**arguments)


def test_build_default_ladder_wires_the_shared_compiler_and_validator():
    ladder = build_default_ladder("godot")
    assert isinstance(ladder, ValidationLadder)
    structures = build_default_structures()
    assert [route.validator_id for route in structures.routes()] == [
        "spriteframes_structure",
        "texture2d_structure",
    ]


def test_build_default_ladder_accepts_family_registries():
    registry = _stylebox_registry()
    structures = build_default_structures()
    ladder = build_default_ladder("godot", registry=registry, structures=structures)
    assert isinstance(ladder, ValidationLadder)


def _structure_request(structure):
    return StructureRequest(
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path=SOURCE,
        artifact_type="Texture2D",
        artifact_path=SOURCE,
        project_root=Path("."),
        probe=ProbeResult(
            res_path=SOURCE,
            expected_type="Texture2D",
            loaded=True,
            godot_class="CompressedTexture2D",
            type_matches=True,
            structure=structure,
        ),
    )


@pytest.mark.parametrize(
    "structure, message",
    [
        ({}, "reported no 'texture2d' structural check"),
        ({"texture2d": None}, "reported no 'texture2d' structural check"),
        ({"texture2d": "words"}, "reported no 'texture2d' structural check"),
        ({"texture2d": {"error": "boom"}}, "could not be performed"),
    ],
)
def test_reading_an_unanswered_check_fails_closed_outside_the_registry(structure, message):
    # A validator used directly gets the same guarantee the registry enforces,
    # rather than an attribute error on a missing answer.
    with pytest.raises(ValidationError, match=message):
        _structure_request(structure).checked_structure("texture2d")


def test_reading_an_answered_check_returns_its_facts():
    request = _structure_request({"texture2d": {"width": 2, "height": 2}})
    assert request.checked_structure("texture2d") == {"width": 2, "height": 2}


def test_the_texture_validator_is_usable_on_its_own():
    request = StructureRequest(
        production_family="ui-kit",
        asset_id="panel",
        source_layout_type="single",
        source_path=SOURCE,
        artifact_type="Texture2D",
        artifact_path=SOURCE,
        project_root=Path("."),
        probe=ProbeResult(
            res_path=SOURCE,
            expected_type="Texture2D",
            loaded=True,
            godot_class="CompressedTexture2D",
            type_matches=True,
            structure={"texture2d": {"width": 32, "height": 16}},
        ),
    )
    assert validate_texture2d(request) == {"width": 32, "height": 16}


# ------------------------------------------------------------------ Godot probe


def test_a_blank_godot_path_is_rejected():
    with pytest.raises(GodotProbeError, match="non-empty string"):
        GodotProbe("   ")


def test_probing_nothing_is_rejected(tmp_path):
    with pytest.raises(GodotProbeError, match="at least one resource request"):
        GodotProbe("godot").probe(tmp_path, [])


def test_probing_a_directory_that_is_not_a_godot_project_is_rejected(tmp_path):
    with pytest.raises(GodotProbeError, match="no project.godot"):
        GodotProbe("godot").probe(
            tmp_path, [ProbeRequest(res_path=SOURCE, expected_type="Texture2D")]
        )


def test_a_missing_godot_binary_is_a_probe_error(tmp_path):
    root = _project(tmp_path)
    probe = GodotProbe(str(tmp_path / "definitely-not-godot"))
    with pytest.raises(GodotProbeError, match="not found|could not be run"):
        probe.probe(root, [ProbeRequest(res_path=SOURCE, expected_type="Texture2D")])


@pytest.mark.parametrize(
    "report, message",
    [
        (["not", "an", "object"], "not a JSON object"),
        ({"resources": "nope"}, "reported 0 resources for 1 requests"),
        ({"resources": []}, "reported 0 resources for 1 requests"),
        ({"resources": ["nope"]}, "must be an object"),
        ({"resources": [{"path": "res://other.tres"}]}, "answered for"),
    ],
)
def test_a_malformed_probe_report_is_rejected(report, message):
    with pytest.raises(GodotProbeError, match=message):
        GodotProbe._parse(
            report, [ProbeRequest(res_path=SOURCE, expected_type="Texture2D")]
        )


def test_a_probe_report_row_is_read_conservatively():
    report = GodotProbe._parse(
        {"resources": [{"path": SOURCE, "loaded": "yes", "type_matches": 1, "structure": []}]},
        [ProbeRequest(res_path=SOURCE, expected_type="Texture2D")],
    )
    (result,) = report.resources
    assert report.godot_version == ""
    # Only a literal JSON ``true`` counts; a truthy string must not pass L3.
    assert result.loaded is False
    assert result.type_matches is False
    assert result.structure == {}
    assert result.godot_class == ""


def test_find_godot_prefers_an_explicit_binary(tmp_path):
    binary = tmp_path / "godot-here"
    binary.write_text("", encoding="utf-8")
    assert find_godot(str(binary)) == str(binary)
    assert find_godot(str(tmp_path / "absent")) is None
