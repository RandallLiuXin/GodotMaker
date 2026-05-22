#!/usr/bin/env python3
"""Check that the GodotMaker development environment is correctly set up.

Verifies: Git, Python, Node.js, Godot, selected coding agent, API keys, pip
packages.

Usage:
    python tools/check_env.py
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from agent_runtime import AGENT_CLAUDE_CODE, AGENT_CODEX, detect_agent, read_godot_path


class EnvCheck:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []

    def ok(self, msg: str):
        self.passed.append(msg)
        print(f"  [PASS] {msg}")

    def fail(self, msg: str):
        self.failed.append(msg)
        print(f"  [FAIL] {msg}")

    def warn(self, msg: str):
        self.warnings.append(msg)
        print(f"  [WARN] {msg}")


def get_version(cmd: str, pattern: str = r"(\d+(?:\.\d+)+)") -> str | None:
    """Run `cmd --version` and extract version number."""
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout + result.stderr
        match = re.search(pattern, output)
        return match.group(1) if match else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def parse_version(v: str) -> tuple[int, ...]:
    """Parse '4.4.1' to (4, 4, 1)."""
    return tuple(int(x) for x in v.split(".")[:3])


def load_project_config(project_dir: Path) -> dict[str, str]:
    """Read simple top-level scalar values from .godotmaker/config.yaml."""
    config_path = project_dir / ".godotmaker" / "config.yaml"
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith((" ", "\t")):
            continue
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and value:
            values[key] = value
    return values


def split_model_selector(selector: str, default_provider: str) -> tuple[str, str]:
    raw = (selector or "").strip()
    if ":" in raw:
        provider, model = raw.split(":", 1)
        return provider.strip(), model.strip()
    if raw in {"native", "codex", "gemini", "openai", "grok", "none"}:
        return raw, raw
    if raw:
        return default_provider, raw
    return default_provider, ""


def image_model_from_config(config: dict[str, str]) -> str:
    if config.get("asset_image_model"):
        return config["asset_image_model"]
    provider = config.get("asset_image_provider")
    if provider == "gemini":
        model = config.get("gemini_image_model") or "gemini-3.1-flash-image-preview"
        return f"gemini:{model}"
    if provider == "grok":
        return f"grok:{config.get('grok_image_model') or 'grok-imagine-image'}"
    if config.get("gemini_image_model"):
        return f"gemini:{config['gemini_image_model']}"
    if config.get("grok_image_model"):
        return f"grok:{config['grok_image_model']}"
    return provider or "native"


def video_model_from_config(config: dict[str, str]) -> str:
    if config.get("asset_video_model"):
        return config["asset_video_model"]
    if config.get("grok_video_model"):
        return f"grok:{config['grok_video_model']}"
    return "none"




# --- Individual checks ---


def check_git(r: EnvCheck):
    print("\n--- Git ---")
    version = get_version("git")
    if not version:
        r.fail("Git not found. Install: https://git-scm.com/downloads")
        return

    if parse_version(version) >= (2, 30):
        r.ok(f"Git {version} (>= 2.30)")
    else:
        r.fail(f"Git {version} too old (>= 2.30 required)")

    # Check identity config
    for key, label in [("user.name", "user.name"), ("user.email", "user.email")]:
        try:
            res = subprocess.run(
                ["git", "config", key],
                capture_output=True, text=True, timeout=5,
            )
            val = res.stdout.strip()
            if val:
                r.ok(f"Git {label}: {val}")
            else:
                r.warn(f"Git {label} not set. Run: git config --global {key} \"...\"")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


def check_python(r: EnvCheck, config: dict[str, str] | None = None):
    print("\n--- Python ---")
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 9):
        r.ok(f"Python {version} (>= 3.9)")
    else:
        r.fail(f"Python {version} too old (>= 3.9 required)")

    config = config or {}
    packages = {"pillow": "PIL", "numpy": "numpy", "requests": "requests"}
    image_provider, _ = split_model_selector(image_model_from_config(config), "gemini")
    video_provider, _ = split_model_selector(video_model_from_config(config), "grok")
    vqa_provider, _ = split_model_selector(
        config.get("vqa_model") or "native", "gemini"
    )
    if "gemini" in {image_provider, vqa_provider}:
        packages["google-genai"] = "google.genai"
    if "openai" in {image_provider, vqa_provider}:
        packages["openai"] = "openai"
    if image_provider == "grok" or video_provider == "grok":
        packages["xai-sdk"] = "xai_sdk"

    for pkg_name, import_name in packages.items():
        try:
            __import__(import_name)
            r.ok(f"Package '{pkg_name}' installed")
        except ImportError:
            r.fail(f"Package '{pkg_name}' missing. Run: pip install {pkg_name}")


def check_node(r: EnvCheck):
    print("\n--- Node.js ---")
    version = get_version("node")
    if not version:
        r.fail("Node.js not found. Install: https://nodejs.org")
        return

    if int(version.split(".")[0]) >= 18:
        r.ok(f"Node.js {version} (>= 18)")
    else:
        r.fail(f"Node.js {version} too old (>= 18 required)")

    if shutil.which("npx"):
        r.ok("npx available")
    else:
        r.fail("npx not found (should come with Node.js)")


def _get_version_from_path(path: str, pattern: str = r"(\d+(?:\.\d+)+)") -> str | None:
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout + result.stderr
        match = re.search(pattern, output)
        return match.group(1) if match else None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def check_godot(r: EnvCheck, project_dir: Path):
    print("\n--- Godot ---")
    configured = read_godot_path(project_dir)
    if configured:
        version = _get_version_from_path(configured)
        if version and parse_version(version)[:2] >= (4, 4):
            r.ok(f"Godot {version}, configured path: {configured}")
            return
        if version:
            r.fail(f"Configured Godot {version} too old at {configured}")
            return
        r.fail(f"Configured Godot path does not run: {configured}")
        return

    for cmd in ("godot", "godot4"):
        version = get_version(cmd)
        if version and parse_version(version)[:2] >= (4, 4):
            r.ok(f"Godot {version}, command: {cmd}")
            return
        elif version:
            r.fail(f"Godot {version} too old (>= 4.4 required)")
            return

    r.warn(
        "Godot not found on PATH. Provide the full path when running publish, "
        "or add it to PATH."
    )


def check_claude(r: EnvCheck):
    print("\n--- Claude Code ---")
    cmd = (
        shutil.which("claude")
        or shutil.which("claude.cmd")
        or shutil.which("claude.exe")
    )
    if cmd:
        r.ok(f"Claude Code found: {cmd}")
    else:
        r.fail("Claude Code not found. Install: npm install -g @anthropic-ai/claude-code")


def check_codex(r: EnvCheck, project_dir: Path):
    print("\n--- Codex ---")
    cmd = (
        shutil.which("codex")
        or shutil.which("codex.cmd")
        or shutil.which("codex.exe")
    )
    if not cmd:
        r.fail("Codex CLI not found. Install Codex before using agent: codex.")
        return
    version = get_version(cmd, pattern=r"(\d+(?:\.\d+)+)")
    r.ok(f"Codex CLI found: {cmd}" + (f" ({version})" if version else ""))

    mapping = project_dir / ".agents" / "references" / "runtime-mapping.md"
    skills = project_dir / ".agents" / "skills"
    config = project_dir / ".agents" / "godotmaker.yaml"
    for path, label in [
        (skills, ".agents/skills"),
        (mapping, ".agents/references/runtime-mapping.md"),
        (config, ".agents/godotmaker.yaml"),
    ]:
        if path.exists():
            r.ok(f"{label} present")
        else:
            r.fail(f"{label} missing; re-run publish with --agent codex")

    try:
        result = subprocess.run(
            [cmd, "mcp", "list"],
            cwd=str(project_dir),
            capture_output=True, text=True, timeout=15,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0 and "godot" in output:
            r.ok("Codex MCP server 'godot' configured")
        elif result.returncode == 0:
            r.fail("Codex MCP server 'godot' missing; re-run publish")
        else:
            r.fail("Could not list Codex MCP servers")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        r.fail("Could not list Codex MCP servers")


def check_selected_agent(r: EnvCheck, project_dir: Path):
    agent = detect_agent(project_dir)
    print(f"\n--- Selected Agent ({agent}) ---")
    if agent == AGENT_CODEX:
        check_codex(r, project_dir)
    elif agent == AGENT_CLAUDE_CODE:
        check_claude(r)
    else:
        r.fail(f"Unsupported GodotMaker agent: {agent}")


def check_runtime_model_provider(
    r: EnvCheck,
    provider: str,
    agent: str,
    capability: str,
):
    print("\n--- Runtime Image Provider ---")
    if provider == "native":
        if capability == "image_inspection" and agent in {AGENT_CODEX, AGENT_CLAUDE_CODE}:
            r.ok("native image inspection uses the active agent runtime")
        elif capability == "image_generation" and agent == AGENT_CODEX:
            r.ok("native image generation uses the active Codex runtime")
        elif capability == "image_generation" and agent == AGENT_CLAUDE_CODE:
            r.warn(
                "native image generation for Claude Code must be provided by "
                "the active runtime"
            )
        else:
            r.fail("native image provider is unsupported for this agent runtime")
        return

    if provider == "codex":
        if agent == AGENT_CODEX:
            r.ok(f"Codex {capability.replace('_', ' ')} uses the active Codex runtime")
            return
        if shutil.which("codex") or shutil.which("codex.cmd") or shutil.which("codex.exe"):
            if capability == "image_generation":
                r.ok("Codex CLI found for Codex image generation")
            else:
                r.ok("Codex CLI found for Codex image inspection")
        else:
            r.fail("Codex image provider selected but Codex CLI was not found")


def check_api_keys(
    r: EnvCheck,
    config: dict[str, str] | None = None,
    agent: str = AGENT_CLAUDE_CODE,
):
    print("\n--- API Keys ---")
    config = config or {}
    image_provider, _ = split_model_selector(image_model_from_config(config), "gemini")
    video_provider, _ = split_model_selector(video_model_from_config(config), "grok")
    vqa_provider, _ = split_model_selector(
        config.get("vqa_model") or "native", "gemini"
    )
    required = {image_provider, vqa_provider}

    if image_provider in {"native", "codex"}:
        required.discard("native")
        required.discard("codex")
        check_runtime_model_provider(r, image_provider, agent, "image_generation")
    if vqa_provider in {"native", "codex"}:
        required.discard("native")
        required.discard("codex")
        if vqa_provider != image_provider:
            check_runtime_model_provider(r, vqa_provider, agent, "image_inspection")

    google_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if "gemini" in required:
        if google_key:
            masked = google_key[:8] + "..." + google_key[-4:] if len(google_key) > 12 else "***"
            r.ok(f"GOOGLE_API_KEY set ({masked})")

            try:
                from google import genai  # noqa: F401
                r.ok("google-genai import OK")
            except Exception as e:
                r.warn(f"google-genai import failed: {e}")
        else:
            r.fail(
                "GOOGLE_API_KEY not set but config uses a Gemini model. "
                "Get one: https://aistudio.google.com/apikey"
            )
    else:
        r.warn("GOOGLE_API_KEY not set (not required by current config)")

    if "openai" in required:
        if os.environ.get("OPENAI_API_KEY"):
            r.ok("OPENAI_API_KEY set")
        else:
            r.fail("OPENAI_API_KEY not set but config uses an OpenAI model")
    elif os.environ.get("OPENAI_API_KEY"):
        r.ok("OPENAI_API_KEY set (optional)")
    else:
        r.warn("OPENAI_API_KEY not set (optional)")

    if image_provider == "grok":
        if os.environ.get("XAI_API_KEY"):
            r.ok("XAI_API_KEY set")
        else:
            r.fail("XAI_API_KEY not set but asset_image_model uses a Grok model")
    elif video_provider == "grok":
        if os.environ.get("XAI_API_KEY"):
            r.ok("XAI_API_KEY set (for configured video generation)")
        else:
            r.warn(
                "XAI_API_KEY not set (required only if you run asset video generation)"
            )
    elif os.environ.get("XAI_API_KEY"):
        r.ok("XAI_API_KEY set (optional)")
    else:
        r.warn("XAI_API_KEY not set (optional)")

    if os.environ.get("TRIPO3D_API_KEY"):
        r.ok("TRIPO3D_API_KEY set (optional)")
    else:
        r.warn("TRIPO3D_API_KEY not set (optional, 3D model generation)")




def main():
    print("GodotMaker Environment Check")
    print("=" * 40)

    r = EnvCheck()
    project_dir = Path(__file__).resolve().parent.parent
    config = load_project_config(project_dir)
    agent = detect_agent(project_dir)

    check_git(r)
    check_python(r, config)
    check_node(r)
    check_godot(r, project_dir)
    check_selected_agent(r, project_dir)
    check_api_keys(r, config, agent)

    # Summary
    total = len(r.passed) + len(r.failed) + len(r.warnings)
    print(f"\n{'=' * 40}")
    print(f"Total: {total} checks")
    print(f"  PASS: {len(r.passed)}")
    print(f"  FAIL: {len(r.failed)}")
    print(f"  WARN: {len(r.warnings)}")

    if r.failed:
        print("\nFailed checks:")
        for f in r.failed:
            print(f"  - {f}")
        print("\nFix the above issues before using GodotMaker.")
        sys.exit(1)
    else:
        print("\nAll required checks passed! Ready to use GodotMaker.")
        sys.exit(0)


if __name__ == "__main__":
    main()
