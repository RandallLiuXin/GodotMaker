# Tag archives

`seal_tag.py` is what `/gm-finalize` calls to turn a finished tag into an
immutable archive under `docs/tags/<Tag>/`. You rarely run it by hand — the
exception is `backfill`, which retrofits the index files onto archives sealed
by an older GodotMaker release.

## What a sealed archive looks like

```text
docs/tags/
├── README.md                 parent index of every sealed tag
└── v0.1.0/
    ├── README.md             navigation page for this tag
    ├── SUMMARY.md            bounded retrieval summary
    ├── CHANGELOG.md          what shipped, written by /gm-finalize
    ├── GDD-snapshot.md
    ├── PLAN.md
    ├── STRUCTURE.md
    ├── STYLE.md
    ├── SCENES.md
    ├── MEMORY.md
    ├── memory/               sub-system files MEMORY.md indexes
    ├── evaluation-final.json
    └── evidence/
        ├── manifest.json     every archived file: path, category, bytes, SHA-256
        ├── e2e/
        └── screenshots/
```

The flat document paths (`PLAN.md`, `STRUCTURE.md`, `SCENES.md`, …) are
unchanged from earlier releases, so anything that already reads
`docs/tags/<Tag>/PLAN.md` keeps working.

## Reading an archive

1. **`docs/tags/README.md`** — which tags exist, in version order, with their
   release date, theme and source revision.
2. **`docs/tags/<Tag>/SUMMARY.md`** — one bounded screen: theme, delivered
   mechanics, systems and scenes changed, verification verdict, known
   limitations, and links to everything else.
3. **`docs/tags/<Tag>/README.md`** — the file-by-file map when you need to know
   what a given document holds before opening it.
4. **The canonical documents and `evidence/`** — complete, but expensive to
   read. Open them only when the summary is not enough.

`SUMMARY.md` is a retrieval index, not a source of truth. It restates facts
from `CHANGELOG.md`, `PLAN.md`, `evaluation-final.json` and `final_report.json`
and nothing else — worker traces, exploration notes and unverified MEMORY
learnings never reach it. When the summary and a canonical document disagree,
the canonical document wins.

## Immutability

`evidence/manifest.json` carries `"sealed": true` once a tag is fully sealed.
From then on `archive` and `index` refuse to touch the directory and exit `3`.
That is what stops a repeated `/gm-finalize` from silently rewriting history.

An archive whose manifest is missing or says `"sealed": false` is a
half-finished finalize — re-running `archive` is the documented recovery path,
and no flag is needed. `--force` exists for a deliberate reseal only.

That guarantee holds because `sealed: true` is committed **last**: `index`
writes `SUMMARY.md`, the tag `README.md` and the parent `docs/tags/README.md`
first, and only then writes the manifest, in a single atomic replace. A full
disk or an I/O error anywhere earlier leaves the tag unsealed and re-runnable
rather than sealed with a missing index. Every generated file is written to a
same-directory temp file and renamed into place, so an interrupted write never
truncates the previous version.

`/gm-finalize`'s completion gate checks the same marker: the archive must have
a parseable `evidence/manifest.json` with `"sealed": true`, and the parent
index must list the tag. Present-but-unsealed files do not pass.

## Subcommands

| Command | What it does |
|---|---|
| `python tools/seal_tag.py archive <Tag>` | Copies the working docs, the `memory/` subtree and `e2e/` evidence into `docs/tags/<Tag>/`, then link-checks the archived `MEMORY.md`. Writes an unsealed manifest. |
| `python tools/seal_tag.py index <Tag>` | Generates `SUMMARY.md`, the tag `README.md`, the sealed manifest and the parent `docs/tags/README.md`. This is the step that seals the tag. |
| `python tools/seal_tag.py backfill <Tag>` / `--all` | Retrofits `README.md`, `SUMMARY.md` and a manifest onto archives sealed by an older release. Already-sealed archives are skipped unless `--force`. |
| `python tools/seal_tag.py bundle <Tag>` | Emits the JSON `/gm-finalize` uses to write the CHANGELOG. |
| `python tools/seal_tag.py reset` | Truncates `.godotmaker/stage.jsonl` and deletes `metrics_current.jsonl`. |

Exit codes: `0` success · `1` filesystem or runtime failure · `2` missing
sources, unresolvable memory links, or bad usage · `3` the tag is already
sealed.

## Memory link checking

`MEMORY.md` indexes per-system notes under `memory/`. Archiving the index
without those files would freeze a set of broken links, so `archive` copies
`memory/` too and then verifies the archived `MEMORY.md`:

- A `memory/…` link with no archived target, an absolute path, or a link that
  escapes the archive directory **blocks the seal** (exit 2). Fix the root
  `MEMORY.md`, or restore the missing file, and re-run.
- A link to a live project file that is deliberately not archived
  (`src/player.gd`, `assets/…`) is recorded in the manifest's `link_warnings`
  and does not block.

Links inside HTML comments and fenced code blocks are ignored, so the example
entries shipped in the `MEMORY.md` template never block a first finalize.

## Backfilling older archives

Archives created before this layout existed have the flat documents but no
`README.md`, `SUMMARY.md` or manifest, so they are invisible to the parent
index. Retrofit them once:

```bash
python tools/seal_tag.py backfill --all
```

Backfill only adds index files. It never rewrites a canonical document — it
hashes them before and after and fails if any changed. It also does **not**
copy today's `memory/` into a historical tag: that would inject present-day
content into a past snapshot. The missing subtree is recorded as a manifest
warning instead, and the tag README reports completeness as `partial`.

Archives that already carry a sealed manifest are skipped — re-indexing one
would replace its recorded seal revision with whatever this run resolves. Pass
`--force` to re-index them anyway. For the archives it does index, the source
revision comes from `git tag <Tag>` (the commit `/gm-finalize` tagged), not
today's `HEAD`; an untagged archive records `null` rather than a fabricated
revision.

`/gm-finalize` never runs `backfill` on its own. Rewriting history is always an
explicit, user-invoked action.
