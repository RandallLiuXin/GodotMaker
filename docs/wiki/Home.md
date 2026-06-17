# GodotMaker Wiki

GodotMaker turns a game idea into a playable Godot 4 prototype. The normal path is `godotmaker-cli`: it helps shape the idea into a GDD, then drives the same `/gm-*` role commands through planning, implementation, tests, gameplay runs, screenshots, evaluation, and fixes until the current design scope is complete.

## New here? Start with these three pages

1. [Installation](01-getting-started/installation.md) - required tools, optional API keys, and environment checks.
2. [Your first game](01-getting-started/first-game.md) - the CLI-driven idea-to-prototype workflow.
3. [How it works](02-concepts/how-it-works.md) - the roles, quality gates, and fix loops behind the CLI.

## Wiki sections

| Section | When to read it |
|---------|-----------------|
| [Getting Started](01-getting-started/installation.md) | First time setting up GodotMaker, or making a fresh project |
| [Concepts](02-concepts/how-it-works.md) | You want to understand the CLI workflow, 9 role commands, ECS, and design choices |
| [Skills](03-skills/skill-system.md) | What the role / supporting / reviewer skills are and which one does what |
| [Troubleshooting](04-troubleshooting/common-problems.md) | A run stopped, was blocked, or behaved oddly - find a fix here |
| [Tools](05-tools/publish.md) | Reference for `publish.py`, `check_env.py`, `check_project.py`, asset helpers |
| [Configuration](06-configuration/project-config.md) | Per-project preferences, provider setup, host paths, addon version pinning |
| [Contributing](07-contributing/development-setup.md) | You want to add a skill, hook, or tool, or cut a release |
| [Reference](08-reference/glossary.md) | Glossary, FAQ, and pointer to the changelog |

## What you can do with GodotMaker

| Capability | What it means for you |
|------------|----------------------|
| **Bring an idea, not a finished spec** | Describe the game in natural language; GodotMaker helps turn it into a GDD and planning docs |
| **Let the workflow keep moving** | A small prototype can take 3-5 hours of agent runtime, but you do not manually drive every role command |
| **Keep the local Godot project** | The generated code, scenes, assets, tests, screenshots, and reports live in your project folder |
| **Get tested code by default** | Unit tests and end-to-end gameplay tests are written alongside game code |
| **Use visual QA as feedback** | Automated screenshots and visual assessment turn UI and scene issues into fix tasks |
| **Stay on a real engine** | The result lands in Godot, so you can keep debugging, extending, exporting, and shipping |

Manual `/gm-*` role commands still exist for advanced users, debugging, and framework development. They are not the recommended first-run path.

## Project status

- Current release: see [`VERSION`](https://github.com/RandallLiuXin/GodotMaker/blob/main/VERSION) and [`CHANGELOG.md`](https://github.com/RandallLiuXin/GodotMaker/blob/main/CHANGELOG.md)
- What's coming next: [`docs/update/next.md`](../update/next.md)
- Roadmap: [`ROADMAP.md`](https://github.com/RandallLiuXin/GodotMaker/blob/main/ROADMAP.md)

## Quick links

- [GodotMaker repository](https://github.com/RandallLiuXin/GodotMaker)
- [gecs - ECS framework](https://github.com/csprance/gecs)
- [gdUnit4 - testing framework](https://github.com/MikeSchulze/gdUnit4)
- [godot-mcp - runtime debugging](https://github.com/Coding-Solo/godot-mcp)
