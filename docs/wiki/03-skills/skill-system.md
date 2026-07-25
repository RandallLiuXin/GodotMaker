# Skill System

In Claude Code, a "skill" is a bundle of instructions and reference documents that Claude loads for a specific job. Think of each skill as a specialist handbook: when Claude needs to do something — scaffold a project, write gameplay code, check for common bugs — it reaches for the matching skill and follows its guidance. GodotMaker's skills are organized into two layers.

## Layer 1 — Core skills

Core skills are the engine that drives the whole game-creation process. They come in two kinds:

**Role skills** are the nine `/gm-*` commands exposed by the framework. Each command handles one part of making a game - designing it, building it, testing it, and so on. In the normal path, `godotmaker-cli` drives them in order for you; advanced users can still run the role commands directly. See [Core skills](core-skills.md) for the full table.

**Supporting skills** are reference packs that role skills load silently in the background. They contain things like Godot API documentation, the ECS framework reference, and helpers for running tests. You never invoke them yourself — they exist so the role skills have accurate, up-to-date information to work from. These are also described in [Core skills](core-skills.md).

## Layer 2 — Reviewer skills

Reviewer skills are eight domain-specific checklists covering areas like physics, UI, audio, and animation. They are not slash commands — you never type them directly. Instead, a reviewer sub-agent (a separate Claude instance that runs automatically) loads the relevant ones during `/gm-build` and `/gm-fixgap`, checks the freshly written code against known Godot pitfalls, and reports any issues it finds.

For the full list and examples of what each reviewer catches, see [Reviewer skills](reviewer-skills.md).

## How skills are deployed

Skills live in this repository under `skills/core/`, `skills/reviewer/`, and `skills/assets/`. When you run `python tools/publish.py <project>`, every non-private skill directory is copied into `<project>/.claude/skills/` where Claude Code can find it automatically. When you run `python tools/publish.py --agent codex <project>`, publish writes the same skills into `<project>/.agents/skills/` and adds Codex runtime mapping references so Codex can interpret Claude-first surface vocabulary such as `.claude/...` paths and `/gm-*` commands. Asset `_shared` is not a skill: it is published to `<project>/.godotmaker/asset-runtime/` with the schemas, compiler registry, and L0-L4 validators that first-class Asset Skills import.

Reference documents that are used by more than one skill (such as the worker dispatch protocol) have a single source-of-truth copy in `skills/core/_shared/`. The publish step deploys each shared file into every consumer skill's `references/` folder. If you are contributing to GodotMaker and need to edit a shared document, always edit the source in `_shared/` — the deployed copies are auto-generated and will be overwritten.

## See also

- [Core skills](core-skills.md) — the nine role commands and twelve supporting skills
- [Reviewer skills](reviewer-skills.md) — the eight domain-specific quality checkers
