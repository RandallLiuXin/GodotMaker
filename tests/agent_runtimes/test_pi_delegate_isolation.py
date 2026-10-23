"""Runtime coverage for Pi's role-specific delegation isolation."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE = (
    REPO_ROOT / "agent-runtimes" / "pi" / "extensions" / "godotmaker-runtime.ts"
)
NODE = shutil.which("node")


def _runtime_module(tmp_path: Path) -> Path:
    runtime = tmp_path / "godotmaker-runtime.ts"
    shutil.copy2(RUNTIME_SOURCE, runtime)
    package = tmp_path / "node_modules" / "typebox"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"type": "module", "exports": "./index.js"}),
        encoding="utf-8",
    )
    (package / "index.js").write_text(
        "export const Type = new Proxy({}, { get: () => (...args) => ({ args }) });\n",
        encoding="utf-8",
    )
    return runtime


def _run_node(source: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            NODE,
            "--disable-warning=ExperimentalWarning",
            "--experimental-strip-types",
            "--input-type=module",
            "-e",
            source,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_role_defaults_and_explicit_isolation_overrides(tmp_path: Path):
    runtime = _runtime_module(tmp_path)
    source = textwrap.dedent(
        f"""
        import {{ ROLE_CONTRACTS, resolveIsolation }} from {json.dumps(runtime.as_uri())};

        const expected = {{
          worker: "worktree",
          decomposer: "shared",
          "asset-producer": "shared",
          verifier: "shared",
          reviewer: "shared",
          analyst: "shared",
          "gdd-auditor": "shared",
        }};
        for (const [role, isolation] of Object.entries(expected)) {{
          if (ROLE_CONTRACTS[role].defaultIsolation !== isolation) throw new Error(role);
          if (resolveIsolation({{ role, task: "test" }}) !== isolation) throw new Error(role);
        }}
        if (resolveIsolation({{ role: "worker", task: "test", isolation: "shared" }}) !== "shared") {{
          throw new Error("worker shared override was ignored");
        }}
        if (resolveIsolation({{ role: "decomposer", task: "test", isolation: "worktree" }}) !== "worktree") {{
          throw new Error("decomposer worktree override was ignored");
        }}
        console.log("ok");
        """
    )
    result = _run_node(source)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def _write_fake_pi(package_dir: Path) -> None:
    cli = package_dir / "dist" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text(
        textwrap.dedent(
            """
            const fs = require("node:fs");
            const path = require("node:path");
            const task = process.argv.at(-1);
            const match = task.match(/WRITE:([^=]+)=(.+)$/m);
            if (!match) process.exit(2);
            const output = path.join(process.cwd(), match[1]);
            fs.mkdirSync(path.dirname(output), { recursive: true });
            fs.writeFileSync(output, match[2] + "\\n", "utf8");
            console.log(JSON.stringify({
              type: "message_end",
              message: { role: "assistant", content: [{ type: "text", text: "PASS" }] },
            }));
            """
        ),
        encoding="utf-8",
    )


def _write_temp_project(project: Path) -> None:
    for relative in (
        ".pi/skills",
        ".pi/agents",
        ".pi/references",
        ".pi/extensions",
        ".godotmaker",
        "tools",
    ):
        (project / relative).mkdir(parents=True, exist_ok=True)
    for relative in (
        "project.godot",
        ".pi/godotmaker.yaml",
        ".pi/references/runtime-mapping.md",
        ".pi/extensions/godotmaker-runtime.ts",
        ".godotmaker/config.yaml",
        "AGENTS.md",
    ):
        (project / relative).write_text("fixture\n", encoding="utf-8")
    for role in ("decomposer", "asset-producer"):
        (project / ".pi" / "agents" / f"{role}.md").write_text(
            f"# {role}\n", encoding="utf-8"
        )


@pytest.mark.skipif(NODE is None, reason="node is required")
def test_parallel_gdd_and_asset_workflows_write_to_shared_main_tree(tmp_path: Path):
    runtime = _runtime_module(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    _write_temp_project(project)
    pi_package = tmp_path / "fake-pi"
    _write_fake_pi(pi_package)

    source = textwrap.dedent(
        f"""
        import registerRuntime from {json.dumps(runtime.as_uri())};

        let delegate;
        registerRuntime({{
          registerTool(tool) {{
            if (tool.name === "godotmaker_delegate") delegate = tool;
          }},
        }});
        const cwd = {json.dumps(str(project))};
        async function dispatch(requests) {{
          const result = await delegate.execute("test", {{ requests }}, undefined, undefined, {{ cwd }});
          if (result.isError) throw new Error(result.content[0].text);
          if (!result.details.results.every((item) => item.cwd === cwd && !item.branch)) {{
            throw new Error("default shared delegation left the main working tree");
          }}
        }}
        await dispatch([
          {{ role: "decomposer", task: "WRITE:PLAN.md=plan", writePaths: ["PLAN.md"] }},
          {{ role: "decomposer", task: "WRITE:STRUCTURE.md=structure", writePaths: ["STRUCTURE.md"] }},
        ]);
        await dispatch([
          {{ role: "asset-producer", task: "WRITE:assets/unit-a/icon.txt=a", writePaths: ["assets/unit-a"] }},
          {{ role: "asset-producer", task: "WRITE:assets/unit-b/icon.txt=b", writePaths: ["assets/unit-b"] }},
        ]);
        for (const [left, right] of [
          ["assets/unit-a", "assets/unit-a/icon.txt"],
          ["assets/generated/sprite/", "assets/generated/sprite/hero/"],
          ["./", "PLAN.md"],
        ]) {{
          const overlap = await delegate.execute("test", {{ requests: [
            {{ role: "decomposer", task: "unused", writePaths: [left] }},
            {{ role: "asset-producer", task: "unused", writePaths: [right] }},
          ] }}, undefined, undefined, {{ cwd }});
          if (!overlap.isError || !overlap.content[0].text.includes("write scopes overlap")) {{
            throw new Error(`overlapping shared writes were not rejected: ${{left}} / ${{right}}`);
          }}
        }}
        console.log("ok");
        """
    )
    env = {**os.environ, "PI_PACKAGE_DIR": str(pi_package)}
    result = _run_node(source, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
    assert (project / "PLAN.md").read_text(encoding="utf-8") == "plan\n"
    assert (project / "STRUCTURE.md").read_text(encoding="utf-8") == "structure\n"
    assert (project / "assets" / "unit-a" / "icon.txt").read_text(encoding="utf-8") == "a\n"
    assert (project / "assets" / "unit-b" / "icon.txt").read_text(encoding="utf-8") == "b\n"
