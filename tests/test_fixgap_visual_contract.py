"""Contract tests for fixgap visual self-check handoff."""
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXGAP = REPO_ROOT / "skills" / "core" / "gm-fixgap" / "SKILL.md"
WORKER = REPO_ROOT / "agents" / "worker.md"
VERIFIER = REPO_ROOT / "agents" / "verifier.md"
WORKER_DISPATCH = REPO_ROOT / "skills" / "core" / "_shared" / "worker-dispatch.md"
VERIFIER_DISPATCH = REPO_ROOT / "skills" / "core" / "_shared" / "verifier-dispatch.md"
SCREENSHOT = REPO_ROOT / "skills" / "core" / "screenshot" / "SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fixgap_dispatches_worker_visual_self_check():
    fixgap = _read(FIXGAP)
    dispatch = _read(WORKER_DISPATCH)

    assert "Visual Self-Check" in fixgap
    assert "Visual Self-Check" in dispatch
    assert "evaluation.json.visual_checks" in dispatch
    assert "Reference:" in dispatch
    assert "Target state:" in dispatch
    assert "Verify:" in dispatch
    assert "reports/fixgap-visual/{task_id}/" in dispatch
    assert "Output directory: `reports/fixgap-visual/{task_id}/`" in dispatch
    assert ".godotmaker/scratch/fixgap-visual/{task_id}/" not in dispatch


def test_worker_reports_visual_self_check_when_requested():
    worker = _read(WORKER)

    assert "Visual Self-Check" in worker
    assert "Required only when the brief includes `Visual Self-Check`." in worker
    assert "visual-qa" in worker
    assert "### Visual Self-Check" in worker
    assert "Screenshot(s):" in worker
    assert "visual-qa verdict:" in worker
    assert "reports/fixgap-visual/" in worker


def test_verifier_rechecks_visual_evidence_when_requested():
    verifier = _read(VERIFIER)
    dispatch = _read(VERIFIER_DISPATCH)

    assert "Visual Verification" in verifier
    assert "Visual Verification" in dispatch
    assert "visual-qa" in verifier
    assert "Missing evidence for a requested Visual Verification is FAIL." in verifier
    assert "Worker self-check result:" in dispatch
    assert "runs visual-qa on evaluator captures" in dispatch
    assert "Worker self-check evidence:" not in dispatch
    assert "reports/verifier-temp/" in dispatch
    assert "/tmp" not in dispatch
    assert "$TMPDIR" not in dispatch


def test_fixgap_uses_screenshot_and_visual_qa_without_e2e_ownership():
    fixgap = _read(FIXGAP)
    screenshot = _read(SCREENSHOT)

    assert "| screenshot |" in fixgap
    assert "| visual-qa |" in fixgap
    assert "reports/fixgap-visual/<task_id>/" in screenshot
    assert "reports/verifier-temp/" in screenshot
    assert ".godotmaker/scratch/fixgap-visual/<task_id>/" not in screenshot


def test_fixgap_preserves_visual_check_context_from_evaluation():
    fixgap = _read(FIXGAP)

    assert "evaluation.json.visual_checks" in fixgap
    assert "captures[]" in fixgap
    assert "vqa_calls[].context" in fixgap
    assert "vqa_calls[].log" in fixgap
