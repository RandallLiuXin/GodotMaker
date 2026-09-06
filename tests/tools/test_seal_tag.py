"""Tests for seal_tag.py — the gm-finalize Step 4/7/5+8 mechanical helper.

Each subcommand has its own block. archive/reset assertions look at the
filesystem after the run; bundle assertions parse the stdout JSON.
"""
import hashlib
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
    (tmp_path / "MEMORY.md").write_text(
        "# MEMORY\n\n## System Index\n\n"
        "- [movement](memory/movement.md) - PlayerMovementSystem notes\n",
        encoding="utf-8",
    )
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "movement.md").write_text("# movement\n", encoding="utf-8")
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
    assert (dest / "memory" / "movement.md").exists()
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_path"] == "docs/tags/v0.1.0/evidence/"
    assert manifest["e2e_files"] == 1
    assert manifest["screenshots"] == 1
    assert manifest["memory_files"] == 1
    assert manifest["warnings"] == []
    # `archive` alone never seals — that is `index`'s job.
    assert manifest["sealed"] is False


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


# ---------- archive: memory subtree + link integrity ----------

CHANGELOG_BODY = (
    "# Changelog - v0.1.0\n\n"
    "**Released:** 2026-05-12\n"
    "**Theme:** Foundation\n\n"
    "## Delivered mechanics\n\n"
    "- [v0.1.0-M1] jump\n"
    "- [v0.1.0-M2] dash\n\n"
    "## Added systems / scenes / assets\n\n"
    "- MovementSystem\n"
    "- Main.tscn\n\n"
    "## Known limitations\n\n"
    "- camera jitter ships as-is\n"
)


def write_changelog(project_dir: Path, tag: str = "v0.1.0", body: str = CHANGELOG_BODY) -> None:
    dest = project_dir / "docs" / "tags" / tag
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "CHANGELOG.md").write_text(body, encoding="utf-8")


def seal(project_dir: Path, tag: str = "v0.1.0") -> subprocess.CompletedProcess:
    """archive -> CHANGELOG -> index, the full /gm-finalize archive path."""
    r = run(project_dir, "archive", tag)
    assert r.returncode == 0, r.stderr
    write_changelog(project_dir, tag)
    return run(project_dir, "index", tag)


def test_archive_freezes_memory_subtree_next_to_memory_md(project_dir: Path):
    (project_dir / "memory" / "collision.md").write_text("# collision\n", encoding="utf-8")
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr

    dest = project_dir / "docs" / "tags" / "v0.1.0"
    assert (dest / "memory" / "movement.md").read_text(encoding="utf-8") == "# movement\n"
    assert (dest / "memory" / "collision.md").exists()
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["memory_files"] == 2
    assert {"memory/movement.md", "memory/collision.md"} <= {
        entry["path"] for entry in manifest["files"]
    }


def test_archive_blocks_when_memory_link_has_no_archived_target(project_dir: Path):
    (project_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- [ghost](memory/ghost.md) - never written\n", encoding="utf-8"
    )
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 2
    assert "memory/ghost.md" in r.stderr

    dest = project_dir / "docs" / "tags" / "v0.1.0"
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sealed"] is False, "a broken index must never seal"


def test_archive_ignores_links_inside_html_comments_and_code_fences(project_dir: Path):
    """templates/MEMORY.md ships its example `memory/*.md` entries inside an
    HTML comment. Treating those as real links would block every first
    finalize on a fresh project."""
    (project_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n"
        "<!-- Example entries (delete when starting):\n"
        "- [movement_system](memory/movement_system.md) - example\n"
        "-->\n\n"
        "```markdown\n- [fenced](memory/fenced.md)\n```\n\n"
        "- [movement](memory/movement.md) - real entry\n",
        encoding="utf-8",
    )
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr


def test_archive_warns_but_does_not_block_on_links_outside_the_archive(project_dir: Path):
    """MEMORY.md legitimately cites source files that are not archived."""
    (project_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- [movement](memory/movement.md)\n- see [player](src/player.gd)\n",
        encoding="utf-8",
    )
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr
    manifest = json.loads(
        (project_dir / "docs" / "tags" / "v0.1.0" / "evidence" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    assert any("src/player.gd" in w for w in manifest["link_warnings"])


def test_archive_blocks_links_that_escape_the_archive_boundary(project_dir: Path):
    (project_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- [escape](../../../secrets.md)\n", encoding="utf-8"
    )
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 2
    assert "escapes the archive boundary" in r.stderr


def test_archive_blocks_absolute_links(project_dir: Path):
    (project_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- [abs](/etc/passwd)\n", encoding="utf-8"
    )
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 2
    assert "absolute path" in r.stderr


def test_archive_excludes_caches_and_temp_files(project_dir: Path):
    (project_dir / "e2e" / "__pycache__").mkdir()
    (project_dir / "e2e" / "__pycache__" / "test_x.pyc").write_text("junk")
    (project_dir / "e2e" / "scratch.tmp").write_text("junk")
    (project_dir / "memory" / "notes.bak").write_text("junk")

    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr
    dest = project_dir / "docs" / "tags" / "v0.1.0"
    assert not (dest / "evidence" / "e2e" / "__pycache__").exists()
    assert not (dest / "evidence" / "e2e" / "scratch.tmp").exists()
    assert not (dest / "memory" / "notes.bak").exists()

    manifest = json.loads((dest / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    paths = [entry["path"] for entry in manifest["files"]]
    assert not any(p.endswith((".pyc", ".tmp", ".bak")) for p in paths)
    assert "evidence/manifest.json" not in paths, "the manifest never lists itself"


def test_archive_preserves_utf8_document_content(project_dir: Path):
    (project_dir / "SCENES.md").write_text(
        "# 场景\n\n- 主场景 — Main.tscn\n", encoding="utf-8"
    )
    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr
    archived = (project_dir / "docs" / "tags" / "v0.1.0" / "SCENES.md").read_text(
        encoding="utf-8"
    )
    assert "主场景 — Main.tscn" in archived


# ---------- index (seal) ----------

def test_index_writes_summary_readme_and_parent_index(project_dir: Path):
    r = seal(project_dir)
    assert r.returncode == 0, r.stderr

    dest = project_dir / "docs" / "tags" / "v0.1.0"
    summary = (dest / "SUMMARY.md").read_text(encoding="utf-8")
    assert "# Summary — v0.1.0" in summary
    assert "2026-05-12" in summary
    assert "Foundation" in summary
    assert "[v0.1.0-M1] jump" in summary
    assert "MovementSystem" in summary
    assert "camera jitter ships as-is" in summary
    assert "**approve**" in summary

    readme = (dest / "README.md").read_text(encoding="utf-8")
    assert "sealed archive" in readme
    assert "[SUMMARY.md](SUMMARY.md)" in readme
    assert "Completeness:** complete" in readme

    parent = (project_dir / "docs" / "tags" / "README.md").read_text(encoding="utf-8")
    assert "[v0.1.0](v0.1.0/)" in parent
    assert "[SUMMARY](v0.1.0/SUMMARY.md)" in parent


def test_index_manifest_carries_full_provenance(project_dir: Path):
    (project_dir / ".godotmaker" / "version").write_text("1.2.3", encoding="utf-8")
    assert seal(project_dir).returncode == 0

    manifest = json.loads(
        (project_dir / "docs" / "tags" / "v0.1.0" / "evidence" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    assert manifest["generator"] == "tools/seal_tag.py"
    assert manifest["generator_version"] == "1.2.3"
    assert manifest["sealed"] is True
    assert manifest["stage"] == "sealed"
    assert "source_revision" in manifest

    by_path = {entry["path"]: entry for entry in manifest["files"]}
    for required in ("PLAN.md", "SUMMARY.md", "README.md", "memory/movement.md",
                     "evidence/e2e/test_v0_1_0_M1_jump.py",
                     "evidence/screenshots/scene_main.png"):
        assert required in by_path, required
        entry = by_path[required]
        assert entry["bytes"] > 0
        assert len(entry["sha256"]) == 64

    assert by_path["PLAN.md"]["category"] == "document"
    assert by_path["SUMMARY.md"]["category"] == "index"
    assert by_path["memory/movement.md"]["category"] == "memory"
    assert by_path["evidence/e2e/test_v0_1_0_M1_jump.py"]["category"] == "e2e"
    assert by_path["evidence/screenshots/scene_main.png"]["category"] == "screenshot"

    # Hashes must match the bytes actually on disk.
    plan = project_dir / "docs" / "tags" / "v0.1.0" / "PLAN.md"
    assert by_path["PLAN.md"]["sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()


def test_index_manifest_paths_are_posix_on_every_platform(project_dir: Path):
    """A manifest written on Windows must compare byte-for-byte with one
    written on Linux, so nested paths never use backslashes."""
    assert seal(project_dir).returncode == 0
    manifest = json.loads(
        (project_dir / "docs" / "tags" / "v0.1.0" / "evidence" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    paths = [entry["path"] for entry in manifest["files"]]
    assert all("\\" not in p for p in paths)
    assert paths == sorted(paths), "manifest order must be stable"


def test_index_refuses_when_changelog_missing(project_dir: Path):
    assert run(project_dir, "archive", "v0.1.0").returncode == 0
    r = run(project_dir, "index", "v0.1.0")
    assert r.returncode == 2
    assert "CHANGELOG.md" in r.stderr


def test_index_regenerates_identical_content(project_dir: Path):
    assert seal(project_dir).returncode == 0
    dest = project_dir / "docs" / "tags" / "v0.1.0"
    first_summary = (dest / "SUMMARY.md").read_bytes()
    first_readme = (dest / "README.md").read_bytes()
    first_manifest = (dest / "evidence" / "manifest.json").read_bytes()

    r = run(project_dir, "index", "v0.1.0", "--force")
    assert r.returncode == 0, r.stderr
    assert (dest / "SUMMARY.md").read_bytes() == first_summary
    assert (dest / "README.md").read_bytes() == first_readme
    assert (dest / "evidence" / "manifest.json").read_bytes() == first_manifest


def test_summary_stays_within_its_length_bound(project_dir: Path):
    seal_tag = _load_seal_tag_module()
    filler = "x" * 400
    body = (
        "# Changelog\n\n**Released:** 2026-05-12\n**Theme:** Big\n\n"
        "## Delivered mechanics\n\n"
        + "".join(f"- [v0.1.0-M{i}] mechanic {i} {filler}\n" for i in range(50))
        + "\n## Added systems / scenes / assets\n\n"
        + "".join(f"- system {i}\n" for i in range(50))
        + "\n## Known limitations\n\n"
        + "".join(f"- limitation {i}\n" for i in range(50))
    )
    assert run(project_dir, "archive", "v0.1.0").returncode == 0
    write_changelog(project_dir, body=body)
    assert run(project_dir, "index", "v0.1.0").returncode == 0

    summary = (project_dir / "docs" / "tags" / "v0.1.0" / "SUMMARY.md").read_text(
        encoding="utf-8"
    )
    lines = summary.splitlines()
    assert len(lines) <= seal_tag.SUMMARY_MAX_LINES
    assert all(len(line) <= seal_tag.SUMMARY_MAX_ITEM_CHARS + 8 for line in lines)
    assert "and 38 more" in summary, "clipped lists must say what was dropped"
    assert "CHANGELOG.md" in summary, "and where the full list lives"


def test_summary_does_not_absorb_worker_exploration_notes(project_dir: Path):
    """SUMMARY is an index over confirmed deliverables. Worker discoveries and
    unverified learnings stay in MEMORY.md."""
    (project_dir / "MEMORY.md").write_text(
        "# MEMORY\n\n- [movement](memory/movement.md)\n\n"
        "## Discoveries\n\n- tried a raycast approach that half worked\n",
        encoding="utf-8",
    )
    assert seal(project_dir).returncode == 0
    summary = (project_dir / "docs" / "tags" / "v0.1.0" / "SUMMARY.md").read_text(
        encoding="utf-8"
    )
    assert "raycast approach" not in summary
    assert "[MEMORY.md](MEMORY.md)" in summary, "but it must still point at it"


def test_summary_ignores_a_final_report_belonging_to_another_tag(project_dir: Path):
    """final_report.json is per-tag overwritten - reading it blindly would
    stamp the next tag's test counts onto this archive."""
    (project_dir / ".godotmaker" / "final_report.json").write_text(
        json.dumps({"tag": "v0.2.0", "summary": {"test_count": {"unit": 99}}}),
        encoding="utf-8",
    )
    assert seal(project_dir).returncode == 0
    summary = (project_dir / "docs" / "tags" / "v0.1.0" / "SUMMARY.md").read_text(
        encoding="utf-8"
    )
    assert "99" not in summary
    assert "Tests: not recorded" in summary


def test_index_fs_failure_returns_exit_1(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    seal_tag = _load_seal_tag_module()
    assert run(project_dir, "archive", "v0.1.0").returncode == 0
    write_changelog(project_dir)

    original = seal_tag._atomic_write_text

    def fake_write(path, text):
        if path.name == "SUMMARY.md":
            raise OSError(28, "No space left on device")
        return original(path, text)

    monkeypatch.setattr(seal_tag, "_atomic_write_text", fake_write)
    assert seal_tag.cmd_index(project_dir, "v0.1.0") == 1


def test_index_leaves_the_tag_unsealed_when_the_parent_index_write_fails(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """The seal commit is the last step on purpose. If anything before it
    fails — here the parent index — the tag must stay unsealed and re-runnable,
    not become a sealed archive that no command will touch again."""
    seal_tag = _load_seal_tag_module()
    assert run(project_dir, "archive", "v0.1.0").returncode == 0
    write_changelog(project_dir)

    def boom(tags_root, pending=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(seal_tag, "_write_parent_readme", boom)
    assert seal_tag.cmd_index(project_dir, "v0.1.0") == 1

    dest = project_dir / "docs" / "tags" / "v0.1.0"
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sealed"] is False
    assert not seal_tag._is_sealed(dest)

    # Recovery is the documented partial-resume path: no --force needed.
    monkeypatch.undo()
    assert run(project_dir, "archive", "v0.1.0").returncode == 0
    r = run(project_dir, "index", "v0.1.0")
    assert r.returncode == 0, r.stderr
    assert seal_tag._is_sealed(dest)
    parent = (project_dir / "docs" / "tags" / "README.md").read_text(encoding="utf-8")
    assert "[v0.1.0](v0.1.0/)" in parent


def test_index_leaves_no_temp_files_behind(project_dir: Path):
    """Index files are written atomically via a same-directory temp file; a
    successful run must not leave one in the archive or the manifest."""
    assert seal(project_dir).returncode == 0
    seal_tag = _load_seal_tag_module()
    tags_root = project_dir / "docs" / "tags"
    assert not list(tags_root.rglob(f"*{seal_tag.TMP_SUFFIX}"))
    manifest = json.loads(
        (tags_root / "v0.1.0" / "evidence" / "manifest.json").read_text(encoding="utf-8")
    )
    assert not any(
        e["path"].endswith(seal_tag.TMP_SUFFIX) for e in manifest["files"]
    )


def test_backfill_commits_no_seal_when_the_parent_index_write_fails(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    """Same ordering guarantee for backfill: a failed parent index must leave
    every target unsealed rather than half of them sealed and unlisted."""
    seal_tag = _load_seal_tag_module()
    _legacy_archive(project_dir, "v0.0.9")
    _legacy_archive(project_dir, "v0.0.8")

    def boom(tags_root, pending=None):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(seal_tag, "_write_parent_readme", boom)
    assert seal_tag.cmd_backfill(project_dir, None, True) == 1
    for tag in ("v0.0.8", "v0.0.9"):
        assert not seal_tag._is_sealed(project_dir / "docs" / "tags" / tag)

    monkeypatch.undo()
    assert run(project_dir, "backfill", "--all").returncode == 0
    for tag in ("v0.0.8", "v0.0.9"):
        assert seal_tag._is_sealed(project_dir / "docs" / "tags" / tag)


# ---------- immutability and resume ----------

def test_sealed_archive_is_not_silently_overwritten(project_dir: Path):
    assert seal(project_dir).returncode == 0
    (project_dir / "PLAN.md").write_text("# PLAN\n**Tag:** v0.1.0\nrewritten\n")

    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 3
    assert "already sealed" in r.stderr
    archived = (project_dir / "docs" / "tags" / "v0.1.0" / "PLAN.md").read_text()
    assert "rewritten" not in archived

    r = run(project_dir, "index", "v0.1.0")
    assert r.returncode == 3
    assert "already sealed" in r.stderr


def test_force_reseals_an_already_sealed_archive(project_dir: Path):
    assert seal(project_dir).returncode == 0
    (project_dir / "PLAN.md").write_text("# PLAN\n**Tag:** v0.1.0\nrewritten\n")

    r = run(project_dir, "archive", "v0.1.0", "--force")
    assert r.returncode == 0, r.stderr
    archived = (project_dir / "docs" / "tags" / "v0.1.0" / "PLAN.md").read_text()
    assert "rewritten" in archived


def test_partial_archive_is_resumable_without_force(project_dir: Path):
    """Documented resume condition: an archive whose manifest is absent or
    says `sealed: false` is a half-finished finalize, and re-running
    `archive` is the recovery path."""
    assert run(project_dir, "archive", "v0.1.0").returncode == 0
    dest = project_dir / "docs" / "tags" / "v0.1.0"
    (dest / "STRUCTURE.md").unlink()            # simulate a crash mid-copy
    (dest / "GDD-snapshot.md").write_text("stale half-run content")

    r = run(project_dir, "archive", "v0.1.0")
    assert r.returncode == 0, r.stderr
    assert (dest / "STRUCTURE.md").exists()
    assert (dest / "GDD-snapshot.md").read_text() == "# GDD\n"
    assert run(project_dir, "index", "v0.1.0").returncode == 2  # still needs CHANGELOG
    write_changelog(project_dir)
    assert run(project_dir, "index", "v0.1.0").returncode == 0


def test_reindexing_a_sealed_tag_leaves_it_byte_identical(project_dir: Path):
    """Repeated finalize runs on a completed tag must be a no-op, not a
    silent rewrite."""
    assert seal(project_dir).returncode == 0
    dest = project_dir / "docs" / "tags" / "v0.1.0"
    before = {p: p.read_bytes() for p in sorted(dest.rglob("*")) if p.is_file()}

    assert run(project_dir, "archive", "v0.1.0").returncode == 3
    assert run(project_dir, "index", "v0.1.0").returncode == 3

    after = {p: p.read_bytes() for p in sorted(dest.rglob("*")) if p.is_file()}
    assert before == after


# ---------- parent index ----------

def _seal_extra_tag(project_dir: Path, tag: str, theme: str) -> None:
    (project_dir / "PLAN.md").write_text(f"# PLAN\n**Tag:** {tag}\n\n- [{tag}-M1] thing\n")
    assert run(project_dir, "archive", tag).returncode == 0
    write_changelog(
        project_dir, tag,
        f"# Changelog\n\n**Released:** 2026-06-01\n**Theme:** {theme}\n\n"
        f"## Delivered mechanics\n\n- [{tag}-M1] thing\n",
    )
    assert run(project_dir, "index", tag).returncode == 0


def test_parent_readme_lists_every_sealed_tag_in_version_order(project_dir: Path):
    assert seal(project_dir).returncode == 0
    _seal_extra_tag(project_dir, "v0.2.0", "Combat")
    _seal_extra_tag(project_dir, "v0.10.0", "Polish")

    parent = (project_dir / "docs" / "tags" / "README.md").read_text(encoding="utf-8")
    order = [parent.index(f"[{t}]({t}/)") for t in ("v0.1.0", "v0.2.0", "v0.10.0")]
    assert order == sorted(order), "v0.2.0 must sort before v0.10.0"
    assert "Combat" in parent and "Polish" in parent


def test_parent_readme_omits_unsealed_and_nonexistent_tags(project_dir: Path):
    assert seal(project_dir).returncode == 0
    # v0.2.0 archived but never indexed - an in-progress finalize.
    (project_dir / "PLAN.md").write_text("# PLAN\n**Tag:** v0.2.0\n")
    assert run(project_dir, "archive", "v0.2.0").returncode == 0
    # A stray directory that is not an archive at all.
    (project_dir / "docs" / "tags" / "scratch").mkdir()

    assert run(project_dir, "index", "v0.1.0", "--force").returncode == 0
    parent = (project_dir / "docs" / "tags" / "README.md").read_text(encoding="utf-8")
    assert "[v0.1.0](v0.1.0/)" in parent
    assert "v0.2.0" not in parent
    assert "scratch" not in parent


def test_generated_index_links_all_resolve(project_dir: Path):
    """Markdown link check over everything seal_tag generates."""
    seal_tag = _load_seal_tag_module()
    assert seal(project_dir).returncode == 0
    tags_root = project_dir / "docs" / "tags"

    for doc in (tags_root / "README.md",
                tags_root / "v0.1.0" / "README.md",
                tags_root / "v0.1.0" / "SUMMARY.md"):
        text = doc.read_text(encoding="utf-8")
        targets = seal_tag._local_markdown_links(text)
        assert targets, f"{doc.name} should link somewhere"
        for target in targets:
            assert (doc.parent / target).exists(), f"{doc.name} -> {target}"


# ---------- backfill ----------

def _legacy_archive(project_dir: Path, tag: str = "v0.0.9") -> Path:
    """An archive in the pre-index layout: flat docs, no README/SUMMARY/memory."""
    dest = project_dir / "docs" / "tags" / tag
    dest.mkdir(parents=True)
    for name in ("GDD-snapshot.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "SCENES.md"):
        (dest / name).write_text(f"# legacy {name}\n", encoding="utf-8")
    (dest / "MEMORY.md").write_text(
        "# MEMORY\n\n- [movement](memory/movement.md) - not archived back then\n",
        encoding="utf-8",
    )
    (dest / "evaluation-final.json").write_text(
        json.dumps({"result": "approve", "minor_issues": ["legacy jitter"]}),
        encoding="utf-8",
    )
    (dest / "CHANGELOG.md").write_text(
        "# Changelog\n\n**Released:** 2025-01-01\n**Theme:** Legacy\n\n"
        f"## Delivered mechanics\n\n- [{tag}-M1] walk\n",
        encoding="utf-8",
    )
    return dest


def test_backfill_adds_index_files_without_touching_canonical_documents(project_dir: Path):
    dest = _legacy_archive(project_dir)
    canonical = {p.name: p.read_bytes() for p in dest.iterdir() if p.is_file()}

    r = run(project_dir, "backfill", "v0.0.9")
    assert r.returncode == 0, r.stderr

    assert (dest / "README.md").is_file()
    assert (dest / "SUMMARY.md").is_file()
    assert (dest / "evidence" / "manifest.json").is_file()
    for name, blob in canonical.items():
        assert (dest / name).read_bytes() == blob, f"{name} must not be rewritten"

    summary = (dest / "SUMMARY.md").read_text(encoding="utf-8")
    assert "Legacy" in summary and "[v0.0.9-M1] walk" in summary
    parent = (project_dir / "docs" / "tags" / "README.md").read_text(encoding="utf-8")
    assert "[v0.0.9](v0.0.9/)" in parent


def test_backfill_records_the_missing_memory_subtree_instead_of_inventing_one(
    project_dir: Path,
):
    """Copying today's memory/ into a historical tag would inject present-day
    content into a past snapshot, so backfill reports the gap instead."""
    dest = _legacy_archive(project_dir)
    assert run(project_dir, "backfill", "v0.0.9").returncode == 0

    assert not (dest / "memory").exists()
    manifest = json.loads((dest / "evidence" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["backfilled"] is True
    assert manifest["sealed"] is True
    assert any("memory/movement.md" in w for w in manifest["warnings"])
    assert "partial" in (dest / "README.md").read_text(encoding="utf-8")


def test_backfill_all_covers_every_archive_on_disk(project_dir: Path):
    _legacy_archive(project_dir, "v0.0.9")
    _legacy_archive(project_dir, "v0.0.8")

    r = run(project_dir, "backfill", "--all")
    assert r.returncode == 0, r.stderr
    for tag in ("v0.0.8", "v0.0.9"):
        assert (project_dir / "docs" / "tags" / tag / "SUMMARY.md").is_file()
    parent = (project_dir / "docs" / "tags" / "README.md").read_text(encoding="utf-8")
    assert "[v0.0.8](v0.0.8/)" in parent and "[v0.0.9](v0.0.9/)" in parent


def test_backfill_requires_exactly_one_target(project_dir: Path):
    assert run(project_dir, "backfill").returncode == 2
    assert run(project_dir, "backfill", "v0.0.9", "--all").returncode == 2


def test_backfill_rejects_a_directory_that_is_not_an_archive(project_dir: Path):
    (project_dir / "docs" / "tags" / "scratch").mkdir(parents=True)
    r = run(project_dir, "backfill", "scratch")
    assert r.returncode == 2
    assert "not a tag archive" in r.stderr


def test_backfill_on_an_empty_tags_root_is_a_noop(project_dir: Path):
    r = run(project_dir, "backfill", "--all")
    assert r.returncode == 0, r.stderr
    assert "no tag archives" in r.stdout


def test_backfill_skips_an_already_sealed_archive(project_dir: Path):
    """Re-indexing a properly sealed tag would replace its recorded seal
    revision with whatever this run resolves — so it is skipped by default."""
    assert seal(project_dir).returncode == 0
    manifest_path = (
        project_dir / "docs" / "tags" / "v0.1.0" / "evidence" / "manifest.json"
    )
    before = manifest_path.read_bytes()

    r = run(project_dir, "backfill", "--all")
    assert r.returncode == 0, r.stderr
    assert "skipped" in r.stdout
    assert manifest_path.read_bytes() == before

    r = run(project_dir, "backfill", "v0.1.0", "--force")
    assert r.returncode == 0, r.stderr
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["backfilled"] is True


def test_backfill_records_the_tag_revision_not_todays_head(project_dir: Path):
    """A historical archive was sealed long ago; HEAD says nothing about it.
    `git tag <Tag>` does, and an untagged archive gets null rather than a
    fabricated revision."""
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
    _legacy_archive(project_dir, "v0.0.9")
    _git("add", "-A")
    _git("commit", "-q", "-m", "seal v0.0.9")
    _git("tag", "v0.0.9")
    seal_commit = _git("rev-parse", "v0.0.9^{commit}").strip()

    _legacy_archive(project_dir, "v0.0.8")  # never tagged
    (project_dir / "later.txt").write_text("later")
    _git("add", "-A")
    _git("commit", "-q", "-m", "much later work")
    assert _git("rev-parse", "HEAD").strip() != seal_commit

    assert run(project_dir, "backfill", "--all").returncode == 0

    tagged = json.loads(
        (project_dir / "docs" / "tags" / "v0.0.9" / "evidence" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    assert tagged["source_revision"] == seal_commit

    untagged = json.loads(
        (project_dir / "docs" / "tags" / "v0.0.8" / "evidence" / "manifest.json")
        .read_text(encoding="utf-8")
    )
    assert untagged["source_revision"] is None
