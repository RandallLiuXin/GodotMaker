"""Tests for the OpenCode hook adapter plugin."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "agent-runtimes" / "opencode" / "plugins" / "godotmaker-hooks.js"


def write_hook(project: Path, name: str, body: str) -> None:
    hooks = project / ".godotmaker" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / name).write_text(body, encoding="utf-8")


def run_node(source: str, project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=project,
        text=True,
        capture_output=True,
        timeout=20,
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_session_idle_stop_block_sends_prompt_to_agent(tmp_path: Path):
    write_hook(
        tmp_path,
        "session_start.py",
        "import sys\nsys.exit(0)\n",
    )
    write_hook(
        tmp_path,
        "check_completion.py",
        "import json\nprint(json.dumps({'decision': 'block', 'reason': 'completion stop'}))\n",
    )
    write_hook(
        tmp_path,
        "check_clean_workspace.py",
        "import json\nprint(json.dumps({'decision': 'block', 'reason': 'dirty stop'}))\n",
    )

    source = f"""
import {{ pathToFileURL }} from 'node:url';
const {{ GodotMakerHooks }} = await import(pathToFileURL({json.dumps(str(PLUGIN))}).href);
const prompts = [];
const client = {{
  session: {{
    prompt: async (input) => {{
      prompts.push(input);
    }},
  }},
}};
const hooks = await GodotMakerHooks({{ directory: {json.dumps(str(tmp_path))}, client }});
await hooks.event({{ event: {{ type: 'session.created', properties: {{ info: {{ id: 'root' }} }} }} }});
await hooks.event({{ event: {{ type: 'session.idle', properties: {{ sessionID: 'root' }} }} }});
console.log(JSON.stringify(prompts));
"""
    result = run_node(source, tmp_path)

    assert result.returncode == 0, result.stderr
    prompts = json.loads(result.stdout)
    assert len(prompts) == 1
    assert prompts[0]["path"]["id"] == "root"
    text = prompts[0]["body"]["parts"][0]["text"]
    assert "GodotMaker Stop hooks blocked this stage from finishing." in text
    assert "check_completion.py: completion stop" in text
    assert "check_clean_workspace.py: dirty stop" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
def test_pre_tool_block_still_throws(tmp_path: Path):
    write_hook(
        tmp_path,
        "check_file_permissions.py",
        (
            "import json\n"
            "print(json.dumps({'hookSpecificOutput': {"
            "'permissionDecision': 'deny', "
            "'permissionDecisionReason': 'write denied'"
            "}}))\n"
        ),
    )

    source = f"""
import {{ pathToFileURL }} from 'node:url';
const {{ GodotMakerHooks }} = await import(pathToFileURL({json.dumps(str(PLUGIN))}).href);
const hooks = await GodotMakerHooks({{ directory: {json.dumps(str(tmp_path))} }});
try {{
  await hooks['tool.execute.before'](
    {{ tool: 'write', callID: 'call-1', sessionID: 'root' }},
    {{ args: {{ filePath: 'PLAN.md', content: 'x' }} }}
  );
}} catch (error) {{
  console.log(error.message);
  process.exit(0);
}}
console.error('expected tool block to throw');
process.exit(2);
"""
    result = run_node(source, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "write denied"
