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
# The cross-tag memory notebook: the root index plus everything under the
# project-root `memory/`. Subagents never write it — a worker reports execution
# results and failure evidence, and the dispatching role decides what, if
# anything, becomes durable project knowledge. See `_is_memory_path`.
MEMORY_INDEX = "memory.md"
E2E_DIR_PREFIX = "e2e/"
ASSETS_DIR_PREFIX = "assets/"
REFERENCES_DIR_PREFIX = "references/"
GODOTMAKER_DIR = ".godotmaker/"
# Subagent types whose entire purpose is writing planning docs — exempt
# from the general subagent block on PLANNING_DOCS and PROJECT_GODOT.
PLANNING_WRITER_AGENT_TYPES = {"decomposer"}
# How much of the subagent rule set a payload asks for. `memory` is the subset
# that needs no role identity — see `_check_subagent`.
SCOPE_FULL = "full"
SCOPE_MEMORY = "memory"
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


def _strip_extended_prefix(path: str) -> str:
    r"""Drop Windows' extended-length prefix so the path anchors normally.

    `\\?\C:\proj\memory\x` names the same file as `C:\proj\memory\x`, but
    neither `abspath` nor `realpath` removes the prefix, so the anchored
    comparison would place it outside the project and wave it through.
    """
    for prefix, replacement in ((r"\\?\UNC" + "\\", "\\\\"), (r"\\?" + "\\", "")):
        if path.startswith(prefix):
            return replacement + path[len(prefix):]
    return path


def _project_relative_segments(file_path: str, resolve: bool) -> list[str] | None:
    """Path segments relative to the project root this write belongs to.

    Returns None when the write lands outside the project entirely.

    Normalization happens before any segment is read, so a rule that anchors
    on the first segment cannot be stepped around by a path that names one
    place and lands in another. Both anchors are absolute paths built from the
    hook's cwd, which IS the project root, so one call covers relative and
    absolute input alike.

    `resolve` picks which of the two readings this is:

    - `False` — `abspath`: `..` folded lexically, symlinks left alone. This is
      the path the caller *named*. It is the only reading that still sees the
      notebook when the root `memory/` is itself a link out of the project.
    - `True` — `realpath`: `..` folded and symlinks followed. This is where
      the write actually *lands*. It is the only reading that sees the
      notebook behind a `Notes -> memory` link.

    Neither is sufficient alone, so `_is_memory_path` asks for both.

    `file_path` must carry its original case: lower-casing it first would make
    `realpath` look up a name that does not exist on a case-sensitive
    filesystem, silently failing to follow the very link this is meant to
    catch. Only the comparison is case-insensitive, which also keeps a
    mixed-case project root matching.

    A worker writes from inside a linked worktree, so everything after
    `.claude/worktrees/<agent>/` is project-root-relative again. That check
    runs on the normalized segments, because `..` can cross the marker.
    """
    normalize = os.path.realpath if resolve else os.path.abspath
    try:
        root = normalize(os.getcwd()).replace("\\", "/").rstrip("/").lower()
        target = normalize(_strip_extended_prefix(file_path))
    except (OSError, ValueError):
        # `realpath` raises on an unreachable UNC path. A hook must never
        # crash, and this reading simply has nothing to say — the lexical
        # reading, which touches no filesystem, still gets its vote.
        return None
    target = target.replace("\\", "/").lower()
    if not target.startswith(f"{root}/"):
        return None  # another drive, or outside the project
    segments = [s for s in target[len(root) + 1:].split("/") if s]

    for i in range(len(segments) - 3, -1, -1):
        if segments[i] == ".claude" and segments[i + 1] == "worktrees":
            return segments[i + 3:]

    return segments


def _is_memory_path(file_path: str, file_name: str) -> bool:
    """True for MEMORY.md or ANY file under the project-root `memory/`.

    The notebook is a directory, not a file type: `memory/learning.txt` and
    `memory/rules.json` are project memory exactly as much as
    `memory/movement.md` is. Anchoring on the project root — rather than
    matching a `memory/` segment anywhere — is what keeps a game's own
    `src/memory/` source directory writable.

    A write is the notebook if EITHER reading of its path says so: the one the
    caller named, or the one the filesystem resolves it to. A link named
    `Notes` pointing at `memory/` is only visible to the second; a root
    `memory/` that is itself a link out of the project is only visible to the
    first.

    MEMORY.md stays a basename match, like PLANNING_DOCS: no subagent has a
    reason to write a file by that name anywhere in the tree.
    """
    if file_name == MEMORY_INDEX:
        return True
    for resolve in (False, True):
        segments = _project_relative_segments(file_path, resolve)
        if segments and segments[0] == "memory" and len(segments) > 1:
            return True
    return False


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


def _check_subagent(file_path: str, path_lower: str, file_name: str,
                    agent_id: str, agent_type: str,
                    scope: str = SCOPE_FULL) -> None:
    """Apply subagent rules. Calls _block on violation.

    `file_path` is the write's original, un-lowercased path — the memory rule
    resolves it against the filesystem and needs the real case to follow a
    link. Every other rule here matches on text, so it reads `path_lower`.

    `scope` is `SCOPE_MEMORY` for a runtime that knows a write comes from a
    delegated session but cannot tell which role it is running (OpenCode child
    sessions). The memory rule holds for every subagent type, so it is safe to
    apply without that identity; the ownership rules below are not.
    """
    _, ext = os.path.splitext(path_lower)
    if _is_memory_path(file_path, file_name):
        _block(f"Subagents cannot write project memory ({file_name}). "
               "Report execution results and failure evidence in your report; "
               "the dispatching role owns MEMORY.md and memory/.",
               file_name, agent_id)
    if scope == SCOPE_MEMORY:
        return

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
    # A runtime without Claude-style agent ids states delegation explicitly.
    is_subagent = bool(agent_id) or bool(data.get("is_subagent"))
    scope = data.get("permission_scope") or SCOPE_FULL
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
        _check_subagent(file_path, path_lower, file_name, agent_id,
                        agent_type, scope)
    else:
        _check_main(role, path_lower, file_name, ext)

    record_event(EventType.HOOK_ALLOW, hook="check_file_permissions",
                 file=file_name, agent_id=agent_id or "main", role=role)


if __name__ == "__main__":
    main()
