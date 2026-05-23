# GodotMaker

[![License: BUSL 1.1](https://img.shields.io/badge/License-BUSL_1.1-orange.svg)](LICENSE)
[![Godot 4.x](https://img.shields.io/badge/Godot-4.x-blue?logo=godotengine)](https://godotengine.org)
[![CI](https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml/badge.svg)](https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-teal)](https://RandallLiuXin.github.io/GodotMaker/)

**English** | [中文](README.zh-CN.md)

> **Bring your idea. Give it to GodotMaker. Get a playable game.**

## Why It Exists

Many tools promise "AI-made games." In practice, they often come with the same problems:

- You only want to realize an idea, but you still sit in front of the computer testing builds, taking screenshots, and feeding the agent step-by-step feedback.
- The platform says it is building the game for you, but the code and project stay on its servers, making it hard to download everything or continue elsewhere.
- You finally get a fun demo, but it is not grounded in a mature game engine, so iteration, debugging, extension, and publishing become difficult.
- What is mostly a development workflow still gets wrapped in expensive token markup and a locked runtime environment.

GodotMaker takes a different route: bring the game idea, let it help shape that idea into a GDD, then let agents run for hours through planning, implementation, tests, gameplay runs, screenshots, evaluation, and fixes. When the run finishes, you review a real Godot project on your disk.

The code is yours. The workflow source is source-available, local-first, and free to run for permitted uses under the Business Source License. If you want a better game, refine the idea or GDD and run another iteration.

## What Makes It Different

- **No-human-in-the-loop by default.** Like long-running goal/task modes in modern coding agents, GodotMaker keeps going after you state the target.
- **Natural language to a complete game project.** Your input can start as a game idea; GodotMaker helps shape it into the design contract.
- **The code is yours.** The output is a normal Godot project with source files, scenes, assets, tests, screenshots, and reports.
- **Iterate through the design.** Keep refining the idea or GDD and let later runs improve the game instead of starting over.
- **Built on a real engine.** The result lands in the Godot ecosystem, so you can keep debugging, extending, exporting, and shipping.
- **No middleman markup.** GodotMaker is the workflow layer. It does not resell agent work through a closed platform.
- **Source-available automation.** The framework and CLI-driven workflow are public to inspect, run, modify for permitted uses, and contribute to.

External agent runtimes and model providers, such as Claude Code, Codex, Gemini, OpenAI, xAI, or Tripo, may have their own pricing, quotas, and data policies. GodotMaker keeps the workflow open and the project local.

## What The Agents Do

During a run, GodotMaker agents keep pushing the design forward:

- turn your idea into `GDD.md`, tasks, scenes, systems, and acceptance criteria
- implement gameplay in Godot
- write gdUnit4 unit tests while writing code
- create end-to-end tests that operate the game like a player
- run the game and capture screenshots
- compare the result against the GDD
- route missing behavior, broken UI, and visual problems back into the fix loop

A small game usually takes about **3-5 hours of agent runtime**. The promise is not instant output. The promise is that the workflow keeps moving without you manually driving every phase.

## Quick Start

```bash
npm install -g godotmaker-cli

mkdir my-game
cd my-game

# Bring your game idea, then run:
godotmaker
```

The CLI drives the workflow from idea capture and GDD planning to a playable Godot tag. Advanced users can still run the underlying role commands directly with Claude Code (`/gm-*`) or Codex (`$gm-*`).

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

Optional API keys are needed only when your project config selects API-backed providers. Runtime-native image or vision paths can use your selected agent runtime instead.

## Learn More

- [Installation](https://RandallLiuXin.github.io/GodotMaker/wiki/01-getting-started/installation/)
- [Your first game](https://RandallLiuXin.github.io/GodotMaker/wiki/01-getting-started/first-game/)
- [How it works](https://RandallLiuXin.github.io/GodotMaker/wiki/02-concepts/how-it-works/)
- [Common problems](https://RandallLiuXin.github.io/GodotMaker/wiki/04-troubleshooting/common-problems/)
- [Full docs](https://RandallLiuXin.github.io/GodotMaker/)

## Status

GodotMaker is preparing for a source-available public alpha. The CLI, Codex support, visual QA, and packaging are moving quickly.

If this direction is useful to you, star the repo, try the CLI, and open issues with the games you want it to build better.

## License

Business Source License 1.1. See [LICENSE](LICENSE). Each released version converts to Apache License 2.0 four years after that version is first publicly distributed. **The games you build with GodotMaker are not GodotMaker and are entirely yours**, subject to any third-party engine, asset, model-provider, runtime, or dependency terms that may apply.
