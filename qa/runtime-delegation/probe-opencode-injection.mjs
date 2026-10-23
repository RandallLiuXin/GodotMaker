import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..", "..");
const plugin = join(repoRoot, "agent-runtimes", "opencode", "plugins", "godotmaker-hooks.js");
const sentinel = "GM_INJECT_SENTINEL_4f2b9d";
const fixedArgs = {
  subagent_type: "worker",
  description: "Exercise the task pre-hook adapter.",
  prompt: "Fixed task payload for the adapter-boundary probe.",
};

function opencodeExecutable() {
  const where = process.platform === "win32" ? "where.exe" : "which";
  const located = spawnSync(where, ["opencode"], { encoding: "utf8", windowsHide: true });
  if (located.status !== 0) throw new Error(`opencode unavailable: ${located.stderr.trim()}`);
  const shim = located.stdout.trim().split(/\r?\n/)[0];
  return process.platform === "win32"
    ? join(dirname(shim), "node_modules", "opencode-ai", "bin", "opencode.exe")
    : shim;
}

function opencodeVersion() {
  const executable = opencodeExecutable();
  const result = spawnSync(executable, ["--version"], { encoding: "utf8", windowsHide: true });
  return result.status === 0 ? result.stdout.trim() : `unavailable: ${result.stderr.trim()}`;
}

function writeHooks(project) {
  const hooksDir = join(project, ".godotmaker", "hooks");
  mkdirSync(hooksDir, { recursive: true });
  writeFileSync(join(hooksDir, "check_stage_prerequisites.py"), [
    "import json, sys",
    "payload = json.load(sys.stdin)",
    `print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': 'GM_INJECT_MARKER=${sentinel}'}}))`,
    "",
  ].join("\n"), "utf8");
  writeFileSync(join(hooksDir, "log_agent_tool.py"), "import sys\nsys.exit(0)\n", "utf8");
}

async function runProbe(repeat) {
  const project = mkdtempSync(join(tmpdir(), "godotmaker-opencode-injection-"));
  writeHooks(project);

  try {
    const { GodotMakerHooks } = await import(`${pathToFileURL(plugin).href}?repeat=${repeat}`);
    const adapter = await GodotMakerHooks({ directory: project });
    const output = { args: structuredClone(fixedArgs) };
    const returned = await adapter["tool.execute.before"](
      { tool: "task", callID: `task-${repeat}`, sessionID: "root" },
      output,
    );
    const serializedOutput = JSON.stringify(output);
    const serializedReturn = JSON.stringify(returned ?? null);
    return {
      repeat,
      input: fixedArgs,
      output,
      returned: returned ?? null,
      sentinel,
      sentinelInDelegationArgs: serializedOutput.includes(sentinel),
      sentinelInHookReturn: serializedReturn.includes(sentinel),
      passed: !serializedOutput.includes(sentinel) && !serializedReturn.includes(sentinel),
    };
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
}

const runs = [await runProbe(1), await runProbe(2)];
const report = {
  schemaVersion: 1,
  generatedAt: new Date().toISOString(),
  runtime: "opencode",
  opencodeVersion: opencodeVersion(),
  prompt: fixedArgs.prompt,
  fixedPayload: { hookSpecificOutput: { hookEventName: "PreToolUse", additionalContext: `GM_INJECT_MARKER=${sentinel}` } },
  interpretation: "The current task pre-hook adapter discards the hook result: it neither propagates the result nor mutates task arguments.",
  defectReproduced: runs.every((run) => run.passed),
  runs,
};
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
