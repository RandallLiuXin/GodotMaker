"""Project config creation helpers for GodotMaker."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from agent_runtime import AGENT_CLAUDE_CODE


DEFAULT_CONFIG_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "config" / "config.yaml.default"
)


@dataclass(frozen=True)
class ProjectConfigResult:
    path: Path
    created: bool


def resolve_config_template(_agent: str) -> Path:
    """Return the config template for the selected coding agent.

    The current release uses one shared project config template. Keeping this
    resolver as the public seam lets future agent-specific defaults land
    without changing callers or wrapper flags.
    """
    return DEFAULT_CONFIG_TEMPLATE


def set_simple_yaml_value(path: Path, key: str, value: str) -> None:
    """Set a top-level scalar key in a simple YAML file."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    updated = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or ":" not in stripped:
            continue
        current_key = stripped.split(":", 1)[0].strip()
        if current_key == key:
            lines[i] = f"{key}: {value}"
            updated = True
            break
    if not updated:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"{key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_project_config(
    target: Path,
    agent: str = AGENT_CLAUDE_CODE,
) -> ProjectConfigResult:
    """Create or update .godotmaker/config.yaml with project settings.

    This helper has deliberately narrow scope: it only creates/preserves the
    user-editable project config. It does not publish framework runtime files,
    write version stamps, initialize git, or run migrations.
    """
    config_dir = target / ".godotmaker"
    config_file = config_dir / "config.yaml"
    if config_file.exists():
        set_simple_yaml_value(config_file, "agent", agent)
        print(".godotmaker/config.yaml already exists, updated agent")
        return ProjectConfigResult(path=config_file, created=False)

    config_dir.mkdir(parents=True, exist_ok=True)
    template = resolve_config_template(agent)
    if template.exists():
        shutil.copy2(template, config_file)
    else:
        config_file.write_text(
            "# GodotMaker config - template not found\n",
            encoding="utf-8",
        )
    set_simple_yaml_value(config_file, "agent", agent)
    print("Created .godotmaker/config.yaml")
    return ProjectConfigResult(path=config_file, created=True)
