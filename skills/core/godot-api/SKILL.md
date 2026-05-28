---
name: godot-api
description: |
  Look up Godot engine class APIs — methods, properties, signals, enums.
  Use when you need to find which class to use or look up specific API details.
  Supports version-specific docs — reads the correct API for the project's Godot version.
---

# Godot API Lookup

$ARGUMENTS

## Version detection

Docs are stored per Godot version under `doc_api/{version}/` and `doc_api_csharp/{version}/`.

Determine the version to use:
1. If the caller specifies a version (e.g. "4.4"), use that
2. If `project.godot` exists in the working directory, extract from `config/features`
3. Otherwise fall back to `latest`

Bootstrap if docs for the target version are missing:
```bash
bash ${CLAUDE_SKILL_DIR}/tools/ensure_doc_api.sh [version]
```

## How to answer

**Language selection:** `doc_api/{version}/` contains GDScript docs. `doc_api_csharp/{version}/` contains C# docs. Default to GDScript unless the caller asks about C#.

1. Read `${CLAUDE_SKILL_DIR}/doc_api/{version}/_common.md` — index of ~128 common classes
   - For C#: `${CLAUDE_SKILL_DIR}/doc_api_csharp/{version}/_common.md`
2. If the class isn't there, read `_other.md` in the same directory
3. Read `${CLAUDE_SKILL_DIR}/doc_api/{version}/{ClassName}.md` for full API
   - For C#: `${CLAUDE_SKILL_DIR}/doc_api_csharp/{version}/{ClassName}.md`
4. Return what the caller needs:
   - **Specific question** → relevant methods/signals with descriptions
   - **Full API request** → the entire class doc

**C# syntax reference:** `${CLAUDE_SKILL_DIR}/csharp.md` — C# Godot syntax, patterns, and recipes.

**GDScript syntax reference:** `${CLAUDE_SKILL_DIR}/gdscript.md` — GDScript language spec, type system, patterns.
