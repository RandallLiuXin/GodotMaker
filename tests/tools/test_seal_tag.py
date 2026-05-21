"""Tests for seal_tag.py — the gm-finalize Step 4/7/5+8 mechanical helper.

Each subcommand has its own block. archive/reset assertions look at the
filesystem after the run; bundle assertions parse the stdout JSON.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools", "seal_tag.py"
)


def _load_seal_tag_module():
    """Import seal_tag.py as a module for direct helper-function tests."""
    spec = importlib.util.spec_from_file_location("seal_tag_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, "--project-path", str(project_dir), *args],
        capture_output=True, text=True, timeout=15,
    )


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Project root with archive sources + a populated .godotmaker/."""
    (tmp_path / ".godotmaker").mkdir()
    (tmp_path / "GDD.md").write_text("# GDD\n")
    (tmp_path / "PLAN.md").write_text(
        "# PLAN\n**Tag:** v0.1.0\n\n"
        "## Tag Mechanics\n"
        "- [v0.1.0-M1] jump\n"
        "- [v0.1.0-M2] dash\n"
    )
    (tmp_path / "STRUCTURE.md").write_text("# STRUCTURE\n")
    (tmp_path / "STYLE.md").write_text("# STYLE\n")
    (tmp_path / "SCENES.md").write_text("# SCENES\n")
    (tmp_path / "MEMORY.md").write_text("# MEMORY\n")
    (tmp_path / ".godotmaker" / "evaluation.json").write_text(
        json.dumps({"result": "approve", "minor_issues": ["small note"]})
    )
    (tmp_path / "e2e" / "screenshots").mkdir(parents=True)
    (tmp_path / "e2e" / "test_v0_1_0_M1_jump.py").write_text("def test_jump(): pass\n")
    (tmp_path / "e2e" / "screenshots" / "scene_main.png").write_text("png")
    return tmp_path


# ---------- archive ----------

def test_archive_copies_docs_and_evidence(project_dir: Path):
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr

    dest = project_dir / "docs" / "tags" / "v0.1.0"
    assert (dest / "GDD-snapshot.md").read_text() == "# GDD\n"
    assert (dest / "PLAN.md").exists()
    assert (dest / "STRUCTURE.md").exists()
    assert (dest / "STYLE.md").exists()
    assert (dest / "SCENES.md").exists()
    assert (dest / "MEMORY.md").exists()
    assert json.loads((dest / "evaluation-final.json").read_text())["result"] == "approve"
    assert (dest / "evidence" / "e2e" / "test_v0_1_0_M1_jump.py").exists()
    assert not (dest / "evidence" / "e2e" / "screenshots").exists()
    assert (dest / "evidence" / "screenshots" / "scene_main.png").exists()
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text())
    assert manifest == {
        "archive_path": "docs/tags/v0.1.0/evidence/",
        "e2e_files": 1,
        "screenshots": 1,
        "warnings": [],
    }


def test_archive_overwrites_partial_existing_archive(project_dir: Path):
    dest = project_dir / "docs" / "tags" / "v0.1.0"
    dest.mkdir(parents=True)
    (dest / "GDD-snapshot.md").write_text("stale content from a previous half-run")

    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr
    assert (dest / "GDD-snapshot.md").read_text() == "# GDD\n"


def test_archive_missing_source_exits_2(project_dir: Path):
    (project_dir / "STRUCTURE.md").unlink()
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 2
    assert "STRUCTURE.md" in r.stderr


def test_archive_lists_every_missing_source_not_just_first(project_dir: Path):
    (project_dir / "GDD.md").unlink()
    (project_dir / "MEMORY.md").unlink()
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 2
    assert "GDD.md" in r.stderr
    assert "MEMORY.md" in r.stderr


def test_archive_succeeds_when_evidence_copy_fails(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    seal_tag = _load_seal_tag_module()

    original_copy_tree_optional = seal_tag._copy_tree_optional

    def fake_copy_tree_optional(src, dst, ignore=None):
        if src.name == "e2e":
            raise OSError(13, "Permission denied")
        return original_copy_tree_optional(src, dst, ignore=ignore)

    monkeypatch.setattr(seal_tag, "_copy_tree_optional", fake_copy_tree_optional)

    rc = seal_tag.cmd_archive(project_dir, "v0.1.0")
    assert rc == 0
    dest = project_dir / "docs" / "tags" / "v0.1.0"
    assert (dest / "GDD-snapshot.md").exists()
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text())
    assert manifest["e2e_files"] == 0
    assert manifest["screenshots"] == 1
    assert manifest["warnings"]


# ---------- reset ----------

def test_reset_truncates_stage_and_deletes_metrics(project_dir: Path):
    gm = project_dir / ".godotmaker"
    (gm / "stage.jsonl").write_text('{"role":"build"}\n{"role":"verify"}\n')
    (gm / "metrics_current.jsonl").write_text('{"event":"x"}\n')

    r = run(project_dir, "reset")
    assert r.returncode == 0, r.stderr
    assert (gm / "stage.jsonl").read_text() == ""
    assert not (gm / "metrics_current.jsonl").exists()


def test_reset_idempotent_when_metrics_already_absent(project_dir: Path):
    (project_dir / ".godotmaker" / "stage.jsonl").write_text("event\n")
    # metrics_current.jsonl deliberately absent
    r = run(project_dir, "reset")
    assert r.returncode == 0, r.stderr
    assert (project_dir / ".godotmaker" / "stage.jsonl").read_text() == ""


def test_reset_leaves_metrics_jsonl_history_alone(project_dir: Path):
    """The permanent cross-session metrics.jsonl must survive a tag reset."""
    history = project_dir / ".godotmaker" / "metrics.jsonl"
    history.write_text('{"session":"old"}\n')
    r = run(project_dir, "reset")
    assert r.returncode == 0
    assert history.read_text() == '{"session":"old"}\n'


def test_reset_missing_godotmaker_dir_exits_1(tmp_path: Path):
    r = run(tmp_path, "reset")
    assert r.returncode == 1
    assert ".godotmaker" in r.stderr


# ---------- bundle ----------

def test_bundle_emits_required_keys(project_dir: Path):
    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0, r.stderr

    data = json.loads(r.stdout)
    assert data["tag"] == "v0.1.0"
    assert "previous_tag" in data
    assert "roadmap_entry" in data
    assert "plan_tag_mechanics" in data
    assert "git_log_since_previous_tag" in data
    assert "test_count" in data
    assert "evidence" in data
    assert set(data["test_count"].keys()) == {"unit", "e2e"}
    assert set(data["evidence"].keys()) == {"archive_path", "e2e_files", "screenshots"}


def test_bundle_extracts_tag_mechanics_from_plan(project_dir: Path):
    r = run(project_dir, "bundle", "v0.1.0")
    data = json.loads(r.stdout)
    assert data["plan_tag_mechanics"] == ["v0.1.0-M1", "v0.1.0-M2"]


def test_bundle_extracts_roadmap_entry(project_dir: Path):
    (project_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        "## v0.1.0 - Foundation\n"
        "Core jump + dash mechanics, single level.\n\n"
        "- jump\n- dash\n\n"
        "## v0.2.0 - Combat\n"
        "Adds enemies.\n",
        encoding="utf-8",
    )
    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["roadmap_entry"] is not None
    assert "Foundation" in data["roadmap_entry"]["heading"]
    assert "Core jump + dash" in data["roadmap_entry"]["body"]
    assert "v0.2.0" not in data["roadmap_entry"]["body"]


def test_bundle_roadmap_entry_null_when_tag_absent(project_dir: Path):
    (project_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## v0.9.9\nUnrelated.\n", encoding="utf-8"
    )
    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["roadmap_entry"] is None


def test_bundle_counts_unit_and_e2e_tests(project_dir: Path):
    (project_dir / "test").mkdir()
    (project_dir / "test" / "test_jump.gd").write_text("")
    (project_dir / "test" / "test_dash.gd").write_text("")
    (project_dir / "e2e").mkdir(exist_ok=True)
    (project_dir / "e2e" / "test_level1.py").write_text("")
    (project_dir / "e2e" / "conftest.py").write_text("")  # must not count

    r = run(project_dir, "bundle", "v0.1.0")
    data = json.loads(r.stdout)
    assert data["test_count"]["unit"] == 2
    assert data["test_count"]["e2e"] == 2


def test_bundle_reads_archived_evidence_manifest(project_dir: Path):
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr

    r = run(project_dir, "bundle", "v0.1.0")
    data = json.loads(r.stdout)
    assert data["evidence"] == {
        "archive_path": "docs/tags/v0.1.0/evidence/",
        "e2e_files": 1,
        "screenshots": 1,
        "warnings": [],
    }


def test_bundle_git_log_empty_when_no_git_repo(project_dir: Path):
    # No `git init` performed under project_dir, so git commands fail —
    # bundle should degrade gracefully, not crash.
    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["previous_tag"] is None
    assert data["git_log_since_previous_tag"] == ""


def test_bundle_git_log_includes_commits_since_previous_tag(project_dir: Path):
    import shutil as _shutil
    if not _shutil.which("git"):
        pytest.skip("git not available")

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(project_dir), *args],
            capture_output=True, text=True, check=True,
        ).stdout

    _git("init", "-q")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    (project_dir / "seed.txt").write_text("seed")
    _git("add", "seed.txt")
    _git("commit", "-q", "-m", "pre-tag-baseline")
    _git("tag", "v0.0.1")
    (project_dir / "post.txt").write_text("post")
    _git("add", "post.txt")
    _git("commit", "-q", "-m", "after-tag-feature")

    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["previous_tag"] == "v0.0.1"
    assert "after-tag-feature" in data["git_log_since_previous_tag"]
    assert "pre-tag-baseline" not in data["git_log_since_previous_tag"]


def test_bundle_previous_tag_when_current_tag_already_exists(project_dir: Path):
    """Retry-finalize shape: current tag exists from a prior partial run, AND
    new commits have landed past the tag. _resolve_tag_anchors must:
      - return the prior tag as previous_tag (not the current tag itself), and
      - cap the log slice at `<Tag>` so post-tag commits don't pollute the
        rerun changelog (architecture-axis MAJOR finding from review round 2)."""
    import shutil as _shutil
    if not _shutil.which("git"):
        pytest.skip("git not available")

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(project_dir), *args],
            capture_output=True, text=True, check=True,
        ).stdout

    _git("init", "-q")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    (project_dir / "seed.txt").write_text("seed")
    _git("add", "seed.txt")
    _git("commit", "-q", "-m", "pre-tag-baseline")
    _git("tag", "v0.0.1")
    (project_dir / "post.txt").write_text("post")
    _git("add", "post.txt")
    _git("commit", "-q", "-m", "v0.1.0-content")
    _git("tag", "v0.1.0")  # current tag already exists (retry-finalize case)
    # Post-tag commit must NOT leak into the slice on rerun — this is the
    # specific regression Codex flagged in review round 2.
    (project_dir / "leak.txt").write_text("leak")
    _git("add", "leak.txt")
    _git("commit", "-q", "-m", "after-v0.1.0-commit-must-not-leak")

    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["previous_tag"] == "v0.0.1"
    assert "v0.1.0-content" in data["git_log_since_previous_tag"]
    assert "pre-tag-baseline" not in data["git_log_since_previous_tag"]
    assert "after-v0.1.0-commit-must-not-leak" not in data["git_log_since_previous_tag"]


def test_bundle_helpers_degrade_when_git_binary_missing(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """FileNotFoundError branch in `_list_tags` / `_git_log_since` /
    `_resolve_tag_anchors`. Direct unit test on the helpers — env-based
    PATH tricks behave inconsistently across Windows installs."""
    seal_tag = _load_seal_tag_module()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(seal_tag.subprocess, "run", fake_run)

    assert seal_tag._list_tags(project_dir) == []
    assert seal_tag._git_log_since(project_dir, "v0.0.1") == ""
    assert seal_tag._resolve_tag_anchors(project_dir, "v0.1.0") == (None, "HEAD")


def test_bundle_roadmap_entry_matches_deeper_heading_and_terminates_correctly(
    project_dir: Path,
):
    """`### <Tag>` is a valid match; body terminates at the next same-or-
    higher heading and includes deeper sub-headings inside the section."""
    (project_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        "## Tag Schedule\n\n"
        "### v0.1.0 - Foundation\n"
        "First-tag scope.\n\n"
        "#### Sub-detail\n"
        "Still inside v0.1.0 section.\n\n"
        "### v0.2.0 - Combat\n"
        "Next tag.\n\n"
        "## Other top-level section\n"
        "Unrelated content.\n",
        encoding="utf-8",
    )
    r = run(project_dir, "bundle", "v0.1.0")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["roadmap_entry"] is not None
    assert "Foundation" in data["roadmap_entry"]["heading"]
    body = data["roadmap_entry"]["body"]
    assert "First-tag scope" in body
    assert "Still inside v0.1.0 section" in body  # deeper sub-heading included
    assert "v0.2.0" not in body                    # same-level heading terminates
    assert "Other top-level section" not in body  # higher-level heading also terminates


def test_archive_oserror_returns_exit_1(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mid-copy fs failure must surface as exit 1 with stderr context, not a
    bare traceback. Monkeypatch shutil.copy2 directly so we don't have to
    fabricate a real-world OSError condition."""
    seal_tag = _load_seal_tag_module()

    def fake_copy2(src, dst, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(seal_tag.shutil, "copy2", fake_copy2)

    rc = seal_tag.cmd_archive(project_dir, "v0.1.0")
    assert rc == 1


def test_reset_oserror_returns_exit_1(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Same shape for reset: write_text / unlink failures must exit 1."""
    seal_tag = _load_seal_tag_module()

    original_write_text = Path.write_text

    def fake_write_text(self, *args, **kwargs):
        if self.name == "stage.jsonl":
            raise OSError(13, "Permission denied")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fake_write_text)

    rc = seal_tag.cmd_reset(project_dir)
    assert rc == 1


def test_bundle_stdout_is_utf8_even_with_em_dash(project_dir: Path):
    """ROADMAP headings often use em-dash (U+2014) per the template. Bundle's
    stdout must round-trip as valid UTF-8 regardless of platform locale —
    Windows text-mode stdout defaults to cp936/GBK and silently mangles
    non-ASCII characters, which then crashes any downstream JSON parser
    expecting UTF-8."""
    (project_dir / "ROADMAP.md").write_text(
        "# Roadmap\n\n## v0.1.0 — Foundation\nBody with em-dash.\n",
        encoding="utf-8",
    )
    # Capture raw bytes (text=False) so we can verify the actual encoding.
    r = subprocess.run(
        [sys.executable, SCRIPT, "--project-path", str(project_dir), "bundle", "v0.1.0"],
        capture_output=True, timeout=15,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", errors="replace")
    # Must decode as UTF-8. cp936-encoded em-dash would raise UnicodeDecodeError.
    data = json.loads(r.stdout.decode("utf-8"))
    assert "—" in data["roadmap_entry"]["heading"]


def test_bundle_oserror_returns_exit_1(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """ROADMAP/PLAN read failures in cmd_bundle must surface as exit 1, not
    bare traceback. Without this guard, a corrupted ROADMAP.md encoding or
    a permission flip mid-finalize would silently abort Step 5."""
    seal_tag = _load_seal_tag_module()

    # Need PLAN.md to actually be hit by read_text — fixture creates it.
    original_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self.name == "PLAN.md":
            raise OSError(13, "Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    rc = seal_tag.cmd_bundle(project_dir, "v0.1.0")
    assert rc == 1
