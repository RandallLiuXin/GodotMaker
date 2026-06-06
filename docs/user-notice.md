# User Notice

Things GodotMaker does automatically, what stays local, and what may be sent to external services.

## Local Project Ownership

GodotMaker creates a normal Godot project on your machine. The generated project is not hosted by GodotMaker and is not locked to a proprietary editor or runtime.

You can open, edit, version, export, and ship the generated game like any other Godot project.

Games, project source code, assets, screenshots, reports, exports, and other outputs created with GodotMaker are not GodotMaker and are not part of the Licensed Work. They belong to their creators, subject to any third-party engine, asset, model-provider, runtime, or dependency terms that may apply.

## Publish Script Auto-Actions

The publish script (`tools/publish.py`) performs local setup actions in your game project directory. If you are experienced with these tools, you can manage them yourself; the script skips steps that are already done.

### Git Repository Initialization

**What happens:** If your project directory does not have a `.git/` folder, the publish script runs `git init` and creates an initial empty commit.

**Why:** GodotMaker uses isolated git worktrees for agent workers. Worktrees require at least one commit to exist.

This has nothing to do with pushing code to GitHub or any remote server. The commit is local and exists to enable the worker infrastructure.

**What if I already have a git repo?** The script detects `.git/` and skips `git init`. If a commit already exists, it skips that too. Your existing history is not rewritten.

## Agent Runtime Data

GodotMaker is an orchestration framework. It relies on the agent runtime you choose, such as Claude Code or Codex, to read project files, write code, run tools, and evaluate results.

Depending on the runtime and settings, the following content may be visible to that runtime:

- your game idea, GDD, and planning docs
- source code and tests in the generated project
- command output and tool logs
- screenshots captured for visual QA
- prompts and instructions sent to implementation, verifier, reviewer, evaluator, or analyst agents

Review the privacy, retention, and billing terms of the agent runtime you use. GodotMaker does not control those external policies.

## Optional API Providers

GodotMaker can call external providers when your project config selects API-backed models.

Possible providers include:

- Gemini, through `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- OpenAI, through `OPENAI_API_KEY`
- xAI Grok, through `XAI_API_KEY`

Depending on the selected feature, requests may include prompts, asset descriptions, screenshots, reference images, or generated asset data. API usage may be billed by the provider.

If you do not want a provider to receive project data, do not configure that provider's model or API key.

## Native Image and Vision Paths

Some configurations use runtime-native image or vision capabilities instead of direct API keys. In that case, image or screenshot data is handled by the active agent runtime rather than by GodotMaker's Python API clients.

This can reduce separate API setup, but it does not make the data local-only. The runtime's own policy still applies.

## Secrets

Do not commit API keys, access tokens, or private credentials into your game project or the GodotMaker repository.

Recommended storage:

- environment variables for API keys
- local, gitignored runtime config for host-specific paths
- GitHub repository secrets for CI or release automation
