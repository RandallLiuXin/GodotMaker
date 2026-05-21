"""Tests for Playable Unit evaluation contract validation."""
import json
import os

from hooks.playability_contract import (
    check_evaluation_playable_unit_complete,
    normalize_row_key,
    parse_playable_unit_rows,
)


PLAN = """# Game Plan

**Tag:** v0.1.0

## Playable Unit

- **Player experience:** start a run and reach the exit
- **Unit outcome:** exit reached through normal play
- **Scenes involved:** Main, Gameplay, Results

| Mechanic | Player operation / content | Expected effect | Required visible content | Evidence |
|----------|----------------------------|-----------------|--------------------------|----------|
| [v0.1.0-M1] | Press Start | Gameplay scene opens | Player and HUD visible | e2e assertion + screenshot |
| [v0.1.0-M2] | Move to exit | Run ends | Results screen visible | e2e assertion + screenshot |

## Main Build
"""


def write_json(path: str, payload: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def write_plan():
    with open("PLAN.md", "w", encoding="utf-8") as f:
        f.write(PLAN)


def write_e2e_tests():
    os.makedirs("e2e", exist_ok=True)
    for filename in [
        "test_v0_1_0_playable_unit_start.py",
        "test_v0_1_0_playable_unit_exit.py",
    ]:
        with open(os.path.join("e2e", filename), "w", encoding="utf-8") as f:
            f.write("def test_placeholder():\n    assert True\n")


def valid_evaluation(result: str = "approve") -> dict:
    return {
        "tag": "v0.1.0",
        "result": result,
        "playable_closed_loop": {
            "builds_clean": True,
            "boots_main_scene": True,
            "playable_unit_coverage": True,
            "completion_fail_or_exit_reached": True,
        },
        "playable_unit": {
            "result": "pass",
            "rows": {
                "v0.1.0-M1": {
                    "result": "pass",
                    "test": "e2e/test_v0_1_0_playable_unit_start.py",
                    "evidence": ["e2e/screenshots/start.png"],
                },
                "v0.1.0-M2": {
                    "result": "pass",
                    "test": "e2e/test_v0_1_0_playable_unit_exit.py",
                    "evidence": ["e2e/screenshots/results.png"],
                },
            },
        },
        "critical_issues": [],
    }


def test_parse_playable_unit_rows_from_plan():
    rows = parse_playable_unit_rows(PLAN)

    assert [row.key for row in rows] == ["v0.1.0-M1", "v0.1.0-M2"]
    assert rows[0].expected_effect == "Gameplay scene opens"
    assert rows[1].visible_content == "Results screen visible"


def test_normalize_row_key_strips_markdown_id():
    assert normalize_row_key("[v0.1.0-M1]") == "v0.1.0-M1"
    assert normalize_row_key("v0.1.0-M1") == "v0.1.0-M1"
    assert normalize_row_key("row-name") == ""


def test_invalid_mechanic_id_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_e2e_tests()
    with open("PLAN.md", "w", encoding="utf-8") as f:
        f.write(PLAN.replace("[v0.1.0-M1]", "Start row").replace("[v0.1.0-M2]", "Exit row"))
    write_json(".godotmaker/evaluation.json", valid_evaluation())

    issues = check_evaluation_playable_unit_complete()

    assert any("must use a mechanic id" in issue for issue in issues)


def test_valid_approve_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    write_json(".godotmaker/evaluation.json", valid_evaluation())

    assert check_evaluation_playable_unit_complete() == []


def test_missing_row_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    evaluation = valid_evaluation()
    del evaluation["playable_unit"]["rows"]["v0.1.0-M2"]
    write_json(".godotmaker/evaluation.json", evaluation)

    issues = check_evaluation_playable_unit_complete()

    assert any("v0.1.0-M2 missing" in issue for issue in issues)


def test_approve_with_failed_row_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    evaluation = valid_evaluation()
    evaluation["playable_unit"]["rows"]["v0.1.0-M1"]["result"] = "fail"
    write_json(".godotmaker/evaluation.json", evaluation)

    issues = check_evaluation_playable_unit_complete()

    assert any("approve requires Playable Unit row v0.1.0-M1 to pass" in issue for issue in issues)


def test_missing_test_file_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    evaluation = valid_evaluation()
    evaluation["playable_unit"]["rows"]["v0.1.0-M1"]["test"] = "e2e/missing.py"
    write_json(".godotmaker/evaluation.json", evaluation)

    issues = check_evaluation_playable_unit_complete()

    assert any("test file not found: e2e/missing.py" in issue for issue in issues)


def test_empty_evidence_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    evaluation = valid_evaluation()
    evaluation["playable_unit"]["rows"]["v0.1.0-M1"]["evidence"] = []
    write_json(".godotmaker/evaluation.json", evaluation)

    issues = check_evaluation_playable_unit_complete()

    assert any("must record non-empty evidence" in issue for issue in issues)


def test_reject_with_failed_row_passes_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    evaluation = valid_evaluation(result="reject")
    evaluation["playable_closed_loop"]["playable_unit_coverage"] = False
    evaluation["playable_unit"]["result"] = "fail"
    evaluation["playable_unit"]["rows"]["v0.1.0-M2"]["result"] = "fail"
    write_json(".godotmaker/evaluation.json", evaluation)

    assert check_evaluation_playable_unit_complete() == []


def test_empty_reject_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_plan()
    write_e2e_tests()
    evaluation = valid_evaluation(result="reject")
    evaluation["playable_unit"]["result"] = "fail"
    write_json(".godotmaker/evaluation.json", evaluation)

    issues = check_evaluation_playable_unit_complete()

    assert any("reject requires at least one failed Playable Unit row" in issue for issue in issues)
