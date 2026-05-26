"""Tests for visual-qa script and prompt contract."""
import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "core" / "visual-qa" / "scripts" / "visual_qa.py"
VQA_SKILL = REPO_ROOT / "skills" / "core" / "visual-qa" / "SKILL.md"
VQA_CRITERIA = REPO_ROOT / "skills" / "core" / "visual-qa" / "scripts" / "criteria.md"
EVALUATE_SKILL = REPO_ROOT / "skills" / "core" / "gm-evaluate" / "SKILL.md"


def _tree() -> ast.AST:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


def test_visual_qa_prompt_reads_are_utf8():
    calls = [
        node for node in ast.walk(_tree())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "read_text"
    ]

    assert calls, "visual_qa.py should read prompt templates"
    for call in calls:
        encoding = next(
            (kw.value for kw in call.keywords if kw.arg == "encoding"),
            None,
        )
        assert encoding is not None, "read_text() must pass encoding"
        assert ast.literal_eval(encoding) == "utf-8"


def test_visual_qa_log_writes_are_utf8():
    append_open_calls = []
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        is_open = (
            isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ) or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "open"
        )
        if not is_open or len(node.args) < 1:
            continue
        mode = node.args[0] if isinstance(node.func, ast.Attribute) else node.args[1]
        if isinstance(mode, ast.Constant) and "a" in str(mode.value):
            append_open_calls.append(node)

    assert append_open_calls, "visual_qa.py should append debug logs"
    for call in append_open_calls:
        encoding = next(
            (kw.value for kw in call.keywords if kw.arg == "encoding"),
            None,
        )
        assert encoding is not None, "append log writes must pass encoding"
        assert ast.literal_eval(encoding) == "utf-8"


def test_visual_qa_contract_avoids_prior_history_inference():
    criteria = VQA_CRITERIA.read_text(encoding="utf-8")
    evaluate = EVALUATE_SKILL.read_text(encoding="utf-8")

    assert "Do not infer prior play history" in criteria
    assert "Visible state only; do not infer prior play history." in evaluate


def test_evaluate_uses_e2e_vqa_log():
    vqa = VQA_SKILL.read_text(encoding="utf-8")
    evaluate = EVALUATE_SKILL.read_text(encoding="utf-8")

    assert "${VQA_LOG:-.vqa.log}" in vqa
    assert "e2e/screenshots/vqa.log" in evaluate
