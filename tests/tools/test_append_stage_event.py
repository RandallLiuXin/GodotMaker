"""Tests for append_stage_event.py.

The parametrized core test mirrors the actual /gm-* SKILL "When Done"
invocations from skills/core/gm-*/SKILL.md — one row per real call site.
If a SKILL changes its append command, update the corresponding row here
so the test catches drift.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

import pytest

# tests/tools/ -> project_root/tools/
SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools", "append_stage_event.py"
)

ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def run(project_dir: str, *args: str) -> tuple[str, str, int]:
    """Run append_stage_event.py and return (stdout, stderr, exit_code)."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args, "--project-path", project_dir],
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout, result.stderr, result.returncode


def read_events(project_dir: str) -> list[dict]:
    path = os.path.join(project_dir, ".godotmaker", "stage.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture
def project_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, ".godotmaker"))
        yield tmpdir


# Each row is a real "When Done" call site in skills/core/gm-*/SKILL.md.
# Format: (test_id, [argv after script path], {expected fields beyond role+ts}).
SKILL_INVOCATIONS = [
    ("gm-scaffold",       ["scaffold"],                            {}),
    ("gm-gdd",            ["gdd", "--tag=v0.1.0"],                 {"tag": "v0.1.0"}),
    ("gm-asset",          ["asset"],                               {}),
    ("gm-build",          ["build"],                               {}),
    ("gm-verify",         ["verify"],                              {}),
    ("gm-evaluate",       ["evaluate", "--tag=v0.1.0"],            {"tag": "v0.1.0"}),
    ("gm-fixgap",         ["fixgap"],                              {}),
    ("gm-accept-accept",  ["accept", "--decision=accept"],         {"decision": "accept"}),
    ("gm-accept-fix",     ["accept", "--decision=fix"],            {"decision": "fix"}),
    ("gm-accept-done",    ["accept", "--decision=done"],           {"decision": "done"}),
    ("gm-finalize",       ["finalize", "--tag=v0.1.0"],            {"tag": "v0.1.0"}),
    ("gm-rescue-defect",  ["rescue", "--conclusion=defect"],       {"conclusion": "defect"}),
    ("gm-rescue-ext",     ["rescue", "--conclusion=external"],     {"conclusion": "external"}),
    ("gm-rescue-insuf",   ["rescue", "--conclusion=insufficient"], {"conclusion": "insufficient"}),
]


@pytest.mark.parametrize(
    "argv,expected_extras",
    [(argv, extras) for _, argv, extras in SKILL_INVOCATIONS],
    ids=[label for label, _, _ in SKILL_INVOCATIONS],
)
def test_skill_invocation_writes_expected_event(project_dir, argv, expected_extras):
    _, stderr, code = run(project_dir, *argv)
    assert code == 0, stderr

    [event] = read_events(project_dir)
    assert event["role"] == argv[0]
    assert ISO_UTC_RE.match(event["ts"]), event["ts"]
    for key, value in expected_extras.items():
        assert event[key] == value
    # Nothing extra sneaks in beyond role + ts + declared extras.
    assert set(event.keys()) == {"role", "ts"} | set(expected_extras.keys())


def test_field_order_role_then_ts_then_extras(project_dir):
    """JSON preserves the convention SKILL prose advertised (role, ts,
    then extras) — relied on by humans reading stage.jsonl."""
    _, stderr, code = run(project_dir, "evaluate", "--tag=v0.1.0")
    assert code == 0, stderr
    raw = open(os.path.join(project_dir, ".godotmaker", "stage.jsonl")).read()
    assert raw.index('"role"') < raw.index('"ts"') < raw.index('"tag"')


def test_append_does_not_overwrite_existing(project_dir):
    pre = os.path.join(project_dir, ".godotmaker", "stage.jsonl")
    with open(pre, "w", encoding="utf-8") as f:
        f.write('{"role": "scaffold", "ts": "2026-05-01T00:00:00Z"}\n')

    _, stderr, code = run(project_dir, "gdd", "--tag=v0.1.0")
    assert code == 0, stderr

    events = read_events(project_dir)
    assert len(events) == 2
    assert events[0]["role"] == "scaffold"
    assert events[1]["role"] == "gdd"


def test_evaluate_archives_current_e2e_screenshots(project_dir):
    screenshots = os.path.join(project_dir, "e2e", "screenshots")
    os.makedirs(os.path.join(screenshots, "scene_main"), exist_ok=True)
    with open(os.path.join(screenshots, "scene_main.png"), "w", encoding="utf-8") as f:
        f.write("png")
    with open(os.path.join(screenshots, "scene_main", "frame_000.png"), "w", encoding="utf-8") as f:
        f.write("frame")
    with open(os.path.join(project_dir, ".godotmaker", "evaluation.json"), "w", encoding="utf-8") as f:
        json.dump({"result": "reject"}, f)

    _, stderr, code = run(project_dir, "evaluate", "--tag=v0.1.0")
    assert code == 0, stderr

    latest_path = os.path.join(project_dir, ".godotmaker", "evaluation-runs", "latest.json")
    with open(latest_path, encoding="utf-8") as f:
        latest = json.load(f)

    archive_path = os.path.join(project_dir, latest["archive_path"])
    assert latest["tag"] == "v0.1.0"
    assert latest["screenshot_files"] == 2
    assert os.path.isfile(os.path.join(archive_path, "evaluation.json"))
    assert os.path.isfile(os.path.join(archive_path, "screenshots", "scene_main.png"))
    assert os.path.isfile(
        os.path.join(archive_path, "screenshots", "scene_main", "frame_000.png")
    )


def test_full_pipeline_sequence_preserves_order(project_dir):
    """End-to-end pipeline shape (one fixgap loop): scaffold → gdd → asset
    → build → verify → evaluate → fixgap → verify → evaluate → accept →
    finalize. All events land in stage.jsonl in invocation order."""
    sequence = [
        ["scaffold"],
        ["gdd", "--tag=v0.1.0"],
        ["asset"],
        ["build"],
        ["verify"],
        ["evaluate", "--tag=v0.1.0"],
        ["fixgap"],
        ["verify"],
        ["evaluate", "--tag=v0.1.0"],
        ["accept", "--decision=accept"],
        ["finalize", "--tag=v0.1.0"],
    ]
    for argv in sequence:
        _, stderr, code = run(project_dir, *argv)
        assert code == 0, stderr

    events = read_events(project_dir)
    assert [e["role"] for e in events] == [argv[0] for argv in sequence]


def test_missing_godotmaker_dir_exits_1():
    with tempfile.TemporaryDirectory() as tmpdir:
        # No .godotmaker/ subdir created.
        result = subprocess.run(
            [sys.executable, SCRIPT, "scaffold", "--project-path", tmpdir],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 1
        assert ".godotmaker" in result.stderr


def test_malformed_extra_no_equals_exits_2(project_dir):
    _, stderr, code = run(project_dir, "scaffold", "--bareflag")
    assert code == 2
    assert "--key=value" in stderr


def test_malformed_extra_empty_key_exits_2(project_dir):
    _, stderr, code = run(project_dir, "scaffold", "--=value")
    assert code == 2
