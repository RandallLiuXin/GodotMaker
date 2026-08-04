#!/usr/bin/env python3
"""SubagentStop dispatcher: validate report, then log the lifecycle event.

Single entry point for the SubagentStop hook. Reads stdin once and runs the
handlers serially:
  1. check_worker_report.evaluate  — decide the verdict (no side effects)
  2. log_subagent.handle_stop      — record metrics, labelled by that verdict
  3. check_worker_report.apply_verdict — emit the decision (may block)

This avoids the race condition that occurs when Claude Code runs multiple
SubagentStop hooks in parallel: log_subagent reads metrics_current.jsonl
while check_worker_report writes to it, causing JSONDecodeError crashes.

Validation is evaluated before the stop is recorded so a rejected report is
logged as a rejected attempt rather than a terminal outcome. Otherwise a
format-only rejection lands in metrics as the run's result and the retry's
real status is discarded by the duplicate-outcome guard.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("hook_event_name") != "SubagentStop":
        sys.exit(0)

    # Dump raw hook data for debugging C/F investigations
    from log_subagent import _debug
    _debug(f"SubagentStop raw keys: {sorted(data.keys())}")
    for k, v in data.items():
        if k == "last_assistant_message":
            _debug(f"  {k}: type={type(v).__name__} len={len(v or '')}")
        else:
            _debug(f"  {k}: {v!r}")

    # 1. Decide the verdict (pure — reads only)
    from check_worker_report import evaluate, apply_verdict
    verdict = evaluate(data)

    # 2. Log lifecycle event, labelled terminal or rejected attempt (never blocks)
    from log_subagent import handle_stop
    handle_stop(data, verdict=verdict)

    # 3. Emit the decision (may block)
    apply_verdict(verdict)


if __name__ == "__main__":
    main()
