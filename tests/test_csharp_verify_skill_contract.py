"""Contract tests for backend-aware gm-verify instructions."""

from pathlib import Path


SKILL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "core"
    / "gm-verify"
    / "SKILL.md"
)


def test_gm_verify_documents_both_supported_backend_pairs():
    text = SKILL.read_text(encoding="utf-8")

    assert "GDScript + gdUnit" in text
    assert "C# + dotnet test" in text
    assert "language_backend" in text
    assert "unit_test_backend" in text


def test_gm_verify_documents_trx_and_explicit_static_skips():
    text = SKILL.read_text(encoding="utf-8")

    assert "TRX" in text
    assert "skipped_checks" in text
    assert "SKIP / N/A" in text


def test_gm_verify_report_schema_exposes_backend_metadata():
    text = SKILL.read_text(encoding="utf-8")

    assert '"backend"' in text
    assert '"framework": "gdunit | dotnet"' in text
    assert '"skipped"' in text
