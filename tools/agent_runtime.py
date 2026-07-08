"""Agent runtime helpers for project-local GodotMaker tools."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import sys


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


def find_project_dir(start: Path | None = None) -> Path:
    """Find the nearest Godot project root at or above `start`."""
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / "project.godot").exists():
            return candidate
    return current


def read_config_value(
    project_dir: Path,
    key: str,
    *,
    agent: str | None = None,
    default: str | None = None,
) -> str | None:
    value = _read_yaml_scalar(godotmaker_yaml(project_dir, agent), key)
    return value if value else default


def read_godot_path(project_dir: Path, default: str | None = None) -> str | None:
    return read_config_value(project_dir, "godot_path", default=default)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read a value from the selected GodotMaker agent config."
    )
    parser.add_argument("key", help="Config key to read, for example godot_path")
    parser.add_argument(
        "--project",
        default=".",
        help="Project directory or a path inside the project (default: cwd)",
    )
    parser.add_argument(
        "--agent",
        choices=[AGENT_CLAUDE_CODE, AGENT_CODEX, AGENT_OPENCODE],
        default=None,
        help="Override selected agent runtime",
    )
    parser.add_argument(
        "--default",
        default=None,
        help="Value to print when the key is absent",
    )
    args = parser.parse_args(argv)

    project_dir = find_project_dir(Path(args.project))
    value = read_config_value(
        project_dir,
        args.key,
        agent=args.agent,
        default=args.default,
    )
    if value:
        print(value)
        return 0

    config_path = godotmaker_yaml(project_dir, args.agent)
    print(
        f"Error: key '{args.key}' not found in {config_path}",
        file=sys.stderr,
    )
    return 1


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


# Godot's `--log-file` disables the engine's built-in log rotation
# (godotengine/godot PR #87373), so we manage retention here and keep the
# newest MAX_GODOT_LOG_FILES per kind — mirroring Godot's own
# `debug/file_logging/max_log_files` default of 5.
MAX_GODOT_LOG_FILES = 5


def _log_timestamp() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).strftime("%Y-%m-%dT%H.%M.%S")


def _prune_godot_logs(logs_dir: Path, kind: str, *, keep: int) -> None:
    """Delete the oldest `godot-<kind>-*.log` files so that once the caller
    writes a new one, at most `keep` remain. Best-effort; never raises."""
    try:
        existing = sorted(
            logs_dir.glob(f"godot-{kind}-*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return
    for stale in existing[max(keep - 1, 0):]:
        try:
            stale.unlink()
        except OSError:
            pass


def godot_log_file(
    project_dir: Path,
    kind: str,
    *,
    keep: int = MAX_GODOT_LOG_FILES,
) -> str:
    """Return an absolute `--log-file` path under `<project>/.godotmaker/logs/`.

    Redirecting Godot's headless log out of the default `user://logs/...`
    lets verify run under sandboxes (e.g. Codex CLI) that cannot create the
    engine's user-data directory. Older logs of the same `kind` are pruned to
    the newest `keep`; `kind` (build / gdunit / static) keeps the concurrent
    headless calls from clobbering each other.
    """
    logs_dir = project_dir / ".godotmaker" / "logs"
    try:
        # parents=False on purpose: only create `logs/` inside an existing
        # `.godotmaker/` project. Outside one (e.g. unit-test stub paths) this
        # raises FileNotFoundError, which we swallow so no stray dirs appear.
        logs_dir.mkdir(exist_ok=True)
    except OSError:
        pass
    _prune_godot_logs(logs_dir, kind, keep=keep)
    return str(logs_dir / f"godot-{kind}-{_log_timestamp()}.log")


if __name__ == "__main__":
    raise SystemExit(main())
