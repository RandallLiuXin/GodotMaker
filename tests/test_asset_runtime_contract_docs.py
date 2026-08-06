"""Regression gates for neutral Asset Skill handoff contracts."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hooks.metrics.outcome import OUTPUT_CATEGORIES, VALIDATION_LEVELS  # noqa: E402


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_asset_producer_outcome_template_matches_runtime_schema():
    producer = _read("agents/asset-producer.md")
    for category in OUTPUT_CATEGORIES:
        assert f'"{category}"' in producer
    for level in VALIDATION_LEVELS:
        assert f'"{level}"' in producer


def test_asset_no_work_resume_path_appends_the_asset_stage_event():
    skill = _read("skills/core/gm-asset/SKILL.md")
    completion = skill[skill.index("After ASSETS.md has no current-tag"):]
    assert "python tools/append_stage_event.py asset" in completion


def test_reference_only_assets_never_become_worker_runtime_inputs():
    registration = _read("skills/core/gm-asset/references/asset-result-registration.md")
    screen_reference = _read("skills/assets/screen-reference/SKILL.md")
    worker_dispatch = _read("skills/core/_shared/worker-dispatch.md")
    assert "do not create a logical row" in registration
    assert "must not enter worker runtime handoff" in screen_reference
    assert "a reference-only asset" in worker_dispatch
