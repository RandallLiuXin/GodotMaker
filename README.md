<p align="center">
  <img src="docs/assets/icon.png" alt="GodotMaker" width="128">
</p>

<h1 align="center">GodotMaker</h1>

<p align="center">
  Bring your idea. Give it to GodotMaker. Get a playable game.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BUSL_1.1-orange.svg" alt="License: BUSL 1.1"></a>
  <a href="https://godotengine.org"><img src="https://img.shields.io/badge/Godot-4.x-blue?logo=godotengine" alt="Godot 4.x"></a>
  <a href="https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml"><img src="https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://RandallLiuXin.github.io/GodotMaker/"><img src="https://img.shields.io/badge/docs-online-teal" alt="Docs"></a>
</p>

**English** | [中文](README.zh-CN.md)

## Why I Built This

In game development, especially early ideation and market validation stages, teams often come up with more ideas than they can develop. The usual approach is to discuss and pick one idea for development, only to find out after a couple of weeks that the idea is not viable, making the previous discussion and development efforts wasted. I built GodotMaker to allow individuals to turn their ideas into playable prototypes quickly, validating the feasibility and fun of their ideas. This will significantly speed up the early stages of game development, helping developers find truly worthwhile game concepts faster.

## Why Choose GodotMaker

Many tools promise that AI can help you make games. Once you actually try to build with them, the same problems tend to show up:

- You only want to realize an idea, but end up sitting at your computer testing builds, taking screenshots, and feeding the agent step-by-step feedback.
- The platform says it is building your game, but the code and project stay on its servers, making it hard to fully download the work or keep developing elsewhere.
- You may get an interesting demo, but it is not grounded in a mature game engine, so iteration, debugging, extension, and publishing become difficult.
- What is mostly a development workflow gets wrapped in platform markup on token usage and a locked runtime environment.

GodotMaker takes a different path: bring the game idea, let it shape that idea into a GDD, then let agents run through planning, implementation, tests, gameplay runs, screenshots, evaluation, and fixes. When the run finishes, you review a real Godot project on your disk.

The code is yours. The GodotMaker framework is source-available, the workflow is local-first. Want a better game? Refine the idea or GDD and run another iteration.

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

- turn your idea into `GDD.md`, tasks, scenes, systems, assets, and acceptance criteria
- implement gameplay in Godot
- write gdUnit4 unit tests while writing code
- create end-to-end tests that operate the game like a player
- run the game and capture screenshots
- compare the result against the GDD
- route missing behavior, broken UI, and visual problems back into the fix loop

A small prototype usually takes about **5-8 hours of agent runtime**. You do not need to manually drive each stage or keep an eye on it the whole time; the workflow is designed to keep going on its own.

## Community

- [Discord](https://discord.gg/rjhP9Z9PHP)

## Quick Start

```bash
npm install -g godotmaker-cli

mkdir my-game
cd my-game

# Bring your game idea, then run:
godotmaker-cli --agent claude-code
```

Use Codex or OpenCode for the same workflow:

```bash
godotmaker-cli --agent codex
godotmaker-cli --agent opencode
```

The CLI drives the workflow from idea capture and GDD planning to a playable Godot prototype. Agent selection resolves in this order: `--agent`, project `.godotmaker/config.yaml`, CLI-global `~/.godotmaker/cli/config.yaml`, then the default runner. Advanced users can still run the underlying role commands directly in Claude Code (`/gm-*`), Codex (`$gm-*`), or OpenCode (`/gm-*`).

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
| [Godot 4.5+](https://godotengine.org) | Runs the generated project |
| [Claude Code](https://claude.ai/code), [Codex](https://openai.com/codex/), or [OpenCode](https://opencode.ai/) | Command-line agent runtime for CLI-driven runs; desktop chat apps are not sufficient |
| Node.js 22+ | Runs `godotmaker-cli` and Godot MCP tooling |
| Python 3.10+ | Runs GodotMaker helper scripts |
| Git 2.30+ | Enables local history and agent worktrees |

You only need to set an API key when your project configuration selects an API provider. Image generation and visual QA can use runtime-native providers only when the selected agent runtime supports them; OpenCode projects should configure `codex` or API-backed image/VQA providers.

## Learn More

- [Installation](https://RandallLiuXin.github.io/GodotMaker/wiki/01-getting-started/installation/)
- [Your first game](https://RandallLiuXin.github.io/GodotMaker/wiki/01-getting-started/first-game/)
- [How it works](https://RandallLiuXin.github.io/GodotMaker/wiki/02-concepts/how-it-works/)
- [Common problems](https://RandallLiuXin.github.io/GodotMaker/wiki/04-troubleshooting/common-problems/)
- [Roadmap](ROADMAP.md)
- [Full docs](https://RandallLiuXin.github.io/GodotMaker/)

## Status And Boundaries

GodotMaker is preparing for a public alpha under a source-available license. The CLI, agent-runner support, visual QA, and packaging workflow are evolving quickly. Core gameplay generation is usually the most reliable part of the flow. Because AI output is still variable and the art pipeline is still alpha, a completed run may still need a follow-up pass with a coding agent to correct visual wiring issues such as the wrong atlas region, missing animation setup, or incomplete asset binding.

Current boundaries:

| Capability | Current status | Notes |
|---|---|---|
| 2D only | The current framework targets 2D Godot games. | Do not start with a 3D game prompt. Add 3D content manually after generation if needed. |
| Level generation | Level-based games can be built, but automatic level design is still limited. | Treat generated levels as draft placeholders and expect to adjust layouts manually. |
| Puzzle design and balance | The agent can implement puzzle mechanics, scoring rules, economy hooks, and win/loss logic, but it does not have human taste for whether a puzzle is clever or whether a numeric curve feels good. | Use GodotMaker to build the functional system, then fill in puzzle content, level data, and balance values yourself. |
| Art pipeline | The art pipeline is alpha. It can generate and bind draft assets, but it may occasionally choose the wrong atlas region, miss an animation configuration, or need a follow-up coding-agent repair pass. | Review the generated project visually. Replace assets under `assets/` or rerun `/gm-asset` when the visual direction is important. |
| Pixel art | Pixel art style is not currently supported by the art pipeline, but support is planned. | Use non-pixel 2D styles for generated art, or provide your own pixel art assets manually for now. |
| TileMap | TileMap is not currently supported. Tile-based terrain, tilesets, tile atlases, and grid-based map generation may not be completed automatically. | Use hand-authored scenes or simple generated layouts for now. TileMap support is planned later. |
| Audio generation | Not supported by the current pipeline. Audio rows are treated as user-provided or deferred. | Provide music/SFX manually and wire them into the project yourself until the audio workflow ships. |
| Long automated runs | GodotMaker is cost-sensitive because it runs coding agents for a long time. The current internal baseline is that Codex Pro can handle long prototype runs comfortably, with capacity still left over in typical use. | If you are using a different runtime or plan, start with smaller prompts and watch the first full run. |
| Non-converging runs | A very small number of projects may fail to converge. In this context, "not converging" means the project still cannot pass acceptance after at least 5 build/fix/evaluate loops. | Please share the local failure case if this happens. These reports are useful for improving the framework. |

A dedicated art-production UI is planned to make curation, slicing, replacement, and review more reliable.

If this direction resonates with you, star the repo, try the CLI, and open issues for the game genres, workflows, and production problems you want GodotMaker to handle better.

## Runtime Note

GodotMaker itself is a workflow layer. Actual execution depends on external agent runtimes. These agents are not components maintained by this repository, and long-running automation can occasionally run into runtime-level issues such as silent timeouts, completed work that does not exit cleanly, transient tool failures, rate limits, or child processes that need cleanup.

Most one-off agent failures can be recovered by stopping the current run and starting `godotmaker-cli` again; the workflow is designed to resume from local project state. Feedback and issue reports are very welcome. If possible, include the key details for that run and the project's `.godotmaker/` directory, which often contains the state and reports needed to diagnose the issue.

## License

Business Source License 1.1. See [LICENSE](LICENSE). Each released version converts to Apache License 2.0 four years after that version is first publicly distributed. **The games you build with GodotMaker fully belong to you**, subject to any third-party engine, asset, model-provider, runtime, or dependency terms that may apply.
