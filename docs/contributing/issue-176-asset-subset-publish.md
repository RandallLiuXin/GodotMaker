# Standalone Asset Skill Subset Publishing

This document defines the implementation and acceptance contract for
[Issue #176](https://github.com/RandallLiuXin/GodotMaker/issues/176). The
development baseline is `origin/main` at
`191745368ac59108bec37c618ebe00124d85e172`.

## Capability

A developer with an existing Godot project can publish and invoke the ten
standalone skills under `skills/assets/` without installing the full
GodotMaker pipeline. The published subset remains usable by every coding-agent
layout already supported by `tools/publish.py`.

## Fixed constraints

- The public entry point is `python tools/publish.py --subset assets`.
- Full publishing remains behaviorally unchanged.
- The subset contains the ten public Asset Skills, their shared runtime,
  provider references, controlled provenance helpers, and the exact tool
  dependency closure required at runtime.
- A subset install does not publish core or reviewer skills, pipeline agents,
  hooks, stage schemas, migrations, pipeline templates, MCP registration, or
  Git initialization.
- Every managed source and target path is project-relative and must reject
  absolute paths and parent traversal.
- `--force --subset assets` may replace only files owned by the subset. It must
  preserve unrelated project files, skills, and tools.
- A subset install must coexist safely with an existing full install and with a
  later full publish.
- Automated checks may establish technical validity. They must not certify
  subjective visual quality.

## Publication interface

```text
python tools/publish.py [--agent <agent>] [--force] --subset assets <target>
```

Supported agent layouts remain `claude-code`, `codex`, `opencode`, and `pi`.
The POSIX and PowerShell wrappers expose the same arguments.

The subset publisher records its owned files in a subset-specific manifest
under `.godotmaker/`. It does not write the full-install version marker or run
the full-install migration lifecycle.

## Implementation sequence

1. Add failing publication-contract tests for argument parsing, exact file
   inventory, supported agent layouts, safe force updates, coexistence, and
   path rejection.
2. Add a validated asset-subset dependency manifest and a focused publisher
   that reuses existing skill/runtime copy primitives.
3. Make standalone Skill instructions portable after publication: no source
   checkout paths and no hard-coded Claude or Codex skill roots.
4. Add published-workspace closure tests that import every shipped tool and
   verify every referenced local script, schema, and reference exists.
5. Run targeted tests, the complete pytest suite, and the full/subset agent
   matrix.
6. Publish into a clean Godot project and invoke the published `tileset` Skill
   for a real end-to-end visual acceptance run.

## Test contract

The deterministic suite must prove:

- exactly ten public Asset Skills are installed;
- `_shared` is deployed only as `.godotmaker/asset-runtime`;
- forbidden full-pipeline surfaces are absent from a clean subset target;
- published tool imports work without the GodotMaker source checkout;
- a deterministic source fixture compiles into loadable Godot resources;
- force updates do not delete unrelated target content;
- subset-to-full and full-to-subset publication preserve valid state;
- existing full-publish tests remain green.

Provider calls are not part of deterministic CI. A separate real run supplies
the acceptance evidence required by the issue.

## Visual acceptance

The real run uses the published `tileset` Skill, not source-tree imports. It
retains the provider trace and produces these review artifacts:

1. provider source image;
2. final atlas with grid, cell identifiers, and bounds overlaid;
3. canonical layout containing every logical tile;
4. randomized terrain scene for seam and connectivity stress testing;
5. magnified randomized terrain crop;
6. screenshot of the resource rendered by Godot;
7. one high-resolution review board containing all views.

Technical validation checks dimensions, alpha, profile coordinates, empty or
contaminated cells, region paths, resource loading, and provenance. Human
review checks style adherence, edge continuity, corner behavior, repetition,
background residue, cropping, and agreement between the atlas and Godot
rendering.

The result records two independent states:

```text
Technical validation: PASS | FAIL
Visual review: APPROVED | CHANGES_REQUESTED | PENDING
```

Visual review remains `PENDING` until a human reviewer inspects the full-size
images. A technical pass must never be presented as visual approval.

## Review handoffs

- After RED: review the expected publication inventory and destructive-update
  boundaries.
- After GREEN: review the published target tree and dependency closure.
- After the real run: review the full-resolution visual artifacts and approve
  or request changes.
- Before PR publication: review the integrated diff, complete test output, and
  sanitized screenshots.

## Non-goals

- Redesigning or generating new Asset Skill families.
- Adding a standalone GUI or package manager.
- Making provider-backed generation deterministic in CI.
- Claiming that all ten skills have received subjective visual approval from a
  single `tileset` acceptance run.
- Changing the full GodotMaker pipeline installation contract.

## Open decisions

- The subset manifest filename and schema are implementation details, but it
  must be distinct from the full-install version and migration markers.
- Review screenshots should be attached to the PR unless maintainers prefer a
  repository-owned evidence directory.

These decisions do not block the initial TDD implementation.

## Validation evidence

The completed implementation was validated against the current `main`
baseline with `1770 passed, 72 skipped`. A clean Codex subset publish reported
ten Asset Skills, 40 runtime files, 119 subset-owned files, and exit code zero.
The published `tileset` Skill then produced a Godot-loadable `blob_47` TileSet
with all 47 required runtime variants rendered, zero mismatches across 423
seam checks, and human visual acceptance.

- [Native subset publish command](../assets/issue-176/publish-subset-command.png)
- [TileSet end-to-end review board](../assets/issue-176/tileset-e2e-review.png)
