# Check your environment

`check_env.py` confirms your machine is set up to run GodotMaker. Run this any time something seems off.

```bash
python tools/check_env.py
```

A clean run ends with:

```
All required checks passed! Ready to use GodotMaker.
```

If anything is missing, you'll see a list of failed checks and what to do about each one.

## What it checks

### Git

- Git 2.30 or later is installed.
- `git user.name` and `git user.email` are set (needed for commits that `/gm-scaffold` and the worktree system create).

### Python

- Python 3.10 or later is running this script.
- Core packages are installed: `requests`, `pillow`, `numpy`.
- Provider packages are checked based on `.godotmaker/config.yaml`: `google-genai` for Gemini, `openai` for OpenAI, and `xai-sdk` for Grok image or video generation.

### Node.js

- Node.js 18 or later is installed (needed to run `godot-mcp` via `npx`).
- `npx` is available on your PATH (it comes with Node.js).

### Godot

- Godot 4.5 or later is reachable as `godot` or `godot4` on your PATH.

If Godot is not on your PATH, this check shows a warning rather than a hard failure — you can still provide the full path to the executable when you run `publish.py`, and it will be saved in `.claude/godotmaker.yaml` for future use.

### Claude Code

- The `claude` command-line tool is installed and on your PATH.

### API keys

| Key | Status | Used for |
|-----|--------|---------|
| `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Required when selected | Gemini image generation or VQA |
| `OPENAI_API_KEY` | Required when selected | OpenAI image generation or VQA |
| `XAI_API_KEY` | Required when selected | xAI Grok image or video generation |
| `TRIPO3D_API_KEY` | Optional | 3D model generation (3D games only) |

API-backed selectors fail when the matching key is absent. `asset_image_model: native` passes for Codex and warns for Claude Code because the checker cannot prove a Claude-side native generation tool is available. `asset_image_model: codex` in a Claude Code project passes when the Codex CLI is on PATH. `asset_video_model: none` does not require `XAI_API_KEY`.

The checker also verifies that the selected provider package can be imported, catching installation issues that version checks alone would miss.

## Reading the output

Each line starts with one of three markers:

```
[PASS] Git 2.43.0 (>= 2.30)
[FAIL] Package 'google-genai' missing. Run: pip install google-genai
[WARN] XAI_API_KEY not set (optional, cheaper image generation)
```

`[WARN]` lines are for optional items — they don't stop you from using GodotMaker. `[FAIL]` lines are blockers.

At the end, any failed checks are listed together so you can fix them in one pass:

```
========================================
Total: 14 checks
  PASS: 12
  FAIL: 1
  WARN: 1

Failed checks:
  - Package 'google-genai' missing. Run: pip install google-genai

Fix the above issues before using GodotMaker.
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All required checks passed (warnings are fine) |
| 1 | One or more required checks failed |

Scripts and CI pipelines can rely on this exit code to gate further steps.

## If you're just getting started

See [installation](../01-getting-started/installation.md) for a step-by-step guide to getting all these prerequisites in place before running `check_env.py`.
