"""Add visual asset contract sections to project docs."""
import re
from pathlib import Path


ASSETS_SECTION = """## Visual Asset Contract

<!-- Runtime contract for visible assets. Each gameplay-visible object, UI
     element, and scene reference should map to an ASSETS.md row or to
     `procedural`, `UI text`, or `not required this tag`.
     Use `asset_name / assets/...` for concrete asset bindings.
     `not required this tag` needs a deferral reason in Readability Requirement. -->

| Tag | Scene / Mechanic | Visible Object | Asset Row / Path | Runtime Size | Visual Role | Readability Requirement | Source |
|-----|------------------|----------------|------------------|--------------|-------------|-------------------------|--------|
"""

PLAN_SECTION = """### Runtime Asset Assignments

<!-- Bind player-facing tasks to concrete assets or explicit procedural/UI
     outputs. Use `asset_name / assets/...` for concrete assets, or
     `procedural`, `UI text`, or `not required this tag`. `not required this tag`
     needs a deferral reason in Verification. Asset names and paths should match
     ASSETS.md and SCENES.md. -->

| Task / Mechanic | Visible Content | Asset Row / Path | Runtime Size | Verification |
|-----------------|-----------------|------------------|--------------|--------------|
"""

SCENE_SECTION = """### Asset bindings

<!-- Bind each gameplay-visible object and non-text UI element to ASSETS.md.
     Use `asset_name / assets/...` for concrete assets, or `procedural`,
     `UI text`, or `not required this tag` when no runtime image/model asset is
     required for this tag. `not required this tag` needs a deferral reason in
     Visual Contract. -->

| Element | Asset Row / Path | Runtime Size | Visual Contract |
|---------|------------------|--------------|-----------------|
"""


def _insert_after_asset_table(text: str) -> str:
    asset_table = re.search(r"(?m)^## Asset Table\s*$", text)
    if asset_table:
        next_h2 = re.search(r"(?m)^## (?!Asset Table\s*$).+", text[asset_table.end():])
        if next_h2:
            insert_at = asset_table.end() + next_h2.start()
            return text[:insert_at].rstrip() + f"\n\n{ASSETS_SECTION}\n" + text[insert_at:].lstrip()
    return text.rstrip() + f"\n\n{ASSETS_SECTION}"


def _insert_runtime_asset_assignments(text: str) -> str:
    if "### Runtime Asset Assignments" in text:
        return text

    main_build = re.search(r"(?m)^## Main Build\s*$", text)
    if main_build:
        next_h2 = re.search(r"(?m)^## (?!Main Build\s*$).+", text[main_build.end():])
        end = main_build.end() + next_h2.start() if next_h2 else len(text)
        section = text[main_build.start():end]
        verify = re.search(r"(?m)^### Verify\s*$", section)
        if verify:
            insert_at = main_build.start() + verify.start()
            return text[:insert_at].rstrip() + f"\n\n{PLAN_SECTION}\n" + text[insert_at:].lstrip()
        return text[:end].rstrip() + f"\n\n{PLAN_SECTION}\n" + text[end:].lstrip()

    return text.rstrip() + f"\n\n{PLAN_SECTION}"


def _insert_scene_asset_bindings(text: str) -> str:
    matches = list(re.finditer(r"(?m)^## Scene: .*$", text))
    if not matches:
        return text

    pieces = [text[:matches[0].start()]]
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[start:end]
        if "### Asset bindings" in chunk:
            pieces.append(chunk)
            continue
        marker = "\n### Acceptance criteria"
        if marker in chunk:
            chunk = chunk.replace(marker, f"\n{SCENE_SECTION}\n{marker.lstrip()}", 1)
        else:
            chunk = chunk.rstrip() + f"\n\n{SCENE_SECTION}\n\n"
        pieces.append(chunk)

    return "".join(pieces)


def migrate(target: Path) -> None:
    """target is the absolute path to the game project root.

    Scripts MUST be idempotent: re-runs after a partial failure must
    not corrupt state. Raise an exception to abort the migration chain.
    """
    changed = False

    assets_path = target / "ASSETS.md"
    if not assets_path.exists():
        print("ASSETS.md missing; skipping Visual Asset Contract migration")
    else:
        text = assets_path.read_text(encoding="utf-8")
        if "## Visual Asset Contract" in text:
            print("ASSETS.md already has Visual Asset Contract")
        else:
            assets_path.write_text(_insert_after_asset_table(text), encoding="utf-8")
            print("Added Visual Asset Contract to ASSETS.md")
            changed = True

    plan_path = target / "PLAN.md"
    if plan_path.exists():
        text = plan_path.read_text(encoding="utf-8")
        updated = _insert_runtime_asset_assignments(text)
        if updated != text:
            plan_path.write_text(updated, encoding="utf-8")
            print("Added Runtime Asset Assignments to PLAN.md")
            changed = True

    scenes_path = target / "SCENES.md"
    if scenes_path.exists():
        text = scenes_path.read_text(encoding="utf-8")
        updated = _insert_scene_asset_bindings(text)
        if updated != text:
            scenes_path.write_text(updated, encoding="utf-8")
            print("Added Asset bindings to SCENES.md")
            changed = True

    if not changed:
        print("Visual asset contract sections already present or not applicable")
