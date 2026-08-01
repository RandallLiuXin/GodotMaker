"""Tests for the controlled scene-prop-set validation command."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import asset_scene_prop_set_validate as validator  # noqa: E402


def test_validation_command_persists_the_exact_validator_result(monkeypatch, tmp_path):
    request_path = tmp_path / "ASSET_REQUEST.json"
    result_path = tmp_path / ".godotmaker" / "asset-generation" / "market-result.json"
    report_path = tmp_path / ".godotmaker" / "asset-generation" / "reports" / "market_validation.json"
    request = {"asset_type": "scene-prop-set", "asset_id": "market", "spec": {}}
    result = {"asset_type": "scene-prop-set", "validation": {"passed": False}}
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.parent.mkdir(parents=True)
    result_path.write_text(json.dumps(result), encoding="utf-8")
    expected = {
        "asset_type": "scene-prop-set",
        "outputs": [],
        "sources": [],
        "previews": [],
        "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}},
    }
    calls = []

    def fake_compile(actual_request, actual_result, *, project_root, godot_path):
        calls.append((actual_request, actual_result, project_root, godot_path))
        return expected

    monkeypatch.setattr(validator, "_validator", lambda: fake_compile)

    actual = validator.validate_scene_prop_set(
        request_path,
        result_path,
        report_path,
        project_root=tmp_path,
        godot_path="D:/Godot/Godot.exe",
    )

    assert actual == expected
    assert json.loads(result_path.read_text(encoding="utf-8")) == expected
    assert json.loads(report_path.read_text(encoding="utf-8")) == expected
    assert calls == [(request, result, tmp_path, "D:/Godot/Godot.exe")]


@pytest.mark.parametrize(
    ("request_data", "result_data", "message"),
    [
        ({"asset_type": "compact-prop-pack"}, {"asset_type": "scene-prop-set"}, "request.asset_type"),
        ({"asset_type": "scene-prop-set"}, {"asset_type": "compact-prop-pack"}, "result.asset_type"),
    ],
)
def test_validation_command_rejects_a_non_scene_prop_handoff(
    tmp_path, request_data, result_data, message
):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request_data), encoding="utf-8")
    result_path.write_text(json.dumps(result_data), encoding="utf-8")

    with pytest.raises(validator.ScenePropSetValidationError, match=message):
        validator.validate_scene_prop_set(
            request_path,
            result_path,
            tmp_path / "report.json",
            project_root=tmp_path,
            godot_path="fake",
        )


def test_validation_command_resolves_the_project_godot_path_not_private_eval_environment(
    monkeypatch, tmp_path
):
    request_path = tmp_path / "ASSET_REQUEST.json"
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    request_path.write_text(json.dumps({"asset_type": "scene-prop-set"}), encoding="utf-8")
    result_path.write_text(json.dumps({"asset_type": "scene-prop-set"}), encoding="utf-8")
    calls = []

    def fake_validate(request, result, report, *, project_root, godot_path):
        calls.append((request, result, report, project_root, godot_path))
        return {"validation": {"passed": True}}

    monkeypatch.setattr(validator, "validate_scene_prop_set", fake_validate)
    monkeypatch.setattr(validator, "read_godot_path", lambda root: "project-configured-godot")
    monkeypatch.setenv("GM_EVAL_GODOT_PATH", "private-eval-godot")
    monkeypatch.setenv("GODOT_BIN", "legacy-environment-godot")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "asset_scene_prop_set_validate.py",
            "--request", str(request_path),
            "--result", str(result_path),
            "--report", str(report_path),
            "--project-root", str(tmp_path),
        ],
    )

    assert validator._main() == 0
    assert calls == [
        (request_path, result_path, report_path, tmp_path.resolve(), "project-configured-godot")
    ]
