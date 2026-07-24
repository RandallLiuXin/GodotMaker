import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
SAMPLES_DIR = REPO_ROOT / "skills" / "assets" / "_shared" / "samples"
sys.path.insert(0, str(TOOLS_DIR))

from asset_skill_contract_check import (  # noqa: E402
    AssetContractError,
    check_document,
    check_request,
    check_result,
)


def valid_request():
    return {
        "asset_type": "character-bundle",
        "asset_id": "player",
        "brief": "A small pixel-art knight with idle and run actions.",
        "references": [
            {"role": "canonical", "path": "res://references/player_canonical.png"}
        ],
        "provider": "native",
        "spec": {"actions": ["idle", "run"]},
    }


def valid_result():
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
        "sources": [
            {
                "path": "res://assets/generated/character-bundle/player/player.png",
                "layout": "grid_sheet",
            }
        ],
        "previews": [{"path": "res://assets/generated/character-bundle/player/p.png"}],
        "validation": {"passed": True},
    }


# ---------------------------------------------------------------------------
# On-disk sample files are all valid.


@pytest.mark.parametrize(
    "sample", sorted((SAMPLES_DIR / "request").glob("*.json")), ids=lambda p: p.name
)
def test_request_samples_are_valid(sample):
    data = json.loads(sample.read_text(encoding="utf-8"))
    result = check_request(data)
    assert result["ok"] is True
    assert result["kind"] == "request"


@pytest.mark.parametrize(
    "sample", sorted((SAMPLES_DIR / "result").glob("*.json")), ids=lambda p: p.name
)
def test_result_samples_are_valid(sample):
    data = json.loads(sample.read_text(encoding="utf-8"))
    result = check_result(data)
    assert result["ok"] is True
    assert result["kind"] == "result"


def test_samples_exist():
    assert list((SAMPLES_DIR / "request").glob("*.json"))
    assert list((SAMPLES_DIR / "result").glob("*.json"))


# ---------------------------------------------------------------------------
# Positive contract behaviors.


def test_kind_is_inferred_from_shape():
    assert check_document(valid_result())["kind"] == "result"
    assert check_document(valid_request())["kind"] == "request"


def test_multiple_runtime_outputs_are_counted():
    data = valid_result()
    data["outputs"].append(
        {
            "role": "runtime",
            "path": "res://assets/generated/character-bundle/player/shadow.tres",
            "godot_type": "Texture2D",
        }
    )
    result = check_result(data)
    assert result["output_count"] == 2
    assert result["runtime_output_count"] == 2


def test_reference_output_needs_no_godot_type_and_allows_project_path():
    data = valid_result()
    data["asset_type"] = "screen-reference"
    data["outputs"] = [{"role": "reference", "path": "references/scene_main.png"}]
    data["sources"] = []
    result = check_result(data)
    assert result["runtime_output_count"] == 0


def test_empty_sources_and_previews_are_allowed():
    data = valid_result()
    data["sources"] = []
    data["previews"] = []
    assert check_result(data)["ok"] is True


def test_validation_levels_all_true_with_passed():
    data = valid_result()
    data["validation"] = {
        "passed": True,
        "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True},
    }
    assert check_result(data)["ok"] is True


# ---------------------------------------------------------------------------
# Fail-closed: request.


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r.pop("asset_type"), id="missing-asset_type"),
        pytest.param(lambda r: r.pop("asset_id"), id="missing-asset_id"),
        pytest.param(lambda r: r.pop("brief"), id="missing-brief"),
        pytest.param(lambda r: r.update(asset_type="sprite"), id="unknown-asset_type"),
        pytest.param(lambda r: r.update(asset_id="Player"), id="asset_id-uppercase"),
        pytest.param(lambda r: r.update(asset_id="-bad"), id="asset_id-leading-dash"),
        pytest.param(lambda r: r.update(brief="   "), id="blank-brief"),
        pytest.param(lambda r: r.update(references={}), id="references-not-list"),
        pytest.param(
            lambda r: r.update(references=[{"path": "x"}]), id="reference-missing-role"
        ),
        pytest.param(
            lambda r: r.update(references=[{"role": "canonical"}]),
            id="reference-missing-path",
        ),
        pytest.param(
            lambda r: r.update(references=[{"role": "hero", "path": "x"}]),
            id="reference-bad-role",
        ),
        pytest.param(
            lambda r: r.update(references=[{"role": "canonical", "path": "x", "z": 1}]),
            id="reference-extra-key",
        ),
        pytest.param(lambda r: r.update(provider="dalle"), id="bad-provider"),
        pytest.param(lambda r: r.update(spec=[]), id="spec-not-object"),
        pytest.param(lambda r: r.update(tag="v0.1.0"), id="forbidden-tag"),
        pytest.param(lambda r: r.update(stage=1), id="forbidden-stage"),
        pytest.param(
            lambda r: r.update(manifest_entry="x"), id="forbidden-manifest_entry"
        ),
        pytest.param(lambda r: r.update(gm_mode="build"), id="forbidden-gm_mode"),
        pytest.param(lambda r: r.update(surprise=1), id="unknown-key"),
    ],
)
def test_request_fails_closed(mutate):
    data = valid_request()
    mutate(data)
    with pytest.raises(AssetContractError):
        check_request(data)


def test_request_rejects_non_dict():
    with pytest.raises(AssetContractError):
        check_request(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# Fail-closed: result.


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r.pop("asset_type"), id="missing-asset_type"),
        pytest.param(lambda r: r.pop("outputs"), id="missing-outputs"),
        pytest.param(lambda r: r.pop("sources"), id="missing-sources"),
        pytest.param(lambda r: r.pop("previews"), id="missing-previews"),
        pytest.param(lambda r: r.pop("validation"), id="missing-validation"),
        pytest.param(lambda r: r.update(asset_type="sprite"), id="unknown-asset_type"),
        pytest.param(lambda r: r.update(outputs=[]), id="empty-outputs"),
        pytest.param(lambda r: r.update(outputs={}), id="outputs-not-list"),
        pytest.param(
            lambda r: r["outputs"][0].pop("role"), id="output-missing-role"
        ),
        pytest.param(
            lambda r: r["outputs"][0].pop("path"), id="output-missing-path"
        ),
        pytest.param(
            lambda r: r["outputs"][0].pop("godot_type"),
            id="runtime-output-missing-godot_type",
        ),
        pytest.param(
            lambda r: r["outputs"][0].update(path="assets/player.tres"),
            id="runtime-output-non-res-path",
        ),
        pytest.param(
            lambda r: r["outputs"][0].update(godot_type="spriteFrames"),
            id="runtime-output-bad-godot_type",
        ),
        pytest.param(
            lambda r: r["outputs"][0].update(role="preview"), id="output-bad-role"
        ),
        pytest.param(
            lambda r: r["outputs"][0].update(godot_artifact={"type": "x"}),
            id="output-forbidden-godot_artifact",
        ),
        pytest.param(
            lambda r: r["outputs"][0].update(extra=1), id="output-unknown-key"
        ),
        pytest.param(
            lambda r: r["sources"][0].update(layout="mosaic"), id="source-bad-layout"
        ),
        pytest.param(
            lambda r: r["sources"][0].pop("path"), id="source-missing-path"
        ),
        pytest.param(
            lambda r: r["sources"][0].update(extra=1), id="source-unknown-key"
        ),
        pytest.param(
            lambda r: r["previews"][0].update(label="   "), id="preview-blank-label"
        ),
        pytest.param(
            lambda r: r.update(validation={}), id="validation-missing-passed"
        ),
        pytest.param(
            lambda r: r.update(validation={"passed": "yes"}),
            id="validation-passed-not-bool",
        ),
        pytest.param(
            lambda r: r.update(
                validation={"passed": True, "levels": {"L9": True}}
            ),
            id="validation-unknown-level",
        ),
        pytest.param(
            lambda r: r.update(
                validation={"passed": True, "levels": {"L0": "yes"}}
            ),
            id="validation-level-not-bool",
        ),
        pytest.param(
            lambda r: r.update(
                validation={"passed": True, "levels": {"L0": True, "L3": False}}
            ),
            id="passed-true-with-failed-level",
        ),
        pytest.param(
            lambda r: r.update(runtime_artifact="single"),
            id="forbidden-runtime_artifact",
        ),
        pytest.param(
            lambda r: r.update(source_layout="grid_sheet"),
            id="forbidden-source_layout",
        ),
        pytest.param(
            lambda r: r.update(manifest_entry="x"), id="forbidden-manifest_entry"
        ),
        pytest.param(lambda r: r.update(tag="v0.1.0"), id="forbidden-tag"),
        pytest.param(lambda r: r.update(mystery=1), id="unknown-key"),
    ],
)
def test_result_fails_closed(mutate):
    data = valid_result()
    mutate(data)
    with pytest.raises(AssetContractError):
        check_result(data)


def test_result_rejects_non_dict():
    with pytest.raises(AssetContractError):
        check_result("nope")


# ---------------------------------------------------------------------------
# CLI.


def _run_cli(path: Path, *args):
    return subprocess.run(
        [sys.executable, str(TOOLS_DIR / "asset_skill_contract_check.py"), str(path), *args],
        capture_output=True,
        text=True,
    )


def test_cli_accepts_valid_result(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(valid_result()), encoding="utf-8")
    proc = _run_cli(path)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["ok"] is True


def test_cli_rejects_invalid_result(tmp_path):
    data = valid_result()
    data["outputs"] = []
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    proc = _run_cli(path, "--kind", "result")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["ok"] is False


def test_valid_samples_are_independent_copies():
    # Guard against shared-reference mutation bugs in the test helpers.
    assert valid_result() is not valid_result()
    assert copy.deepcopy(valid_request()) == valid_request()
