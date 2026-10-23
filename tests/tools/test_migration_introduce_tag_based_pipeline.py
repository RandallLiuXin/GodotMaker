"""Tests for migrations/20260507120000_introduce_tag_based_pipeline.py.

Migration moves an existing GodotMaker game project (with a single
all-of-game PLAN.md and no ROADMAP.md) into the new tag-based layout:
docs/tags/v0.1.0/ archive + a stub ROADMAP.md, plus three schema
upgrades for legacy ASSETS.md / PLAN.md (Tag column, scene reference
rows, Tag Mechanics section). Every step is idempotent — second run is
a no-op.
"""
import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "20260507120000_introduce_tag_based_pipeline.py"


@pytest.fixture
def migration_module():
    spec = importlib.util.spec_from_file_location("tag_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    """A pre-tag-pipeline project: GDD, PLAN, the usual root docs, no ROADMAP."""
    (tmp_path / "GDD.md").write_text(
        "# Game Design Document: Tiny Test Game\n\nDesign content here.",
        encoding="utf-8",
    )
    (tmp_path / "PLAN.md").write_text(
        "# Game Plan: Tiny Test Game\n\n"
        "## Main Build\n\n"
        "### Systems & Components\n\n"
        "| System | Components | Purpose |\n"
        "|---|---|---|\n"
        "| MovementSystem | Transform | move things |\n"
        "| RenderSystem | Sprite | draw things |\n"
        "| HealthSystem | Health | track HP |\n",
        encoding="utf-8",
    )
    (tmp_path / "STRUCTURE.md").write_text("# Structure", encoding="utf-8")
    (tmp_path / "SCENES.md").write_text("# Scenes", encoding="utf-8")
    (tmp_path / "ASSETS.md").write_text("# Assets", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("# Memory", encoding="utf-8")
    return tmp_path


@pytest.fixture
def rich_legacy_project(tmp_path):
    """A pre-tag-pipeline project closer to GodotMakerTest1's actual shape:
    real ASSETS.md with a 7-column Asset Table, SCENES.md with multiple
    `## Scene:` headings (some with parentheticals), PLAN.md with
    `## Game Description` + `## Main Build` but no Tag Mechanics section.
    Used for end-to-end coverage of the C1 / C2 / C3 schema upgrades.
    """
    (tmp_path / "GDD.md").write_text(
        "# Game Design Document: Survivor Clone\n\nDesign content here.",
        encoding="utf-8",
    )
    (tmp_path / "PLAN.md").write_text(
        "# Game Plan: Survivor Clone\n\n"
        "## Game Description\n\n"
        "Top-down survivor game.\n\n"
        "## Main Build\n\n"
        "### Systems & Components\n\n"
        "| System | Purpose |\n"
        "|---|---|\n"
        "| MovementSystem | move things |\n"
        "| RenderSystem | draw things |\n",
        encoding="utf-8",
    )
    (tmp_path / "SCENES.md").write_text(
        "# Scenes: Survivor Clone\n\n"
        "## Scene: MainMenu\n\nElements...\n\n"
        "## Scene: CharacterSelect\n\nElements...\n\n"
        "## Scene: Gameplay\n\nElements...\n\n"
        "## Scene: PauseOverlay (CanvasLayer, layer = 20, child of Gameplay)\n\nElements...\n\n"
        "## Scene: GameOverOverlay (CanvasLayer, layer = 20)\n\nElements...\n",
        encoding="utf-8",
    )
    (tmp_path / "ASSETS.md").write_text(
        "# Assets: Survivor Clone\n\n"
        "## Asset Table\n\n"
        "| # | Name | Type | Size | Generation Params | File Path | Status |\n"
        "|---|------|------|------|-------------------|-----------|--------|\n"
        "| 1 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\n"
        "| 2 | mage | sprite | 16x16 | manifest | assets/mage.png | provided |\n"
        "| ... | ... | ... | ... | ... | ... | ... |\n",
        encoding="utf-8",
    )
    (tmp_path / "STRUCTURE.md").write_text("# Structure\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    return tmp_path


class TestMigration:
    def test_first_run_creates_archive_and_roadmap(self, migration_module, project):
        migration_module.migrate(project)
        assert (project / "ROADMAP.md").is_file()
        archive = project / "docs" / "tags" / "v0.1.0"
        assert archive.is_dir()
        assert (archive / "GDD-snapshot.md").is_file()
        assert (archive / "PLAN.md").is_file()
        assert (archive / "STRUCTURE.md").is_file()
        assert (archive / "SCENES.md").is_file()
        assert not (archive / "MEMORY.md").exists()
        # ASSETS.md is cross-tag; not archived
        assert not (archive / "ASSETS.md").exists()

    def test_first_run_preserves_root_files(self, migration_module, project):
        migration_module.migrate(project)
        # Root files MUST stay — gm-gdd subsequent-mode picks them up
        for f in ("GDD.md", "PLAN.md", "STRUCTURE.md", "SCENES.md", "ASSETS.md", "MEMORY.md"):
            assert (project / f).is_file(), f"{f} disappeared from root"

    def test_first_run_injects_tag_header_into_root_plan(self, migration_module, project):
        migration_module.migrate(project)
        plan_text = (project / "PLAN.md").read_text(encoding="utf-8")
        assert "**Tag:** v0.1.0" in plan_text, \
            "migration must inject `**Tag:** v0.1.0` so check_tag_archived passes"
        # Header should sit just below the first H1, not at the very top
        lines = plan_text.splitlines()
        h1_idx = next(i for i, line in enumerate(lines) if line.startswith("# "))
        tag_idx = next(i for i, line in enumerate(lines) if line.strip() == "**Tag:** v0.1.0")
        assert tag_idx > h1_idx, "Tag header must come after the H1 title"

    def test_archived_plan_carries_tag_header(self, migration_module, project):
        migration_module.migrate(project)
        archived = (project / "docs" / "tags" / "v0.1.0" / "PLAN.md").read_text(encoding="utf-8")
        assert "**Tag:** v0.1.0" in archived

    def test_first_run_does_not_create_git_tag(self, migration_module, project):
        # Migration explicitly does not auto-tag — the user decides
        migration_module.migrate(project)
        # No .git/refs/tags/ since no git repo and no auto-tag attempt
        assert not (project / ".git" / "refs" / "tags").exists()

    def test_roadmap_has_v010_entry_with_extracted_features(self, migration_module, project):
        migration_module.migrate(project)
        roadmap = (project / "ROADMAP.md").read_text(encoding="utf-8")
        assert "v0.1.0" in roadmap
        # Features should be extracted from the PLAN system table
        assert "MovementSystem" in roadmap
        assert "RenderSystem" in roadmap

    def test_roadmap_uses_project_name_from_gdd(self, migration_module, project):
        migration_module.migrate(project)
        roadmap = (project / "ROADMAP.md").read_text(encoding="utf-8")
        # _extract_project_name strips the "Game Design Document:" prefix
        assert "Tiny Test Game" in roadmap

    def test_second_run_is_noop(self, migration_module, project):
        migration_module.migrate(project)
        # Capture state after first run
        roadmap_before = (project / "ROADMAP.md").read_text(encoding="utf-8")
        archived_plan_before = (project / "docs" / "tags" / "v0.1.0" / "PLAN.md").read_text(encoding="utf-8")

        migration_module.migrate(project)

        # No changes — second run detected "already migrated" via per-step idempotency
        roadmap_after = (project / "ROADMAP.md").read_text(encoding="utf-8")
        archived_plan_after = (project / "docs" / "tags" / "v0.1.0" / "PLAN.md").read_text(encoding="utf-8")
        assert roadmap_before == roadmap_after
        assert archived_plan_before == archived_plan_after

    def test_skip_when_no_gdd_or_plan(self, migration_module, tmp_path):
        # Empty project — should skip without writing anything
        migration_module.migrate(tmp_path)
        assert not (tmp_path / "ROADMAP.md").exists()
        assert not (tmp_path / "docs").exists()

    def test_partial_archive_completes_on_rerun(self, migration_module, project):
        # If a previous run was interrupted (mkdir succeeded but ROADMAP write
        # didn't get there), re-running must complete the migration. Per-step
        # idempotency means there's no early-return bail-out — every step
        # checks its own end state.
        (project / "docs" / "tags" / "v0.1.0").mkdir(parents=True)
        migration_module.migrate(project)
        assert (project / "ROADMAP.md").is_file()
        assert (project / "docs" / "tags" / "v0.1.0" / "GDD-snapshot.md").is_file()

    def test_rerun_after_buggy_old_migration_state(self, migration_module, rich_legacy_project):
        # The exact recovery scenario this commit is built for: a project
        # ran the OLD (pre-fix) tag-pipeline migration, so it has the
        # archive + ROADMAP + Tag header on PLAN.md, but is still missing
        # the three schema gaps (ASSETS Tag column, scene rows, Tag
        # Mechanics). User drops the entry from applied_migrations.json
        # and re-publishes — re-running migrate() must complete the
        # gaps without re-doing the archive copy / ROADMAP write.
        # Step 1: simulate the post-old-migration state.
        (rich_legacy_project / "ROADMAP.md").write_text(
            "# Roadmap: Survivor Clone\n\n## v0.1.0 — Initial implementation\n",
            encoding="utf-8",
        )
        archive = rich_legacy_project / "docs" / "tags" / "v0.1.0"
        archive.mkdir(parents=True)
        (archive / "GDD-snapshot.md").write_text("snapshot", encoding="utf-8")
        for n in ("PLAN.md", "STRUCTURE.md", "SCENES.md", "MEMORY.md"):
            (archive / n).write_text(f"old {n}", encoding="utf-8")
        # Inject Tag header into root PLAN.md (simulates the old migration's
        # one schema upgrade that DID land).
        plan = rich_legacy_project / "PLAN.md"
        plan.write_text(
            "# Game Plan: Survivor Clone\n\n**Tag:** v0.1.0\n\n"
            + plan.read_text(encoding="utf-8").split("# Game Plan: Survivor Clone\n\n", 1)[1],
            encoding="utf-8",
        )
        roadmap_before = (rich_legacy_project / "ROADMAP.md").read_bytes()
        archive_snapshot_before = (archive / "GDD-snapshot.md").read_bytes()

        # Step 2: re-run migration.
        migration_module.migrate(rich_legacy_project)

        # Step 3: existing archive + ROADMAP untouched (per-step idempotency
        # short-circuits each "already done" step).
        assert (rich_legacy_project / "ROADMAP.md").read_bytes() == roadmap_before
        assert (archive / "GDD-snapshot.md").read_bytes() == archive_snapshot_before

        # Step 4: the three schema gaps are NOW filled.
        assets_text = (rich_legacy_project / "ASSETS.md").read_text(encoding="utf-8")
        assert "| # | Tag | Name |" in assets_text
        assert "references/scene_main_menu.png" in assets_text
        plan_text = (rich_legacy_project / "PLAN.md").read_text(encoding="utf-8")
        assert "## Tag Mechanics" in plan_text

    def test_aborts_cleanly_on_non_utf8_plan(self, migration_module, project, capsys):
        # CP-1252-encoded PLAN.md (\xe9 = é) is not valid UTF-8 — strict read
        # at the top of migrate() must abort BEFORE any mutation.
        (project / "PLAN.md").write_bytes(b"# Game Plan: Latin1\n\n\xe9clair section\n")
        migration_module.migrate(project)
        # No mutations: neither ROADMAP.md nor docs/tags/ created
        assert not (project / "ROADMAP.md").exists()
        assert not (project / "docs").exists()
        # Original PLAN.md byte-for-byte preserved
        assert (project / "PLAN.md").read_bytes() == b"# Game Plan: Latin1\n\n\xe9clair section\n"
        out = capsys.readouterr().out
        assert "[error]" in out and "UTF-8" in out

    def test_handles_missing_optional_root_files(self, migration_module, tmp_path):
        # GDD + PLAN required; others optional. Migration should still succeed.
        (tmp_path / "GDD.md").write_text("# Game Design Document: Minimal\n", encoding="utf-8")
        (tmp_path / "PLAN.md").write_text("# Game Plan: Minimal\n", encoding="utf-8")
        migration_module.migrate(tmp_path)
        assert (tmp_path / "ROADMAP.md").is_file()
        archive = tmp_path / "docs" / "tags" / "v0.1.0"
        assert (archive / "GDD-snapshot.md").is_file()
        assert (archive / "PLAN.md").is_file()
        # SCENES/ASSETS/STRUCTURE were skipped — not in archive
        assert not (archive / "STRUCTURE.md").is_file()


class TestTagHeaderInjection:
    def test_injects_after_first_h1(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        plan.write_text("# Game Plan: X\n\nbody\n", encoding="utf-8")
        modified = migration_module._inject_tag_header(plan, "v0.1.0")
        assert modified is True
        content = plan.read_text(encoding="utf-8")
        assert content.startswith("# Game Plan: X\n\n**Tag:** v0.1.0\n")

    def test_idempotent_when_header_already_present(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        original = "# Game Plan: X\n\n**Tag:** v0.5.0\n\nbody\n"
        plan.write_text(original, encoding="utf-8")
        modified = migration_module._inject_tag_header(plan, "v0.1.0")
        assert modified is False
        # Existing header (even with a different tag value) must not be overwritten
        assert plan.read_text(encoding="utf-8") == original

    def test_prepends_when_no_h1(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        plan.write_text("just plain prose\n", encoding="utf-8")
        modified = migration_module._inject_tag_header(plan, "v0.1.0")
        assert modified is True
        assert plan.read_text(encoding="utf-8").startswith("**Tag:** v0.1.0\n")


class TestProjectNameExtraction:
    def test_strips_gdd_prefix(self, migration_module, tmp_path):
        gdd = tmp_path / "GDD.md"
        gdd.write_text("# Game Design Document: My Game\n", encoding="utf-8")
        plan = tmp_path / "PLAN.md"
        plan.write_text("# something else\n", encoding="utf-8")
        assert migration_module._extract_project_name(gdd, plan) == "My Game"

    def test_strips_plan_prefix(self, migration_module, tmp_path):
        gdd = tmp_path / "GDD.md"
        gdd.write_text("not a heading\n", encoding="utf-8")
        plan = tmp_path / "PLAN.md"
        plan.write_text("# Game Plan: Survivor Clone\n", encoding="utf-8")
        assert migration_module._extract_project_name(gdd, plan) == "Survivor Clone"

    def test_falls_back_to_untitled(self, migration_module, tmp_path):
        gdd = tmp_path / "GDD.md"
        gdd.write_text("plain text\n", encoding="utf-8")
        plan = tmp_path / "PLAN.md"
        plan.write_text("plain text\n", encoding="utf-8")
        assert migration_module._extract_project_name(gdd, plan) == "Untitled"


class TestSceneIdFromHeading:
    """Scene heading → snake_case id, matching .tscn file naming."""

    @pytest.mark.parametrize("heading,expected", [
        ("## Scene: MainMenu",                                       "main_menu"),
        ("## Scene: CharacterSelect",                                "character_select"),
        ("## Scene: Gameplay",                                       "gameplay"),
        ("## Scene: PauseOverlay (CanvasLayer, layer = 20)",         "pause_overlay"),
        ("## Scene: LevelUpOverlay (CanvasLayer, layer = 20, ...)",  "level_up_overlay"),
        ("## Scene: GameOverOverlay (CanvasLayer, layer = 20)",      "game_over_overlay"),
    ])
    def test_camelcase_with_optional_parenthetical(self, migration_module, heading, expected):
        assert migration_module._scene_id_from_heading(heading) == expected


class TestTagColumnInjection:
    """C2: Asset Table / 3D Models / Audio / Budget tables get a Tag column."""

    def test_seven_col_asset_table_becomes_eight_col(self, migration_module, tmp_path):
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "# Assets\n\n"
            "## Asset Table\n\n"
            "| # | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|------|------|------|-------------------|-----------|--------|\n"
            "| 1 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\n"
            "| 2 | mage | sprite | 16x16 | manifest | assets/mage.png | provided |\n",
            encoding="utf-8",
        )
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        text = assets.read_text(encoding="utf-8")
        assert "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |" in text
        assert "| 1 | v0.1.0 | knight |" in text
        assert "| 2 | v0.1.0 | mage |" in text

    def test_already_eight_col_is_skipped(self, migration_module, tmp_path):
        assets = tmp_path / "ASSETS.md"
        before = (
            "# Assets\n\n"
            "## Asset Table\n\n"
            "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|-----|------|------|------|-------------------|-----------|--------|\n"
            "| 1 | v0.1.0 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\n"
        )
        assets.write_text(before, encoding="utf-8")
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        assert assets.read_text(encoding="utf-8") == before

    def test_placeholder_dot_row_stays_dot(self, migration_module, tmp_path):
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "## Asset Table\n\n"
            "| # | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|------|------|------|-------------------|-----------|--------|\n"
            "| 1 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\n"
            "| ... | ... | ... | ... | ... | ... | ... |\n",
            encoding="utf-8",
        )
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        text = assets.read_text(encoding="utf-8")
        # Real row backfilled with v0.1.0
        assert "| 1 | v0.1.0 | knight |" in text
        # Placeholder row stays all `...`
        assert "| ... | ... | ... | ... | ... | ... | ... | ... |" in text

    def test_budget_table_gets_tag_after_asset(self, migration_module, tmp_path):
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "## Budget Tracking\n\n"
            "| Asset | Tool | Cost | Notes |\n"
            "|-------|------|------|-------|\n"
            "| knight | gemini | $0.01 | |\n"
            "| **Total** | | **$0.01** | |\n",
            encoding="utf-8",
        )
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        text = assets.read_text(encoding="utf-8")
        # Header gets Tag at position 1 (after Asset)
        assert "| Asset | Tag | Tool | Cost | Notes |" in text
        # Data row gets v0.1.0
        assert "| knight | v0.1.0 | gemini |" in text
        # Summary `**Total**` row gets `—`, not the tag
        assert "| **Total** | — |" in text

    def test_empty_asset_table_header_only(self, migration_module, tmp_path):
        # Asset Table with header + separator but no data rows yet — common
        # state for projects between scaffold and the first /gm-asset run.
        # Tag column should still be inserted into header + separator without
        # crashing on the absent data-row loop.
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "## Asset Table\n\n"
            "| # | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|------|------|------|-------------------|-----------|--------|\n"
            "\nMore prose after the table.\n",
            encoding="utf-8",
        )
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        text = assets.read_text(encoding="utf-8")
        # Header now has 8 columns including Tag in slot 2.
        assert "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |" in text
        # Separator row also got a new cell — 8 cells means 9 pipes.
        sep_line = next(
            line for line in text.splitlines()
            if line.strip().startswith("|") and "---" in line
        )
        assert sep_line.count("|") == 9, f"expected 8-cell separator, got: {sep_line!r}"
        # Trailing prose untouched.
        assert "More prose after the table." in text

    def test_crlf_input_normalizes_to_lf(self, migration_module, tmp_path):
        # ASSETS.md edited on Windows often arrives with CRLF. The migration's
        # _atomic_write_text normalizes line endings to LF on every rewrite
        # (deliberate — so repo-tracked files diff cleanly across platforms).
        # This test pins that contract: CRLF input becomes fully-LF output,
        # not a half-and-half mix.
        assets = tmp_path / "ASSETS.md"
        crlf = (
            "## Asset Table\r\n\r\n"
            "| # | Name | Type | Size | Generation Params | File Path | Status |\r\n"
            "|---|------|------|------|-------------------|-----------|--------|\r\n"
            "| 1 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\r\n"
        )
        assets.write_bytes(crlf.encode("utf-8"))
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        out = assets.read_bytes()
        assert b"\r\n" not in out, "migration should normalize CRLF → LF"
        assert b"| # | Tag | Name |" in out
        # And data row's tag was backfilled even though input was CRLF.
        assert b"| 1 | v0.1.0 | knight |" in out

    def test_multiple_tables_in_one_file_all_migrate(self, migration_module, tmp_path):
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "## Asset Table\n\n"
            "| # | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|------|------|------|-------------------|-----------|--------|\n"
            "| 1 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\n\n"
            "## 3D Models\n\n"
            "| # | Name | Format | Poly Budget | Generation Tool | File Path | Status |\n"
            "|---|------|--------|-------------|-----------------|-----------|--------|\n"
            "| 1 | barrel | .glb | 200 | tripo3d | assets/barrel.glb | provided |\n\n"
            "## Audio\n\n"
            "| # | Name | Type | Duration | File Path | Status |\n"
            "|---|------|------|----------|-----------|--------|\n"
            "| 1 | jump | sfx | 0.3s | assets/jump.wav | provided |\n",
            encoding="utf-8",
        )
        migration_module._add_tag_column_to_assets(assets, "v0.1.0")
        text = assets.read_text(encoding="utf-8")
        assert "| # | Tag | Name | Type | Size |" in text
        assert "| # | Tag | Name | Format |" in text
        assert "| # | Tag | Name | Type | Duration |" in text


class TestSceneReferenceRows:
    """C1: each `## Scene:` in SCENES.md → MISSING row in ASSETS.md Asset Table."""

    @pytest.fixture
    def assets_with_8col_table(self, tmp_path):
        """ASSETS.md with the post-Tag-column 8-column Asset Table."""
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "# Assets\n\n"
            "## Asset Table\n\n"
            "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|-----|------|------|------|-------------------|-----------|--------|\n"
            "| 1 | v0.1.0 | knight | sprite | 16x16 | manifest | assets/knight.png | provided |\n",
            encoding="utf-8",
        )
        return assets

    def test_scenes_become_missing_rows(self, migration_module, tmp_path, assets_with_8col_table):
        scenes = tmp_path / "SCENES.md"
        scenes.write_text(
            "## Scene: MainMenu\n\n## Scene: Gameplay\n",
            encoding="utf-8",
        )
        migration_module._add_scene_reference_rows(assets_with_8col_table, scenes, "v0.1.0")
        text = assets_with_8col_table.read_text(encoding="utf-8")
        assert "references/scene_main_menu.png" in text
        assert "references/scene_gameplay.png" in text
        # Tag column populated, status MISSING
        assert "| 2 | v0.1.0 | scene_main_menu | reference |" in text
        assert "| MISSING |" in text

    def test_existing_scene_row_is_skipped_with_state_preserved(self, migration_module, tmp_path):
        # ASSETS.md already has scene_main_menu — only scene_gameplay should be added
        # AND the existing scene_main_menu row's `provided` status must NOT
        # be downgraded to MISSING (regression: a naive "remove + re-add"
        # implementation would lose the user's hand-edits).
        assets = tmp_path / "ASSETS.md"
        assets.write_text(
            "## Asset Table\n\n"
            "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
            "|---|-----|------|------|------|-------------------|-----------|--------|\n"
            "| 1 | v0.1.0 | scene_main_menu | reference | — | — | references/scene_main_menu.png | provided |\n",
            encoding="utf-8",
        )
        scenes = tmp_path / "SCENES.md"
        scenes.write_text("## Scene: MainMenu\n## Scene: Gameplay\n", encoding="utf-8")

        migration_module._add_scene_reference_rows(assets, scenes, "v0.1.0")
        text = assets.read_text(encoding="utf-8")
        # MainMenu row stays exactly as it was — `provided`, not MISSING
        assert text.count("references/scene_main_menu.png") == 1
        assert "scene_main_menu | reference | — | — | references/scene_main_menu.png | provided" in text
        # Gameplay row newly added as MISSING
        assert "references/scene_gameplay.png" in text
        assert "scene_gameplay | reference | — | — | references/scene_gameplay.png | MISSING" in text

    def test_parenthetical_scene_names_normalize_correctly(self, migration_module, tmp_path, assets_with_8col_table):
        scenes = tmp_path / "SCENES.md"
        scenes.write_text(
            "## Scene: PauseOverlay (CanvasLayer, layer = 20, child of Gameplay)\n",
            encoding="utf-8",
        )
        migration_module._add_scene_reference_rows(assets_with_8col_table, scenes, "v0.1.0")
        text = assets_with_8col_table.read_text(encoding="utf-8")
        assert "references/scene_pause_overlay.png" in text
        # The `(CanvasLayer, ...)` part must NOT leak into the path
        assert "CanvasLayer" not in text or text.count("CanvasLayer") == 0

    def test_no_scene_headings_is_skipped(self, migration_module, tmp_path, assets_with_8col_table):
        scenes = tmp_path / "SCENES.md"
        scenes.write_text("# Scenes (header only, no scenes yet)\n", encoding="utf-8")
        before = assets_with_8col_table.read_text(encoding="utf-8")
        migration_module._add_scene_reference_rows(assets_with_8col_table, scenes, "v0.1.0")
        # No-op
        assert assets_with_8col_table.read_text(encoding="utf-8") == before


class TestPlanMechanicSections:
    """C3: PLAN.md gets `## Tag Mechanics` section if missing.
    Inherited Mechanics is NEVER injected (INITIAL_TAG hardcoded to v0.1.0)."""

    def test_injects_after_game_description(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "# Game Plan: X\n\n"
            "## Game Description\n\n"
            "It's a game.\n\n"
            "## Main Build\n\n"
            "Stuff.\n",
            encoding="utf-8",
        )
        migration_module._add_plan_mechanic_sections(plan)
        text = plan.read_text(encoding="utf-8")
        assert "## Tag Mechanics" in text
        # Tag Mechanics must come after Game Description and before Main Build
        idx_desc = text.index("## Game Description")
        idx_tag = text.index("## Tag Mechanics")
        idx_build = text.index("## Main Build")
        assert idx_desc < idx_tag < idx_build

    def test_inherited_mechanics_never_injected(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "# Game Plan: X\n\n## Game Description\n\nIt's a game.\n\n## Main Build\n",
            encoding="utf-8",
        )
        migration_module._add_plan_mechanic_sections(plan)
        text = plan.read_text(encoding="utf-8")
        # Per templates/PLAN.md the v0.1.0 (first tag) PLAN omits this section.
        assert "## Inherited Mechanics" not in text

    def test_idempotent_when_already_present(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        original = (
            "# Game Plan: X\n\n## Game Description\n\nIt's a game.\n\n"
            "## Tag Mechanics\n\n- [v0.1.0-M1] WASD movement\n\n## Main Build\n"
        )
        plan.write_text(original, encoding="utf-8")
        migration_module._add_plan_mechanic_sections(plan)
        # Existing section is left exactly as-is — no duplication.
        assert plan.read_text(encoding="utf-8") == original

    def test_injects_before_first_h2_when_no_game_description(self, migration_module, tmp_path):
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "# Game Plan: X\n\n**Tag:** v0.1.0\n\n## Main Build\n\nStuff.\n",
            encoding="utf-8",
        )
        migration_module._add_plan_mechanic_sections(plan)
        text = plan.read_text(encoding="utf-8")
        assert "## Tag Mechanics" in text
        idx_tag = text.index("## Tag Mechanics")
        idx_build = text.index("## Main Build")
        assert idx_tag < idx_build


class TestRichLegacyProjectEndToEnd:
    """End-to-end coverage: a project shaped like GodotMakerTest1 — real
    7-col ASSETS.md, multi-scene SCENES.md, PLAN.md without Tag
    Mechanics — must come out of migrate() with all three schema gaps
    closed. Idempotent on a second run."""

    def test_full_run_closes_all_three_schema_gaps(self, migration_module, rich_legacy_project):
        migration_module.migrate(rich_legacy_project)

        # C2: ASSETS.md Asset Table is now 8-col with Tag backfilled
        assets_text = (rich_legacy_project / "ASSETS.md").read_text(encoding="utf-8")
        assert "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |" in assets_text
        assert "| 1 | v0.1.0 | knight |" in assets_text
        assert "| 2 | v0.1.0 | mage |" in assets_text

        # C1: every scene from SCENES.md has a MISSING reference row
        for sid in ("main_menu", "character_select", "gameplay", "pause_overlay", "game_over_overlay"):
            assert f"references/scene_{sid}.png" in assets_text, f"missing row for scene_{sid}"
            assert f"| scene_{sid} | reference |" in assets_text

        # C3: PLAN.md has Tag Mechanics section but NO Inherited Mechanics
        plan_text = (rich_legacy_project / "PLAN.md").read_text(encoding="utf-8")
        assert "## Tag Mechanics" in plan_text
        assert "## Inherited Mechanics" not in plan_text

    def test_second_run_is_strictly_noop_on_rich_project(self, migration_module, rich_legacy_project):
        # Regression guard: any future change that breaks per-step
        # idempotency on a richer project lights this up. Compare every
        # mutated file byte-for-byte before vs after.
        migration_module.migrate(rich_legacy_project)
        paths = [
            rich_legacy_project / "ASSETS.md",
            rich_legacy_project / "PLAN.md",
            rich_legacy_project / "SCENES.md",
            rich_legacy_project / "ROADMAP.md",
            # Archived PLAN.md is a separate file from the root PLAN.md and
            # carries the pre-injection content — use full paths, not just
            # `name`, or both PLAN.md entries collide on the dict key.
            rich_legacy_project / "docs" / "tags" / "v0.1.0" / "PLAN.md",
        ]
        snapshots = {p: p.read_bytes() for p in paths}

        migration_module.migrate(rich_legacy_project)

        for path, before in snapshots.items():
            rel = path.relative_to(rich_legacy_project)
            assert path.read_bytes() == before, f"{rel} changed on second run"
