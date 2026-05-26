"""Tests for migrate.py and migrations/_helpers.py."""
import json
import os
import subprocess
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

from migrate import (
    APPLIED_FILE_REL,
    TrackerCorruptionError,
    applied_ids,
    baseline_applied,
    create_migration_template,
    discover_migrations,
    parse_migration_filename,
    read_applied,
    run_migration_script,
    run_migrations,
    write_applied,
)


# ---------------------------------------------------------------------------
# parse_migration_filename
# ---------------------------------------------------------------------------

class TestParseMigrationFilename:
    def test_valid_filename_returns_full_stem(self):
        # ID is the whole filename minus .py — NOT just the timestamp prefix
        assert parse_migration_filename("20260429100000_fix_state_path.py") \
            == "20260429100000_fix_state_path"

    def test_same_second_distinct_slugs_have_distinct_ids(self):
        """Two scripts created in the same UTC second with different slugs
        must produce different IDs — this is the BLOCKER the codex review
        flagged."""
        a = parse_migration_filename("20260429100000_fix_a.py")
        b = parse_migration_filename("20260429100000_fix_b.py")
        assert a is not None and b is not None
        assert a != b

    def test_underscore_in_slug_ok(self):
        assert parse_migration_filename("20260101000000_a_b_c.py") \
            == "20260101000000_a_b_c"

    def test_uppercase_slug_rejected(self):
        assert parse_migration_filename("20260429100000_FixPath.py") is None

    def test_short_timestamp_rejected(self):
        assert parse_migration_filename("2026042910_x.py") is None

    def test_non_py_rejected(self):
        assert parse_migration_filename("20260429100000_x.txt") is None

    def test_no_slug_rejected(self):
        assert parse_migration_filename("20260429100000_.py") is None

    def test_helper_files_rejected(self):
        assert parse_migration_filename("_helpers.py") is None
        assert parse_migration_filename("__init__.py") is None
        assert parse_migration_filename("README.md") is None


# ---------------------------------------------------------------------------
# discover_migrations
# ---------------------------------------------------------------------------

class TestDiscoverMigrations:
    def test_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)
        assert discover_migrations() == []

    def test_missing_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path / "nope")
        assert discover_migrations() == []

    def test_filters_invalid_names(self, tmp_path, monkeypatch):
        (tmp_path / "20260101000000_first.py").write_text("pass")
        (tmp_path / "_helpers.py").write_text("pass")
        (tmp_path / "README.md").write_text("# doc")
        (tmp_path / "20260102000000_second.py").write_text("pass")
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)

        names = [p.name for p in discover_migrations()]
        assert names == ["20260101000000_first.py", "20260102000000_second.py"]

    def test_chronological_sort(self, tmp_path, monkeypatch):
        # Write out of order to verify sort
        (tmp_path / "20260301120000_c.py").write_text("pass")
        (tmp_path / "20260101120000_a.py").write_text("pass")
        (tmp_path / "20260201120000_b.py").write_text("pass")
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)

        names = [p.name for p in discover_migrations()]
        assert names == [
            "20260101120000_a.py",
            "20260201120000_b.py",
            "20260301120000_c.py",
        ]

    def test_legacy_pair_directory_emits_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        """Pre-refactor `0.X_to_0.Y/` directories are silently ignored
        by the discovery scan (only flat timestamped files match). For
        downstream forks who haven't migrated their layout, that means
        scripts inside such directories never run with no signal.
        Verify the protective stderr warning fires."""
        (tmp_path / "0.3_to_0.4").mkdir()
        (tmp_path / "0.3_to_0.4" / "001_old.py").write_text("pass")
        (tmp_path / "20260101000000_new.py").write_text("pass")
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)

        files = discover_migrations()
        # Old layout is NOT picked up
        assert [p.name for p in files] == ["20260101000000_new.py"]

        # But a warning was emitted to stderr
        err = capsys.readouterr().err
        assert "0.3_to_0.4" in err
        assert "no longer recognised" in err


# ---------------------------------------------------------------------------
# read/write_applied — strict validation
# ---------------------------------------------------------------------------

class TestAppliedTracking:
    def test_read_missing_returns_empty(self, tmp_path):
        """Missing file is the legitimate 'no tracker yet' state."""
        assert read_applied(tmp_path) == {"applied": []}

    def test_read_invalid_json_raises_corruption(self, tmp_path):
        """Corruption must surface, not be silently treated as empty —
        otherwise a damaged tracker would re-run all of project history."""
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        f.write_text("not json")
        with pytest.raises(TrackerCorruptionError):
            read_applied(tmp_path)

    def test_read_utf16_tracker_raises_corruption(self, tmp_path):
        """Windows PowerShell 5.1 default `echo > file` writes UTF-16 LE
        with BOM. read_applied() must convert that into a controlled
        TrackerCorruptionError instead of leaking a raw UnicodeDecodeError
        traceback (round-4 codex MAJOR-1)."""
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        # Even valid JSON, but encoded as UTF-16 with BOM — what PowerShell
        # 5.1 `echo '{"applied": []}' > file` actually produces. Python's
        # "utf-16" codec (no -le/-be suffix) emits a BOM by default.
        f.write_bytes('{"applied": []}'.encode("utf-16"))
        with pytest.raises(TrackerCorruptionError):
            read_applied(tmp_path)

    def test_read_wrong_top_level_shape_raises(self, tmp_path):
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        f.write_text('["array", "not", "object"]')
        with pytest.raises(TrackerCorruptionError):
            read_applied(tmp_path)

    def test_read_applied_not_a_list_raises(self, tmp_path):
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        f.write_text('{"applied": "not a list"}')
        with pytest.raises(TrackerCorruptionError):
            read_applied(tmp_path)

    def test_read_entry_missing_field_raises(self, tmp_path):
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"applied": [
            {"id": "20260101000000_a", "applied_at": "2026-04-29T10:00:00Z"},
            # missing 'source'
        ]}))
        with pytest.raises(TrackerCorruptionError, match="source"):
            read_applied(tmp_path)

    def test_read_entry_wrong_field_type_raises(self, tmp_path):
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"applied": [
            {"id": 12345, "applied_at": "2026-04-29T10:00:00Z", "source": "baseline"},
        ]}))
        with pytest.raises(TrackerCorruptionError, match="must be a string"):
            read_applied(tmp_path)

    def test_read_entry_unknown_source_raises(self, tmp_path):
        f = tmp_path / APPLIED_FILE_REL
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"applied": [
            {"id": "20260101000000_a", "applied_at": "2026-04-29T10:00:00Z",
             "source": "imported"},
        ]}))
        with pytest.raises(TrackerCorruptionError, match="source"):
            read_applied(tmp_path)

    def test_write_then_read_roundtrip(self, tmp_path):
        data = {"applied": [
            {"id": "20260101000000_first", "applied_at": "2026-04-29T10:00:00Z",
             "source": "baseline"}
        ]}
        write_applied(tmp_path, data)
        assert read_applied(tmp_path) == data

    def test_write_is_atomic(self, tmp_path):
        """A successful write_applied leaves no .tmp file behind."""
        data = {"applied": []}
        write_applied(tmp_path, data)
        f = tmp_path / APPLIED_FILE_REL
        tmp = f.with_name(f.name + ".tmp")
        assert f.exists()
        assert not tmp.exists()

    def test_applied_ids_extracts_set(self):
        data = {"applied": [
            {"id": "20260101000000_a", "applied_at": "x", "source": "baseline"},
            {"id": "20260202000000_b", "applied_at": "x", "source": "executed"},
        ]}
        assert applied_ids(data) == {"20260101000000_a", "20260202000000_b"}


# ---------------------------------------------------------------------------
# baseline_applied
# ---------------------------------------------------------------------------

class TestBaselineApplied:
    def test_baselines_all_current(self, tmp_path, monkeypatch):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "20260101000000_a.py").write_text("pass")
        (migrations / "20260202000000_b.py").write_text("pass")
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", migrations)

        target = tmp_path / "project"
        target.mkdir()
        n = baseline_applied(target)

        assert n == 2
        data = read_applied(target)
        ids = applied_ids(data)
        assert ids == {"20260101000000_a", "20260202000000_b"}
        assert all(e["source"] == "baseline" for e in data["applied"])

    def test_baseline_empty_migrations_dir(self, tmp_path, monkeypatch):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", migrations)

        target = tmp_path / "project"
        target.mkdir()
        assert baseline_applied(target) == 0
        assert read_applied(target) == {"applied": []}

    def test_baseline_twice_overwrites_cleanly(self, tmp_path, monkeypatch):
        """A second baseline should not accumulate duplicates — it overwrites."""
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "20260101000000_a.py").write_text("pass")
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", migrations)

        target = tmp_path / "project"
        target.mkdir()
        baseline_applied(target)
        baseline_applied(target)

        data = read_applied(target)
        assert len(data["applied"]) == 1
        assert applied_ids(data) == {"20260101000000_a"}


# ---------------------------------------------------------------------------
# run_migration_script
# ---------------------------------------------------------------------------

class TestRunMigrationScript:
    def test_successful_script(self, tmp_path):
        marker = tmp_path / "target" / "migrated.txt"
        marker.parent.mkdir()
        script = tmp_path / "20260101000000_test.py"
        script.write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "migrated.txt").write_text("done")
        """))
        assert run_migration_script(script, marker.parent) is True
        assert marker.read_text() == "done"

    def test_script_without_migrate_function(self, tmp_path):
        script = tmp_path / "20260101000000_bad.py"
        script.write_text("x = 1\n")
        assert run_migration_script(script, tmp_path) is False

    def test_script_that_raises(self, tmp_path):
        script = tmp_path / "20260101000000_fail.py"
        script.write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                raise RuntimeError("intentional failure")
        """))
        assert run_migration_script(script, tmp_path) is False


# ---------------------------------------------------------------------------
# run_migrations (integration)
# ---------------------------------------------------------------------------

class TestRunMigrations:
    def _setup(self, tmp_path, monkeypatch):
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        target = tmp_path / "project"
        target.mkdir()
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", migrations)
        return migrations, target

    def test_no_migrations_returns_true(self, tmp_path, monkeypatch):
        _, target = self._setup(tmp_path, monkeypatch)
        assert run_migrations(target) is True

    def test_legacy_target_with_no_migrations_bootstraps_empty_tracker(
        self, tmp_path, monkeypatch
    ):
        """Legacy target (has version, no tracker) + empty migrations/
        must bootstrap an empty applied_migrations.json. Otherwise the
        next release that ships V files would hit the legacy branch
        again with a non-empty migrations/ — and we now raise on that
        ambiguous case (see test_legacy_target_with_migrations_raises).
        Bootstrapping here closes the BLOCKER round-3 codex flagged."""
        _, target = self._setup(tmp_path, monkeypatch)
        (target / ".godotmaker").mkdir()
        (target / ".godotmaker" / "version").write_text("0.2.0\n")

        assert run_migrations(target) is True

        # Tracker file now exists (bootstrap), with empty applied list
        assert (target / APPLIED_FILE_REL).exists()
        assert read_applied(target) == {"applied": []}

    def test_empty_pending_no_op(self, tmp_path, monkeypatch):
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_a.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "should_not_run.txt").write_text("x")
        """))
        # Pre-record as applied (note: id is full stem now)
        write_applied(target, {"applied": [
            {"id": "20260101000000_a",
             "applied_at": "2026-04-29T10:00:00Z",
             "source": "executed"}
        ]})
        assert run_migrations(target) is True
        assert not (target / "should_not_run.txt").exists()

    def test_applies_in_chronological_order(self, tmp_path, monkeypatch):
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_first.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                log = target / "log.txt"
                log.write_text(log.read_text() + "first\\n" if log.exists() else "first\\n")
        """))
        (migrations / "20260202000000_second.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                log = target / "log.txt"
                log.write_text(log.read_text() + "second\\n" if log.exists() else "second\\n")
        """))
        assert run_migrations(target) is True
        assert (target / "log.txt").read_text() == "first\nsecond\n"

    def test_records_applied_after_each_success(self, tmp_path, monkeypatch):
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_a.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "a.txt").write_text("a")
        """))
        (migrations / "20260202000000_b.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "b.txt").write_text("b")
        """))
        assert run_migrations(target) is True

        data = read_applied(target)
        assert applied_ids(data) == {"20260101000000_a", "20260202000000_b"}
        assert all(e["source"] == "executed" for e in data["applied"])

    def test_aborts_on_failure_preserves_partial_progress(self, tmp_path, monkeypatch):
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_ok.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "ok.txt").write_text("ok")
        """))
        (migrations / "20260202000000_boom.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                raise RuntimeError("boom")
        """))
        assert run_migrations(target) is False

        # First migration ran and was recorded
        assert (target / "ok.txt").exists()
        data = read_applied(target)
        assert applied_ids(data) == {"20260101000000_ok"}

        # Re-running picks up where it left off — fix the bad script and try again
        (migrations / "20260202000000_boom.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "fixed.txt").write_text("now ok")
        """))
        assert run_migrations(target) is True
        assert applied_ids(read_applied(target)) == {
            "20260101000000_ok", "20260202000000_boom",
        }

    def test_legacy_target_with_migrations_auto_bootstraps(
        self, tmp_path, monkeypatch, capsys
    ):
        """Legacy target (no tracker) + non-empty migrations/ now
        auto-creates `{"applied": []}` and runs every pending migration.

        Reasoning: for any project stamped at a version predating a given
        migration's introduction, the migration could not have run yet
        (it didn't exist when the project was stamped), so the answer is
        unambiguously "no, not applied". The previous behaviour raised
        an error to force the user through manual recovery — that
        friction had no payoff, since the auto-decision is correct in
        this code path. The hand-applied edge case (user ran migrations
        manually on the old version) still has the explicit
        `python tools/migrate.py <target> --baseline` opt-out —
        run_migrations doesn't override that; main() exits before
        run_migrations on `--baseline`.
        """
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_legacy_target_v.py").write_text(
            textwrap.dedent("""\
                from pathlib import Path
                def migrate(target: Path) -> None:
                    (target / "migration_ran.txt").write_text("yes")
            """)
        )
        # Mark target as a previously published project (legacy).
        (target / ".godotmaker").mkdir()
        (target / ".godotmaker" / "version").write_text("0.2.0\n")

        assert run_migrations(target) is True

        # The auto-bootstrap created the tracker file (was: assert NOT exists).
        assert (target / APPLIED_FILE_REL).exists()

        # Migration body actually ran (was: assert NOT run). This is the
        # whole point of auto-bootstrap — the migration could not have
        # run on the legacy stamp, so we run it now.
        assert (target / "migration_ran.txt").exists()
        assert (target / "migration_ran.txt").read_text() == "yes"

        # The migration that ran is recorded so the next publish skips it.
        assert applied_ids(read_applied(target)) == {
            "20260101000000_legacy_target_v",
        }

        # User-facing print explains what happened and how to opt out.
        # The auto-bootstrap path needs to surface --baseline as the
        # alternative for hand-applied state, otherwise a user who DID
        # apply migrations manually has no way to discover the override.
        out = capsys.readouterr().out
        assert "Legacy target detected" in out
        assert "--baseline" in out

    def test_legacy_then_new_migration_runs_normally(
        self, tmp_path, monkeypatch
    ):
        """Full two-release transition that the BLOCKER cared about:

        Release A introduces tracking with an empty migrations/. A legacy
        target reaches Release A via the bootstrap path (empty tracker
        written). Release B then ships the first real migration. The
        target is no longer legacy (has tracker), so the migration must
        actually execute on the next publish.
        """
        migrations, target = self._setup(tmp_path, monkeypatch)
        # Legacy target on the old version
        (target / ".godotmaker").mkdir()
        (target / ".godotmaker" / "version").write_text("0.2.0\n")

        # ── Release A: tracking machinery, empty migrations/ ─────────
        # (migrations/ is empty by setup)
        assert run_migrations(target) is True
        # Bootstrap fired, tracker exists with empty list
        assert read_applied(target) == {"applied": []}

        # ── Release B: first real migration appears ───────────────────
        (migrations / "20260301120000_first_real_v.py").write_text(
            textwrap.dedent("""\
                from pathlib import Path
                def migrate(target: Path) -> None:
                    (target / "release_b_marker.txt").write_text("ran")
            """)
        )
        assert run_migrations(target) is True

        # Migration ACTUALLY ran (this is the bug fix — previously it
        # would have been baselined and skipped)
        assert (target / "release_b_marker.txt").exists()
        assert (target / "release_b_marker.txt").read_text() == "ran"

        data = read_applied(target)
        assert applied_ids(data) == {"20260301120000_first_real_v"}
        # And source is "executed" — proof it ran, not baselined
        assert data["applied"][0]["source"] == "executed"

    def test_no_auto_baseline_for_fresh_project(self, tmp_path, monkeypatch):
        """Fresh target (no .godotmaker/version) should run pending migrations
        normally — the auto-baseline only triggers for legacy upgrades."""
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_a.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "a.txt").write_text("a")
        """))
        # No .godotmaker/version file
        assert run_migrations(target) is True
        # Actually executed
        assert (target / "a.txt").exists()
        data = read_applied(target)
        assert data["applied"][0]["source"] == "executed"

    def test_baseline_then_run_is_no_op(self, tmp_path, monkeypatch):
        """publish.py FRESH path simulation: baseline first, then a subsequent
        run_migrations() must execute nothing — every V is already recorded."""
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_a.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "should_not_run.txt").write_text("x")
        """))
        (migrations / "20260202000000_b.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "also_should_not_run.txt").write_text("x")
        """))

        # Simulate publish.py FRESH path: baseline marks everything applied
        baseline_applied(target)

        # Subsequent run_migrations finds no pending — nothing executes
        assert run_migrations(target) is True
        assert not (target / "should_not_run.txt").exists()
        assert not (target / "also_should_not_run.txt").exists()

        # And nothing got upgraded from "baseline" to "executed"
        data = read_applied(target)
        assert all(e["source"] == "baseline" for e in data["applied"])

    def test_corrupt_tracker_surfaces_error(self, tmp_path, monkeypatch):
        """run_migrations must propagate TrackerCorruptionError instead of
        silently treating a damaged tracker as 'no migrations applied'."""
        migrations, target = self._setup(tmp_path, monkeypatch)
        (migrations / "20260101000000_a.py").write_text(textwrap.dedent("""\
            from pathlib import Path
            def migrate(target: Path) -> None:
                (target / "ran.txt").write_text("x")
        """))
        # Mark as having been published (so we hit the read_applied path,
        # not the legacy auto-baseline path)
        (target / ".godotmaker").mkdir()
        (target / ".godotmaker" / "version").write_text("0.2.0\n")
        # Plant a corrupt tracker
        (target / APPLIED_FILE_REL).write_text("totally not json")

        with pytest.raises(TrackerCorruptionError):
            run_migrations(target)
        # Migration body did NOT run despite the failure
        assert not (target / "ran.txt").exists()


# ---------------------------------------------------------------------------
# create_migration_template
# ---------------------------------------------------------------------------

class TestCreateMigrationTemplate:
    def test_creates_with_timestamp_and_slug(self, tmp_path, monkeypatch):
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)
        path = create_migration_template("fix-state-path")
        assert path.parent == tmp_path
        # 14-digit timestamp + "_fix_state_path.py"
        assert path.name.endswith("_fix_state_path.py")
        mid = parse_migration_filename(path.name)
        assert mid is not None
        assert mid.endswith("_fix_state_path")
        # File contains the template
        content = path.read_text(encoding="utf-8")
        assert "def migrate(target: Path)" in content

    def test_sanitises_uppercase_and_special_chars(self, tmp_path, monkeypatch):
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)
        path = create_migration_template("Fix State!! Path")
        assert path.name.endswith("_fix_state_path.py")

    def test_empty_slug_after_sanitisation_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", tmp_path)
        with pytest.raises(ValueError):
            create_migration_template("!!!")

    def test_creates_migrations_dir_if_missing(self, tmp_path, monkeypatch):
        target_dir = tmp_path / "fresh"
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", target_dir)
        assert not target_dir.exists()
        path = create_migration_template("init")
        assert target_dir.exists()
        assert path.parent == target_dir


# ---------------------------------------------------------------------------
# select_migration_action (publish.py routing)
# ---------------------------------------------------------------------------

class TestSelectMigrationAction:
    """The pure decision function that routes publish.py between
    baseline_applied() and run_migrations(). Locks the routing as a
    contract so refactors of publish.main() can't silently drift."""

    def test_fresh_baselines(self):
        from publish import select_migration_action
        assert select_migration_action("FRESH", force=False) == "baseline"
        assert select_migration_action("FRESH", force=True) == "baseline"

    def test_major_force_baselines(self):
        from publish import select_migration_action
        assert select_migration_action("MAJOR", force=True) == "baseline"

    def test_major_without_force_defensive_run(self):
        """MAJOR without --force is filtered out by check_version_upgrade,
        so this path is unreachable in production. Test the defensive
        default anyway."""
        from publish import select_migration_action
        assert select_migration_action("MAJOR", force=False) == "run"

    def test_same_runs(self):
        from publish import select_migration_action
        assert select_migration_action("SAME", force=False) == "run"
        assert select_migration_action("SAME", force=True) == "run"

    def test_patch_runs(self):
        from publish import select_migration_action
        assert select_migration_action("PATCH", force=False) == "run"

    def test_minor_runs(self):
        from publish import select_migration_action
        assert select_migration_action("MINOR", force=False) == "run"
        assert select_migration_action("MINOR", force=True) == "run"

    def test_downgrade_with_force_runs(self):
        from publish import select_migration_action
        assert select_migration_action("DOWNGRADE", force=True) == "run"


# ---------------------------------------------------------------------------
# MAJOR --force cleanup of applied_migrations.json
# ---------------------------------------------------------------------------

class TestMajorForceBaselineRebuild:
    """End-to-end behaviour test for the MAJOR --force re-baseline path.

    Complements TestPublishMainMigrationRouting below: that class verifies
    publish.main() routes correctly; this one verifies the resulting
    library-level interaction (cleanup + baseline) actually reaches the
    intended state.
    """

    def test_baseline_after_cleanup_recreates_tracker(
        self, tmp_path, monkeypatch
    ):
        """Seed an old applied_migrations.json, simulate cleanup by
        deleting it, then baseline_applied() recreates it with the
        current set of V files (and only those)."""
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "20260101000000_new_only.py").write_text("pass")
        monkeypatch.setattr("migrate.MIGRATIONS_DIR", migrations)

        target = tmp_path / "project"
        target.mkdir()
        # Pre-existing tracker from old MAJOR with stale entries
        write_applied(target, {"applied": [
            {"id": "20250101000000_old_major_v",
             "applied_at": "2025-01-01T00:00:00Z",
             "source": "executed"},
        ]})

        # Simulate publish.py MAJOR --force cleanup
        (target / APPLIED_FILE_REL).unlink()

        # select_migration_action returns "baseline" for (MAJOR, force=True)
        n = baseline_applied(target)
        assert n == 1

        # Tracker now reflects ONLY current V files
        data = read_applied(target)
        assert applied_ids(data) == {"20260101000000_new_only"}
        # No stale entry from the old MAJOR
        assert "20250101000000_old_major_v" not in applied_ids(data)


# ---------------------------------------------------------------------------
# publish.main() integration — actually drives main() and asserts which
# migration entry point is invoked for each upgrade level.
# ---------------------------------------------------------------------------

class TestPublishMainMigrationRouting:
    """Drive publish.main() with all side effects stubbed, asserting which
    migration entry point is invoked for each upgrade level.

    Closes the gap codex round-2 flagged: TestSelectMigrationAction tests
    the pure decision helper, but does not prove main() actually calls it
    or routes through to baseline_applied / run_migrations correctly.
    These tests replace baseline_applied / run_migrations with recording
    mocks and exercise main() end-to-end across FRESH / SAME / PATCH /
    MINOR / MAJOR-force scenarios.
    """

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        """Stub every side-effecting helper in publish.main() except the
        two migration entry points (which become recording mocks)."""
        import publish

        target = tmp_path / "target"
        target.mkdir()

        def _no_op(*a, **kw):
            return None

        # File deployment / interactive / subprocess helpers — irrelevant
        # to migration routing, replaced with no-ops.
        for name in (
            "publish_skills", "publish_shared_refs", "publish_directory",
            "deploy_agent_hook_config", "deploy_agent_instructions", "create_godotmaker_yaml",
            "create_project_config", "deploy_stage_schemas",
            "create_project_dirs", "register_mcp", "register_codex_mcp",
            "register_godot_permissions",
            "ensure_gitignore", "ensure_gitattributes",
            "ensure_git_repo", "write_target_version",
        ):
            monkeypatch.setattr(publish, name, _no_op)
        monkeypatch.setattr(publish, "read_godot_path",
                            lambda *a, **kw: "godot")

        # Migration entry points — recording mocks
        baseline_calls: list = []
        run_calls: list = []

        def _baseline(t):
            baseline_calls.append(t)
            return 0

        def _run(t):
            run_calls.append(t)
            return True

        monkeypatch.setattr(publish, "baseline_applied", _baseline)
        monkeypatch.setattr(publish, "run_migrations", _run)

        return {
            "target": target,
            "baseline_calls": baseline_calls,
            "run_calls": run_calls,
        }

    def _run_main(self, monkeypatch, target, force=False):
        """Invoke publish.main() via sys.argv."""
        import publish
        argv = ["publish.py", str(target)]
        if force:
            argv.append("--force")
        monkeypatch.setattr(sys, "argv", argv)
        publish.main()

    def _seed_target_version(self, target, version):
        """Pre-populate .godotmaker/version on the target."""
        gm = target / ".godotmaker"
        gm.mkdir(exist_ok=True)
        (gm / "version").write_text(version + "\n")

    def _force_source_version(self, monkeypatch, major, minor, patch):
        """Override read_source_version so tests don't depend on the
        actual VERSION file in the repo root."""
        from _version import SemVer
        import publish
        monkeypatch.setattr(publish, "read_source_version",
                            lambda _: SemVer(major, minor, patch))


    def test_fresh_install_calls_baseline_only(self, env, monkeypatch):
        """No existing .godotmaker/version → FRESH → baseline."""
        self._force_source_version(monkeypatch, 0, 4, 0)
        self._run_main(monkeypatch, env["target"])
        assert len(env["baseline_calls"]) == 1
        assert env["baseline_calls"][0] == env["target"]
        assert env["run_calls"] == []

    def test_same_version_calls_run_only(self, env, monkeypatch):
        """Source ver == target ver → SAME → run (Flyway-style same-version
        republish; locally added migrations should still apply)."""
        self._force_source_version(monkeypatch, 0, 4, 0)
        self._seed_target_version(env["target"], "0.4.0")
        self._run_main(monkeypatch, env["target"])
        assert env["baseline_calls"] == []
        assert len(env["run_calls"]) == 1
        assert env["run_calls"][0] == env["target"]

    def test_patch_upgrade_calls_run_only(self, env, monkeypatch):
        self._force_source_version(monkeypatch, 0, 4, 1)
        self._seed_target_version(env["target"], "0.4.0")
        self._run_main(monkeypatch, env["target"])
        assert env["baseline_calls"] == []
        assert len(env["run_calls"]) == 1

    def test_minor_upgrade_with_confirm_calls_run_only(
        self, env, monkeypatch
    ):
        """MINOR upgrade prompts for confirmation; on 'y', run (not baseline)."""
        self._force_source_version(monkeypatch, 0, 5, 0)
        self._seed_target_version(env["target"], "0.4.0")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        self._run_main(monkeypatch, env["target"])
        assert env["baseline_calls"] == []
        assert len(env["run_calls"]) == 1

    def test_major_force_calls_baseline_only(self, env, monkeypatch):
        """MAJOR + --force → baseline (NOT run; the cleanup wipes state
        first, then baseline marks current migrations as applied)."""
        self._force_source_version(monkeypatch, 1, 0, 0)
        self._seed_target_version(env["target"], "0.4.0")
        self._run_main(monkeypatch, env["target"], force=True)
        assert len(env["baseline_calls"]) == 1
        assert env["run_calls"] == []

    def test_major_force_cleanup_removes_applied_migrations_file(
        self, env, monkeypatch
    ):
        """The MAJOR --force cleanup loop must delete an existing
        applied_migrations.json (so the subsequent baseline starts fresh).
        Replaces the previous source-text grep test with a real one."""
        self._force_source_version(monkeypatch, 1, 0, 0)
        self._seed_target_version(env["target"], "0.4.0")

        applied_file = env["target"] / ".godotmaker" / "applied_migrations.json"
        applied_file.write_text(
            '{"applied":[{"id":"old_v","applied_at":"x","source":"executed"}]}'
        )
        assert applied_file.exists()

        self._run_main(monkeypatch, env["target"], force=True)

        # baseline_applied is mocked, so the file is NOT recreated here;
        # we only verify the cleanup loop did its job.
        assert not applied_file.exists()
        assert len(env["baseline_calls"]) == 1
        assert env["run_calls"] == []

    def test_downgrade_force_calls_run_only(self, env, monkeypatch):
        """Forced downgrade goes through run_migrations() (not baseline)
        for routing consistency. In practice pending is always empty
        because applied is a superset of disk, but the call must happen
        and must NOT route through baseline. Closes the round-3 coverage
        gap the codex review flagged: every other level had a publish.main()
        integration test; downgrade was only covered by the pure helper."""
        # source < target (publish a 0.3.x onto a project that's at 0.4.0)
        self._force_source_version(monkeypatch, 0, 3, 0)
        self._seed_target_version(env["target"], "0.4.0")
        self._run_main(monkeypatch, env["target"], force=True)
        assert env["baseline_calls"] == []
        assert len(env["run_calls"]) == 1
        assert env["run_calls"][0] == env["target"]

    def test_run_migrations_tracker_corruption_exits_2(
        self, env, monkeypatch, capsys
    ):
        """publish.main() must catch TrackerCorruptionError, print a
        clear message to stderr, and exit with code 2. Without this
        test the corruption-handling try/except is dead code from a
        coverage standpoint (round-3 codex finding)."""
        import publish
        self._force_source_version(monkeypatch, 0, 4, 1)
        self._seed_target_version(env["target"], "0.4.0")

        def _raise_corruption(_target):
            raise TrackerCorruptionError("simulated tracker corruption")
        monkeypatch.setattr(publish, "run_migrations", _raise_corruption)

        with pytest.raises(SystemExit) as exc:
            self._run_main(monkeypatch, env["target"])
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "tracker is corrupt" in err
        assert "simulated tracker corruption" in err


# ---------------------------------------------------------------------------
# migrate.py CLI error handling
# ---------------------------------------------------------------------------

class TestMigrateCliErrors:
    """Legacy --from / --to detection in migrate.py main(). Anyone who
    scripted the old CLI gets a targeted message instead of argparse's
    generic 'unrecognized arguments'."""

    def test_legacy_from_flag_emits_targeted_error(
        self, monkeypatch, capsys
    ):
        import migrate
        monkeypatch.setattr(sys, "argv",
                            ["migrate.py", "/some/target", "--from", "0.1.0"])
        with pytest.raises(SystemExit) as exc:
            migrate.main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--from" in err
        assert "no longer supported" in err
        assert "applied_migrations.json" in err
        # And the user gets the new equivalents
        assert "--baseline" in err

    def test_legacy_to_flag_with_equals_form_detected(
        self, monkeypatch, capsys
    ):
        """--to=0.2.0 form (equals separator) must also be caught."""
        import migrate
        monkeypatch.setattr(sys, "argv",
                            ["migrate.py", "/some/target", "--to=0.2.0"])
        with pytest.raises(SystemExit) as exc:
            migrate.main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--to" in err

    def test_no_legacy_flags_proceeds_normally(self, monkeypatch, tmp_path):
        """Sanity check: without legacy flags, main() proceeds past the
        sniff (it'll fail later for other reasons, but not exit 2 with
        the legacy-flag message)."""
        import migrate
        # Use --new which doesn't need a target
        monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)
        monkeypatch.setattr(sys, "argv", ["migrate.py", "--new", "test"])
        with pytest.raises(SystemExit) as exc:
            migrate.main()
        # --new succeeds and exits 0
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# ensure_git_tracked (_helpers.py)
# ---------------------------------------------------------------------------

class TestEnsureGitTracked:
    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temp git repo."""
        subprocess.run(["git", "init"], cwd=str(tmp_path),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=str(tmp_path), capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=str(tmp_path), capture_output=True, timeout=10)
        return tmp_path

    def _import_helper(self):
        """Import ensure_git_tracked from migrations/_helpers.py."""
        migrations_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "migrations",
        )
        if migrations_dir not in sys.path:
            sys.path.insert(0, migrations_dir)
        from _helpers import ensure_git_tracked
        return ensure_git_tracked

    def test_skips_nonexistent_path(self, tmp_path, capsys):
        ensure = self._import_helper()
        ensure(tmp_path, "no/such/path", "test")
        assert "[skip]" in capsys.readouterr().out

    def test_adds_existing_path(self, git_repo, capsys):
        ensure = self._import_helper()
        d = git_repo / ".godotmaker" / "hooks"
        d.mkdir(parents=True)
        (d / "test.py").write_text("pass")
        ensure(git_repo, ".godotmaker/hooks/", ".godotmaker/hooks/")
        out = capsys.readouterr().out
        assert "[done]" in out

    def test_idempotent(self, git_repo, capsys):
        """Running twice on the same path should succeed both times."""
        ensure = self._import_helper()
        f = git_repo / "test.txt"
        f.write_text("hello")
        ensure(git_repo, "test.txt", "test.txt")
        ensure(git_repo, "test.txt", "test.txt")
        out = capsys.readouterr().out
        assert out.count("[done]") == 2


# ---------------------------------------------------------------------------
# check_version_upgrade (VersionCheckResult) — unchanged from before
# ---------------------------------------------------------------------------

class TestCheckVersionUpgrade:
    """check_version_upgrade still drives the prompt/block flow; the migration
    invocation logic is now decoupled and lives in publish.main() via
    select_migration_action()."""

    def _setup_versions(self, tmp_path, source_ver, target_ver=None):
        """Create repo with VERSION file and optionally a target with version."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "VERSION").write_text(source_ver)
        (repo / "CHANGELOG.md").write_text("# Changelog\n")

        target = tmp_path / "target"
        target.mkdir()
        if target_ver:
            gm = target / ".godotmaker"
            gm.mkdir()
            (gm / "version").write_text(target_ver)

        return repo, target

    def test_fresh_install(self, tmp_path):
        from publish import check_version_upgrade, VersionCheckResult
        repo, target = self._setup_versions(tmp_path, "0.4.0")
        result = check_version_upgrade(repo, target, force=False)
        assert isinstance(result, VersionCheckResult)
        assert result.proceed is True
        assert result.level == "FRESH"
        assert result.target_ver is None

    def test_same_version(self, tmp_path):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.4.0", "0.4.0")
        result = check_version_upgrade(repo, target, force=False)
        assert result.proceed is True
        assert result.level == "SAME"

    def test_patch_upgrade(self, tmp_path):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.4.1", "0.4.0")
        result = check_version_upgrade(repo, target, force=False)
        assert result.proceed is True
        assert result.level == "PATCH"

    def test_minor_upgrade_without_force_prompts(self, tmp_path, monkeypatch):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.5.0", "0.4.0")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        result = check_version_upgrade(repo, target, force=False)
        assert result.proceed is True
        assert result.level == "MINOR"

    def test_minor_upgrade_declined(self, tmp_path, monkeypatch):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.5.0", "0.4.0")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        result = check_version_upgrade(repo, target, force=False)
        assert result.proceed is False
        assert result.level == "MINOR"

    def test_minor_upgrade_with_force(self, tmp_path):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.5.0", "0.4.0")
        result = check_version_upgrade(repo, target, force=True)
        assert result.proceed is True
        assert result.level == "MINOR"

    def test_major_upgrade_without_force_prompts(self, tmp_path, monkeypatch):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "1.0.0", "0.4.0")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        result = check_version_upgrade(repo, target, force=False)
        assert result.proceed is False
        assert result.level == "MAJOR"

    def test_major_upgrade_with_force(self, tmp_path):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "1.0.0", "0.4.0")
        result = check_version_upgrade(repo, target, force=True)
        assert result.proceed is True
        assert result.level == "MAJOR"

    def test_downgrade_blocked(self, tmp_path):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.3.0", "0.4.0")
        result = check_version_upgrade(repo, target, force=False)
        assert result.proceed is False
        assert result.level == "DOWNGRADE"

    def test_downgrade_with_force(self, tmp_path):
        from publish import check_version_upgrade
        repo, target = self._setup_versions(tmp_path, "0.3.0", "0.4.0")
        result = check_version_upgrade(repo, target, force=True)
        assert result.proceed is True
        assert result.level == "DOWNGRADE"
