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


def test_declarative_schema_rejects_representative_invalids():
    jsonschema = pytest.importorskip("jsonschema")
    result_schema = _read_json(SCHEMA_DIR / "asset-skill-result.schema.json")

    base = _read_json(SAMPLES_DIR / "result" / "character-bundle.json")

    invalids = [
        {**base, "outputs": []},
        {**base, "extra": 1},
        {**base, "runtime_artifact": "single"},
        {
            **base,
            "outputs": [
                {"role": "runtime", "path": "assets/x.tres", "godot_type": "Texture2D"}
            ],
        },
        {**base, "outputs": [{"role": "runtime", "path": "res://x.tres"}]},
    ]
    for invalid in invalids:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, result_schema)
