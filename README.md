# GodotMaker

[![License: BUSL 1.1](https://img.shields.io/badge/License-BUSL_1.1-orange.svg)](LICENSE)
[![Godot 4.x](https://img.shields.io/badge/Godot-4.x-blue?logo=godotengine)](https://godotengine.org)
[![CI](https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml/badge.svg)](https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-teal)](https://RandallLiuXin.github.io/GodotMaker/)

**English** | [中文](README.zh-CN.md)

> **Bring your idea. Give it to GodotMaker. Get a playable game.**

## Why It Exists

Many tools promise that AI can help you make games. Once you actually try to build with them, the same problems tend to show up:

- You only want to realize an idea, but end up sitting at your computer testing builds, taking screenshots, and feeding the agent step-by-step feedback.
- The platform says it is building your game, but the code and project stay on its servers, making it hard to fully download the work or keep developing elsewhere.
- You may get an interesting demo, but it is not grounded in a mature game engine, so iteration, debugging, extension, and publishing become difficult.
- What is mostly a development workflow gets wrapped in platform markup on token usage and a locked runtime environment.

GodotMaker takes a different path: bring the game idea, let it shape that idea into a GDD, then let agents run through planning, implementation, tests, gameplay runs, screenshots, evaluation, and fixes. When the run finishes, you review a real Godot project on your disk.

The code is yours. The GodotMaker framework is source-available, the workflow is local-first, and permitted uses are free under the Business Source License. Want a better game? Refine the idea or GDD and run another iteration.

## What Makes It Different

- **No-human-in-the-loop by default.** Like long-running goal modes in modern coding agents, GodotMaker keeps going after you state the target.
- **From natural language to a complete game project.** Your input can start as a simple game idea; GodotMaker helps turn it into a design contract.
- **The code is yours.** The output is a normal Godot project with source files, scenes, assets, tests, screenshots, and reports.
- **Design-driven iteration.** This is not a one-shot generator. You can keep improving the idea or GDD and keep raising the quality of the game.
- **Built on a mature engine.** The result lands in the Godot ecosystem, where you can continue debugging, extending, exporting, and publishing.
- **No middleman markup.** GodotMaker is the workflow layer. It does not resell agent work through a closed platform.
- **Source-available framework.** The GodotMaker framework is public to inspect, run, modify for permitted uses, and contribute to.
- **Driven by GodotMaker CLI.** The command-line tool drives the workflow end to end so you can run GodotMaker with minimal manual coordination.

External agent runtimes and model providers, such as Claude Code, Codex, Gemini, OpenAI, xAI, or Tripo, may have their own pricing, quotas, and data policies. GodotMaker keeps the framework source-available, the workflow local-first, and the generated project on your machine.

## What The Agents Do

During a run, GodotMaker agents keep moving the design forward:

- turn your idea into `GDD.md`, tasks, scenes, systems, and acceptance criteria
- implement gameplay in Godot
- write gdUnit4 unit tests while writing code
- create end-to-end tests that operate the game like a player
- run the game and capture screenshots
- compare the result against the GDD
- route missing behavior, broken UI, and visual problems back into the fix loop

A small game usually takes about **3-5 hours of agent runtime**. You do not need to manually drive each stage or keep an eye on it the whole time; the workflow is designed to keep going on its own.

## Quick Start

```bash
npm install -g godotmaker-cli

mkdir my-game
cd my-game

# Bring your game idea, then run:
godotmaker
```

The CLI drives the workflow from idea capture and GDD planning to a playable Godot project. Advanced users can still run the underlying role commands directly in Claude Code (`/gm-*`) or Codex (`$gm-*`).

For framework development:

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker
pip install -r tools/requirements.txt
python tools/check_env.py
```

## Requirements

| Tool | Why |
|---|---|
| [Godot 4.5+](https://godotengine.org) | Runs the generated game |
| [Claude Code](https://claude.ai/code) or [Codex](https://openai.com/codex/) | Agent runtime |
| Node.js 18+ | Runs `godotmaker-cli` and Godot MCP tooling |
| Python 3.10+ | Runs GodotMaker helper scripts |
| Git 2.30+ | Enables local history and agent worktrees |

You only need to set an API key when your project configuration selects an API provider. Image generation and visual QA can also use the selected agent runtime when the project is configured for runtime-native providers.

## Learn More

- [Installation](https://RandallLiuXin.github.io/GodotMaker/wiki/01-getting-started/installation/)
- [Your first game](https://RandallLiuXin.github.io/GodotMaker/wiki/01-getting-started/first-game/)
- [How it works](https://RandallLiuXin.github.io/GodotMaker/wiki/02-concepts/how-it-works/)
- [Common problems](https://RandallLiuXin.github.io/GodotMaker/wiki/04-troubleshooting/common-problems/)
- [Roadmap](ROADMAP.md)
- [Full docs](https://RandallLiuXin.github.io/GodotMaker/)

## Status

GodotMaker is preparing for a public alpha under a source-available license. The CLI, Codex support, visual QA, and packaging workflow are evolving quickly.

Preview features and practical fallbacks:

| Area | Current status | If you need predictability |
|---|---|---|
| Codex runner | Preview. It is useful for experimenting with native image generation and Codex-driven runs, but the path is still newer than the Claude Code workflow. | Use Claude Code for the main pipeline run. |
| Art-production pipeline | Preview. The workflow can generate references, canonical character sources, action source sheets, UI sheets, and draft runtime assets, but characters, animation, UI pieces, UI motion, and visual consistency still need human review and may need manual replacement. | Put your own visual assets under `assets/`, then run `/gm-asset` so the workflow can inspect them, update `assets/manifest.json`, and mark matching `ASSETS.md` rows as `provided`. |
| 3D games | Not supported by the current pipeline. The workflow targets 2D games. | Build 2D games for now, or add 3D work manually after generation. |
| Audio generation | Not supported by the current pipeline. Audio rows are treated as user-provided or deferred. | Provide music/SFX manually and wire them into the project yourself until the audio workflow ships. |

A dedicated art-production UI is planned to make curation, slicing, replacement, and review more reliable.

If this direction resonates with you, star the repo, try the CLI, and open issues for the game genres, workflows, and production problems you want GodotMaker to handle better.

## Runtime Note

GodotMaker itself is a workflow layer. Actual execution depends on external agent runtimes. These agents are not components maintained by this repository, and long-running automation can occasionally run into runtime-level issues such as silent timeouts, completed work that does not exit cleanly, transient tool failures, rate limits, or child processes that need cleanup.

Most one-off agent failures can be recovered by stopping the current run and starting `godotmaker-cli` again; the workflow is designed to resume from local project state. Feedback and issue reports are very welcome. If possible, include the key details for that run and the project's `.godotmaker/` directory, which often contains the state and reports needed to diagnose the issue.

## License

Business Source License 1.1. See [LICENSE](LICENSE). Each released version converts to Apache License 2.0 four years after that version is first publicly distributed. **The games you build with GodotMaker fully belong to you**, subject to any third-party engine, asset, model-provider, runtime, or dependency terms that may apply.
