from importlib import import_module


migration = import_module("migrations.20260528004107_visual_asset_contract")


def test_adds_visual_asset_contract_after_asset_table(tmp_path):
    assets = tmp_path / "ASSETS.md"
    assets.write_text(
        "# Assets\n\n"
        "## Asset Table\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
        "|---|-----|------|------|------|-------------------|-----------|--------|\n"
        "| 1 | v0.1.0 | player | sprite | 32x32 | prompt | assets/player.png | generated |\n\n"
        "## Animated Sprites\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    text = assets.read_text(encoding="utf-8")
    assert "## Visual Asset Contract" in text
    assert text.index("## Asset Table") < text.index("## Visual Asset Contract")
    assert text.index("## Visual Asset Contract") < text.index("## Animated Sprites")


def test_visual_asset_contract_migration_is_idempotent(tmp_path):
    assets = tmp_path / "ASSETS.md"
    plan = tmp_path / "PLAN.md"
    scenes = tmp_path / "SCENES.md"
    assets.write_text(
        "# Assets\n\n"
        "## Asset Table\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
        "|---|-----|------|------|------|-------------------|-----------|--------|\n\n"
        "## Visual Asset Contract\n\n"
        "| Tag | Scene / Mechanic | Visible Object | Asset Row / Path | Runtime Size | Visual Role | Readability Requirement | Source |\n"
        "|-----|------------------|----------------|------------------|--------------|-------------|-------------------------|--------|\n",
        encoding="utf-8",
    )
    plan.write_text(
        "# Plan\n\n## Main Build\n\n### Runtime Asset Assignments\n\n"
        "| Task / Mechanic | Visible Content | Asset Row / Path | Runtime Size | Verification |\n"
        "|-----------------|-----------------|------------------|--------------|--------------|\n",
        encoding="utf-8",
    )
    scenes.write_text(
        "# Scenes\n\n## Scene: Gameplay\n\n### Asset bindings\n\n"
        "| Element | Asset Row / Path | Runtime Size | Visual Contract |\n"
        "|---------|------------------|--------------|-----------------|\n",
        encoding="utf-8",
    )

    before = {
        "assets": assets.read_text(encoding="utf-8"),
        "plan": plan.read_text(encoding="utf-8"),
        "scenes": scenes.read_text(encoding="utf-8"),
    }
    migration.migrate(tmp_path)

    assert assets.read_text(encoding="utf-8") == before["assets"]
    assert plan.read_text(encoding="utf-8") == before["plan"]
    assert scenes.read_text(encoding="utf-8") == before["scenes"]


def test_adds_runtime_asset_assignments_before_verify(tmp_path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        "# Plan\n\n"
        "## Main Build\n\n"
        "### Assets Needed\n\n"
        "- player sprite\n\n"
        "### Verify\n\n"
        "- tests pass\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    text = plan.read_text(encoding="utf-8")
    assert "### Runtime Asset Assignments" in text
    assert text.index("### Runtime Asset Assignments") < text.index("### Verify")
    assert "asset_name / assets/..." in text


def test_adds_runtime_asset_assignments_inside_main_build(tmp_path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    plan = tmp_path / "PLAN.md"
    plan.write_text(
        "# Plan\n\n"
        "## Warmup\n\n"
        "### Verify\n\n"
        "- warmup check\n\n"
        "## Main Build\n\n"
        "### Build Tasks\n\n"
        "| Task | Details |\n"
        "|---|---|\n\n"
        "### Verify\n\n"
        "- build check\n\n"
        "## Task Status\n\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    text = plan.read_text(encoding="utf-8")
    assert text.index("## Main Build") < text.index("### Runtime Asset Assignments")
    assert text.index("### Runtime Asset Assignments") < text.index("## Task Status")


def test_adds_asset_bindings_to_each_scene(tmp_path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    scenes = tmp_path / "SCENES.md"
    scenes.write_text(
        "# Scenes\n\n"
        "## Scene: Gameplay\n\n"
        "### Elements\n\n"
        "| Element | Position | Size | Description |\n"
        "|---|---|---|---|\n\n"
        "### Acceptance criteria\n\n"
        "- player visible\n\n"
        "## Scene: Results\n\n"
        "### Elements\n\n"
        "- score text\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    text = scenes.read_text(encoding="utf-8")
    assert text.count("### Asset bindings") == 2
    assert text.index("## Scene: Gameplay") < text.index("### Asset bindings") < text.index("### Acceptance criteria")
    assert "`not required this tag`" in text


def test_adds_asset_bindings_to_partially_migrated_scenes(tmp_path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    scenes = tmp_path / "SCENES.md"
    scenes.write_text(
        "# Scenes\n\n"
        "## Scene: Gameplay\n\n"
        "### Asset bindings\n\n"
        "| Element | Asset Row / Path | Runtime Size | Visual Contract |\n"
        "|---------|------------------|--------------|-----------------|\n\n"
        "### Acceptance criteria\n\n"
        "- player visible\n\n"
        "## Scene: Results\n\n"
        "### Elements\n\n"
        "- score text\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    text = scenes.read_text(encoding="utf-8")
    assert text.count("### Asset bindings") == 2
    gameplay = text.split("## Scene: Results", 1)[0]
    assert gameplay.count("### Asset bindings") == 1
