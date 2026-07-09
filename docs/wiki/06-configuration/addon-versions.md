# Addon versions

`addon_versions.json` pins the exact Godot addon versions that GodotMaker uses — currently `gecs` for ECS, `gdUnit4` for unit testing, and `godot-e2e` for end-to-end testing. Keeping them pinned per Godot engine version means upgrades do not silently break your build.

The file lives in the GodotMaker repository at `config/addon_versions.json`, not inside your game project.

## What's in it

The file maps each supported Godot version to a set of addon entries. Each entry records the GitHub repository, the exact git tag to download, and where to install the files inside your project. Here is the current pinning:

| Godot version | gecs | gdUnit4 | godot-e2e |
|---|---|---|---|
| 4.3 | v7.1.0 | v5.1.1 | v1.1.0 |
| 4.4 | v7.1.0 | v5.1.1 | v1.1.0 |
| 4.5 | v7.1.0 | v6.1.0 | v1.3.0 |

Notable rules:

- **gdUnit4** v5.x works with Godot 4.3 and 4.4; v6.x requires Godot 4.5 or later.
- **godot-e2e** v1.3.0 is used for Godot 4.5+; 4.3/4.4 stay on v1.1.0.

GodotMaker selects the right row automatically based on the Godot version you have installed. If a Godot version is not listed, scaffold uses the closest lower mapped version; if no lower mapping exists, it reports the issue instead of guessing. Godot 4.5+ gets the latest addon line on every dimension.

## Why they are pinned

Godot addons can change their API between releases. GodotMaker's skills and hooks call specific functions in `gecs` and specific CLI flags in `gdUnit4`. If an addon silently changes how those work, builds can start failing in ways that are hard to diagnose. Pinning to a known-good tag means you always get a tested combination.

## What happens during `/gm-scaffold`

When you run `/gm-scaffold` to set up a new game project, it reads `addon_versions.json`, determines which Godot version you are running, and downloads the matching addon tags from GitHub into the project's `addons/` folder. It also enables each addon as a plugin in `project.godot`. You do not need to download or configure addons manually.

## How to pick up an upgrade

As an end user, you do not edit `addon_versions.json` directly. When GodotMaker ships a new release with updated addon versions, you get the new pinning by republishing:

```bash
python tools/publish.py <your-game-project>
```

If the pinned addon versions changed in the new release, you will need to re-run `/gm-scaffold` (or manually update the `addons/` folder) to actually install the new addon files into your game project.

## For contributors: bumping a version

Updating the pinning is a contributor task. The high-level flow is:

1. Update the relevant entry in `config/addon_versions.json` (change the `tag` value).
2. Test that the new addon version works with the targeted Godot version — run the full test suite and a sample `/gm-scaffold` → `/gm-build` flow.
3. Publish to test projects and verify no hook or skill breaks.
4. Commit and note the change in `CHANGELOG.md`.

See [Release process](../07-contributing/release-process.md) for where this step fits in the full release workflow.
