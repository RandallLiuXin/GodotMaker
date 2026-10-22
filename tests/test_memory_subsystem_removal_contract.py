from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
REMOVED_REFERENCES = ("MEMORY.md", "memory/", "memory_subsystem")


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


def test_active_framework_contracts_have_no_removed_subsystem_references():
    roots = (
        "templates",
        "skills",
        "tools",
        "hooks",
        "agents",
        "agent-runtimes",
        "migrations",
    )
    offenders = []
    for root_name in roots:
        for path in (REPO_ROOT / root_name).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".js", ".ts"}:
                continue
            content = path.read_text(encoding="utf-8")
            if any(reference in content for reference in REMOVED_REFERENCES):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []
