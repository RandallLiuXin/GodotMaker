# Installation

GodotMaker turns a game idea into a playable Godot 4 project. The normal path is `godotmaker-cli`: it helps shape the idea into a GDD, then drives the agent workflow until the current design scope is built, tested, evaluated, and fixed.

## Prerequisites

| Tool | Minimum version | Why GodotMaker needs it | Where to get it |
|------|-----------------|-------------------------|-----------------|
| Godot | 4.5+ | Compiles and runs the generated game | https://godotengine.org/download |
| Git | 2.30+ | Tracks changes and enables isolated agent worktrees | https://git-scm.com/downloads |
| Node.js | 22+ | Runs `godotmaker-cli` and Godot MCP tooling | https://nodejs.org |
| Python | 3.10+ | Runs GodotMaker helper scripts and verification tools | https://python.org/downloads |
| Claude Code or Codex | Latest | Agent runtime used to implement and evaluate the game | https://claude.ai/code or https://openai.com/codex/ |

Install each one, then continue. You only need one authenticated agent runtime for the first run: Claude Code or Codex.

## Choose an agent runner

GodotMaker is normally launched through `godotmaker-cli`. Pick the runner at launch time:

```bash
godotmaker-cli --agent claude-code
godotmaker-cli --agent codex
```

`--agent` is the safest way to switch runners for one run. If it is omitted, the CLI resolves the runner from the project config, then the CLI-global config, then the default runner.

## API Keys

GodotMaker can use runtime-native image and vision capabilities or API-backed providers depending on `.godotmaker/config.yaml`.

API keys are required only when the project selects an API-backed provider. GodotMaker itself does not provide the external model service. If you want Codex to provide image generation in a Claude Code project, set `asset_image_model: codex`; this requires Codex CLI on PATH and does not require an image API key.

| Key | Required when | What it unlocks |
|-----|---------------|-----------------|
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | `vqa_model` or an asset model uses `gemini:<model>` | Gemini visual QA and image generation |
| `OPENAI_API_KEY` | `vqa_model` or an asset model uses `openai:<model>` | OpenAI vision and image generation |
| `XAI_API_KEY` | an asset image model uses `grok:<model>` | xAI image generation |

### Windows PowerShell

```powershell
[System.Environment]::SetEnvironmentVariable("GOOGLE_API_KEY", "your-key-here", "User")
```

Repeat for any optional key you use, then close and reopen your terminal.

### macOS or Linux

Add the relevant lines to your shell profile, then restart your terminal:

```bash
export GOOGLE_API_KEY="your-key-here"
# Optional:
# export OPENAI_API_KEY="your-key-here"
# export XAI_API_KEY="your-key-here"
```

## Install GodotMaker

Install the CLI:

```bash
npm install -g godotmaker-cli
```

Check the installed command:

```bash
godotmaker-cli --help
```

For framework development or manual publishing, clone the repository:

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker
pip install -r tools/requirements.txt
python tools/check_env.py
```

Set your Git identity if you have never done it:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## What the Environment Check Means

`python tools/check_env.py` verifies local tools and selected providers.

- `[PASS]` means the item is ready.
- `[WARN]` means an optional feature is unavailable.
- `[FAIL]` means a required item for the selected workflow is missing.

Fix every `[FAIL]` line before starting your first game.

## Next

Continue to [Your first game](first-game.md).
