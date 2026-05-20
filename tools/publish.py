#!/usr/bin/env python3
"""Publish GodotMaker skills into a target Godot project directory.

Flattens skills/core/* and skills/reviewer/* into the selected agent-native
skill location: .claude/skills/ for Claude Code or .agents/skills/ for Codex.
Also copies tools, config, hooks, templates, and sets up agent-specific files.

Supports versioned upgrades: compares source VERSION against the
target's .godotmaker/version and prompts accordingly.

Usage:
    python tools/publish.py <target_godot_project_dir>
    python tools/publish.py --agent codex <target_godot_project_dir>
    python tools/publish.py --force <target_godot_project_dir>
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from agent_runtime import AGENT_CLAUDE_CODE, AGENT_CODEX
from project_config import (
    ProjectConfigResult,
    create_project_config as create_project_config_file,
    set_simple_yaml_value,
)

from _version import SemVer, parse_version
from migrate import (
    TrackerCorruptionError,
    baseline_applied,
    run_migrations,
)


class VersionCheckResult(NamedTuple):
    proceed: bool
    level: str  # "FRESH" | "SAME" | "PATCH" | "MINOR" | "MAJOR" | "DOWNGRADE"
    target_ver: SemVer | None
    source_ver: SemVer | None

EXCLUDE_DIRS = {"__pycache__", "doc_source", ".workspace"}
AGENT_CHOICES = (AGENT_CLAUDE_CODE, AGENT_CODEX)
AGENT_RUNTIME_SOURCE_ROOTS = {
    AGENT_CODEX: Path("agent-runtimes") / "codex",
}
AGENT_RUNTIME_REFERENCES = {
    AGENT_CODEX: (
        Path("references") / "runtime-mapping.md",
        Path("references") / "delegation-worktree.md",
    ),
}
AGENT_ROOT_BOOTSTRAP_TEMPLATES = {
    AGENT_CODEX: Path("templates") / "agents-bootstrap.md",
}

@dataclass(frozen=True)
class AgentPublishAdapter:
    """Selected-agent publish contract for project-local GodotMaker output."""

    agent_id: str
    project_config_root: str
    skill_root: str
    agents_root: str
    config_root: str
    templates_root: str
    runtime_references_root: str | None
    root_instruction_filename: str
    deploy_settings: bool
    register_claude_mcp: bool
    register_godot_permissions: bool
    ensure_worktreeinclude: bool

    def project_config_dir(self, target: Path) -> Path:
        return target / self.project_config_root

    def skill_dir(self, target: Path) -> Path:
        return target / self.skill_root

    def agents_dir(self, target: Path) -> Path:
        return target / self.agents_root

    def config_dir(self, target: Path) -> Path:
        return target / self.config_root

    def templates_dir(self, target: Path) -> Path:
        return target / self.templates_root

    def runtime_references_dir(self, target: Path) -> Path | None:
        if self.runtime_references_root is None:
            return None
        return target / self.runtime_references_root


AGENT_ADAPTERS = {
    AGENT_CLAUDE_CODE: AgentPublishAdapter(
        agent_id=AGENT_CLAUDE_CODE,
        project_config_root=".claude",
        skill_root=".claude/skills",
        agents_root=".claude/agents",
        config_root=".claude/config",
        templates_root=".claude/templates",
        runtime_references_root=None,
        root_instruction_filename="CLAUDE.md",
        deploy_settings=True,
        register_claude_mcp=True,
        register_godot_permissions=True,
        ensure_worktreeinclude=True,
    ),
    AGENT_CODEX: AgentPublishAdapter(
        agent_id=AGENT_CODEX,
        project_config_root=".agents",
        skill_root=".agents/skills",
        agents_root=".agents/agents",
        config_root=".agents/config",
        templates_root=".agents/templates",
        runtime_references_root=".agents/references",
        root_instruction_filename="AGENTS.md",
        deploy_settings=False,
        register_claude_mcp=False,
        register_godot_permissions=False,
        ensure_worktreeinclude=False,
    ),
}


def get_agent_adapter(agent: str) -> AgentPublishAdapter:
    """Return the publish adapter for a supported coding agent."""
    try:
        return AGENT_ADAPTERS[agent]
    except KeyError as e:
        raise ValueError(f"Unsupported coding agent: {agent}") from e


def read_source_version(repo_root: Path) -> SemVer | None:
    """Read VERSION file from GodotMaker repo root."""
    version_file = repo_root / "VERSION"
    if not version_file.exists():
        return None
    return parse_version(version_file.read_text(encoding="utf-8"))


def read_target_version(target: Path) -> SemVer | None:
    """Read deployed version from target project's .godotmaker/version."""
    version_file = target / ".godotmaker" / "version"
    if not version_file.exists():
        return None
    return parse_version(version_file.read_text(encoding="utf-8"))


def write_target_version(target: Path, version: SemVer):
    """Stamp the deployed version into the target project."""
    version_dir = target / ".godotmaker"
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / "version").write_text(str(version) + "\n", encoding="utf-8")


def read_changelog_section(repo_root: Path, version: SemVer) -> str | None:
    """Extract the CHANGELOG.md section for a specific version."""
    changelog = repo_root / "CHANGELOG.md"
    if not changelog.exists():
        return None
    content = changelog.read_text(encoding="utf-8")
    # Match from "## [version]" to next "## [" or end
    pattern = rf"(## \[{re.escape(str(version))}\].*?)(?=\n## \[|\Z)"
    m = re.search(pattern, content, re.DOTALL)
    return m.group(1).strip() if m else None


def check_version_upgrade(repo_root: Path, target: Path, force: bool
                          ) -> VersionCheckResult:
    """Compare source and target versions, prompt user if needed.

    Returns a VersionCheckResult with fields:
      - proceed: True if publish should continue
      - level: "FRESH" | "SAME" | "PATCH" | "MINOR" | "MAJOR" | "DOWNGRADE"
      - target_ver: version currently in the target project (None if fresh)
      - source_ver: version in the GodotMaker repo (None if no VERSION file)
    """
    source_ver = read_source_version(repo_root)
    if not source_ver:
        return VersionCheckResult(True, "FRESH", None, None)

    target_ver = read_target_version(target)

    # Fresh install — no existing version
    if not target_ver:
        print(f"\n  GodotMaker v{source_ver} (fresh install)")
        return VersionCheckResult(True, "FRESH", None, source_ver)

    # Same version
    if source_ver == target_ver:
        print(f"\n  GodotMaker v{source_ver} (same version, re-publishing)")
        return VersionCheckResult(True, "SAME", target_ver, source_ver)

    # Downgrade
    if source_ver < target_ver:
        print(f"\n  WARNING: Downgrade detected: v{target_ver} -> v{source_ver}")
        if not force:
            print("  Use --force to downgrade.")
            return VersionCheckResult(False, "DOWNGRADE", target_ver, source_ver)
        return VersionCheckResult(True, "DOWNGRADE", target_ver, source_ver)

    # Upgrade — determine severity
    if source_ver.major != target_ver.major:
        level = "MAJOR"
        color = "!!! "
        msg = "Breaking changes — backup your project first!"
    elif source_ver.minor != target_ver.minor:
        level = "MINOR"
        color = ">>  "
        msg = "Backward-compatible new features / behavior changes. Review changelog below."
    else:
        level = "PATCH"
        color = "    "
        msg = "Backward-compatible bug fixes."

    print(f"\n  {color}Upgrade: v{target_ver} -> v{source_ver} ({level})")
    print(f"  {color}{msg}")

    # Show changelog for the new version
    changelog = read_changelog_section(repo_root, source_ver)
    if changelog:
        print()
        for line in changelog.splitlines():
            print(f"  {line}")
        print()

    # MAJOR upgrade — block incremental, require --force for clean re-init
    if level == "MAJOR" and not force:
        print("  MAJOR upgrades require --force (clean re-initialization).")
        print("  This will wipe .claude/skills/ and .godotmaker/hooks/ and re-deploy.")
        try:
            answer = input("  Proceed with MAJOR upgrade? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print("  Upgrade cancelled.")
            return VersionCheckResult(False, level, target_ver, source_ver)

    # MINOR upgrades require confirmation (unless --force)
    elif level == "MINOR" and not force:
        try:
            answer = input(f"  Proceed with {level} upgrade? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer not in ("y", "yes"):
            print("  Upgrade cancelled.")
            return VersionCheckResult(False, level, target_ver, source_ver)

    return VersionCheckResult(True, level, target_ver, source_ver)


def select_migration_action(level: str, force: bool) -> str:
    """Decide whether publish should baseline or run migrations.

    Returns "baseline" or "run".

    - FRESH (no `.godotmaker/version`) and MAJOR `--force` (cleanup wiped
      state) start at the latest format and have nothing to migrate from
      → "baseline" (mark every current migration as applied without
      executing it).
    - All other resolved upgrade levels — SAME, PATCH, MINOR, DOWNGRADE
      with `--force` — already have a tracked state → "run" (apply
      pending migrations). A legacy target lacking the tracker file is
      handled inside `run_migrations()` itself: an empty tracker is
      auto-created, then any pending migrations run normally through
      the standard pending-application path.

    MAJOR without `--force` is filtered out by check_version_upgrade()
    before this function is called, so the (level="MAJOR", force=False)
    case is unreachable in practice; if it does arrive (defensive),
    treating it as "run" is harmless because publish would have aborted.
    """
    if level == "FRESH" or (level == "MAJOR" and force):
        return "baseline"
    return "run"


def _rmtree_handle_readonly(func, path, _):
    """rmtree onerror/onexc handler: clear the read-only bit and retry.

    Windows refuses to unlink read-only files (e.g. git pack-*.idx in
    cloned doc sources are r--r--r--), so plain shutil.rmtree raises
    PermissionError [WinError 5]. Linux/macOS unlink them without
    issue, which is why this is a Windows-only crash. The third
    parameter is exc_info (3.10/3.11 onerror) or an Exception (3.12+
    onexc); we ignore it either way.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def rmtree_force(path: Path):
    """shutil.rmtree that survives Windows read-only files."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_rmtree_handle_readonly)
    else:
        shutil.rmtree(path, onerror=_rmtree_handle_readonly)


def copy_tree(src: Path, dst: Path):
    """Copy directory tree, overwriting destination. Excludes __pycache__ etc."""
    if dst.exists():
        rmtree_force(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*EXCLUDE_DIRS))


# ── Publish steps ──────────────────────────────────────────────


def render_root_instruction_text(text: str, adapter: AgentPublishAdapter) -> str:
    """Render the selected agent's root instruction file."""
    if adapter.agent_id == AGENT_CLAUDE_CODE:
        return text

    return text.replace("CLAUDE.md", adapter.root_instruction_filename)


def render_agent_template_tree(root: Path, adapter: AgentPublishAdapter) -> None:
    """Rename generated project instruction templates for the selected agent.

    This is intentionally narrow. Shared skills and references keep their
    GodotMaker/Claude-first surface vocabulary; Codex interprets it through the
    published runtime mapping instead of receiving inline rewritten docs.
    """
    if adapter.agent_id == AGENT_CLAUDE_CODE:
        return

    for file in root.rglob("*"):
        if not file.is_file() or file.name != "claude.md.tmpl":
            continue
        text = file.read_text(encoding="utf-8")
        rewritten = text.replace("CLAUDE.md", adapter.root_instruction_filename)
        if rewritten != text:
            file.write_text(rewritten, encoding="utf-8")
        file.replace(file.with_name("agents.md.tmpl"))


def publish_skills(repo_root: Path, skills_target: Path,
                   agent: str = AGENT_CLAUDE_CODE) -> int:
    """Flatten-copy skills/core/* and skills/reviewer/* to target.

    Directory names starting with `_` (e.g. _shared/) are excluded — they hold
    cross-skill source material rather than self-contained skills, and are
    distributed by publish_shared_refs() instead.
    """
    adapter = get_agent_adapter(agent)
    count = 0
    for layer in ("core", "reviewer"):
        layer_dir = repo_root / "skills" / layer
        if not layer_dir.exists():
            continue
        for skill_dir in sorted(layer_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith("_"):
                continue
            dst = skills_target / skill_dir.name
            copy_tree(skill_dir, dst)
            render_agent_template_tree(dst, adapter)
            count += 1

    # Copy _read_config.sh helper
    helper = repo_root / "shell" / "_read_config.sh"
    if helper.exists():
        helper_target = skills_target / "_read_config.sh"
        shutil.copy2(helper, helper_target)

    print(f"Published skills: {count}")
    return count


SHARED_HEADER_TEMPLATE = (
    "<!-- AUTO-GENERATED from skills/core/_shared/{filename}. "
    "Do NOT edit this deployed copy — it is overwritten on every publish. "
    "Edit the source under skills/core/_shared/ instead. -->\n\n"
)

RUNTIME_REFERENCE_HEADER_TEMPLATE = (
    "<!-- AUTO-GENERATED from {source_path}. "
    "Do NOT edit this deployed copy - it is overwritten on every publish. "
    "Edit the source runtime reference instead. -->\n\n"
)


def _shared_manifest_targets(entry: object, filename: str) -> list[str]:
    """Return target skills from a legacy or agent-aware shared ref entry."""
    if isinstance(entry, list):
        return entry
    if isinstance(entry, dict):
        targets = entry.get("skills", entry.get("targets"))
        if isinstance(targets, list):
            return targets
    raise ValueError(
        f"_shared/manifest.json entry for {filename} must be a list of skill "
        "names or an object with a 'skills' list."
    )


def _shared_manifest_applies_to_agent(entry: object, agent: str) -> bool:
    """Return whether a shared ref entry should publish for the selected agent."""
    if not isinstance(entry, dict):
        return True
    agents = entry.get("agents")
    if agents is None:
        return True
    if not isinstance(agents, list):
        raise ValueError(
            "_shared/manifest.json 'agents' must be a list when present."
        )
    return agent in agents


def publish_shared_refs(repo_root: Path, skills_target: Path,
                        agent: str = AGENT_CLAUDE_CODE) -> int:
    """Distribute shared reference docs into each consumer skill's references/.

    The single source of truth is `skills/core/_shared/`. `_shared/manifest.json`
    maps each shared filename to the skills that consume it. For every entry,
    `<file>` is written into `<skill>/references/<file>` (with an
    AUTO-GENERATED header prepended) so deployed skills are self-contained —
    no `.claude/skills/_shared/` directory exists at runtime, and editors
    opening a deployed copy see an explicit warning at the top.
    """
    shared_dir = repo_root / "skills" / "core" / "_shared"
    manifest_path = shared_dir / "manifest.json"
    if not manifest_path.exists():
        return 0

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Invalid JSON in {manifest_path}: {e.msg} "
            f"(line {e.lineno}, col {e.colno})"
        ) from e
    files = manifest.get("files", {})
    distributions = 0
    for filename, entry in files.items():
        if not _shared_manifest_applies_to_agent(entry, agent):
            continue
        target_skills = _shared_manifest_targets(entry, filename)
        src = shared_dir / filename
        if not src.exists():
            raise FileNotFoundError(
                f"_shared/manifest.json references {filename}, but source "
                f"file does not exist at {src}."
            )
        deployed_content = (
            SHARED_HEADER_TEMPLATE.format(filename=filename)
            + src.read_text(encoding="utf-8")
        )
        for skill_name in target_skills:
            skill_root = skills_target / skill_name
            if not skill_root.exists():
                raise FileNotFoundError(
                    f"_shared/manifest.json maps {filename} -> {skill_name}, "
                    f"but skill directory {skill_root} does not exist (was "
                    f"publish_skills() called first?)."
                )
            references = skill_root / "references"
            references.mkdir(parents=True, exist_ok=True)
            (references / filename).write_text(deployed_content, encoding="utf-8")
            distributions += 1

    print(f"Distributed shared refs: {distributions} copies "
          f"({len(files)} source file(s))")
    return distributions


def publish_runtime_references(repo_root: Path, target: Path,
                               agent: str = AGENT_CLAUDE_CODE) -> int:
    """Publish agent-wide runtime references outside individual skills."""
    source_root = AGENT_RUNTIME_SOURCE_ROOTS.get(agent)
    reference_paths = AGENT_RUNTIME_REFERENCES.get(agent, ())
    if source_root is None or not reference_paths:
        return 0

    adapter = get_agent_adapter(agent)
    references_dir = adapter.runtime_references_dir(target)
    if references_dir is None:
        return 0

    source_dir = repo_root / source_root
    references_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for relative_path in reference_paths:
        src = source_dir / relative_path
        if not src.exists():
            raise FileNotFoundError(
                f"Agent runtime reference {relative_path} does not exist at {src}."
            )
        content = (
            RUNTIME_REFERENCE_HEADER_TEMPLATE.format(
                source_path=(source_root / relative_path).as_posix()
            )
            + src.read_text(encoding="utf-8")
        )
        (references_dir / relative_path.name).write_text(content, encoding="utf-8")
        count += 1

    print(f"Published {agent} runtime refs: {count}")
    return count


def publish_directory(
    src: Path,
    dst: Path,
    label: str,
    count_pattern: str = "*.py",
):
    """Copy a directory from repo to target, printing file count."""
    if not src.exists():
        return
    copy_tree(src, dst)
    count = len(list(dst.glob(count_pattern)))
    print(f"Published {label} ({count} files)")


def deploy_settings(repo_root: Path, config_dir: Path, force: bool):
    """Deploy settings.json (hooks configuration) — only if not exists."""
    src = repo_root / "config" / "settings.json"
    dst = config_dir / "settings.json"
    if not src.exists():
        return
    if not dst.exists() or force:
        shutil.copy2(src, dst)
        print("Created settings.json (hooks enabled)")
    else:
        print("settings.json already exists, skipping (use --force to overwrite)")


def deploy_agent_instructions(repo_root: Path, target: Path, agent: str):
    """Deploy root agent instructions for the selected coding agent."""
    adapter = get_agent_adapter(agent)
    filename = adapter.root_instruction_filename
    dst = target / filename
    if dst.exists():
        return

    content = render_agent_instructions(repo_root, agent)
    if content is None:
        return
    dst.write_text(content, encoding="utf-8")
    print(f"Created {filename}")


def render_agent_instructions(repo_root: Path, agent: str) -> str | None:
    """Render root agent instructions from one source template."""
    adapter = get_agent_adapter(agent)
    template = repo_root / "templates" / "game-claude.md"
    if not template.exists():
        return None
    content = template.read_text(encoding="utf-8")
    rendered = render_root_instruction_text(content, adapter)
    if adapter.agent_id == AGENT_CODEX:
        rendered = _inject_agent_root_bootstrap(repo_root, rendered, adapter)
    return rendered


def _inject_agent_root_bootstrap(
    repo_root: Path,
    content: str,
    adapter: AgentPublishAdapter,
) -> str:
    """Add selected-agent bootstrap text to generated root instructions."""
    template_path = AGENT_ROOT_BOOTSTRAP_TEMPLATES.get(adapter.agent_id)
    source_root = AGENT_RUNTIME_SOURCE_ROOTS.get(adapter.agent_id)
    if template_path is None or source_root is None:
        return content

    template = repo_root / source_root / template_path
    if not template.exists():
        return content

    bootstrap = template.read_text(encoding="utf-8")
    if bootstrap.strip() and bootstrap.strip() in content:
        return content

    lines = content.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        return "".join([lines[0], "\n", bootstrap, *lines[1:]])
    return bootstrap + content


def _verify_godot_path(godot_path: str) -> tuple[bool, str]:
    """Run `<godot_path> --version` and return (ok, message).

    Empty input is rejected before this is called. A bare 'godot' is also
    rejected unless it actually resolves on PATH and runs — silently
    accepting it leads to /gm-scaffold and other downstream tools failing
    later with a confusing 'godot not found' instead of failing at config
    time.
    """
    try:
        result = subprocess.run(
            [godot_path, "--version"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        return False, f"executable not found at {godot_path!r}"
    except subprocess.TimeoutExpired:
        return False, f"{godot_path!r} did not return within 15s"
    except OSError as e:
        return False, f"cannot run {godot_path!r}: {e}"

    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()[-1:] or ["(no stderr)"]
        return False, f"{godot_path!r} exited {result.returncode}: {stderr[0]}"

    version = (result.stdout or "").strip().splitlines()[-1:] or ["?"]
    return True, version[0]


def create_godotmaker_yaml(config_file: Path) -> bool:
    """Interactive godotmaker.yaml generation on first run.

    Re-prompts until the user provides a path that actually launches Godot.
    The previous behaviour silently fell back to godot_path: "godot" when
    the user pressed Enter, which caused every downstream skill needing
    Godot to fail with a confusing PATH error and re-ask the user.
    """
    if config_file.exists():
        print("godotmaker.yaml already exists, skipping")
        return True

    print()
    print("No godotmaker.yaml found. Let's create one.")
    print("Enter the full path to your Godot executable")
    print("  (e.g. C:/path/to/Godot_v4.4-stable_win64.exe)")

    max_attempts = 5
    godot_path = ""
    for attempt in range(1, max_attempts + 1):
        try:
            entered = (
                input("godot_path: ")
                .strip()
                .lstrip("\ufeff")
                .strip()
                .strip('"')
                .strip("'")
            )
        except (EOFError, KeyboardInterrupt):
            print("\nAborted: godotmaker.yaml not created. "
                  "Re-run publish to set godot_path.")
            return False

        if not entered:
            print("  Path is required — please enter the full path to Godot.")
            continue

        ok, msg = _verify_godot_path(entered)
        if ok:
            print(f"  Verified Godot: {msg}")
            godot_path = entered
            break

        print(f"  Could not verify Godot at this path: {msg}")
        if attempt < max_attempts:
            print("  Try again, or Ctrl+C to abort.")
    else:
        print(f"\nGave up after {max_attempts} attempts. "
              f"godotmaker.yaml not created. Re-run publish to set godot_path.")
        return False

    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        f'# Host-specific tool paths — not committed to git\n'
        f'godot_path: "{godot_path}"\n',
        encoding="utf-8",
    )
    print(f"Created {config_file}")
    return True


def _set_simple_yaml_value(path: Path, key: str, value: str) -> None:
    """Backward-compatible wrapper for tests and older imports."""
    set_simple_yaml_value(path, key, value)


def create_project_config(target: Path, agent: str = AGENT_CLAUDE_CODE):
    """Create or update .godotmaker/config.yaml with project settings."""
    return create_project_config_file(target, agent)


def review_created_project_config(result: ProjectConfigResult) -> None:
    """Give the operator a chance to edit a newly-created project config."""
    print()
    print("Project config created:")
    print(f"  {result.path.resolve()}")
    print()
    print("Edit this file now if you want to change model settings.")
    print("When finished, return here and press Enter to continue.")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted before publish continued.")
        sys.exit(1)


def deploy_stage_schemas(repo_root: Path, target: Path):
    """Deploy stage_schemas.json to .godotmaker/ directory."""
    src = repo_root / "config" / "stage_schemas.json"
    dst = target / ".godotmaker" / "stage_schemas.json"
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print("Deployed stage_schemas.json")


def create_project_dirs(target: Path):
    """Create standard game project directories."""
    dirs = [
        "assets/sprites", "assets/audio", "assets/fonts", "assets/ui",
        "references",
    ]
    created = 0
    for d in dirs:
        p = target / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created += 1
    if created:
        print(f"Created {created} project directories")


def read_godot_path(config_file: Path) -> str:
    """Read godot_path from godotmaker.yaml."""
    if not config_file.exists():
        return "godot"
    for line in config_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("godot_path:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if val:
                return val
    return "godot"


def register_mcp(target: Path, godot_path: str):
    """Register godot-mcp MCP server."""
    # Remove existing registration first
    claude_cmd = (
        shutil.which("claude")
        or shutil.which("claude.cmd")
        or shutil.which("claude.exe")
    )
    if not claude_cmd:
        print("WARNING: claude CLI not found. Skipping godot-mcp registration.")
        print("  Install Claude Code, then run manually:")
        print(f'  claude mcp add godot -e GODOT_PATH="{godot_path}" -- npx @coding-solo/godot-mcp')
        return

    if not shutil.which("npx"):
        print("WARNING: npx not found. Skipping godot-mcp registration.")
        print("  Install Node.js, then run manually:")
        print(f'  claude mcp add godot -e GODOT_PATH="{godot_path}" -- npx @coding-solo/godot-mcp')
        return

    try:
        subprocess.run(
            [claude_cmd, "mcp", "remove", "godot"],
            cwd=str(target), capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

    print("Registering godot-mcp MCP server...")
    cmd = [claude_cmd, "mcp", "add", "godot",
           "-e", f"GODOT_PATH={godot_path}", "--"]

    if sys.platform == "win32":
        cmd.extend(["cmd", "/c", "npx", "@coding-solo/godot-mcp"])
    else:
        cmd.extend(["npx", "@coding-solo/godot-mcp"])

    try:
        result = subprocess.run(cmd, cwd=str(target), timeout=60)
        if result.returncode == 0:
            print("godot-mcp registered")
        else:
            print("WARNING: godot-mcp registration failed. Register manually if needed.")
    except (subprocess.TimeoutExpired, OSError):
        print("WARNING: godot-mcp registration failed. Register manually if needed.")


def register_codex_mcp(target: Path, godot_path: str) -> bool:
    """Register godot-mcp for Codex via `codex mcp`.

    Codex MCP configuration is managed by Codex, not by GodotMaker's `.agents/`
    runtime files. This mirrors register_mcp()'s CLI-driven behavior while
    using Codex's own MCP management command.
    """
    codex_cmd = (
        shutil.which("codex")
        or shutil.which("codex.cmd")
        or shutil.which("codex.exe")
    )
    if not codex_cmd:
        print("ERROR: codex CLI not found. Cannot register godot-mcp.")
        print("  Install Codex, then run manually:")
        print(f'  codex mcp add godot --env GODOT_PATH="{godot_path}" -- npx @coding-solo/godot-mcp')
        return False

    if not shutil.which("npx"):
        print("ERROR: npx not found. Cannot register godot-mcp.")
        print("  Install Node.js, then run manually:")
        print(f'  codex mcp add godot --env GODOT_PATH="{godot_path}" -- npx @coding-solo/godot-mcp')
        return False

    try:
        subprocess.run(
            [codex_cmd, "mcp", "remove", "godot"],
            cwd=str(target), capture_output=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

    print("Registering godot-mcp MCP server for Codex...")
    cmd = [codex_cmd, "mcp", "add", "godot",
           "--env", f"GODOT_PATH={godot_path}", "--"]

    if sys.platform == "win32":
        cmd.extend(["cmd", "/c", "npx", "@coding-solo/godot-mcp"])
    else:
        cmd.extend(["npx", "@coding-solo/godot-mcp"])

    try:
        result = subprocess.run(cmd, cwd=str(target), timeout=60)
        if result.returncode == 0:
            print("godot-mcp registered for Codex")
            return True
        else:
            print("ERROR: Codex godot-mcp registration failed.")
            return False
    except (subprocess.TimeoutExpired, OSError):
        print("ERROR: Codex godot-mcp registration failed.")
        return False


def _escape_permission_rule_content(content: str) -> str:
    """Mirror claude-code's permissionRuleParser.ts `escapeRuleContent`.

    Permission rule strings use `Tool(content)` syntax, so backslashes and
    parentheses in `content` must be escaped or the parser mis-extracts the
    tool name and content. Escaping order matters — backslashes first, then
    parentheses — so the round-trip with `unescapeRuleContent` is stable.

    Without this, godot paths under `C:\\Program Files (x86)\\...` produce
    rules whose `(x86)` confuses the outer `Tool(...)` boundary parser.
    """
    return (
        content
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def register_godot_permissions(settings_path: Path, godot_path: str) -> None:
    """Pre-approve `<godot_path> ...` Bash invocations in `.claude/settings.json`.

    Without this, every `/gm-build` and `/gm-verify` headless run triggers
    a Claude Code permission prompt because the user-specific absolute
    `godot_path` doesn't match any built-in allow pattern. Sub-agents in
    worktrees are also affected — `settings.local.json` is gitignored and
    not carried into worktrees, so an interactive "yes don't ask again"
    by the parent doesn't propagate. The project-level `settings.json`
    does propagate, so this is the durable fix.

    Idempotent: skips when the entry is already present, safe to re-run
    on every publish.
    """
    if not settings_path.exists():
        print("WARNING: .claude/settings.json missing; skipping godot permission entry")
        return
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"WARNING: .claude/settings.json invalid JSON ({e}); skipping godot permission entry")
        return
    perms = data.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    entry = f"Bash({_escape_permission_rule_content(godot_path)}:*)"
    if entry in allow:
        return
    allow.append(entry)
    settings_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Registered godot permission: {entry}")


def ensure_git_repo(target: Path):
    """Initialize git repo with initial commit if needed.

    Worktree isolation (used by parallel workers) requires at least one commit.
    Without it: 'fatal: not a valid object name: HEAD'.
    """
    git_dir = target / ".git"
    if not git_dir.exists():
        try:
            subprocess.run(["git", "init"], cwd=str(target),
                           capture_output=True, timeout=15)
            print("Initialized git repository")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("WARNING: git not found. Initialize manually: git init && git commit --allow-empty -m 'init'")
            return

    # Check if there are any commits
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target), capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return  # Already has commits
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return

    # No commits yet — create initial empty commit
    try:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit (GodotMaker publish)"],
            cwd=str(target), capture_output=True, timeout=15,
        )
        print("Created initial git commit (required for worktree isolation)")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("WARNING: could not create initial commit. Run manually: git commit --allow-empty -m 'init'")


def ensure_gitignore(target: Path, agent: str = AGENT_CLAUDE_CODE):
    """Ensure .gitignore covers local-only agent config and runtime state.

    .claude/ is fully ignored (Claude Code config, not project code). Codex
    `.agents/` is intentionally not ignored because Codex-managed git
    worktrees need the published skills and runtime mapping from git.
    .godotmaker/ is selectively ignored: hooks and config are tracked,
    runtime state (metrics, session state) is ignored. This allows
    git worktrees to inherit hooks automatically.
    """
    gitignore = target / ".gitignore"
    adapter = get_agent_adapter(agent)

    # Lines that must be present
    agent_entries = []
    if adapter.agent_id == AGENT_CLAUDE_CODE:
        agent_entries.append(f"{adapter.project_config_root}/")
    entries_needed = [
        *agent_entries,
        ".godotmaker/state.json",
        ".godotmaker/metrics.jsonl",
        ".godotmaker/metrics_current.jsonl",
        ".godotmaker/traces/",
        ".godotmaker/applied_migrations.json",
        "reports/",
        "__pycache__/",
        "*.pyc",
    ]

    # If upgrading from old blanket ignores, remove them.
    old_blankets = [".godotmaker/"]
    if adapter.agent_id == AGENT_CODEX:
        old_blankets.append(".agents/")

    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        line_set = set(line.strip() for line in lines)

        # Remove old blanket ignores managed by earlier publish versions.
        updated = False
        for old_blanket in old_blankets:
            if old_blanket in line_set:
                lines = [line for line in lines
                         if line.strip() != old_blanket]
                line_set = set(line.strip() for line in lines)
                updated = True

        # Add missing entries
        missing = [e for e in entries_needed if e not in line_set]
        if missing:
            for entry in missing:
                lines.append(entry)
            updated = True

        if updated:
            gitignore.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print("Updated .gitignore (selective .godotmaker/ ignore for worktree support)")
    else:
        gitignore.write_text("\n".join(entries_needed) + "\n", encoding="utf-8")
        print("Created .gitignore")


def ensure_gitattributes(target: Path):
    """Ensure generated projects have stable text line endings."""
    gitattributes = target / ".gitattributes"
    entries_needed = [
        "* text=auto eol=lf",
        "*.sh text eol=lf",
        "*.bat text eol=crlf",
        "*.cmd text eol=crlf",
    ]

    if gitattributes.exists():
        content = gitattributes.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        line_set = set(line.strip() for line in lines)
        missing = [entry for entry in entries_needed if entry not in line_set]
        if missing:
            lines.extend(missing)
            gitattributes.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print("Updated .gitattributes (stable text line endings)")
    else:
        gitattributes.write_text("\n".join(entries_needed) + "\n", encoding="utf-8")
        print("Created .gitattributes")


def ensure_worktreeinclude(target: Path):
    """Ensure `.worktreeinclude` carries `.claude/` into sub-agent worktrees.

    Sub-agents dispatched with `isolation: "worktree"` get a fresh git
    checkout that contains only git-tracked files. `.claude/` is fully
    gitignored (host-specific config + deployed skills, never committed),
    so workers in worktrees couldn't read `.claude/godotmaker.yaml` (the
    `godot_path` source of truth that gm-verify / gm-evaluate / gm-finalize
    SKILLs depend on) or `.claude/skills/` (the SKILL files themselves).
    Without carry-over, every sub-agent dispatched into a worktree fell
    back to scanning PATH for godot, often picking the wrong binary.

    Anthropic ships `.worktreeinclude` (gitignore syntax) at project root
    as the documented mechanism for this carry-over. See
    https://code.claude.com/docs/en/worktrees.

    `.claude/worktrees/` is excluded so a sub-agent already running inside
    a worktree doesn't try to recursively carry-over its own siblings.
    """
    worktreeinclude = target / ".worktreeinclude"

    entries_needed = [
        ".claude/",
        "!.claude/worktrees/",
    ]
    header = (
        "# Carry-over rules for sub-agent worktrees (gitignore syntax).\n"
        "# Sub-agents dispatched with isolation: \"worktree\" need .claude/\n"
        "# (godotmaker.yaml + skills/ + agents/) in their fresh checkout.\n"
        "# See https://code.claude.com/docs/en/worktrees.\n"
        "# Managed by tools/publish.py — your additions are preserved.\n"
    )

    if worktreeinclude.exists():
        content = worktreeinclude.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        line_set = set(line.strip() for line in lines)

        missing = [e for e in entries_needed if e not in line_set]
        if missing:
            for entry in missing:
                lines.append(entry)
            worktreeinclude.write_text("\n".join(lines) + "\n",
                                       encoding="utf-8")
            print(f"Updated .worktreeinclude (added: {', '.join(missing)})")
    else:
        worktreeinclude.write_text(
            header + "\n" + "\n".join(entries_needed) + "\n",
            encoding="utf-8",
        )
        print("Created .worktreeinclude (sub-agent worktree carry-over)")


# ── Main ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Publish GodotMaker skills into a target Godot project directory"
    )
    parser.add_argument("target", help="Path to the target Godot project directory")
    parser.add_argument("--agent", choices=AGENT_CHOICES, default=AGENT_CLAUDE_CODE,
                        help="Coding agent target to publish for "
                             "(default: claude-code)")
    parser.add_argument("--force", action="store_true",
                        help="Clean existing agent skills before publishing; "
                             "skip upgrade confirmation prompts")
    parser.add_argument("--no-config-review", action="store_true",
                        help="Do not pause after creating .godotmaker/config.yaml")
    args = parser.parse_args()

    # Resolve paths
    repo_root = Path(__file__).resolve().parent.parent
    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    # Version check — may abort on MAJOR/MINOR without --force
    proceed, level, target_ver, source_ver = check_version_upgrade(
        repo_root, target, args.force
    )
    if not proceed:
        sys.exit(1)

    agent = args.agent
    adapter = get_agent_adapter(agent)
    config_dir = adapter.project_config_dir(target)
    skills_target = adapter.skill_dir(target)
    config_file = config_dir / "godotmaker.yaml"

    # MAJOR upgrade with --force: clean all framework-managed content
    if level == "MAJOR" and args.force:
        # Directories to wipe and recreate
        for d in [
            skills_target,                      # selected agent skills
            adapter.agents_dir(target),          # selected agent agents refs
            adapter.config_dir(target),          # selected agent config
            adapter.templates_dir(target),       # selected agent templates
            target / ".godotmaker" / "hooks",   # .godotmaker/hooks/
            target / "tools",                   # tools/
        ]:
            if d.exists():
                print(f"  Cleaning {d}")
                rmtree_force(d)
        runtime_refs_dir = adapter.runtime_references_dir(target)
        if runtime_refs_dir is not None and runtime_refs_dir.exists():
            print(f"  Cleaning {runtime_refs_dir}")
            rmtree_force(runtime_refs_dir)
        # State files to remove
        for f in [
            target / ".godotmaker" / "state.json",
            target / ".godotmaker" / "metrics.jsonl",
            target / ".godotmaker" / "metrics_current.jsonl",
            target / ".godotmaker" / "stage_schemas.json",
            target / ".godotmaker" / "applied_migrations.json",
        ]:
            if f.exists():
                f.unlink()
                print(f"  Removed {f.name}")
        print("  Full rebuild: framework content cleaned.")
        print("  Preserved: root agent instructions, godotmaker.yaml, config.yaml")
    elif args.force and skills_target.exists():
        print(f"Force: cleaning {skills_target}")
        rmtree_force(skills_target)

    print(f"Publishing to: {target} (agent: {agent})")
    skills_target.mkdir(parents=True, exist_ok=True)

    # Publish all components
    publish_skills(repo_root, skills_target, agent)
    publish_shared_refs(repo_root, skills_target, agent)
    publish_runtime_references(repo_root, target, agent)
    publish_directory(repo_root / "agents", adapter.agents_dir(target),
                      "agents/", "*.md")
    publish_directory(repo_root / "tools", target / "tools", "tools/")
    publish_directory(repo_root / "config", adapter.config_dir(target),
                      "config/", "*")
    godotmaker_dir = target / ".godotmaker"
    godotmaker_dir.mkdir(parents=True, exist_ok=True)
    publish_directory(repo_root / "hooks", godotmaker_dir / "hooks", "hooks/")
    if adapter.deploy_settings:
        deploy_settings(repo_root, config_dir, args.force)
    publish_directory(repo_root / "templates", adapter.templates_dir(target),
                      "templates/", "*.md")
    deploy_agent_instructions(repo_root, target, agent)

    # Interactive config generation
    config_ready = create_godotmaker_yaml(config_file)
    project_config = create_project_config(target, agent)
    if (
        isinstance(project_config, ProjectConfigResult)
        and project_config.created
        and not args.no_config_review
    ):
        review_created_project_config(project_config)
    deploy_stage_schemas(repo_root, target)
    create_project_dirs(target)

    # Agent-specific CLI integrations.
    godot_path = read_godot_path(config_file)
    if adapter.register_claude_mcp:
        register_mcp(target, godot_path)
    elif adapter.agent_id == AGENT_CODEX:
        if not config_ready:
            print("ERROR: Codex publish requires godotmaker.yaml before MCP "
                  "registration can run.")
            sys.exit(1)
        if not register_codex_mcp(target, godot_path):
            sys.exit(1)
    if adapter.register_godot_permissions:
        register_godot_permissions(config_dir / "settings.json", godot_path)

    # Ensure git metadata
    ensure_gitignore(target, agent)
    ensure_gitattributes(target)

    # .worktreeinclude is Claude Code's documented worktree carry-over surface.
    # Codex worktree semantics are not wired through this file, so avoid
    # creating a misleading Codex rule until that adapter is verified.
    if adapter.ensure_worktreeinclude:
        ensure_worktreeinclude(target)

    # Initialize git repo with initial commit (required for worktree isolation)
    ensure_git_repo(target)

    # Migration handling — per-target applied tracking
    # (.godotmaker/applied_migrations.json), decoupled from the bump level.
    # select_migration_action() decides between two paths:
    #   "baseline" — skip execution, mark all current migrations as applied
    #     (FRESH / MAJOR --force: target starts at the latest format and
    #     has nothing to migrate from).
    #   "run" — apply any pending migrations
    #     (SAME / PATCH / MINOR / DOWNGRADE: target has tracked state.
    #     Legacy targets without applied_migrations.json are auto-
    #     bootstrapped to an empty tracker — pending migrations then
    #     run through the standard path. Handled inside run_migrations()
    #     itself.)
    action = select_migration_action(level, args.force)
    if action == "baseline":
        n = baseline_applied(target)
        if n:
            scope = "fresh install" if level == "FRESH" else "MAJOR re-init"
            print(f"Baselined {n} migration(s) for {scope}.")
    else:
        try:
            ok = run_migrations(target)
        except TrackerCorruptionError as e:
            print(f"\nERROR: applied-migrations tracker is corrupt:\n  {e}",
                  file=sys.stderr)
            sys.exit(2)
        if not ok:
            print("\nMigration failed. Published files are updated but migrations incomplete.")
            print("Fix the issue and re-run publish, or use --force for clean install.")
            sys.exit(1)

    # Stamp deployed version
    if source_ver:
        write_target_version(target, source_ver)

    print(f"\nDone (v{source_ver or '?'}). Run 'python tools/check_env.py' in the target project to verify setup.")


if __name__ == "__main__":
    main()
