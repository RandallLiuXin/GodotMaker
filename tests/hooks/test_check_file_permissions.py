"""Tests for check_file_permissions.py hook."""
import os
import tempfile
import pytest
from .helpers import run_hook, is_blocked, cleanup_metrics, write_current_role

HOOK = "check_file_permissions.py"


@pytest.fixture(autouse=True)
def clean():
    cleanup_metrics()
    yield
    cleanup_metrics()


@pytest.fixture
def project_dir():
    """Temp dir to isolate .godotmaker/current_role per test."""
    original = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        yield tmpdir
        os.chdir(original)


class TestNoRoleRegularConversation:
    """Without current_role, hooks must not restrict ordinary conversations."""

    @pytest.mark.parametrize("ext", [".gd", ".tscn", ".tres"])
    def test_main_agent_can_write_game_code_extensions(self, ext):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": f"scripts/player{ext}"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), f"No-role main agent should write {ext}"

    def test_allow_planning_docs(self):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "PLAN.md"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), "Main agent should be allowed to write PLAN.md"

    def test_allow_memory(self):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "MEMORY.md"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), "Main agent should be allowed to edit MEMORY.md"


class TestNoRoleSubagentRegularConversation:
    """Without current_role, subagents are not treated as pipeline workers."""

    @pytest.mark.parametrize("doc", ["PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md"])
    def test_allow_planning_docs(self, doc):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": doc},
            "agent_id": "worker-123",
        })
        assert not is_blocked(parsed), f"No-role subagent should write {doc}"

    def test_allow_game_code(self):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "scripts/player.gd"},
            "agent_id": "worker-123",
        })
        assert not is_blocked(parsed), "Worker should be allowed to write .gd files"

    def test_allow_test_files(self):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "test/test_player.gd"},
            "agent_id": "worker-456",
        })
        assert not is_blocked(parsed), "Worker should be allowed to write test files"


class TestDecomposerSubagent:
    """Decomposer subagent owns planning docs — must be exempt from the worker block."""

    @pytest.fixture(autouse=True)
    def active_gdd_role(self, project_dir):
        write_current_role("gdd")

    # Full decomposer-owned set: PLANNING_DOCS minus gap.md (which belongs to
    # /gm-fixgap's lead, not decomposer) plus project.godot.
    _DECOMPOSER_OWNED_FILES = [
        "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md",
        "project.godot",
    ]

    @pytest.mark.parametrize("doc", _DECOMPOSER_OWNED_FILES)
    def test_allow_owned_files_via_payload_agent_type(self, doc):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": doc},
            "agent_id": "decomposer-1",
            "agent_type": "decomposer",
        })
        assert not is_blocked(parsed), (
            f"Decomposer should be allowed to write {doc}"
        )

    @pytest.mark.parametrize("doc", _DECOMPOSER_OWNED_FILES)
    def test_other_subagent_type_blocked_from_owned_files(self, doc):
        """Worker subagent must NOT inherit decomposer's privileges on any
        of the owned files (planning docs + project.godot)."""
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": doc},
            "agent_id": "worker-1",
            "agent_type": "worker",
        })
        assert is_blocked(parsed), (
            f"Non-decomposer subagent must be blocked from {doc}"
        )

    def test_allow_via_metrics_lookup_when_payload_missing_agent_type(self, project_dir):
        """Real-world PreToolUse may not carry agent_type — _lookup_agent_type
        must recover it from metrics_current.jsonl."""
        os.makedirs(".godotmaker", exist_ok=True)
        with open(".godotmaker/metrics_current.jsonl", "w", encoding="utf-8") as f:
            f.write('{"ts":"2026-04-30T00:00:00Z","event":"subagent_start",'
                    '"agent_id":"decomposer-2","agent_type":"decomposer"}\n')
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "PLAN.md"},
            "agent_id": "decomposer-2",
            # NO agent_type in payload — must be recovered from metrics
        })
        assert not is_blocked(parsed), (
            "Decomposer recovered via metrics lookup should be allowed"
        )

    def test_subagent_blocked_from_writing_metrics_file(self, project_dir):
        """The metrics-fallback only stays trustworthy if subagents can't
        forge entries. Writes to .godotmaker/metrics_current.jsonl must
        always be denied for any subagent (even decomposer)."""
        for agent_type in ("worker", "decomposer"):
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": ".godotmaker/metrics_current.jsonl"},
                "agent_id": f"{agent_type}-x",
                "agent_type": agent_type,
            })
            assert is_blocked(parsed), (
                f"{agent_type} subagent must NOT be able to write the metrics "
                "log — that's the trust root for agent_type lookup"
            )


class TestIdentityResolution:
    """Lock the current payload-vs-metrics identity-resolution behavior.

    Current rule: `agent_type = data.get("agent_type", "") or _lookup_agent_type(agent_id)`.
    Payload wins when present; metrics is consulted only when payload is empty.
    These tests document and freeze that priority — if the resolution rule
    changes (e.g., to require both to agree), update these tests deliberately."""

    @pytest.fixture(autouse=True)
    def active_gdd_role(self, project_dir):
        write_current_role("gdd")

    def test_payload_decomposer_metrics_worker_allows(self, project_dir):
        """When payload says decomposer and metrics says worker, the payload
        wins (current behavior). Subagents cannot forge their own payload
        agent_type — Claude Code constructs it — so this is safe in practice."""
        os.makedirs(".godotmaker", exist_ok=True)
        with open(".godotmaker/metrics_current.jsonl", "w", encoding="utf-8") as f:
            f.write('{"ts":"2026-04-30T00:00:00Z","event":"subagent_start",'
                    '"agent_id":"agent-mismatch-1","agent_type":"worker"}\n')
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "PLAN.md"},
            "agent_id": "agent-mismatch-1",
            "agent_type": "decomposer",
        })
        assert not is_blocked(parsed), (
            "Payload agent_type wins over metrics — decomposer payload allows."
        )

    def test_payload_worker_metrics_decomposer_blocks(self, project_dir):
        """Inverse: when payload says worker and metrics says decomposer,
        payload still wins, so the write is BLOCKED. This pins the
        priority — if we ever flip to 'metrics wins', this test must change."""
        os.makedirs(".godotmaker", exist_ok=True)
        with open(".godotmaker/metrics_current.jsonl", "w", encoding="utf-8") as f:
            f.write('{"ts":"2026-04-30T00:00:00Z","event":"subagent_start",'
                    '"agent_id":"agent-mismatch-2","agent_type":"decomposer"}\n')
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "PLAN.md"},
            "agent_id": "agent-mismatch-2",
            "agent_type": "worker",
        })
        assert is_blocked(parsed), (
            "Payload agent_type wins over metrics — worker payload blocks."
        )

    def test_payload_empty_metrics_worker_blocks(self, project_dir):
        """Empty payload triggers metrics lookup. If lookup says worker,
        the write must be blocked."""
        os.makedirs(".godotmaker", exist_ok=True)
        with open(".godotmaker/metrics_current.jsonl", "w", encoding="utf-8") as f:
            f.write('{"ts":"2026-04-30T00:00:00Z","event":"subagent_start",'
                    '"agent_id":"worker-via-lookup","agent_type":"worker"}\n')
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "PLAN.md"},
            "agent_id": "worker-via-lookup",
            # NO agent_type in payload — lookup resolves to worker
        })
        assert is_blocked(parsed), (
            "Lookup-resolved worker identity must block planning-doc writes."
        )


class TestEdgeCases:
    """Edge cases and non-file-write tools."""

    def test_non_write_tool_allowed(self):
        _, code, parsed = run_hook(HOOK, {
            "tool_name": "Read",
            "tool_input": {"file_path": "scripts/player.gd"},
            "agent_id": "",
        })
        assert code == 0
        assert not is_blocked(parsed), "Non-write tools should always pass"

    def test_empty_input(self):
        _, code, _ = run_hook(HOOK, {})
        assert code == 0, "Empty input should not crash"

    def test_missing_file_path(self):
        _, code, _ = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {},
            "agent_id": "",
        })
        assert code == 0, "Missing file_path should not crash"

    def test_windows_backslash_path(self):
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "scripts\\player_system.gd"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), "No-role regular conversation should allow Windows paths"


class TestRoleBased:
    """Role-based permissions per current_role file."""

    @pytest.mark.parametrize("ext", [".gd", ".tscn", ".tres"])
    def test_scaffold_can_write_game_code(self, project_dir, ext):
        write_current_role("scaffold")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": f"scripts/x{ext}"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), "Scaffold may write game code"

    def test_scaffold_can_write_e2e_conftest(self, project_dir):
        """Scaffold creates the initial e2e/conftest.py — permissive role."""
        write_current_role("scaffold")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "e2e/conftest.py"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), "Scaffold must be able to seed e2e/conftest.py"

    @pytest.mark.parametrize("role", ["gdd", "asset", "build", "fixgap", "accept", "finalize"])
    def test_main_blocked_from_e2e(self, project_dir, role):
        write_current_role(role)
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "e2e/test_player.py"},
            "agent_id": "",
        })
        assert is_blocked(parsed), f"role={role} must not write to e2e/"

    @pytest.mark.parametrize("role", ["build", "fixgap"])
    def test_dispatch_role_blocked_from_game_code(self, project_dir, role):
        write_current_role(role)
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "scripts/move.gd"},
            "agent_id": "",
        })
        assert is_blocked(parsed)

    def test_gdd_can_write_planning_docs(self, project_dir):
        write_current_role("gdd")
        for path in ["GDD.md", "PLAN.md", "STRUCTURE.md", "STYLE.md", "ASSETS.md", "SCENES.md", "TOC.md", "ROADMAP.md"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert not is_blocked(parsed), f"gdd must allow {path}"

    def test_gdd_can_write_project_godot(self, project_dir):
        write_current_role("gdd")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": "project.godot"},
            "agent_id": "",
        })
        assert not is_blocked(parsed), "gdd may tweak project.godot for design changes"

    @pytest.mark.parametrize("ext", [".gd", ".tscn", ".tres"])
    def test_gdd_blocked_from_game_code(self, project_dir, ext):
        write_current_role("gdd")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": f"src/x{ext}"},
            "agent_id": "",
        })
        assert is_blocked(parsed), f"gdd must not write {ext}"

    def test_gdd_blocked_from_assets_dir(self, project_dir):
        write_current_role("gdd")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "assets/sprite.png"},
            "agent_id": "",
        })
        assert is_blocked(parsed), "gdd must not write to assets/"

    def test_asset_can_write_assets_md(self, project_dir):
        write_current_role("asset")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "ASSETS.md"},
            "agent_id": "",
        })
        assert not is_blocked(parsed)

    def test_asset_can_write_godotmaker(self, project_dir):
        write_current_role("asset")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": ".godotmaker/state.json"},
            "agent_id": "",
        })
        assert not is_blocked(parsed)

    def test_asset_blocked_from_other_files(self, project_dir):
        write_current_role("asset")
        for path in ["assets/sprite.png", "PLAN.md", "STRUCTURE.md", "STYLE.md", "SCENES.md",
                     "GAP.md", "src/x.gd", "GDD.md"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert is_blocked(parsed), f"asset role must block {path}"

    def test_asset_can_write_root_assets_md_relative_and_absolute(self, project_dir):
        """Asset role must accept the project-root ASSETS.md whether the
        agent passes a bare relative name or a fully resolved absolute
        path. The original bug was matching on full path equality
        (`path_lower == "assets.md"`), which rejected the absolute form
        Claude Code emits on Windows."""
        write_current_role("asset")
        abs_root = os.path.join(project_dir, "ASSETS.md")
        for path in ["ASSETS.md", "assets.md", abs_root]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert not is_blocked(parsed), (
                f"asset role must allow project-root ASSETS.md: {path}"
            )

    def test_asset_blocked_from_non_root_assets_md(self, project_dir):
        """Project-root ASSETS.md only — a sibling/nested ASSETS.md must
        be blocked even though the basename matches. The hook's deny
        message and SKILL.md contract are explicitly project-root, so
        bare basename matching alone would over-permit."""
        write_current_role("asset")
        abs_subdir = os.path.join(project_dir, "subdir", "ASSETS.md")
        abs_other = os.path.join(
            os.path.dirname(project_dir.rstrip("/\\")) or project_dir,
            "other-project", "ASSETS.md",
        )
        for path in ["subdir/ASSETS.md", "src/ASSETS.md", abs_subdir, abs_other]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert is_blocked(parsed), (
                f"asset role must block non-root ASSETS.md: {path}"
            )

    def test_verify_is_read_only(self, project_dir):
        write_current_role("verify")
        for path in ["scripts/x.gd", "PLAN.md", "e2e/test.py",
                     ".godotmaker/evaluation.json", ".godotmaker/random.json"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert is_blocked(parsed), f"verify must block {path}"

    def test_verify_can_write_stage_jsonl_and_current_role(self, project_dir):
        """Verify needs to update bookkeeping files even though it is otherwise
        read-only (per gm-verify SKILL.md 'Session Setup' + 'When Done')."""
        write_current_role("verify")
        for path in [".godotmaker/stage.jsonl", ".godotmaker/current_role",
                     ".godotmaker/verify_report.json"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Edit",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert not is_blocked(parsed), f"verify must allow {path}"

    def test_evaluate_can_write_e2e(self, project_dir):
        write_current_role("evaluate")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "e2e/test_game.py"},
            "agent_id": "",
        })
        assert not is_blocked(parsed)

    def test_evaluate_can_write_evaluation_json(self, project_dir):
        write_current_role("evaluate")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": ".godotmaker/evaluation.json"},
            "agent_id": "",
        })
        assert not is_blocked(parsed)

    def test_evaluate_can_write_stage_jsonl(self, project_dir):
        """Evaluate must append its completion event to .godotmaker/stage.jsonl
        (per gm-evaluate SKILL.md 'When Done')."""
        write_current_role("evaluate")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Edit",
            "tool_input": {"file_path": ".godotmaker/stage.jsonl"},
            "agent_id": "",
        })
        assert not is_blocked(parsed)

    def test_evaluate_blocked_from_other_files(self, project_dir):
        write_current_role("evaluate")
        # Includes other .godotmaker/ paths that are NOT in the allow-list
        # (final_report.json belongs to finalize; config.yaml is user-owned).
        for path in ["scripts/x.gd", "PLAN.md", "MEMORY.md", "config.yaml",
                     ".godotmaker/final_report.json", ".godotmaker/config.yaml",
                     ".godotmaker/random.json"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert is_blocked(parsed), f"evaluate must block {path}"

    def test_finalize_can_update_docs(self, project_dir):
        write_current_role("finalize")
        for path in ["GDD.md", "MEMORY.md", "STRUCTURE.md", ".godotmaker/final_report.json"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert not is_blocked(parsed), f"finalize must allow {path}"

    def test_rescue_can_write_bookkeeping(self, project_dir):
        """Rescue's two carve-outs (per gm-rescue SKILL.md 'Hard rules' +
        'Session Setup' + 'When Done') — current_role to set the role lock,
        stage.jsonl to record the rescue event."""
        write_current_role("rescue")
        for path in [".godotmaker/stage.jsonl", ".godotmaker/current_role"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Edit",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert not is_blocked(parsed), f"rescue must allow {path}"

    def test_rescue_blocked_from_everything_else(self, project_dir):
        """Rescue is diagnostic-only — chat output, no file mutations beyond
        the two bookkeeping carve-outs. Includes innocuous .md / .json paths
        the SKILL never touches but a misbehaving agent might try to write."""
        write_current_role("rescue")
        for path in ["scripts/x.gd", "PLAN.md", "MEMORY.md", "GDD.md",
                     "ROADMAP.md", "GAP.md", ".godotmaker/evaluation.json",
                     ".godotmaker/verify_report.json",
                     ".godotmaker/final_report.json",
                     ".godotmaker/random.json", "e2e/test_x.py"]:
            _, _, parsed = run_hook(HOOK, {
                "tool_name": "Write",
                "tool_input": {"file_path": path},
                "agent_id": "",
            })
            assert is_blocked(parsed), f"rescue must block {path}"


class TestSubagentInRole:
    """Subagent rules apply on top of role rules."""

    def test_worker_blocked_from_e2e_in_build(self, project_dir):
        write_current_role("build")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "e2e/test_x.py"},
            "agent_id": "worker-1",
        })
        assert is_blocked(parsed)

    def test_worker_can_write_game_code(self, project_dir):
        write_current_role("build")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "systems/move.gd"},
            "agent_id": "worker-1",
        })
        assert not is_blocked(parsed)

    def test_worker_blocked_from_planning_docs(self, project_dir):
        write_current_role("build")
        _, _, parsed = run_hook(HOOK, {
            "tool_name": "Write",
            "tool_input": {"file_path": "PLAN.md"},
            "agent_id": "worker-1",
        })
        assert is_blocked(parsed)
