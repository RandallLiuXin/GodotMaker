from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
REMOVED_REFERENCES = (
    "memory.md",
    "memory/",
    "memory_subsystem",
    "memory/learning",
)
DEPRECATION_DOCS = {
    "docs/wiki/01-getting-started/upgrade-to-v1.md",
    "docs/zh/wiki/01-getting-started/upgrade-to-v1.md",
}
LEGACY_REFERENCE_IMPLEMENTATIONS = {
    "tools/publish.py",
}


def test_removed_templates_are_absent_and_structure_owns_architecture_contract():
    templates = REPO_ROOT / "templates"
    assert not (templates / "MEMORY.md").exists()
    assert not (templates / "memory_subsystem.md").exists()

    structure = (templates / "STRUCTURE.md").read_text(encoding="utf-8")
    for heading in (
        "## Architecture Ownership",
        "## Architecture Dependencies",
        "## Ordering Constraints",
        "## Stable Invariants",
    ):
        assert heading in structure


def test_dispatch_roles_read_structure_before_workers():
    for relative in ("skills/core/gm-build/SKILL.md", "skills/core/gm-fixgap/SKILL.md"):
        content = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "Read `STRUCTURE.md` before dispatching workers." in content


def test_structure_durable_sections_are_carried_across_tags():
    durable_sections = (
        "Architecture Ownership",
        "Architecture Dependencies",
        "Ordering Constraints",
        "Stable Invariants",
    )
    contracts = {
        "agents/decomposer.md": (REPO_ROOT / "agents/decomposer.md").read_text(
            encoding="utf-8"
        ),
        "skills/core/gm-gdd/SKILL.md": (
            REPO_ROOT / "skills/core/gm-gdd/SKILL.md"
        ).read_text(encoding="utf-8"),
    }

    for relative, content in contracts.items():
        assert "carry forward" in content, relative
        assert "previous tag" in content, relative
        for section in durable_sections:
            assert section in content, f"{relative}: {section}"

    gm_gdd = contracts["skills/core/gm-gdd/SKILL.md"]
    assert (
        "none of the four sections has been reset to template placeholders"
        in gm_gdd
    )


def test_active_framework_contracts_have_no_removed_subsystem_references():
    roots = (
        "templates",
        "skills",
        "tools",
        "hooks",
        "agents",
        "agent-runtimes",
        "migrations",
        "docs",
    )
    offenders = []
    for root_name in roots:
        for path in (REPO_ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {
                ".md",
                ".py",
                ".js",
                ".ts",
            }:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative.startswith("docs/update/"):
                continue
            if relative in LEGACY_REFERENCE_IMPLEMENTATIONS:
                continue
            content = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(content.splitlines(), start=1):
                normalized = line.casefold()
                if not any(reference in normalized for reference in REMOVED_REFERENCES):
                    continue
                if (
                    relative in DEPRECATION_DOCS
                    and "project-owned after upgrade" in normalized
                ):
                    continue
                if (
                    relative in DEPRECATION_DOCS
                    and "升级后" in line
                    and "项目自行所有" in line
                ):
                    continue
                offenders.append(f"{relative}:{line_number}")
    assert offenders == []
