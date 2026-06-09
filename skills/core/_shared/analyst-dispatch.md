# Analyst Dispatch Protocol

Use this protocol when a role needs image or audio inspection for
user-provided files under `assets/`.

The dispatching role must not read image binaries directly. Dispatch
`analyst` with the candidate paths and use the returned report plus
`assets/manifest.json`.

## Before Dispatch

For `/gm-asset`, run:

```bash
python tools/asset_user_preflight.py --project-root .
```

Dispatch `analyst` only when the preflight output has image candidates. Handle
audio-only candidates in the dispatching role with exact path or filename
matches.

## Brief

```text
## Analyze User-Provided Assets

### Project Root
{absolute project path}

### Candidate Paths
- {assets/... path}

### Matching ASSETS.md Rows
- {row id/name/status/path when available}

### Visual Context
- STYLE.md is an initial visual seed.
- Existing scene references and canonical asset references are primary style anchors.
- Do not treat STYLE.md as the final style source when image references exist.

### Task
1. Inspect only the listed candidate paths.
2. Classify each image as sprite, sprite_sheet, tileset, background, ui, icon,
   prop, reference, or unknown.
3. Record dimensions, frame/grid observations, transparency, and visible text.
4. Classify audio as bgm or sfx and record duration when available.
5. Write or update `assets/manifest.json`.
6. Mark each image as `direct_runtime`, `source_for_processing`, or
   `uncertain`.
7. Report high-confidence matches to current ASSETS.md rows.
8. Report source sheets, tilesets, UI kits, and prop sheets as processing
   sources.
9. Report uncertain files without changing ASSETS.md.

### Report Format
## Analyst Report:

### Status: DONE | PARTIAL | FAILED

### Candidate Summary
- Images: {count}
- Audio: {count}
- Matched ASSETS rows: {count}
- Uncertain: {count}

### Manifest
- Path: assets/manifest.json
- Status: written | updated | unchanged | failed

### Row Matches
- {asset row/name}: {candidate path} ({confidence}; {notes})

### Uncertain Files
- {candidate path}: {reason}
```

## Manifest Shape

Write `assets/manifest.json` as JSON:

```json
{
  "version": 1,
  "assets": [
    {
      "file": "assets/sprites/player.png",
      "kind": "image",
      "type": "sprite",
      "role": "player idle",
      "dimensions": "64x64",
      "frames": 1,
      "frame_size": null,
      "alpha": true,
      "visible_text": false,
      "handoff": "direct_runtime",
      "candidate_for": "player_idle",
      "confidence": "high",
      "notes": ""
    }
  ]
}
```

## Rules

1. Read only the candidate paths listed in the brief.
2. Write only `assets/manifest.json`.
3. Do not modify ASSETS.md.
4. Do not modify game code.
5. Do not generate new visual assets.
6. Do not create STYLE.md or update visual style direction.
7. Use `candidate_for` only for high-confidence row matches.
8. Use `handoff: direct_runtime` only for single files that already match a
   final ASSETS.md runtime path.
9. Use `handoff: source_for_processing` for sprite sheets, tilesets, UI kits,
   prop sheets, and references that need extraction or selection.
