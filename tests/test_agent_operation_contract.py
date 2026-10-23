"""Completeness checks for the canonical agent operation contract."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import publish  # noqa: E402


CONTRACT = REPO_ROOT / "agent-runtimes" / "capability-contract.md"
MAPPINGS = {
    "claude-code": (
        REPO_ROOT / "agent-runtimes" / "claude-code" / "references"
        / "runtime-mapping.md"
    ),
    "codex": (
        REPO_ROOT / "agent-runtimes" / "codex" / "references"
        / "runtime-mapping.md"
    ),
    "opencode": (
        REPO_ROOT / "agent-runtimes" / "opencode" / "references"
        / "runtime-mapping.md"
    ),
    "pi": (
        REPO_ROOT / "agent-runtimes" / "pi" / "references"
        / "runtime-mapping.md"
    ),
}
CLASSES = {"native", "emulated", "gated", "unsupported"}
CONTRACT_ROW = re.compile(r"^\| `([^`]+)` \| (.+) \|$", re.MULTILINE)
MAPPING_ROW = re.compile(
    r"^\| `([^`]+)` \| `(native|emulated|gated|unsupported)` \| (.+) \|$",
    re.MULTILINE,
)


def contract_operations() -> list[str]:
    return [name for name, _contract in CONTRACT_ROW.findall(
        CONTRACT.read_text(encoding="utf-8")
    )]


def published_skill_docs() -> list[Path]:
    docs: list[Path] = []
    for layer in ("core", "reviewer", "assets"):
        layer_dir = REPO_ROOT / "skills" / layer
        for skill_dir in layer_dir.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith("_"):
                docs.extend(skill_dir.glob("**/*.md"))
    return docs


def operation_mapping_rows(path: Path) -> list[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    section = re.search(
        r"^## Operation Mapping\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    assert section, f"{path} is missing its Operation Mapping section"
    return MAPPING_ROW.findall(section["body"])


def test_each_runtime_maps_every_canonical_operation_once():
    canonical = contract_operations()
    assert canonical
    assert not [name for name, count in Counter(canonical).items() if count != 1]

    for runtime, path in MAPPINGS.items():
        rows = operation_mapping_rows(path)
        names = [name for name, _classification, _invocation in rows]
        assert not [
            name for name, count in Counter(names).items() if count != 1
        ], f"{runtime} has duplicate operation rows"
        assert set(names) == set(canonical), (
            f"{runtime} mapping drift: missing={sorted(set(canonical) - set(names))}, "
            f"extra={sorted(set(names) - set(canonical))}"
        )
        for name, classification, invocation in rows:
            assert classification in CLASSES
            assert invocation.strip() and "TBD" not in invocation, (
                f"{runtime}.{name} needs a concrete invocation path"
            )


def test_published_skill_operation_surfaces_exist_in_canonical_contract():
    canonical = set(contract_operations())
    skill_docs = published_skill_docs()
    text = "\n".join(path.read_text(encoding="utf-8") for path in skill_docs)
    discovered: set[str] = set()

    for declaration in re.findall(
        r"<!-- agent-operations: ([a-z0-9_, -]+) -->", text
    ):
        discovered.update(item.strip() for item in declaration.split(","))

    role_operations = {
        "worker": "dispatch_worker",
        "reviewer": "dispatch_reviewer",
        "verifier": "dispatch_verifier",
        "analyst": "dispatch_analyst",
        "asset-producer": "dispatch_asset_producer",
        "decomposer": "dispatch_decomposer",
        "gdd-auditor": "dispatch_gdd_auditor",
    }
    for role in re.findall(r'subagent_type:\s*["\']([^"\']+)["\']', text):
        assert role in role_operations, f"unclassified published role: {role}"
        discovered.add(role_operations[role])

    surface_tokens = {
        "AskUserQuestion": "ask_user_question",
        "repair-attempt-accounting.md": "classify_repair_attempt",
        "asset_image_model": "generate_images",
        "vqa_model": "inspect_images",
        "godot-mcp": "access_godot_mcp",
        'isolation: "worktree"': "create_or_use_isolated_workspace",
        "WebFetch": "fetch_web_content",
    }
    for token, operation in surface_tokens.items():
        if token in text:
            discovered.add(operation)

    assert discovered
    assert discovered <= canonical, (
        "published skills use operations missing from the canonical matrix: "
        f"{sorted(discovered - canonical)}"
    )


@pytest.mark.parametrize(
    ("runtime", "skill_path", "user_entrypoint"),
    [
        ("codex", ".agents/skills/<skill-name>/SKILL.md", "$<skill-name>"),
        ("pi", ".pi/skills/<skill-name>/SKILL.md", "/skill:<skill-name>"),
    ],
)
def test_agent_driven_supporting_skill_invocation_is_executable(
    runtime: str, skill_path: str, user_entrypoint: str
):
    rows = operation_mapping_rows(MAPPINGS[runtime])
    operations = {
        name: (classification, invocation)
        for name, classification, invocation in rows
    }
    classification, invocation = operations["invoke_supporting_skill"]

    assert classification == "emulated"
    assert skill_path in invocation
    assert "task context" in invocation
    assert user_entrypoint in invocation
    assert "user-side entrypoint" in invocation


@pytest.mark.parametrize(
    ("agent", "runtime_root"),
    [
        (publish.AGENT_CODEX, ".agents"),
        (publish.AGENT_OPENCODE, ".opencode"),
        (publish.AGENT_PI, ".pi"),
    ],
)
def test_non_claude_supporting_skill_paths_publish_and_resolve(
    tmp_path: Path, agent: str, runtime_root: str
):
    target = tmp_path / agent
    skills = target / runtime_root / "skills"
    assert publish.publish_skills(REPO_ROOT, skills, agent) > 0
    assert publish.publish_runtime_references(REPO_ROOT, target, agent) >= 1

    godot_api = (skills / "godot-api" / "SKILL.md").read_text(encoding="utf-8")
    visual_qa = (skills / "visual-qa" / "SKILL.md").read_text(encoding="utf-8")
    screenshot = (skills / "screenshot" / "SKILL.md").read_text(encoding="utf-8")
    mapping = (
        target / runtime_root / "references" / "runtime-mapping.md"
    ).read_text(encoding="utf-8")

    assert "${CLAUDE_SKILL_DIR}" not in godot_api + visual_qa
    assert 'Skill(skill="visual-qa")' not in screenshot
    assert "<godot-api-skill-dir>" in godot_api
    assert "<visual-qa-skill-dir>" in visual_qa
    assert "`invoke_supporting_skill`" in mapping
    assert (skills / "godot-api" / "tools" / "ensure_doc_api.sh").is_file()
    assert (skills / "visual-qa" / "scripts" / "visual_qa.py").is_file()
