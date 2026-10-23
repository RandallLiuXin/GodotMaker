import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..", "..");
const model = "deepseek/deepseek-v4-pro";
const prompt = "Reply exactly GM_DONE.";
const timeoutMs = 10_000;

function commandOutput(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", windowsHide: true });
  if (result.status !== 0) throw new Error(result.stderr || `${command} exited ${result.status}`);
  return result.stdout.trim();
}

function locatePiCli() {
  const where = process.platform === "win32" ? "where.exe" : "which";
  const shim = commandOutput(where, ["pi"]).split(/\r?\n/)[0];
  return join(dirname(shim), "node_modules", "@earendil-works", "pi-coding-agent", "dist", "cli.js");
}

function finalAssistantText(stdout) {
  let finalText = "";
  for (const line of stdout.split(/\r?\n/).filter(Boolean)) {
    try {
      const event = JSON.parse(line);
      if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
      const text = (event.message.content ?? [])
        .filter((part) => part?.type === "text")
        .map((part) => part.text)
        .join("");
      if (text) finalText = text;
    } catch {
      // A malformed or partial line cannot establish the control result.
    }
  }
  return finalText;
}

async function runCase(args, stdinMode, repeat) {
  const started = performance.now();
  let stdout = "";
  let stderr = "";
  let timedOut = false;
  const options = {
    cwd: repoRoot,
    shell: false,
    windowsHide: true,
    ...(stdinMode === "ignore" ? { stdio: ["ignore", "pipe", "pipe"] } : {}),
  };
  const child = spawn(process.execPath, args, options);
  child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
  child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
  const timer = setTimeout(() => {
    timedOut = true;
    child.kill();
  }, timeoutMs);
  const outcome = await new Promise((resolveOutcome) => {
    let finished = false;
    const finish = (exitCode, signal, error = null) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolveOutcome({ exitCode, signal, error });
    };
    child.once("close", (code, signal) => finish(code, signal));
    child.once("error", (error) => finish(null, null, String(error)));
  });
  return {
    repeat,
    stdinMode,
    timedOut,
    exitCode: outcome.exitCode,
    signal: outcome.signal,
    spawnError: outcome.error,
    elapsedMs: Number((performance.now() - started).toFixed(3)),
    stdoutBytes: Buffer.byteLength(stdout),
    stderrBytes: Buffer.byteLength(stderr),
    stderrTail: stderr.slice(-1000),
    finalAssistant: finalAssistantText(stdout),
  };
}

const promptDir = mkdtempSync(join(tmpdir(), "godotmaker-pi-stdin-"));
try {
  const promptFile = join(promptDir, "role.md");
  writeFileSync(promptFile, "Return the requested fixed response without using tools.\n", "utf8");
  const piCli = locatePiCli();
  const args = [
    piCli,
    "--provider", "deepseek",
    "--model", model,
    "--thinking", "off",
    "--approve",
    "--mode", "json",
    "--no-session",
    "-p",
    "--append-system-prompt", promptFile,
    prompt,
  ];
  const productionRuns = [];
  const controlRuns = [];
  for (let repeat = 1; repeat <= 2; repeat += 1) {
    // No stdio option: this is the investigated pre-fix runDelegate spawn shape.
    productionRuns.push(await runCase(args, "open-pipe", repeat));
  }
  for (let repeat = 1; repeat <= 2; repeat += 1) {
    controlRuns.push(await runCase(args, "ignore", repeat));
  }
  const report = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    command: "node qa/runtime-delegation/probe-pi-stdin-hang.mjs",
    environment: {
      runtime: `pi ${commandOutput(process.execPath, [piCli, "--version"])}`,
      node: process.version,
      model,
      thinking: "off",
      mode: "json",
    },
    fixedInput: { prompt, timeoutMs, repeats: 2 },
    productionSpawn: "pre-fix spawn(command, args, { cwd, shell: false, windowsHide: true })",
    controlDifference: "stdio[0] is ignore; stdout and stderr remain pipes",
    productionRuns,
    controlRuns,
    hangReproduced: productionRuns.every((run) => run.timedOut && run.stdoutBytes === 0),
    controlPassed: controlRuns.every((run) => (
      !run.timedOut && run.exitCode === 0 && run.finalAssistant === "GM_DONE"
    )),
  };
  report.passed = report.hangReproduced && report.controlPassed;
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} finally {
  rmSync(promptDir, { recursive: true, force: true });
}
