"""Contract tests for C#-aware finalize/evaluate workflow documentation."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_finalize_requires_dotnet_verify_evidence_and_reports_backend():
    skill = _read("skills/core/gm-finalize/SKILL.md")

    assert ".godotmaker/verify_report.json" in skill
    assert "test_count.unit_backend" in skill
    assert "dotnet" in skill
    assert "passing" in skill.lower()


def test_finalize_makes_gdscript_ecs_consistency_backend_conditional():
    skill = _read("skills/core/gm-finalize/SKILL.md")

    assert "language_backend" in skill
    assert "N/A" in skill


def test_evaluate_prunes_orphan_gdscript_and_python_tests():
    skill = _read("skills/core/gm-evaluate/SKILL.md")

    assert "e2e/test_*.gd" in skill
    assert "e2e/test_*.py" in skill
