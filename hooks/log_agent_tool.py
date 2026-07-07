#!/usr/bin/env python3
"""PreToolUse + PostToolUse hook: capture Agent tool prompt + final output.

Why this and not log_subagent.py:
  SubagentStart's payload schema (claude-code source `coreSchemas.ts:540`)
  has only `agent_id` + `agent_type` — NO `prompt`. SubagentStop's payload
  has `last_assistant_message` (final text excerpt only) and an internal
  `agent_transcript_path`. Neither gives a clean way to capture the full
  Agent dispatch contract via documented public API.

  PreToolUse + PostToolUse with matcher=Agent does:
  - PreToolUse `tool_input` is the official Agent dispatch dict
    {prompt, description, subagent_type, model} — `prompt` is documented
    and present (https://code.claude.com/docs/en/hooks).
  - PostToolUse `tool_response` is documented as the COMPLETE final
    output of the subagent including its tool calls and conclusions.
  - `tool_use_id` pairs the two events.

Both events write to `.godotmaker/traces/` via tmpfile + os.replace so a
killed-mid-write hook process can never leave a 0-byte stub on disk
(the failure mode that produced 37 of 38 zero-byte files in the
2026-05-09 e2e test session under the old SubagentStart/Stop approach).

Never blocks (always exit 0). Filter is defensive: settings.json registers
this hook only against matcher="Agent|Task", but if Claude Code dispatches
something else through the same hook slot we still no-op cleanly.

DIAGNOSTIC LOGGING:
  After the 2026-05-12 GodotMakerTest2 AAR found 72 zero-byte .tmp_ files
  and 0 successful real files, every step of this hook is now logged to
  `.godotmaker/traces/log_agent_tool_debug.log`. Each line is timestamped
  + PID + tool_use_id + phase. This is best-effort — log writes never
  raise. Read that log after the next live run to pinpoint where the
  pipeline breaks (mkstemp / fdopen / write / replace / exception).
"""
import json
import os
import sys
import tempfile
import time
import traceback

# Same legacy alias as Anthropic carries internally — claude-code-src
# `tools/AgentTool/constants.ts` exports `Task` for back-compat.
AGENT_TOOL_NAMES = {"Agent", "Task"}

TRACES_DIR = os.path.join(".godotmaker", "traces")
# Diagnostic log lives ONE LEVEL ABOVE traces/, so tests asserting trace
# contents (e.g. test_path_traversal_in_tool_use_id_is_neutralized) don't
# see it, and so it survives even if traces/ gets sweep-cleaned.
LOG_PATH = os.path.join(".godotmaker", "log_agent_tool_debug.log")


def _log(*parts):
    """Best-effort timestamped append to the diagnostic log. Never raises."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] [pid={os.getpid()}] " + " ".join(str(p) for p in parts) + "\n"
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _summarize(value, max_len=120):
    """Short, single-line description of a payload value for logging."""
    if value is None:
        return "None"
    if isinstance(value, str):
        snippet = value.replace("\n", "\\n").replace("\r", "\\r")
        if len(snippet) > max_len:
            snippet = snippet[: max_len - 3] + "..."
        return f"str(len={len(value)}, head={snippet!r})"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        return f"dict(keys={keys})"
    if isinstance(value, (list, tuple)):
        return f"{type(value).__name__}(len={len(value)})"
    return f"{type(value).__name__}({value!r}[:80])"


def _sanitize_id(raw: str) -> str:
    """Reject path traversal in tool_use_id without mangling normal ids."""
    safe = raw.replace("/", "_").replace("\\", "_").replace("..", "_")
    return safe or "unknown"


def _atomic_write(path: str, content: str, ctx: str) -> None:
    """Write `content` to `path` atomically: tmpfile in same dir + os.replace.

    If anything fails between open and replace, the visible file at `path`
    is either the previous version or absent — never a half-written stub.

    `ctx` is a short label for the diagnostic log (e.g. tool_use_id + phase).
    """
    _log(ctx, "_atomic_write enter", "path=", path, "content_len=", len(content) if content else 0)
    if not content:
        _log(ctx, "_atomic_write skip (empty content)")
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as e:
        _log(ctx, "_atomic_write makedirs FAIL", repr(e))
        return

    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".tmp_", dir=os.path.dirname(path))
        _log(ctx, "mkstemp ok", "tmp=", os.path.basename(tmp), "fd=", fd)
    except OSError as e:
        _log(ctx, "mkstemp FAIL", repr(e))
        return

    try:
        # errors="backslashreplace": Agent prompts / tool responses can carry
        # lone Unicode surrogates (e.g. a byte that got surrogate-escaped
        # upstream survives json.loads -> json.dumps(ensure_ascii=False) as a
        # raw \udcXX char). A strict UTF-8 encoder raises UnicodeEncodeError on
        # those, which used to silently drop the whole trace file. Escaping the
        # un-encodable chars keeps the file valid UTF-8 and readable; for the
        # input.json path the escape is exactly a JSON \uXXXX sequence, so the
        # file still round-trips through json.loads.
        with os.fdopen(fd, "w", encoding="utf-8", errors="backslashreplace") as f:
            f.write(content)
        _log(ctx, "write+close ok", "bytes_written=", len(content))
    except Exception as e:  # noqa: BLE001 — log then unlink, never block
        _log(ctx, "write+close FAIL", repr(e))
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return

    try:
        os.replace(tmp, path)
        _log(ctx, "os.replace ok", "->", os.path.basename(path))
    except OSError as e:
        _log(ctx, "os.replace FAIL", repr(e))
        try:
            os.unlink(tmp)
        except OSError as e2:
            _log(ctx, "unlink-on-fail FAIL", repr(e2))


def _stringify_response(response):
    """tool_response is `unknown` per schema. In practice it's a string for
    Agent tool, but fall back to JSON serialization for any structured
    payload we might encounter."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    try:
        return json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return repr(response)


def main():
    raw = None
    try:
        raw = sys.stdin.read()
    except (OSError, EOFError) as e:
        _log("(no id)", "stdin.read FAIL", repr(e))
        sys.exit(0)
    _log("(no id)", "stdin.read ok", "raw_len=", len(raw or ""))

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        _log("(no id)", "json.loads FAIL", repr(e), "head=", (raw or "")[:120])
        sys.exit(0)

    event = data.get("hook_event_name") or ""
    tool_name = data.get("tool_name") or ""
    raw_id = data.get("tool_use_id") or ""
    tool_use_id = _sanitize_id(raw_id)
    ctx = f"id={tool_use_id} event={event} tool={tool_name}"

    _log(ctx, "main enter", "data_keys=", sorted(data.keys()))

    if tool_name not in AGENT_TOOL_NAMES:
        _log(ctx, "skip (tool not Agent|Task)")
        sys.exit(0)

    if event == "PreToolUse":
        tool_input = data.get("tool_input")
        _log(ctx, "tool_input =", _summarize(tool_input))
        if not tool_input:
            _log(ctx, "skip PreToolUse (empty tool_input)")
            sys.exit(0)
        try:
            content = json.dumps(tool_input, ensure_ascii=False, indent=2, sort_keys=True)
            _log(ctx, "json.dumps ok", "out_len=", len(content))
        except (TypeError, ValueError) as e:
            _log(ctx, "json.dumps FAIL, falling back to repr", repr(e))
            content = repr(tool_input)
        _atomic_write(
            os.path.join(TRACES_DIR, f"agent_{tool_use_id}_input.json"),
            content,
            ctx + " phase=PreToolUse",
        )

    elif event == "PostToolUse":
        tool_response = data.get("tool_response")
        _log(ctx, "tool_response =", _summarize(tool_response))
        content = _stringify_response(tool_response)
        _atomic_write(
            os.path.join(TRACES_DIR, f"agent_{tool_use_id}_output.md"),
            content,
            ctx + " phase=PostToolUse",
        )

    else:
        _log(ctx, "skip (event not Pre/PostToolUse)")

    _log(ctx, "main exit normally")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # noqa: BLE001 — never let the hook crash silently
        try:
            _log("(top-level)", "UNCAUGHT", repr(e))
            _log("(top-level)", traceback.format_exc().replace("\n", " | "))
        except Exception:
            pass
        # Hook contract: never block. Exit 0 even after uncaught.
        sys.exit(0)
