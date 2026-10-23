## Summary

Brief description of the changes.

## Motivation

Why is this change needed? Link related issues: `Closes #xxx`

## Changes

- [ ] Change 1
- [ ] Change 2

## Testing

- [ ] New or updated tests pass (`pytest` / gdUnit4 where relevant)
- [ ] Gitleaks passes or no secret-bearing files were touched
- [ ] Manual testing completed, if applicable

## Benchmark Verification

Required only for performance-sensitive changes.

- [ ] Not performance-sensitive
- [ ] Performance-sensitive; benchmark results are attached below or linked

<details>
<summary>Benchmark Results</summary>

```text
Paste benchmark output here when relevant.
Include test name, before/after numbers, and environment info.
```

</details>

## Version Compatibility

Does this PR change behavior, move files, rename config keys, or break existing target projects?

- [ ] **No** - no migration needed
- [ ] **Yes** - migration script added to `migrations/` ([guide](migrations/README.md))

> If "Yes": run `python tools/migrate.py --new <slug>` to scaffold
> `migrations/<utc-timestamp>_<slug>.py`. The script must define
> `migrate(target: Path) -> None` and be idempotent. The bump level does
> NOT gate migrations; PATCH releases can ship them too.

### Migration Upgrade Gate

Required if a migration script is added or modified.

- [ ] Real GodotMaker game project pinned at the previous version was upgraded via `python tools/publish.py <target>`
- [ ] Post-upgrade `<target>/.godotmaker/applied_migrations.json` contains the new migration ID with `source: "executed"`
- [ ] Post-upgrade on-disk state was inspected and matches expectations
- [ ] Re-running `tools/publish.py` produces no further migration changes
- [ ] Result attached or summarized below

## Checklist

- [ ] Code follows project conventions
- [ ] ECS systems declare proper read/write metadata, if applicable
- [ ] No hardcoded secrets or API keys
- [ ] The [release-note entry contract](https://github.com/RandallLiuXin/GodotMaker/blob/main/CONTRIBUTING.md#release-note-entries) is satisfied
