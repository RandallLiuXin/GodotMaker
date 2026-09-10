"""Structural checks for the shared reviewer triage contract."""
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TRIAGE = REPO_ROOT / "skills" / "core" / "_shared" / "reviewer-finding-triage.md"
MANIFEST = REPO_ROOT / "skills" / "core" / "_shared" / "manifest.json"


def _content() -> str:
    return TRIAGE.read_text(encoding="utf-8")


def test_triage_reference_is_published_to_both_consumers():
    consumers = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"].get(
        "reviewer-finding-triage.md"
    )
    assert consumers is not None
    assert {"gm-build", "gm-fixgap"} <= set(consumers)


def test_triage_keeps_decisions_defaults_and_citation_gate():
    content = _content()
    for token in ["ACCEPT", "REJECT", "SKIP", "critical / major", "minor"]:
        assert token in content
    for source in ["gotcha", "MEMORY.md", "PLAN.md", "GAP.md"]:
        assert source in content
    assert "Required" in content


def test_triage_does_not_persist_dynamic_findings_in_memory():
    content = _content()
    persistence_boundary = content.split("## Persistence boundary", maxsplit=1)
    assert len(persistence_boundary) == 2
    assert "`MEMORY.md`" in persistence_boundary[1]
    assert "REJECT/SKIP" in persistence_boundary[1]
    assert "Reviewer Triage Log" not in content
