"""Tests for check_asset_access.py hook."""
import pytest

from .helpers import run_hook, is_blocked, cleanup_metrics, write_current_role

HOOK = "check_asset_access.py"


@pytest.fixture(autouse=True)
def clean():
    cleanup_metrics()
    yield
    cleanup_metrics()


def _read_payload(path: str, agent_id: str = "") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": {"file_path": path},
        "agent_id": agent_id,
    }


def test_no_role_allows_main_agent_asset_image_read():
    _, _, parsed = run_hook(HOOK, _read_payload("assets/player.png"))

    assert not is_blocked(parsed)


def test_pipeline_role_blocks_main_agent_asset_image_read():
    write_current_role("build")

    _, _, parsed = run_hook(HOOK, _read_payload("assets/player.png"))

    assert is_blocked(parsed)


def test_pipeline_role_allows_subagent_asset_image_read():
    write_current_role("build")

    _, _, parsed = run_hook(HOOK, _read_payload("assets/player.png", agent_id="analyst-1"))

    assert not is_blocked(parsed)


def test_pipeline_role_allows_non_image_asset_read():
    write_current_role("build")

    _, _, parsed = run_hook(HOOK, _read_payload("assets/manifest.json"))

    assert not is_blocked(parsed)
