# Your First Game

This walkthrough takes you from a game idea to a playable Godot game. The normal path uses `godotmaker-cli`, which helps turn the idea into a GDD and then drives the workflow automatically until the current design scope is complete.

**Time to expect:** a small game usually takes about **3-5 hours of agent runtime**. You do not need to supervise every step. Bring the idea, start the workflow, and review the playable result when it finishes.

Advanced users can still run the underlying `/gm-*` commands directly. This page focuses on the CLI path.

## Before You Start

Complete [Installation](installation.md) first. You need:

- `godotmaker-cli` installed
- Godot, Git, Node.js, and Python available
- one selected agent runtime installed and authenticated: Claude Code or Codex
- optional API keys only if your config selects API-backed providers

## Create a Game Folder

```bash
mkdir my-first-game
cd my-first-game
```

You do not need to arrive with a finished GDD. Bring a rough game idea, notes, references, or constraints. GodotMaker will help turn that into `GDD.md` before implementation starts.

For example, a first idea can be as simple as:

```text
Make a 2D arcade game where the player controls a bird that flies through gaps between pipes.
It should be bright, simple, readable, and family-friendly.
```

You can make the design more detailed later. GodotMaker treats the resulting GDD as the design contract for the run.

## Run GodotMaker

From the game folder:

```bash
godotmaker-cli --agent claude-code
```

Use Codex for the same project:

```bash
godotmaker-cli --agent codex
```

The CLI publishes the framework into the project if needed, creates the editable `.godotmaker/config.yaml` project config on first publish, helps capture the idea as a GDD, then drives planning, build, verification, evaluation, and fix loops until the current design scope is complete.

## What Happens During the Run

GodotMaker will:

1. Scaffold a Godot project if the folder does not have one yet.
2. Help turn your game idea into `GDD.md` and tag-scoped planning docs.
3. Generate or inspect assets.
4. Dispatch implementation agents.
5. Run gdUnit4 unit tests and mechanical verification.
6. Create end-to-end gameplay tests that operate the game like a player.
7. Run the game, capture screenshots, and compare the result to the design.
8. Feed missing behavior, UI overlap, visual mismatch, or runtime failures back into the fix loop.
9. Finalize the tag when the current scope passes.

You can expect a lot of terminal output. That is normal. The important artifacts are written into the game folder.

## What Lands on Disk

After a successful run, expect:

- `project.godot`
- `src/` game code
- `scenes/` Godot scenes
- `assets/` generated or provided art
- `test/` gdUnit4 unit tests
- `e2e/` gameplay tests and screenshots
- `GDD.md`, `PLAN.md`, `STRUCTURE.md`, `SCENES.md`, `ASSETS.md`
- `.godotmaker/` run state and reports
- `docs/tags/<Tag>/` archived planning docs

## Review the Result

Open the project in Godot:

```bash
godot --editor --path .
```

Or run it directly:

```bash
godot --path .
```

If the result needs a design change, refine the idea in `GDD.md` or add new notes, then run `godotmaker-cli` again. The next run plans from the updated design and continues from the existing project state.

## Manual Role Commands

The CLI drives these roles for you:

```text
gm-scaffold -> gm-gdd -> gm-asset -> gm-build -> gm-verify
-> gm-evaluate -> gm-fixgap loop -> gm-accept -> gm-finalize
```

Advanced users can run them as `/gm-*`. Manual mode is useful for debugging, framework development, or reviewing an intermediate stage, but it is no longer the recommended first-run path.

For a tour of what every project file means, see [Project layout](project-layout.md).
