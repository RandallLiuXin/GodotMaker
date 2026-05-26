# Development Setup

This page gets you from a fresh clone to a running test suite, and walks through the loops you will repeat while working on GodotMaker.

## Get the source

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker
pip install -r tools/requirements.txt
```

You also need **Godot 4.5 or later** on your `PATH`. Run this to confirm everything is in place before you start:

```bash
python tools/check_env.py
```

## Project structure at a glance

```
GodotMaker/
├── hooks/          8 hook scripts enforcing pipeline rules + hooks/metrics/ subsystem
├── skills/
│   ├── core/       Role skills + supporting skills + _shared/ cross-skill reference docs
│   └── reviewer/   8 domain reviewer skills (physics, animation, ui, ...)
├── tools/          CLI tools: publish.py, check_env.py, check_project.py, asset_gen.py, migrate.py
├── config/         config.yaml.default, stage_schemas.json, addon_versions.json
├── agent-runtimes/ runner-specific references, templates, and hook config
├── templates/      Document templates deployed into generated game projects
├── tests/          ~320 unit tests for hooks and tools
├── docs/           Wiki, contributing guides, versioning reference, hooks reference
├── shell/          publish.sh / publish.ps1, report.sh / report.bat
├── migrations/     Per-version-jump migration scripts
├── VERSION         Semantic version (MAJOR.MINOR.PATCH) — source of truth
└── CHANGELOG.md    Per-release change notes
```

One sentence per folder: `hooks/` is the enforcement layer; `skills/` is the AI instruction layer; `tools/` contains the Python scripts contributors and users run directly; `config/` drives both; `tests/` keeps all of it honest.

## Common development loops

### Running the test suite

```bash
python -m pytest tests/ -x -q
```

The `-x` flag stops at the first failure. Drop it to see all failures at once. The suite currently has ~320 tests and covers all 8 hooks, publish, check_project, migrations, and the end-to-end pipeline.

To run a single file:

```bash
python -m pytest tests/hooks/test_check_worker_report.py -x -q
```

To run by test name:

```bash
python -m pytest tests/ -k "test_blocks_missing_sections" -x -q
```

### Trying a change in a real project

When you want to verify your change end-to-end:

1. Pick a Godot project folder (or create a scratch folder).
2. Push your current working tree into it:

   ```bash
   python tools/publish.py /path/to/my-test-game
   ```

3. Open the project folder in Claude Code and exercise the relevant `/gm-*` command.
4. Inspect the outputs (`.godotmaker/`, `PLAN.md`, skill files under the selected agent skill directory, etc.) to confirm behaviour.

Re-publishing the same version is always allowed, so you can iterate without bumping the version number during development.

### Linting

No formatter is enforced by the repo. Match the style of the file you are editing: 4-space indent, double quotes for strings in Python, blank line between top-level definitions.

## Branching

`main` is the trunk; all pull requests land here. Keep changes small and open a PR early rather than accumulating a large branch. Every PR must add at least one entry to `docs/update/next.md` under the appropriate category. See [Release process](release-process.md) for the full workflow.
