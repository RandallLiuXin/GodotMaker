# Release Process

GodotMaker uses semantic versioning. Each release follows a short checklist;
this page summarises it. The canonical checklist is
[`docs/update/release-checklist.md`](../../update/release-checklist.md).

For version scheme details and how `publish.py` handles upgrades in target projects, see [../../versioning.md](../../versioning.md).

---

## When to bump what

| Level | When | Example |
|-------|------|---------|
| PATCH | Backward-compatible bug fixes (no new behaviour) | `0.4.0 → 0.4.1` |
| MINOR | Backward-compatible new features or behaviour changes | `0.4.0 → 0.5.0` |
| MAJOR | Breaking changes; incremental migration not possible | `0.x → 1.0.0` |

`publish.py` auto-proceeds on PATCH, prompts for confirmation on MINOR, and requires `--force` on MAJOR. Migration scripts under `migrations/` (timestamped, decoupled from version) are applied on any non-MAJOR upgrade — see [`../../versioning.md`](../../versioning.md) for the full policy.

---

## The next.md workflow

Contributors never edit `CHANGELOG.md` directly. Instead, every pull request adds at least one bullet to `docs/update/next.md` under the appropriate category:

```markdown
## Added
- Brief description of the new thing (#123) — @author

## Changed
- What changed and why (#124) — @author

## Fixed
- What was broken (#125) — @author

## Removed
- What was deleted (#126) — @author
```

Use [Keep a Changelog](https://keepachangelog.com/) conventions for category names. If none of the four standard categories fits, add a new one.

At release time, `next.md` is archived and a fresh copy is created. Contributors working on the next batch of changes immediately start adding to the new `next.md`. This means `CHANGELOG.md` is touched only once per release, by whoever cuts the release.

---

## Cutting a release

High-level checklist. Follow the canonical steps in
[`docs/update/release-checklist.md`](../../update/release-checklist.md):

1. **Merge all pending PRs** that should be in this release. Confirm `next.md` has entries for all of them.

2. **Archive next.md.** Rename `docs/update/next.md` to `docs/update/vX.Y.Z.md`. Create a fresh `docs/update/next.md` from the template at the top of that file.

3. **Update CHANGELOG.md.** Prepend a new section:

   ```markdown
   ## [X.Y.Z] — YYYY-MM-DD

   ### Added
   - (items from next.md)

   ### Changed / Fixed / Removed
   - ...
   ```

4. **Update release metadata.** Keep `VERSION` and `pyproject.toml` in
   lockstep, and set the `LICENSE` Change Date from the intended publication
   date as described by the canonical checklist.

5. **Add migration scripts** (if needed). If any change requires rewriting files inside an existing game project, scaffold a migration with `python tools/migrate.py --new <slug>` — this writes `migrations/<utc-timestamp>_<slug>.py`. The bump level does not gate migrations; PATCH and MINOR alike. See `migrations/README.md` for the script format and the applied-tracking model.

6. **Validate the release preparation.** Run the full local test and
   documentation checks, then publish to an appropriate disposable test
   project with the release-specific arguments before tagging.

7. **Create a release-preparation PR.**

   ```bash
   git switch -c release/vX.Y.Z
   git add <reviewed-release-files>
   git commit -m "chore: prepare release vX.Y.Z"
   git push -u origin release/vX.Y.Z
   gh pr create --base main --head release/vX.Y.Z
   ```

   A maintainer merges this PR only after CI and review. Creating the PR does
   not authorize the release agent to merge it.

8. **Tag the fetched `main` after separate release authorization.**

   After the release-preparation PR is merged, fetch `main`, verify that
   `origin/main` points at the merged release commit, and tag that remote
   tracking ref explicitly:

   ```bash
   git fetch origin
   git tag vX.Y.Z origin/main
   git push origin vX.Y.Z
   ```

9. **Verify the GitHub Release.** Confirm that the release exists and its
   notes match `CHANGELOG.md`.

---

## Migrations

Releases may ship migration scripts that automatically fix compatibility issues in existing game projects. Scripts live directly under `migrations/`, named by UTC timestamp:

```
migrations/20260429100000_fix_state_path.py
migrations/20260430153000_rename_metrics_field.py
```

`tools/migrate.py` reads each target's `.godotmaker/applied_migrations.json` and applies the diff in chronological order. If a script fails, the chain aborts and publish exits with an error; already-successful scripts keep their entries in `applied_migrations.json`, so a re-run picks up where it left off.

MAJOR upgrades skip migrations entirely and use `--force` for clean re-initialisation; the migration tracker is reset and re-baselined after re-deploy. The timestamp series is monotonic and global — old scripts stay on disk as historical record and are baselined as already-applied for any fresh install or post-MAJOR re-init.
