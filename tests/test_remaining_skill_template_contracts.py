"""Contracts for GAP provenance, agent dispatch inputs, and SCENES viewport."""

import importlib.util
import json
import re
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXGAP = REPO_ROOT / "skills" / "core" / "gm-fixgap" / "SKILL.md"
GAP_TEMPLATE = REPO_ROOT / "templates" / "GAP.md"
SCENES_TEMPLATE = REPO_ROOT / "templates" / "SCENES.md"
DECOMPOSER = REPO_ROOT / "agents" / "decomposer.md"

_APPEND_SPEC = importlib.util.spec_from_file_location(
    "append_stage_event_contract", REPO_ROOT / "tools" / "append_stage_event.py"
)
assert _APPEND_SPEC is not None and _APPEND_SPEC.loader is not None
_APPEND_MODULE = importlib.util.module_from_spec(_APPEND_SPEC)
_APPEND_SPEC.loader.exec_module(_APPEND_MODULE)
_archive_evaluation_run = _APPEND_MODULE._archive_evaluation_run

DISPATCH_CONTRACTS = {
    "worker": {
        "dispatch": REPO_ROOT / "skills" / "core" / "_shared" / "worker-dispatch.md",
        "required": (
            "## Task:",
            "### Objective",
            "### Context",
            "### Input Files (Read These First)",
            "### Game Mechanic Function",
            "### Deliverables",
            "### Component Definitions",
            "### Scope Boundaries",
            "### Prohibited Actions",
        ),
    },
    "reviewer": {
        "dispatch": REPO_ROOT / "skills" / "core" / "_shared" / "reviewer-dispatch.md",
        "required": (
            "## Review:",
            "### Project Path",
            "### Files to Review",
            "### Context",
        ),
    },
    "verifier": {
        "dispatch": REPO_ROOT / "skills" / "core" / "_shared" / "verifier-dispatch.md",
        "required": (
            "## Verify:",
            "### Project Path",
            "### Godot Path",
            "### Commands to Run (run ALL, do not skip)",
            "### Success Criteria",
        ),
    },
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _gap_archive_path(
    gap_text: str, existing: set[PurePosixPath] | None = None
) -> PurePosixPath:
    match = re.search(r"^- Archive path:\s+(.+)$", gap_text, re.MULTILINE)
    assert match, "GAP.md must record its source evaluation archive path"
    run_id = PurePosixPath(match.group(1).strip()).name
    assert run_id not in {"", ".", "evaluation-runs"}
    existing = existing or set()
    candidate = PurePosixPath(".godotmaker/gaps") / run_id / "GAP.md"
    suffix = 2
    while candidate in existing:
        candidate = (
            PurePosixPath(".godotmaker/gaps") / f"{run_id}-{suffix}" / "GAP.md"
        )
        suffix += 1
    return candidate


def test_gap_run_identity_comes_only_from_latest_evaluation_run():
    fixgap = _read(FIXGAP)
    template = _read(GAP_TEMPLATE)

    assert ".godotmaker/evaluation-runs/latest.json" in fixgap
    for field in ("archive_path", "stage_event_ts", "tag"):
        assert field in fixgap
    assert "Do not expect or read `iteration`, `ts`" in " ".join(fixgap.split())
    assert "<source-evaluation-iteration>" not in fixgap
    assert "Source Evaluation: <evaluation iteration / ts>" not in fixgap

    assert "## Source Evaluation Run" in template
    assert "- Archive path:" in template
    assert "latest.json stage_event_ts" in template
    assert "- Iteration:" not in template
    assert "- Generated at:" not in template


def test_real_latest_artifact_shape_resolves_a_unique_gap_archive(tmp_path):
    (tmp_path / ".godotmaker").mkdir()
    (tmp_path / ".godotmaker" / "evaluation.json").write_text(
        json.dumps({"result": "reject"}), encoding="utf-8"
    )
    event = {
        "role": "evaluate",
        "ts": "2026-10-22T12:34:56Z",
        "tag": "v0.2.0",
    }

    _archive_evaluation_run(tmp_path, event)
    first = json.loads(
        (tmp_path / ".godotmaker" / "evaluation-runs" / "latest.json").read_text(
            encoding="utf-8"
        )
    )
    _archive_evaluation_run(tmp_path, event)
    latest = json.loads(
        (tmp_path / ".godotmaker" / "evaluation-runs" / "latest.json").read_text(
            encoding="utf-8"
        )
    )

    assert latest["role"] == "evaluate"
    assert latest["stage_event_ts"] == event["ts"]
    assert latest["evaluation_json"] == f'{latest["archive_path"]}/evaluation.json'
    assert latest["archive_path"] != first["archive_path"]

    gap = _read(GAP_TEMPLATE).replace(
        "{.godotmaker/evaluation-runs/<run-id>}", latest["archive_path"]
    )
    gap_archive = _gap_archive_path(gap)
    run_id = PurePosixPath(latest["archive_path"]).name
    assert str(gap_archive) == f".godotmaker/gaps/{run_id}/GAP.md"
    assert run_id not in {"", ".", "evaluation-runs"}


def test_stale_gap_archives_under_its_own_source_run():
    fixgap = _read(FIXGAP)
    old_archive = ".godotmaker/evaluation-runs/20261022T120000Z_v0.2.0"
    latest = {
        "archive_path": ".godotmaker/evaluation-runs/20261022T130000Z_v0.2.0"
    }
    stale_gap = _read(GAP_TEMPLATE).replace(
        "{.godotmaker/evaluation-runs/<run-id>}", old_archive
    )

    archive_path = _gap_archive_path(stale_gap)

    assert archive_path == PurePosixPath(
        ".godotmaker/gaps/20261022T120000Z_v0.2.0/GAP.md"
    )
    assert PurePosixPath(latest["archive_path"]).name not in archive_path.parts
    assert "archive the stale GAP under the run id from its own header" in fixgap
    assert (
        "Never archive the stale GAP under the current `latest.json` run id"
        in fixgap
    )
    assert "Read `Archive path` from the `Source Evaluation Run` header" in fixgap


def test_repeated_fixgap_rounds_allocate_unique_archives_for_the_same_run():
    fixgap = _read(FIXGAP)
    gap = _read(GAP_TEMPLATE).replace(
        "{.godotmaker/evaluation-runs/<run-id>}",
        ".godotmaker/evaluation-runs/20261022T120000Z_v0.2.0",
    )
    first = _gap_archive_path(gap)
    second = _gap_archive_path(gap, {first})
    third = _gap_archive_path(gap, {first, second})

    assert first == PurePosixPath(
        ".godotmaker/gaps/20261022T120000Z_v0.2.0/GAP.md"
    )
    assert second == PurePosixPath(
        ".godotmaker/gaps/20261022T120000Z_v0.2.0-2/GAP.md"
    )
    assert third == PurePosixPath(
        ".godotmaker/gaps/20261022T120000Z_v0.2.0-3/GAP.md"
    )
    assert "allocate the first free sibling" in fixgap
    assert "never\noverwrite or replace an archived GAP" in fixgap


def test_dispatch_contracts_are_the_single_source_of_required_inputs():
    for role, contract in DISPATCH_CONTRACTS.items():
        dispatch = _read(contract["dispatch"])
        agent = _read(REPO_ROOT / "agents" / f"{role}.md")

        for heading in contract["required"]:
            assert heading in dispatch, f"{role} dispatch is missing {heading}"
        assert "## Dispatch Input Contract" in agent
        assert f"skills/core/_shared/{role}-dispatch.md" in agent
        assert "intentionally does not duplicate that schema" in " ".join(
            agent.split()
        )
        assert "## Brief Format (What You Receive)" not in agent


def test_scenes_template_renders_the_resolved_non_default_viewport():
    template = _read(SCENES_TEMPLATE)
    decomposer = _read(DECOMPOSER)
    resolution_line = next(
        line for line in template.splitlines() if "**Resolution reference:**" in line
    )

    rendered = resolution_line.replace(
        "{resolved target viewport width}", "1024"
    ).replace("{resolved target viewport height}", "600")

    assert rendered == "- **Resolution reference:** 1024×600"
    assert "- **Resolution reference:** 1920×1080" not in template
    assert "Use the explicit GDD" in decomposer
    assert "Otherwise use `480×270`" in decomposer
    assert "`1280×720` for the non-pixel profile" in decomposer
    assert (
        "never substitute the\n  `1920×1080` pixel-profile window override"
        in decomposer
    )
