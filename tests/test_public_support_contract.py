"""Public support and capability docs must follow repository-owned facts."""
from __future__ import annotations

import sys
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from asset_family_registry import FAMILIES  # noqa: E402


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "README.zh-CN.md",
        "docs/wiki/01-getting-started/installation.md",
        "docs/zh/wiki/01-getting-started/installation.md",
        "docs/wiki/05-tools/check-env.md",
        "docs/zh/wiki/05-tools/check-env.md",
        "docs/wiki/07-contributing/development-setup.md",
        "docs/zh/wiki/07-contributing/development-setup.md",
        "docs/wiki/07-contributing/testing.md",
        "docs/zh/wiki/07-contributing/testing.md",
        "CONTRIBUTING.md",
    ],
)
def test_public_environment_baseline_matrix(relative):
    text = _read(relative)
    for tool, version in (("Python", "3.10"), ("Node.js", "22"), ("Godot", "4.5")):
        assert re.search(
            rf"{re.escape(tool)}.{{0,40}}{re.escape(version)}",
            text,
            re.DOTALL,
        ), f"{relative} is missing the supported {tool} {version} baseline"


def _asset_matrix(relative: str) -> dict[str, tuple[str, str, str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    in_table = False
    for line in _read(relative).splitlines():
        if line.startswith("| Family |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0].startswith("---"):
            continue
        rows[cells[0]] = (cells[1], cells[2], cells[3])
    return rows


def test_asset_skill_source_to_doc_matrix_matches_registry():
    expected = {
        name: (
            ", ".join(variant.variant for variant in family.variants),
            ", ".join(family.artifact_types) or "—",
            family.terminal_status,
        )
        for name, family in FAMILIES.items()
    }
    for relative in (
        "docs/wiki/03-skills/asset-skills.md",
        "docs/zh/wiki/03-skills/asset-skills.md",
    ):
        assert _asset_matrix(relative) == expected


def test_repository_inventory_docs_cover_shipped_directories():
    codebase_guides = [
        _read("docs/wiki/07-contributing/codebase-guide.md"),
        _read("docs/zh/wiki/07-contributing/codebase-guide.md"),
    ]
    hook_names = {
        path.name for path in (ROOT / "hooks").glob("*.py")
        if path.name != "__init__.py"
    }
    agent_names = {path.name for path in (ROOT / "agents").glob("*.md")}
    for guide in codebase_guides:
        for name in hook_names | agent_names:
            assert f"`{name}`" in guide

    core_guides = [
        _read("docs/wiki/03-skills/core-skills.md"),
        _read("docs/zh/wiki/03-skills/core-skills.md"),
    ]
    core_names = {
        path.name for path in (ROOT / "skills" / "core").iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }
    for guide in core_guides:
        for name in core_names:
            assert f"`{name}`" in guide or f"`/{name}`" in guide


def test_current_inventory_docs_do_not_use_stale_bare_totals():
    current_docs = "\n".join(
        _read(relative)
        for relative in (
            "CLAUDE.md",
            "ROADMAP.md",
            "docs/wiki/03-skills/skill-system.md",
            "docs/zh/wiki/03-skills/skill-system.md",
            "docs/wiki/07-contributing/development-setup.md",
            "docs/zh/wiki/07-contributing/development-setup.md",
            "docs/wiki/07-contributing/testing.md",
            "docs/zh/wiki/07-contributing/testing.md",
            "docs/wiki/07-contributing/codebase-guide.md",
            "docs/zh/wiki/07-contributing/codebase-guide.md",
            "docs/wiki/08-reference/glossary.md",
            "docs/zh/wiki/08-reference/glossary.md",
        )
    )
    for stale in (
        "8 hook scripts",
        "8 个 hook",
        "~320",
        "193+ tests",
        "Supporting skills (11)",
        "辅助技能（11 个）",
        "12 supporting skills",
        "十二个支撑技能",
    ):
        assert stale not in current_docs


def test_asset_and_provider_docs_are_in_site_navigation():
    navigation = _read("mkdocs.yml")
    required_paths = {
        "wiki/03-skills/asset-skills.md",
        "wiki/06-configuration/providers/README.md",
        *{
            f"wiki/06-configuration/providers/agent-runtimes/{name}.md"
            for name in ("claude-code", "codex", "opencode", "pi")
        },
        *{
            f"wiki/06-configuration/providers/image-vqa/{name}.md"
            for name in ("native", "codex", "gemini", "openai", "grok", "wan")
        },
    }
    for path in required_paths:
        assert path in navigation


def test_delivered_camera_and_tileset_capabilities_are_public():
    roadmap = _read("ROADMAP.md")
    readme = _read("README.md")
    assert "- [x] `R-050` **Phantom Camera guidance**" in roadmap
    assert "- [x] `R-100` **TileSet and TileMap support**" in roadmap
    assert "L0-L4-validated native `TileSet`" in readme
    assert "TileMap is not currently supported" not in readme

    public_home_pages = {
        "docs/index.md": (
            "TileSet generation and TileMap authoring are supported",
            "not currently supported",
        ),
        "docs/wiki/Home.md": (
            "TileSet generation and TileMap authoring are supported",
            "not currently supported",
        ),
        "docs/zh/index.md": (
            "已支持生成 TileSet 和编写 TileMap",
            "暂不支持",
        ),
        "docs/zh/wiki/Home.md": (
            "已支持生成 TileSet 和编写 TileMap",
            "暂不支持",
        ),
    }
    for relative, (supported, unsupported_marker) in public_home_pages.items():
        text = _read(relative)
        assert supported in text, (
            f"{relative} is missing the delivered TileMap capability"
        )
        assert not any(
            "TileMap" in line and unsupported_marker in line
            for line in text.splitlines()
        ), f"{relative} still claims TileMap is unsupported"
