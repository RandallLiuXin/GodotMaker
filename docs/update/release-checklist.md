# Release Checklist

Steps to follow when publishing a new version of GodotMaker.

## Pre-release

1. **Finalize `docs/update/next.md`**
   - Review all entries, fix typos, group by category
   - Rename `next.md` to `vX.Y.Z.md` (e.g., `v0.5.0.md`) as a permanent archive
   - Create a new empty `next.md` by copying `next.template.md`
   ```bash
   cd docs/update
   mv next.md vX.Y.Z.md
   cp next.template.md next.md
   ```

2. **Check migration scripts** (any bump level — applied tracking is decoupled from the version)
   - If this release rewrites files inside existing target projects (moved
     paths, renamed config keys, hook fix-ups, etc.), scaffold a migration:
     ```bash
     python tools/migrate.py --new <slug>
     # writes migrations/<utc-timestamp>_<slug>.py
     ```
   - Test migrations against a real target project:
     ```bash
     python tools/migrate.py /path/to/test-project
     ```
   - See `migrations/README.md` for script format and the applied-tracking model
   - **MAJOR bump:** old migration scripts are NOT deleted at release time.
     The timestamp series is monotonic and global; existing scripts stay on
     disk as historical record. MAJOR upgrades use `--force` full rebuild,
     and `baseline_applied()` re-marks every current migration as applied
     after re-deploy.
   - **Recommended — release that introduces applied-tracking machinery.**
     The release that *first* ships the applied-tracking subsystem (see
     `migrations/README.md` Transition note) prefers shipping with
     `migrations/` **empty**. Legacy targets reach the bootstrap branch
     and emerge as "tracked, zero applied"; the next release that ships
     V files goes through the normal pending path. Shipping V files in
     the same release as the machinery also works — `run_migrations()`
     auto-bootstraps the legacy target and runs the V files as pending
     in one step — but you forgo the chance to land the tracker change
     in isolation, which makes the diff harder to review. Pick based on
     review surface, not safety. Once applied-tracking is in any
     released version, this guidance no longer applies — drop it from
     your release notes for that release.

3. **Update version numbers** — these MUST stay in lockstep. Skipping any one ships a half-bumped release.
   - **`VERSION`** — single-line file at the repo root, content is the bare `X.Y.Z` (no leading `v`, no trailing newline issues). This is the **source-of-truth** `tools/publish.py` reads (`read_source_version()` at `tools/publish.py:43`) and writes into target projects' `.godotmaker/version`. Forgetting this bump causes downstream consumers (`godotmaker-cli`, `publish.py` upgrade detection) to see `installed_version != target_version` on every run, triggering an infinite "framework upgrade X.Y.Z-1 → X.Y.Z" loop that never converges.
   - `pyproject.toml` — update `version = "X.Y.Z"`. Python package metadata only; not consumed by the publish pipeline, but kept in sync so PyPI/SDK consumers see the same number.
   - `CHANGELOG.md` — add a new `## [X.Y.Z] — YYYY-MM-DD` section with entries from the archived `next.md`
   - **`LICENSE` Change Date** — in the `Change Date` field, pin this release's concrete Change Date: the calendar date equal to this release's publication date plus four years (a release published 2026-06-01 records `2030-06-01`). BUSL treats `Change Date` as a license parameter, so the tagged release's `LICENSE` should contain only the concrete value, followed directly by `Change License`.
     ```text
     Change Date:
     2030-06-01.

     Change License:
     Apache License, Version 2.0.
     ```
     Do not leave the rolling-main explanatory text under `Change Date` in a tagged release:
     ```text
     For each specific version of the Licensed Work, the fourth anniversary of the
     first publicly available distribution of that version under this License. For
     this purpose, a "version" of the Licensed Work means a release published under a
     Semantic Versioning tag (for example, v0.4.0). The LICENSE file included in each
     such tagged release records that version's Change Date as a specific calendar
     date.
     ```
     Keep that rule in this checklist/docs instead. BUSL converts each version on its own date — never reuse a previous release's date.

4. **Run all tests locally**
   ```bash
   pytest --tb=short
   gitleaks detect --source . --config .gitleaks.toml
   ```

5. **Cross-layer consistency gates** — these catch the contract drifts that
   shipped past previous releases. Run before tagging.

   - **README + wiki entry-flow consistency.** The first command shown in
     `README.md`, `README.zh-CN.md`, and
     `docs/wiki/01-getting-started/first-game.md` must match the current
     public entrypoint. For the CLI-first path this is `godotmaker`; direct
     `/gm-scaffold` or `/gm-gdd` role commands are advanced/manual entrypoints,
     not the first-run command shown to new users.
   - **New config keys are in `config.yaml.default`.** Any `*_model` field
     newly referenced by a skill must also be declared in
     `config/config.yaml.default` with the same default value. The automated
     check is `tests/test_config_consistency.py`; if you add a new
     `<role>_model`, run pytest before tagging.
   - **Documented artifacts match real outputs.** If a wiki page or skill
     description claims a role produces a file (e.g., `.godotmaker/foo.json`),
     either the role's `SKILL.md` actually writes that file or the doc claim
     is removed. There is no "documented but not produced" file in the
     pipeline.
   - **Release notes are visible.** Every new `docs/update/vX.Y.Z.md` must
     appear under the `Release Notes` section of `mkdocs.yml`. Adding the
     archive without the nav entry hides it from the published site.
   - **Chinese release-note policy.** Release notes under `docs/update/` are
     **English-only by design** — the i18n plugin shows the same English
     page on the Chinese site rather than maintaining a parallel translation
     track. If this policy ever changes, mirror notes under `docs/zh/update/`
     and update this checklist.

6. **Commit and push**
   ```bash
   git add -A
   git commit -m "chore: prepare release vX.Y.Z"
   git push origin main
   ```

## Publish

7. **Create a git tag and push**
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
   This triggers the `release.yml` workflow, which automatically:
   - Reads release notes from `docs/update/vX.Y.Z.md`
   - Creates a GitHub Release (source code archives are attached by GitHub)

8. **Verify the release**
   - Check the [Releases page](https://github.com/RandallLiuXin/GodotMaker/releases)
   - Verify release notes match `CHANGELOG.md`

## Post-release

9. **Announce** (optional)
   - Post on relevant communities (Godot forums, Reddit, etc.)
