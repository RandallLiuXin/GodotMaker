"""Tests for publish_shared_refs() and the _shared/ exclusion in publish_skills()."""
import json
import os
import re
import sys
import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
))

from publish import (
    AGENT_CLAUDE_CODE,
    AGENT_CODEX,
    AGENT_OPENCODE,
    render_agent_instructions,
    publish_skills,
    publish_shared_refs,
)
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "core" / "_shared"
ROOT_INSTRUCTION_TEMPLATES = [
    REPO_ROOT / "templates" / "game-claude.md",
]
def _load_shared_manifest() -> dict[str, object]:
    manifest_path = SHARED_DIR / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _shared_source_text(filename: str) -> str:
    return (SHARED_DIR / filename).read_text(encoding="utf-8")


def _skill_content(skill_name: str) -> str:
    skill_md = REPO_ROOT / "skills" / "core" / skill_name / "SKILL.md"
    return skill_md.read_text(encoding="utf-8")


def _shared_refs_for_skill(
    manifest: dict[str, object],
    skill_name: str,
    agent: str | None = None,
) -> list[str]:
    files = manifest.get("files", {})
    assert isinstance(files, dict)
    return [
        filename for filename, entry in files.items()
        if _manifest_entry_applies(entry, agent)
        and skill_name in _manifest_entry_targets(entry)
    ]


def _manifest_entry_targets(entry: object) -> list[str]:
    if isinstance(entry, list):
        return entry
    assert isinstance(entry, dict)
    targets = entry.get("skills", entry.get("targets"))
    assert isinstance(targets, list)
    return targets


def _manifest_entry_applies(entry: object, agent: str | None) -> bool:
    if agent is None or not isinstance(entry, dict):
        return True
    agents = entry.get("agents")
    return agents is None or agent in agents


def _manifest_entry_agents(entry: object) -> list[str | None]:
    if not isinstance(entry, dict):
        return [None]
    agents = entry.get("agents")
    if agents is None:
        return [None]
    assert isinstance(agents, list)
    return agents


def _root_instruction_indexes(
    filename: str,
    skill_name: str,
    agent: str | None = None,
) -> bool:
    """Return true when a root instruction template indexes a deployed ref.

    Source templates are Claude-shaped and Codex publish renders them to
    `.agents/...`, so Codex-only indexes may be injected during render instead
    of living in the shared Claude template.
    """
    if agent is not None:
        content = render_agent_instructions(REPO_ROOT, agent) or ""
        runtime_root = {
            AGENT_CLAUDE_CODE: ".claude",
            AGENT_CODEX: ".agents",
            AGENT_OPENCODE: ".opencode",
        }[agent]
        return (
            f"{runtime_root}/skills/{skill_name}/references/{filename}"
            in content
        )

    deployed_paths = [
        f".claude/skills/{skill_name}/references/{filename}",
        f".agents/skills/{skill_name}/references/{filename}",
        f".opencode/skills/{skill_name}/references/{filename}",
    ]
    for template_path in ROOT_INSTRUCTION_TEMPLATES:
        if not template_path.exists():
            continue
        content = template_path.read_text(encoding="utf-8")
        if any(path in content for path in deployed_paths):
            return True
    return False


def _shared_ref_indexes(
    manifest: dict[str, object],
    filename: str,
    skill_name: str,
) -> bool:
    for shared_filename in _shared_refs_for_skill(manifest, skill_name):
        if shared_filename == filename:
            continue
        if f"references/{filename}" in _shared_source_text(shared_filename):
            return True
    return False


def _assert_no_legacy_runtime_ref(
    content: str,
    location: str,
    filename: str,
) -> None:
    assert f"orchestrator/{filename}" not in content, \
        f"{location} still references legacy orchestrator/{filename}"
    assert f"_shared/{filename}" not in content, \
        f"{location} should not reference _shared/{filename} at runtime"


class TestSharedSurfaceDocs:
    """Shared source docs stay GodotMaker/Claude-first, not Codex-inline."""

    def test_shared_dir_does_not_hold_agent_runtime_docs(self):
        forbidden = {
            "agent-capabilities.md",
            "claude-code-tools.md",
            "codex-tools.md",
            "codex-delegation-worktree.md",
        }
        present = {path.name for path in SHARED_DIR.glob("*.md")}

        assert not (present & forbidden), (
            "Agent runtime docs belong under agent-runtimes/, not "
            "skills/core/_shared/."
        )

    def test_shared_source_docs_do_not_inline_codex_compatibility(self):
        checked_paths = list((REPO_ROOT / "agents").glob("*.md"))
        checked_paths.extend(SHARED_DIR.glob("*.md"))

        offenders: list[str] = []
        for path in checked_paths:
            text = path.read_text(encoding="utf-8")
            if "runtime-local" in text:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)} contains runtime-local"
                )
            for forbidden in (
                "Codex:",
                "In Codex",
                ".agents/",
                "spawn_agent(",
                "agent_type=\"worker\"",
            ):
                if forbidden in text:
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)} contains {forbidden}"
                    )

        assert not offenders, (
            "Shared GodotMaker docs should not carry inline Codex "
            "compatibility prose:\n" + "\n".join(offenders)
        )

    def test_reviewer_keeps_claude_skill_discovery_glob(self):
        reviewer = (REPO_ROOT / "agents" / "reviewer.md").read_text(
            encoding="utf-8"
        )

        assert "glob `.claude/skills/*/checklist.md`" in reviewer
        assert ".agents/skills/*/checklist.md" not in reviewer


def _make_repo(tmp_path: Path,
               shared_files: dict[str, list[str]] | None = None,
               skills: list[str] | None = None) -> Path:
    """Build a minimal fake repo with skills/core/* and an optional _shared/."""
    repo = tmp_path / "repo"
    skills = skills or ["gm-build", "gm-fixgap", "gm-asset"]
    for name in skills:
        skill_dir = repo / "skills" / "core" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")

    if shared_files is not None:
        shared_dir = repo / "skills" / "core" / "_shared"
        shared_dir.mkdir(parents=True)
        for filename in shared_files:
            (shared_dir / filename).write_text(f"shared: {filename}\n",
                                               encoding="utf-8")
        (shared_dir / "manifest.json").write_text(
            json.dumps({"files": shared_files}), encoding="utf-8")

    # _read_config.sh helper (publish_skills copies it)
    shell_dir = repo / "shell"
    shell_dir.mkdir(parents=True)
    (shell_dir / "_read_config.sh").write_text("#!/bin/bash\n",
                                               encoding="utf-8")
    return repo


class TestSharedExcludedFromPublishSkills:
    """publish_skills() must skip directories starting with `_`."""

    def test_underscore_dir_not_deployed(self, tmp_path):
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build"])
        target = tmp_path / "target"
        target.mkdir()
        count = publish_skills(repo, target)
        assert count == 1, "only gm-build counted as a skill"
        assert not (target / "_shared").exists(), \
            "_shared/ must NOT appear in deployed skills/"

    def test_real_skill_still_deployed(self, tmp_path):
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build", "gm-fixgap"])
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        assert (target / "gm-build" / "SKILL.md").exists()
        assert (target / "gm-fixgap" / "SKILL.md").exists()


class TestPublishSharedRefs:
    """publish_shared_refs() distributes _shared/<file> to consumer skills."""

    def test_distributes_to_each_consumer(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            shared_files={
                "worker-dispatch.md": ["gm-build", "gm-fixgap"],
                "analyst-dispatch.md": ["gm-asset", "gm-build", "gm-fixgap"],
            },
            skills=["gm-build", "gm-fixgap", "gm-asset"],
        )
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        count = publish_shared_refs(repo, target)
        # 2 + 3 = 5 distributions
        assert count == 5
        for skill in ["gm-build", "gm-fixgap"]:
            assert (target / skill / "references" / "worker-dispatch.md").exists()
        for skill in ["gm-asset", "gm-build", "gm-fixgap"]:
            assert (target / skill / "references" / "analyst-dispatch.md").exists()

    def test_deployed_copy_carries_auto_generated_header(self, tmp_path):
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build"])
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        publish_shared_refs(repo, target)
        deployed = (target / "gm-build" / "references" /
                    "worker-dispatch.md").read_text(encoding="utf-8")
        assert deployed.startswith("<!-- AUTO-GENERATED")
        assert "worker-dispatch.md" in deployed.split("\n")[0]
        # original source body still present below the header
        assert "shared: worker-dispatch.md" in deployed

    def test_invalid_manifest_json_raises_with_path(self, tmp_path):
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build"])
        # Corrupt the manifest
        (repo / "skills" / "core" / "_shared" /
         "manifest.json").write_text("{ not valid json", encoding="utf-8")
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        with pytest.raises(ValueError, match="Invalid JSON in.*manifest.json"):
            publish_shared_refs(repo, target)

    def test_creates_references_dir_if_missing(self, tmp_path):
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build"])
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        # gm-build doesn't have references/ in the fake repo
        assert not (target / "gm-build" / "references").exists()
        publish_shared_refs(repo, target)
        assert (target / "gm-build" / "references" / "worker-dispatch.md").exists()

    def test_no_manifest_returns_zero(self, tmp_path):
        repo = _make_repo(tmp_path, shared_files=None, skills=["gm-build"])
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        assert publish_shared_refs(repo, target) == 0

    def test_missing_source_file_raises(self, tmp_path):
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build"])
        # Delete the source file but leave the manifest claiming it exists
        (repo / "skills" / "core" / "_shared" / "worker-dispatch.md").unlink()
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        with pytest.raises(FileNotFoundError, match="worker-dispatch.md"):
            publish_shared_refs(repo, target)

    def test_missing_target_skill_raises(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            shared_files={"worker-dispatch.md": ["gm-nonexistent"]},
            skills=["gm-build"],
        )
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        with pytest.raises(FileNotFoundError, match="gm-nonexistent"):
            publish_shared_refs(repo, target)

    def test_idempotent(self, tmp_path):
        """Re-publishing must overwrite cleanly, not accumulate or fail."""
        repo = _make_repo(tmp_path,
                          shared_files={"worker-dispatch.md": ["gm-build"]},
                          skills=["gm-build"])
        target = tmp_path / "target"
        target.mkdir()
        publish_skills(repo, target)
        publish_shared_refs(repo, target)
        # Modify source then re-publish
        src = repo / "skills" / "core" / "_shared" / "worker-dispatch.md"
        src.write_text("updated\n", encoding="utf-8")
        publish_shared_refs(repo, target)
        deployed = (target / "gm-build" / "references" /
                    "worker-dispatch.md").read_text(encoding="utf-8")
        # Header is regenerated, source body is the new content
        assert deployed.startswith("<!-- AUTO-GENERATED")
        assert deployed.endswith("updated\n")

    def test_agent_specific_entries_only_publish_to_matching_agent(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            shared_files={
                "shared-common.md": ["gm-build"],
                "codex-only.md": {
                    "skills": ["gm-build"],
                    "agents": [AGENT_CODEX],
                },
            },
            skills=["gm-build"],
        )
        claude_target = tmp_path / "claude_target"
        codex_target = tmp_path / "codex_target"
        claude_target.mkdir()
        codex_target.mkdir()

        publish_skills(repo, claude_target, AGENT_CLAUDE_CODE)
        publish_skills(repo, codex_target, AGENT_CODEX)

        assert publish_shared_refs(repo, claude_target, AGENT_CLAUDE_CODE) == 1
        assert publish_shared_refs(repo, codex_target, AGENT_CODEX) == 2

        assert (
            claude_target / "gm-build" / "references" / "shared-common.md"
        ).exists()
        assert not (
            claude_target / "gm-build" / "references" / "codex-only.md"
        ).exists()
        assert (
            codex_target / "gm-build" / "references" / "codex-only.md"
        ).exists()


class TestProductionManifest:
    """Sanity-check the real _shared/manifest.json against the live repo."""

    def test_all_source_files_exist(self):
        manifest_path = SHARED_DIR / "manifest.json"
        assert manifest_path.exists(), "_shared/manifest.json missing"
        manifest = _load_shared_manifest()
        for filename in manifest.get("files", {}):
            src = SHARED_DIR / filename
            assert src.exists(), f"_shared/{filename} listed in manifest but missing"

    def test_all_target_skills_exist(self):
        manifest = _load_shared_manifest()
        for filename, entry in manifest.get("files", {}).items():
            for skill_name in _manifest_entry_targets(entry):
                skill_dir = REPO_ROOT / "skills" / "core" / skill_name
                assert skill_dir.is_dir(), \
                    f"manifest maps {filename} -> {skill_name}, but {skill_dir} missing"

    def test_consumer_skills_reference_deployed_path(self):
        """Each deployed shared ref must be reachable at runtime.

        Valid reachability paths:
        - the consumer SKILL.md directly references `references/<file>`;
        - another shared ref deployed to the same skill references it;
        - a root instruction template indexes its stable deployed path.
        """
        manifest = _load_shared_manifest()
        for filename, entry in manifest.get("files", {}).items():
            for skill_name in _manifest_entry_targets(entry):
                skill_location = f"{skill_name}/SKILL.md"
                skill_content = _skill_content(skill_name)
                _assert_no_legacy_runtime_ref(
                    skill_content,
                    skill_location,
                    filename,
                )
                for shared_filename in _shared_refs_for_skill(manifest, skill_name):
                    shared_location = f"_shared/{shared_filename}"
                    _assert_no_legacy_runtime_ref(
                        _shared_source_text(shared_filename),
                        shared_location,
                        filename,
                    )
                for template_path in ROOT_INSTRUCTION_TEMPLATES:
                    if template_path.exists():
                        _assert_no_legacy_runtime_ref(
                            template_path.read_text(encoding="utf-8"),
                            str(template_path.relative_to(REPO_ROOT)),
                            filename,
                        )

                has_direct_ref = f"references/{filename}" in skill_content
                has_transitive_ref = _shared_ref_indexes(
                    manifest,
                    filename,
                    skill_name,
                )
                has_root_index = any(
                    _root_instruction_indexes(filename, skill_name, agent)
                    for agent in _manifest_entry_agents(entry)
                )

                assert has_direct_ref or has_transitive_ref or has_root_index, (
                    f"{filename} is deployed to {skill_name}, but no runtime "
                    "entry references its deployed path. Add a direct "
                    f"`references/{filename}` reference, a transitive deployed "
                    "shared-ref reference, or a root instruction index."
                )

    def test_deployed_shared_refs_do_not_use_unresolvable_bare_refs(self):
        """Bare shared filenames in deployed shared refs must resolve locally."""
        manifest = _load_shared_manifest()
        files = manifest.get("files", {})
        assert isinstance(files, dict)

        all_skills = {
            skill_name
            for entry in files.values()
            for skill_name in _manifest_entry_targets(entry)
        }
        for skill_name in all_skills:
            deployed_refs = set(_shared_refs_for_skill(manifest, skill_name))
            for filename in files:
                pattern = re.compile(
                    r"(?<!references/)\b" + re.escape(filename) + r"\b"
                )
                for shared_filename in deployed_refs:
                    content = _shared_source_text(shared_filename)
                    bare_hits = pattern.findall(content)
                    if filename in deployed_refs:
                        continue
                    assert not bare_hits, (
                        f"_shared/{shared_filename} has {len(bare_hits)} bare "
                        f"reference(s) to {filename}, but {filename} is not "
                        f"deployed to {skill_name}; use `references/{filename}` "
                        "or update the manifest so the runtime path resolves."
                    )

    def test_no_bare_shared_filename_references(self):
        """Every mention of a shared filename in a consumer SKILL.md must be
        prefixed with `references/`. Bare mentions (like `\\`worker-dispatch.md\\``
        in body prose) deploy to a path that doesn't exist at runtime."""
        manifest = _load_shared_manifest()
        files = manifest.get("files", {})
        assert isinstance(files, dict)
        for filename, entry in files.items():
            # Match the filename only when it is NOT preceded by "references/".
            pattern = re.compile(
                r"(?<!references/)\b" + re.escape(filename) + r"\b"
            )
            for skill_name in _manifest_entry_targets(entry):
                content = _skill_content(skill_name)
                bare_hits = pattern.findall(content)
                assert not bare_hits, (
                    f"{skill_name}/SKILL.md has {len(bare_hits)} bare "
                    f"reference(s) to {filename} without the `references/` "
                    f"prefix — these will not resolve at runtime."
                )
