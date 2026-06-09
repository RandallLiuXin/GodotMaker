#!/usr/bin/env python3
"""PreToolUse hook: enforce file write permissions per pipeline role.

Reads .godotmaker/current_role and applies the role's write rules. See the
gm-*/SKILL.md files for the canonical per-role rules; this hook enforces
them. When no role is set, no /gm-* pipeline role is active, so regular
coding-agent conversations are allowed to write normally.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import record_event, EventType, get_current_role, WORKER_DISPATCH_ROLES

GAME_CODE_EXTENSIONS = {".gd", ".tscn", ".tres"}
# Project-root planning artifacts — subagents may NOT modify these unless
# their agent_type is in PLANNING_WRITER_AGENT_TYPES. Includes the four
# 1c decomposer outputs (PLAN/STRUCTURE/STYLE/ASSETS + SCENES/TOC), the
# tag-iteration roadmap (ROADMAP.md, owned by /gm-gdd), and GAP.md
# (owned by /gm-fixgap's lead, not subagents).
PLANNING_DOCS = {"plan.md", "structure.md", "style.md", "assets.md", "gap.md",
                 "scenes.md", "toc.md", "roadmap.md"}
# project.godot is the engine config and changes the whole game. Subagents
# may not edit it unless their agent_type is in PLANNING_WRITER_AGENT_TYPES.
PROJECT_GODOT = "project.godot"
E2E_DIR_PREFIX = "e2e/"
ASSETS_DIR_PREFIX = "assets/"
REFERENCES_DIR_PREFIX = "references/"
GODOTMAKER_DIR = ".godotmaker/"
# Subagent types whose entire purpose is writing planning docs — exempt
# from the general subagent block on PLANNING_DOCS and PROJECT_GODOT.
PLANNING_WRITER_AGENT_TYPES = {"decomposer"}
# Per-role narrow write allow-lists under .godotmaker/. Each role needs
# current_role + stage.jsonl for bookkeeping; evaluate / verify also write
# their structured verdict; rescue is diagnostic-only (chat output only),
# so it gets ONLY the bookkeeping pair — anything else attempted is a SKILL
# violation worth blocking.
EVAL_ALLOWED_GM_FILES = {".godotmaker/evaluation.json",
                          ".godotmaker/stage.jsonl",
                          ".godotmaker/current_role"}
VERIFY_ALLOWED_GM_FILES = {".godotmaker/stage.jsonl",
                            ".godotmaker/current_role",
                            ".godotmaker/verify_report.json"}
RESCUE_ALLOWED_GM_FILES = {".godotmaker/stage.jsonl",
                            ".godotmaker/current_role"}


def _is_e2e_path(path_lower: str) -> bool:
    return path_lower.startswith(E2E_DIR_PREFIX) or f"/{E2E_DIR_PREFIX}" in path_lower


def _is_assets_path(path_lower: str) -> bool:
    return path_lower.startswith(ASSETS_DIR_PREFIX) or f"/{ASSETS_DIR_PREFIX}" in path_lower


def _is_references_path(path_lower: str) -> bool:
    return path_lower.startswith(REFERENCES_DIR_PREFIX) or f"/{REFERENCES_DIR_PREFIX}" in path_lower


def _is_godotmaker_path(path_lower: str) -> bool:
    return path_lower.startswith(GODOTMAKER_DIR) or f"/{GODOTMAKER_DIR}" in path_lower


def _is_asset_generation_path(path_lower: str) -> bool:
    return (
        path_lower.startswith(".godotmaker/asset-generation/")
        or "/.godotmaker/asset-generation/" in path_lower
    )


def _matches_allowed_gm(path_lower: str, allowed: set[str]) -> bool:
    """True if path ends with one of the allowed `.godotmaker/<file>` entries."""
    return any(path_lower.endswith(p) for p in allowed)


def _is_project_root_assets_md(path_lower: str) -> bool:
    """True iff path_lower resolves to the project-root ASSETS.md.

    The hook runs with cwd = project root, so abspath() of a relative
    input is anchored to that root. Accepts both bare `"assets.md"` and
    any absolute path that resolves to `<cwd>/ASSETS.md`. Subdirectory
    variants (`subdir/ASSETS.md`) and absolute paths to a different
    project's ASSETS.md are rejected — the asset role's contract and
    the deny message in `_check_main` are explicitly project-root only.

    Uses realpath (not abspath) because macOS routes /var/folders/...
    through a /private/var/folders/... symlink — abspath leaves the
    input untouched but cwd-derived paths often arrive already resolved,
    so the two sides drift and a legitimately-rooted ASSETS.md gets
    rejected. realpath collapses symlinks on both sides identically.
    """
    if path_lower == "assets.md":
        return True
    abs_input = os.path.realpath(path_lower).replace("\\", "/").lower()
    abs_root = os.path.realpath("assets.md").replace("\\", "/").lower()
    return abs_input == abs_root


def _block(reason: str, file_name: str, agent_id: str = "") -> None:
    record_event(EventType.HOOK_BLOCK, hook="check_file_permissions",
                 reason=reason, file=file_name, agent_id=agent_id or "main")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def _check_main(role: str, path_lower: str, file_name: str, ext: str) -> None:
    """Apply main-agent rules for the active role. Calls _block on violation."""
    is_e2e = _is_e2e_path(path_lower)
    is_code = ext in GAME_CODE_EXTENSIONS
    is_godotmaker = _is_godotmaker_path(path_lower)
    is_assets = _is_assets_path(path_lower)

    if role == "evaluate":
        if is_e2e or _matches_allowed_gm(path_lower, EVAL_ALLOWED_GM_FILES):
            return
        _block(f"Evaluator can only write e2e/, .godotmaker/evaluation.json, "
               f".godotmaker/stage.jsonl, or .godotmaker/current_role "
               f"(attempted: {file_name}).", file_name)

    if role == "verify":
        if _matches_allowed_gm(path_lower, VERIFY_ALLOWED_GM_FILES):
            return
        _block(f"Verify is read-only except .godotmaker/stage.jsonl, "
               f".godotmaker/current_role, and .godotmaker/verify_report.json "
               f"(attempted: {file_name}).", file_name)

    if role == "rescue":
        if _matches_allowed_gm(path_lower, RESCUE_ALLOWED_GM_FILES):
            return
        _block(f"Rescue is diagnostic-only — output goes to chat, not files. "
               f"Only .godotmaker/stage.jsonl and .godotmaker/current_role "
               f"may be written (attempted: {file_name}).", file_name)

    if role == "scaffold":
        return

    if is_e2e:
        _block(f"{role.capitalize()} role cannot write to e2e/ ({file_name}). "
               "E2E tests are owned by the Evaluator.", file_name)

    if role == "asset":
        if _is_project_root_assets_md(path_lower) or is_godotmaker:
            return
        _block(f"Asset role can only write the project-root ASSETS.md "
               f"or .godotmaker/ (attempted: {file_name}). Image files go "
               f"through tools/asset_source_generate.py (Bash) or the analyst subagent.",
               file_name)

    if role == "gdd":
        if is_assets:
            _block(f"GDD role cannot write to assets/ ({file_name}). "
                   "Asset files are produced during /gm-asset.", file_name)
        if ext == ".md" or file_name == "project.godot" or is_godotmaker:
            return
        _block(f"GDD role may only write planning docs, project.godot, or "
               f".godotmaker/ (attempted: {file_name}).", file_name)

    if is_code:
        if role in WORKER_DISPATCH_ROLES:
            _block(f"{role.capitalize()} role cannot write game code directly "
                   f"({file_name}). Dispatch a Worker subagent.", file_name)
        else:
            _block(f"{role.capitalize()} role cannot modify game code "
                   f"({file_name}).", file_name)


def _lookup_agent_type(agent_id: str) -> str:
    """Find the agent_type recorded at SubagentStart for this agent_id.

    Falls back to scanning metrics_current.jsonl when the PreToolUse payload
    doesn't carry agent_type directly.
    """
    if not agent_id:
        return ""
    try:
        from metrics import read_current_events
        for evt in reversed(list(read_current_events())):
            if (evt.get("event") == "subagent_start"
                    and evt.get("agent_id") == agent_id
                    and evt.get("agent_type")):
                return evt["agent_type"]
    except Exception:
        pass
    return ""


def _check_subagent(path_lower: str, file_name: str, agent_id: str,
                    agent_type: str) -> None:
    """Apply subagent rules. Calls _block on violation."""
    if agent_type == "asset-producer":
        if (_is_asset_generation_path(path_lower)
                or _is_assets_path(path_lower)
                or _is_references_path(path_lower)):
            return
        if file_name in PLANNING_DOCS or file_name == PROJECT_GODOT:
            _block(f"Asset producers cannot modify planning documents or project.godot ({file_name}).",
                   file_name, agent_id)
        if _is_e2e_path(path_lower):
            _block(f"Asset producers cannot write to e2e/ ({file_name}).",
                   file_name, agent_id)
        _, ext = os.path.splitext(path_lower)
        if ext in GAME_CODE_EXTENSIONS:
            _block(f"Asset producers cannot modify game code ({file_name}).",
                   file_name, agent_id)
        _block(f"Asset producers can only write asset outputs and .godotmaker/asset-generation/ ({file_name}).",
               file_name, agent_id)

    if _is_e2e_path(path_lower):
        _block(f"Workers cannot write to e2e/ ({file_name}). "
               "E2E tests are owned by the Evaluator.", file_name, agent_id)
    if _is_godotmaker_path(path_lower):
        # Subagents must not write under .godotmaker/ — that's hook trust
        # ground (metrics_current.jsonl, current_role, stage.jsonl,
        # evaluation.json). Without this rule, a worker could forge a
        # subagent_start event with agent_type=decomposer and bypass the
        # PLANNING_DOCS gate via the metrics-fallback lookup below.
        _block(f"Workers cannot write to .godotmaker/ ({file_name}). "
               "Pipeline state files are managed by the lead skill, "
               "not subagents.", file_name, agent_id)
    if file_name in PLANNING_DOCS:
        if agent_type in PLANNING_WRITER_AGENT_TYPES:
            return  # Decomposer's whole job is writing these — allow.
        _block(f"Workers cannot modify planning documents ({file_name}). "
               "Report changes in your Report Notes section.", file_name, agent_id)
    if file_name == PROJECT_GODOT:
        if agent_type in PLANNING_WRITER_AGENT_TYPES:
            return  # Decomposer may tweak engine config during 1b.
        _block("Workers cannot modify project.godot. Engine config is "
               "owned by the gdd / scaffold roles or the decomposer subagent.",
               file_name, agent_id)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    path_lower = file_path.replace("\\", "/").lower()
    file_name = os.path.basename(path_lower)
    _, ext = os.path.splitext(path_lower)

    agent_id = data.get("agent_id", "")
    is_subagent = bool(agent_id)
    agent_type = data.get("agent_type", "") or _lookup_agent_type(agent_id)

    record_event(
        EventType.FILE_WRITE if tool_name == "Write" else EventType.FILE_EDIT,
        file=file_name,
        agent_id=agent_id or "main",
        is_subagent=is_subagent,
    )

    role = get_current_role()

    if not role:
        record_event(EventType.HOOK_ALLOW, hook="check_file_permissions",
                     file=file_name, agent_id=agent_id or "main", role=role)
        sys.exit(0)
    elif is_subagent:
        _check_subagent(path_lower, file_name, agent_id, agent_type)
    else:
        _check_main(role, path_lower, file_name, ext)

    record_event(EventType.HOOK_ALLOW, hook="check_file_permissions",
                 file=file_name, agent_id=agent_id or "main", role=role)


if __name__ == "__main__":
    main()
