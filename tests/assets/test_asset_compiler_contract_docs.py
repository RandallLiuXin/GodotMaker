"""Bind the compiler contract doc to the code it describes.

The routing table in `godot-artifact-compiler-contract.md` is a human-readable
mirror of the frozen `LAYOUT_ARTIFACT_TYPES` relation. The registry tests walk
that relation dynamically, so they stay green when it is extended — only these
assertions catch the doc going stale.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
CONTRACT_DOC = SHARED_DIR / "godot-artifact-compiler-contract.md"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import SOURCE_IS_ARTIFACT_TYPES  # noqa: E402
from asset_stable_entry import LAYOUT_ARTIFACT_TYPES  # noqa: E402

_ROW = re.compile(r"^\|\s*`(?P<layout>[a-z_]+)`\s*\|(?P<types>[^|]+)\|\s*$")


def _documented_relation() -> dict[str, tuple[str, ...]]:
    relation: dict[str, tuple[str, ...]] = {}
    for line in CONTRACT_DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        relation[match.group("layout")] = tuple(
            cell.strip().strip("`") for cell in match.group("types").split(",")
        )
    return relation


def test_documented_routing_table_matches_the_frozen_relation():
    assert _documented_relation() == LAYOUT_ARTIFACT_TYPES


def test_doc_states_the_rules_the_registry_enforces():
    doc = CONTRACT_DOC.read_text(encoding="utf-8")
    for claim in (
        "LAYOUT_ARTIFACT_TYPES",
        "SOURCE_IS_ARTIFACT_TYPES",
        "writes_artifact=False",
        "build_default_registry()",
        "CompilerError",
    ):
        assert claim in doc, f"the contract doc no longer mentions {claim}"
    # The doc must not promise a module-level registry the package removed.
    assert "DEFAULT_REGISTRY" not in doc


def test_doc_names_every_type_allowed_to_skip_writing():
    doc = CONTRACT_DOC.read_text(encoding="utf-8")
    for artifact_type in SOURCE_IS_ARTIFACT_TYPES:
        assert f"`{artifact_type}`" in doc


def test_shared_has_no_skill_md():
    # _shared holds cross-skill material and is not independently triggerable.
    assert not (SHARED_DIR / "SKILL.md").exists()
