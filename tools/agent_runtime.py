"""Agent runtime helpers for project-local GodotMaker tools."""
from __future__ import annotations

from pathlib import Path


AGENT_CLAUDE_CODE = "claude-code"
AGENT_CODEX = "codex"
AGENT_OPENCODE = "opencode"


def _read_yaml_scalar(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        current_key, value = stripped.split(":", 1)
        if current_key.strip() == key:
            value = value.strip().strip('"').strip("'")
            return value or None
    return None


def normalize_agent(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-")
    if normalized in {"codex", "openai-codex"}:
        return AGENT_CODEX
    if normalized in {"opencode", "open-code"}:
        return AGENT_OPENCODE
    if normalized in {"claude", "claude-code", "anthropic-claude-code"}:
        return AGENT_CLAUDE_CODE
    return None


def detect_agent(project_dir: Path) -> str:
    """Detect the selected coding agent for a published project."""
    config = project_dir / ".godotmaker" / "config.yaml"
    for key in ("agent", "agent_runtime"):
        agent = normalize_agent(_read_yaml_scalar(config, key))
        if agent:
            return agent

    # Backward-compatible fallback for older projects without `agent`.
    if (project_dir / ".agents").exists():
        return AGENT_CODEX
    if (project_dir / ".opencode").exists():
        return AGENT_OPENCODE
    return AGENT_CLAUDE_CODE


def agent_config_root(project_dir: Path, agent: str | None = None) -> Path:
    selected = normalize_agent(agent) or detect_agent(project_dir)
    if selected == AGENT_CODEX:
        return project_dir / ".agents"
    if selected == AGENT_OPENCODE:
        return project_dir / ".opencode"
    return project_dir / ".claude"


def agent_skill_root(project_dir: Path, agent: str | None = None) -> Path:
    return agent_config_root(project_dir, agent) / "skills"


def agent_runtime_mapping(project_dir: Path, agent: str | None = None) -> Path:
    selected = normalize_agent(agent) or detect_agent(project_dir)
    if selected == AGENT_CODEX:
        return project_dir / ".agents" / "references" / "runtime-mapping.md"
    if selected == AGENT_OPENCODE:
        return project_dir / ".opencode" / "references" / "runtime-mapping.md"
    return project_dir / ".claude" / "references" / "runtime-mapping.md"


def godotmaker_yaml(project_dir: Path, agent: str | None = None) -> Path:
    return agent_config_root(project_dir, agent) / "godotmaker.yaml"


def read_godot_path(project_dir: Path, default: str | None = None) -> str | None:
    value = _read_yaml_scalar(godotmaker_yaml(project_dir), "godot_path")
    return value if value else default


def prefer_console_godot_path(godot_path: str | None) -> str | None:
    """Prefer Godot's Windows console sibling when it exists.

    The GUI Windows executable can detach from the caller quickly and hide
    headless output. Godot distributes a sibling named `*_console.exe` for
    command-line use; use it at runtime without rewriting the configured path.
    """
    if not godot_path:
        return godot_path

    path = Path(godot_path)
    if path.suffix.lower() != ".exe":
        return godot_path
    if path.stem.lower().endswith("_console"):
        return godot_path

    console_path = path.with_name(f"{path.stem}_console{path.suffix}")
    try:
        if console_path.exists():
            return str(console_path)
    except OSError:
        return godot_path
    return godot_path
