import { spawnSync } from "node:child_process";
import { copyFileSync, mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..", "..");
const plugin = join(repoRoot, "agent-runtimes", "opencode", "plugins", "godotmaker-hooks.js");
const sentinel = "GM_INJECT_SENTINEL_4f2b9d";
const fixedArgs = {
  subagent_type: "worker",
  description: "Return the runtime-injected sentinel exactly.",
  prompt: "Return the runtime-injected sentinel exactly.",
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
    `print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': 'GM_INJECT_TOKEN=${sentinel}'}}))`,
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

function runLiveProbe(repeat) {
  const project = mkdtempSync(join(tmpdir(), "godotmaker-opencode-live-"));
  const pluginDir = join(project, ".opencode", "plugins");
  const agentsDir = join(project, ".opencode", "agents");
  mkdirSync(pluginDir, { recursive: true });
  mkdirSync(agentsDir, { recursive: true });
  copyFileSync(plugin, join(pluginDir, "godotmaker-hooks.js"));
  writeHooks(project);
  writeFileSync(join(agentsDir, "worker.md"), [
    "---",
    "name: worker",
    "description: Reads a runtime-injected token and reports it.",
    "mode: subagent",
    "permission:",
    "  read: deny",
    "  grep: deny",
    "  bash: deny",
    "  edit: deny",
    "---",
    "Return the value of GM_INJECT_TOKEN from the delegated prompt or runtime context.",
    "If it is absent, return exactly CONTEXT_MISSING.",
    "",
  ].join("\n"), "utf8");
  const livePrompt = [
    "Use the task tool exactly once with subagent_type worker.",
    "Ask the worker to return the value of GM_INJECT_TOKEN supplied by runtime hook context.",
    "Do not guess a value. Return only the worker's answer.",
  ].join(" ");
  const started = performance.now();
  try {
    const result = spawnSync(opencodeExecutable(), [
      "run",
      "--model", "deepseek/deepseek-v4-pro",
      "--format", "json",
      "--auto",
      livePrompt,
    ], {
      cwd: project,
      encoding: "utf8",
      timeout: 120000,
      windowsHide: true,
      maxBuffer: 1024 * 1024 * 4,
    });
    const stdout = result.stdout ?? "";
    return {
      repeat,
      prompt: livePrompt,
      exitCode: result.status,
      elapsedMs: Number((performance.now() - started).toFixed(3)),
      stdoutBytes: Buffer.byteLength(stdout),
      stderrTail: (result.stderr ?? "").slice(-2000),
      taskObserved: /\btask\b|subagent_type|worker/i.test(stdout),
      sentinelObserved: stdout.includes(sentinel),
      contextMissingObserved: stdout.includes("CONTEXT_MISSING"),
      stdoutTail: stdout.slice(-4000),
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
  model: "deepseek/deepseek-v4-pro",
  prompt: fixedArgs.prompt,
  fixedPayload: { hookSpecificOutput: { hookEventName: "PreToolUse", additionalContext: `GM_INJECT_TOKEN=${sentinel}` } },
  interpretation: "The current adapter returns neither hook context nor mutated task arguments.",
  defectReproduced: runs.every((run) => run.passed),
  runs,
};
if (process.argv.includes("--live")) {
  report.liveRuns = [runLiveProbe(1), runLiveProbe(2)];
  report.liveDefectReproduced = report.liveRuns.every((run) => (
    run.exitCode === 0
    && run.taskObserved
    && !run.sentinelObserved
    && run.contextMissingObserved
  ));
}
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
