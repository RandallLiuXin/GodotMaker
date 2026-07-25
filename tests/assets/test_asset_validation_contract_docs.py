"""Bind the readiness-ladder doc, the Python levels, and the GDScript probe.

The doc's ladder table is a human-readable mirror of ``LEVELS``, and the probe's
``KNOWN_CHECKS`` must cover every check a registered structure validator asks
for. Nothing else notices when one of the three drifts.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
CONTRACT_DOC = SHARED_DIR / "asset-validation-ladder.md"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_validation import (  # noqa: E402
    LEVELS,
    PROBE_SCRIPT,
    build_default_structures,
)

_ROW = re.compile(
    r"^\|\s*`(?P<level>L\d)`\s*\|\s*`(?P<name>\w+)`\s*\|"
    r"(?P<consumes>[^|]+)\|(?P<proves>[^|]+)\|\s*$"
)
_KNOWN_CHECKS = re.compile(r"^const KNOWN_CHECKS := \[(?P<items>[^\]]*)\]", re.MULTILINE)


def _documented_levels():
    rows = []
    for line in CONTRACT_DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is not None:
            rows.append(
                (
                    match.group("level"),
                    match.group("name"),
                    match.group("consumes").strip(),
                    match.group("proves").strip(),
                )
            )
    return rows


def _probe_known_checks() -> tuple[str, ...]:
    text = PROBE_SCRIPT.read_text(encoding="utf-8")
    match = _KNOWN_CHECKS.search(text)
    assert match is not None, "probe.gd no longer declares KNOWN_CHECKS"
    return tuple(
        item.strip().strip('"') for item in match.group("items").split(",") if item.strip()
    )


def test_the_documented_ladder_matches_the_implemented_levels():
    assert _documented_levels() == [
        (spec.level, spec.name, spec.consumes, spec.proves) for spec in LEVELS
    ]


def test_the_doc_states_the_rules_the_ladder_enforces():
    doc = CONTRACT_DOC.read_text(encoding="utf-8")
    for claim in (
        "ResourceLoader.load",
        "--import",
        "is_class",
        "not_run",
        "source_ready",
        "ValidationError",
        "GodotProbeError",
        "StructureValidatorRegistry",
        "build_default_structures()",
        "build_default_ladder()",
        "KNOWN_CHECKS",
    ):
        assert claim in doc, f"the contract doc no longer mentions {claim}"


def test_the_doc_does_not_promise_the_private_evaluation_layers():
    doc = CONTRACT_DOC.read_text(encoding="utf-8")
    # L5 and L6 are named only to place them outside this layer.
    assert "not runtime readiness gates" in doc
    assert "GodotMakerApp" in doc


def test_every_registered_structure_check_is_implemented_by_the_probe():
    known = _probe_known_checks()
    for route in build_default_structures().routes():
        for check in route.checks:
            assert check in known, (
                f"{route.validator_id} asks for the {check!r} structural check, "
                "which probe.gd does not implement"
            )


def test_the_probe_script_runs_as_a_headless_scene_tree():
    text = PROBE_SCRIPT.read_text(encoding="utf-8")
    assert "extends SceneTree" in text
    assert "func _initialize()" in text
    # The verdict travels through the report file, never the console.
    assert "FileAccess.open(report_path, FileAccess.WRITE)" in text


def test_shared_has_no_skill_md():
    # _shared holds cross-skill material and is not independently triggerable.
    assert not (SHARED_DIR / "SKILL.md").exists()
