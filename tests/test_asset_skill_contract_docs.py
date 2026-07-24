"""Structural and parity checks for the standalone asset-skill contract.

The declarative JSON Schema under `skills/assets/_shared/schema/` is the
canonical contract. `tools/asset_skill_contract_check.py` is a dependency-free
implementation of the same rules. These tests assert the two agree and that the
`_shared/` contract material is shaped correctly.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
SCHEMA_DIR = SHARED_DIR / "schema"
SAMPLES_DIR = SHARED_DIR / "samples"
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_skill_contract_check import (  # noqa: E402
    ASSET_TYPES,
    OUTPUT_ROLES,
    PROVIDERS,
    REFERENCE_ROLES,
    SOURCE_LAYOUTS,
    VALIDATION_LEVELS,
)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_shared_has_no_skill_md():
    # _shared holds cross-skill contract material and is not triggerable.
    assert not (SHARED_DIR / "SKILL.md").exists()


def test_contract_doc_documents_the_result_keys():
    doc = (SHARED_DIR / "asset-skill-contract.md").read_text(encoding="utf-8")
    for key in ("asset_type", "outputs", "sources", "previews", "validation"):
        assert key in doc
    for field in ("role", "path", "godot_type"):
        assert field in doc
    assert "There is no separate \"gm mode\"" in doc
    assert "additionalProperties" in doc
    # Independence: the doc names the pipeline state a skill must not read.
    for forbidden in ("ASSETS.md", "manifest", "tag", "stage state"):
        assert forbidden in doc


def test_schema_files_are_valid_json_with_no_additional_properties():
    request_schema = _read_json(SCHEMA_DIR / "asset-skill-request.schema.json")
    result_schema = _read_json(SCHEMA_DIR / "asset-skill-result.schema.json")
    assert request_schema["additionalProperties"] is False
    assert result_schema["additionalProperties"] is False
    assert result_schema["required"] == [
        "asset_type",
        "outputs",
        "sources",
        "previews",
        "validation",
    ]
    assert result_schema["properties"]["outputs"]["minItems"] == 1


def test_schema_enums_match_validator_constants():
    request_schema = _read_json(SCHEMA_DIR / "asset-skill-request.schema.json")
    result_schema = _read_json(SCHEMA_DIR / "asset-skill-result.schema.json")
    props = request_schema["properties"]
    rprops = result_schema["properties"]

    assert set(props["asset_type"]["enum"]) == ASSET_TYPES
    assert set(rprops["asset_type"]["enum"]) == ASSET_TYPES
    assert set(props["references"]["items"]["properties"]["role"]["enum"]) == REFERENCE_ROLES
    assert set(props["provider"]["enum"]) == PROVIDERS
    assert set(rprops["outputs"]["items"]["properties"]["role"]["enum"]) == OUTPUT_ROLES
    assert set(rprops["sources"]["items"]["properties"]["layout"]["enum"]) == SOURCE_LAYOUTS
    assert set(rprops["validation"]["properties"]["levels"]["properties"]) == VALIDATION_LEVELS


def test_samples_validate_against_declarative_schema():
    jsonschema = pytest.importorskip("jsonschema")
    request_schema = _read_json(SCHEMA_DIR / "asset-skill-request.schema.json")
    result_schema = _read_json(SCHEMA_DIR / "asset-skill-result.schema.json")

    for sample in sorted((SAMPLES_DIR / "request").glob("*.json")):
        jsonschema.validate(_read_json(sample), request_schema)
    for sample in sorted((SAMPLES_DIR / "result").glob("*.json")):
        jsonschema.validate(_read_json(sample), result_schema)


def _result_base():
    return {
        "asset_type": "character-bundle",
        "outputs": [
            {
                "role": "runtime",
                "name": "player",
                "path": "res://assets/generated/character-bundle/player/player.tres",
                "godot_type": "SpriteFrames",
            }
        ],
        "sources": [{"path": "res://assets/generated/x.png", "layout": "grid_sheet"}],
        "previews": [{"path": "res://assets/generated/x.png", "label": "idle"}],
        "validation": {"passed": True},
    }


def _with(base, mutate):
    doc = json.loads(json.dumps(base))
    mutate(doc)
    return doc


# (label, doc, expected_valid). The declarative schema and the checker must
# reach the SAME verdict on every row — both directions, valid and invalid.
def _result_parity_cases():
    base = _result_base()
    ref_only = {
        "asset_type": "screen-reference",
        "outputs": [{"role": "reference", "path": "references/scene_main.png"}],
        "sources": [],
        "previews": [],
        "validation": {"passed": True, "levels": {"L0": True, "L1": True}},
    }
    return [
        ("valid-base", base, True),
        ("valid-reference-only", ref_only, True),
        (
            "valid-all-levels-true",
            _with(base, lambda d: d["validation"].update(
                levels={"L0": True, "L1": True, "L2": True, "L3": True, "L4": True}
            )),
            True,
        ),
        (
            "valid-levels-subset-true",
            _with(base, lambda d: d["validation"].update(levels={"L0": True})),
            True,
        ),
        (
            "valid-passed-false-level-false",
            _with(base, lambda d: d.update(
                validation={"passed": False, "levels": {"L0": False}}
            )),
            True,
        ),
        (
            "valid-multi-runtime",
            _with(base, lambda d: d["outputs"].append(
                {"role": "runtime", "path": "res://a/b.tres", "godot_type": "Texture2D"}
            )),
            True,
        ),
        # --- invalid: the two P1 drift/weakness cases the reviewer flagged ---
        (
            "passed-true-level-false",
            _with(base, lambda d: d.update(
                validation={"passed": True, "levels": {"L0": False}}
            )),
            False,
        ),
        ("bare-res", _with(base, lambda d: d["outputs"][0].update(path="res://")), False),
        ("triple-slash-res", _with(base, lambda d: d["outputs"][0].update(path="res:///")), False),
        # --- invalid: whitespace-only strings ---
        ("whitespace-output-path", _with(base, lambda d: d["outputs"][0].update(path="  ")), False),
        ("whitespace-output-name", _with(base, lambda d: d["outputs"][0].update(name="  ")), False),
        ("whitespace-source-path", _with(base, lambda d: d["sources"][0].update(path="  ")), False),
        ("whitespace-preview-label", _with(base, lambda d: d["previews"][0].update(label="  ")), False),
        # --- invalid: explicit null on optional fields ---
        ("null-output-name", _with(base, lambda d: d["outputs"][0].update(name=None)), False),
        (
            "null-reference-godot_type",
            _with(base, lambda d: d["outputs"].__setitem__(
                0, {"role": "reference", "path": "references/x.png", "godot_type": None}
            )),
            False,
        ),
        ("null-source-layout", _with(base, lambda d: d["sources"][0].update(layout=None)), False),
        ("null-preview-label", _with(base, lambda d: d["previews"][0].update(label=None)), False),
        ("null-levels", _with(base, lambda d: d.update(validation={"passed": True, "levels": None})), False),
        ("null-notes", _with(base, lambda d: d.update(validation={"passed": True, "notes": None})), False),
        # --- invalid: dot / traversal path segments ---
        ("path-dot", _with(base, lambda d: d["outputs"][0].update(path="res://.")), False),
        ("path-dotdot", _with(base, lambda d: d["outputs"][0].update(path="res://..")), False),
        ("path-traversal", _with(base, lambda d: d["outputs"][0].update(path="res://../outside.tres")), False),
        ("path-mid-traversal", _with(base, lambda d: d["outputs"][0].update(path="res://a/../b.tres")), False),
        # --- valid: legitimate dotted names ---
        ("valid-dotted-filename", _with(base, lambda d: d["outputs"][0].update(path="res://a/b.name.tres")), True),
        ("valid-hidden-dir", _with(base, lambda d: d["outputs"][0].update(path="res://.hidden/x.tres")), True),
        # --- invalid: structural / enum / forbidden ---
        ("empty-outputs", _with(base, lambda d: d.update(outputs=[])), False),
        ("non-res-runtime", _with(base, lambda d: d["outputs"][0].update(path="assets/x.tres")), False),
        ("missing-godot_type", _with(base, lambda d: d["outputs"][0].pop("godot_type")), False),
        ("bad-godot_type", _with(base, lambda d: d["outputs"][0].update(godot_type="spriteFrames")), False),
        ("bad-role", _with(base, lambda d: d["outputs"][0].update(role="preview")), False),
        ("bad-source-layout", _with(base, lambda d: d["sources"][0].update(layout="mosaic")), False),
        # --- invalid: non-scalar values on enum fields (must not crash) ---
        ("role-list", _with(base, lambda d: d["outputs"][0].update(role=[])), False),
        ("role-dict", _with(base, lambda d: d["outputs"][0].update(role={})), False),
        ("layout-list", _with(base, lambda d: d["sources"][0].update(layout=[])), False),
        ("layout-dict", _with(base, lambda d: d["sources"][0].update(layout={})), False),
        ("unknown-output-key", _with(base, lambda d: d["outputs"][0].update(z=1)), False),
        ("unknown-top-key", _with(base, lambda d: d.update(extra=1)), False),
        ("forbidden-tag", _with(base, lambda d: d.update(tag="v0.1.0")), False),
        ("forbidden-runtime_artifact", _with(base, lambda d: d.update(runtime_artifact="single")), False),
        ("unknown-asset_type", _with(base, lambda d: d.update(asset_type="sprite")), False),
    ]


@pytest.mark.parametrize(
    "doc,expected", [(c[1], c[2]) for c in _result_parity_cases()],
    ids=[c[0] for c in _result_parity_cases()],
)
def test_result_schema_and_checker_agree(doc, expected):
    jsonschema = pytest.importorskip("jsonschema")
    from asset_skill_contract_check import AssetContractError, check_result

    result_schema = _read_json(SCHEMA_DIR / "asset-skill-result.schema.json")
    schema_valid = jsonschema.Draft202012Validator(result_schema).is_valid(doc)

    try:
        check_result(doc)
        checker_valid = True
    except AssetContractError:
        checker_valid = False

    assert schema_valid == expected, f"schema verdict {schema_valid} != expected {expected}"
    assert checker_valid == expected, f"checker verdict {checker_valid} != expected {expected}"


def _request_parity_cases():
    base = {
        "asset_type": "character-bundle",
        "asset_id": "player",
        "brief": "A knight.",
        "references": [{"role": "canonical", "path": "res://references/p.png"}],
    }
    return [
        ("valid-base", base, True),
        ("whitespace-brief", _with(base, lambda d: d.update(brief="   ")), False),
        (
            "whitespace-reference-path",
            _with(base, lambda d: d.update(references=[{"role": "style", "path": "  "}])),
            False,
        ),
        ("forbidden-tag", _with(base, lambda d: d.update(tag="v0.1.0")), False),
        ("unknown-asset_type", _with(base, lambda d: d.update(asset_type="sprite")), False),
        ("null-references", _with(base, lambda d: d.update(references=None)), False),
        ("null-provider", _with(base, lambda d: d.update(provider=None)), False),
        ("null-spec", _with(base, lambda d: d.update(spec=None)), False),
        ("provider-list", _with(base, lambda d: d.update(provider=[])), False),
        ("provider-dict", _with(base, lambda d: d.update(provider={})), False),
        (
            "reference-role-list",
            _with(base, lambda d: d.update(references=[{"role": [], "path": "x"}])),
            False,
        ),
    ]


@pytest.mark.parametrize(
    "doc,expected", [(c[1], c[2]) for c in _request_parity_cases()],
    ids=[c[0] for c in _request_parity_cases()],
)
def test_request_schema_and_checker_agree(doc, expected):
    jsonschema = pytest.importorskip("jsonschema")
    from asset_skill_contract_check import AssetContractError, check_request

    request_schema = _read_json(SCHEMA_DIR / "asset-skill-request.schema.json")
    schema_valid = jsonschema.Draft202012Validator(request_schema).is_valid(doc)

    try:
        check_request(doc)
        checker_valid = True
    except AssetContractError:
        checker_valid = False

    assert schema_valid == expected
    assert checker_valid == expected
