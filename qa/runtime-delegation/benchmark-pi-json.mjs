import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const extension = join(here, "pi-fixed-payload.ts");
const model = "deepseek/deepseek-v4-pro";
const prompt = [
  "Call fixed_payload exactly once with an empty object.",
  "When it returns GM_TOOL_DONE, reply exactly GM_DONE.",
  "Do not call any other tool and do not explain.",
].join(" ");

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

function textParts(message) {
  return (message?.content ?? [])
    .filter((part) => part?.type === "text")
    .map((part) => part.text)
    .join("");
}

function validateJsonl(stdout, expectedChunks) {
  const lines = stdout.split(/\r?\n/).filter(Boolean);
  let markerUpdates = 0;
  let finalAssistant = "";
  let invalidLine = null;
  for (let index = 0; index < lines.length; index += 1) {
    let event;
    try {
      event = JSON.parse(lines[index]);
    } catch (error) {
      invalidLine = { index: index + 1, error: String(error) };
      break;
    }
    if (event.type === "tool_execution_update") {
      const content = event.partialResult?.content ?? [];
      if (content.some((part) => part.type === "text" && part.text?.startsWith("GM_CHUNK:"))) {
        markerUpdates += 1;
      }
    }
    if (event.type === "message_end" && event.message?.role === "assistant") {
      const text = textParts(event.message);
      if (text) finalAssistant = text;
    }
  }
  return {
    lineCount: lines.length,
    invalidLine,
    markerUpdates,
    expectedChunks,
    finalAssistant,
    passed: invalidLine === null && markerUpdates === expectedChunks && finalAssistant === "GM_DONE",
  };
}

async function runWorker() {
  const chunkBytes = Number.parseInt(process.env.GM_BENCH_CHUNK_BYTES, 10);
  const chunkCount = Number.parseInt(process.env.GM_BENCH_CHUNK_COUNT, 10);
  const timeoutMs = Number.parseInt(process.env.GM_BENCH_TIMEOUT_MS ?? "120000", 10);
  const piCli = locatePiCli();
  const args = [
    piCli,
    "--provider", "deepseek",
    "--model", model,
    "--thinking", "off",
    "--mode", "json",
    "--no-session",
    "--no-builtin-tools",
    "--no-skills",
    "--no-context-files",
    "--no-prompt-templates",
    "--no-themes",
    "--extension", extension,
    "--tools", "fixed_payload",
    "-p",
    prompt,
  ];

  const started = performance.now();
  const baselineRssBytes = process.memoryUsage().rss;
  let peakRssBytes = baselineRssBytes;
  let stdout = "";
  let stderr = "";
  let stdoutBytes = 0;
  let firstPayloadAt = null;
  let lastPayloadAt = null;
  let markerCarry = "";
  const growth = [];
  const requestedPayloadBytes = chunkBytes * chunkCount;
  const growthStep = Math.max(1, Math.floor(requestedPayloadBytes / 4));
  let nextGrowthAt = growthStep;
  let timedOut = false;

  const child = spawn(process.execPath, args, {
    cwd: resolve(here, "..", ".."),
    env: { ...process.env, GM_BENCH_CHUNK_BYTES: String(chunkBytes), GM_BENCH_CHUNK_COUNT: String(chunkCount) },
    shell: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  const timer = setTimeout(() => {
    timedOut = true;
    child.kill();
  }, timeoutMs);

  child.stdout.on("data", (buffer) => {
    const text = buffer.toString();
    stdout += text; // Mirrors the production stdout accumulation operation only.
    stdoutBytes += buffer.length;
    peakRssBytes = Math.max(peakRssBytes, process.memoryUsage().rss);
    const scan = markerCarry + text;
    const matches = scan.match(/GM_CHUNK:/g)?.length ?? 0;
    if (matches > 0) {
      const now = performance.now();
      firstPayloadAt ??= now;
      lastPayloadAt = now;
    }
    markerCarry = scan.slice(-16);
    while (nextGrowthAt <= requestedPayloadBytes && stdoutBytes >= nextGrowthAt) {
      growth.push({
        elapsedMs: Number((performance.now() - started).toFixed(3)),
        stdoutBytes,
        rssBytes: process.memoryUsage().rss,
      });
      nextGrowthAt += growthStep;
    }
  });
  child.stderr.on("data", (buffer) => { stderr += buffer.toString(); });

  const exitCode = await new Promise((resolveExit) => child.once("close", (code) => resolveExit(code ?? 1)));
  clearTimeout(timer);
  const exitedAt = performance.now();
  const integrity = validateJsonl(stdout, chunkCount);
  peakRssBytes = Math.max(peakRssBytes, process.memoryUsage().rss);
  const finishedAt = performance.now();
  const sha256 = createHash("sha256").update(stdout).digest("hex");

  const result = {
    runtime: "pi",
    piVersion: commandOutput(process.execPath, [piCli, "--version"]),
    nodeVersion: process.version,
    model,
    thinking: "off",
    prompt,
    mode: "json",
    chunkBytes,
    chunkCount,
    requestedPayloadBytes,
    exitCode,
    timedOut,
    elapsedMs: Number((exitedAt - started).toFixed(3)),
    payloadStreamElapsedMs: firstPayloadAt === null || lastPayloadAt === null
      ? null
      : Number((lastPayloadAt - firstPayloadAt).toFixed(3)),
    validationElapsedMs: Number((finishedAt - exitedAt).toFixed(3)),
    stdoutBytes,
    stdoutSha256: sha256,
    stderrBytes: Buffer.byteLength(stderr),
    stderrTail: stderr.slice(-1000),
    baselineRssBytes,
    peakRssBytes,
    rssDeltaBytes: peakRssBytes - baselineRssBytes,
    growth,
    integrity,
  };
  result.passed = exitCode === 0 && !timedOut && integrity.passed && result.elapsedMs <= timeoutMs;
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

async function runSuite() {
  const cases = [
    { name: "8MiB", chunkBytes: 65536, chunkCount: 128 },
    { name: "32MiB", chunkBytes: 65536, chunkCount: 512 },
  ];
  const runs = [];
  for (const benchmarkCase of cases) {
    for (let repeat = 1; repeat <= 2; repeat += 1) {
      const child = spawnSync(process.execPath, [fileURLToPath(import.meta.url), "--worker"], {
        cwd: resolve(here, "..", ".."),
        env: {
          ...process.env,
          GM_BENCH_CHUNK_BYTES: String(benchmarkCase.chunkBytes),
          GM_BENCH_CHUNK_COUNT: String(benchmarkCase.chunkCount),
          GM_BENCH_TIMEOUT_MS: "120000",
        },
        encoding: "utf8",
        timeout: 130000,
        windowsHide: true,
        maxBuffer: 1024 * 1024 * 2,
      });
      if (child.status !== 0) {
        throw new Error(`benchmark ${benchmarkCase.name} repeat ${repeat} failed: ${child.stderr || child.stdout}`);
      }
      runs.push({ case: benchmarkCase.name, repeat, ...JSON.parse(child.stdout) });
    }
  }
  const grouped = Object.fromEntries(cases.map((benchmarkCase) => {
    const samples = runs.filter((run) => run.case === benchmarkCase.name);
    const elapsedSpreadMs = Math.max(...samples.map((run) => run.elapsedMs)) - Math.min(...samples.map((run) => run.elapsedMs));
    const rssSpreadBytes = Math.max(...samples.map((run) => run.peakRssBytes)) - Math.min(...samples.map((run) => run.peakRssBytes));
    const elapsedToleranceMs = Math.max(5000, Math.min(...samples.map((run) => run.elapsedMs)) * 0.5);
    const rssToleranceBytes = Math.max(64 * 1024 * 1024, Math.min(...samples.map((run) => run.peakRssBytes)) * 0.5);
    return [benchmarkCase.name, {
      repeatsPassed: samples.every((run) => run.passed),
      elapsedSpreadMs,
      elapsedToleranceMs,
      elapsedWithinTolerance: elapsedSpreadMs <= elapsedToleranceMs,
      rssSpreadBytes,
      rssToleranceBytes,
      rssWithinTolerance: rssSpreadBytes <= rssToleranceBytes,
    }];
  }));
  const largeRuns = runs.filter((run) => run.case === "32MiB");
  const operationalThresholds = {
    maxElapsedMs: 120000,
    exactJsonAndPayloadIntegrity: true,
    maxRssToStdoutRatio: 6,
  };
  const maxLargeRssRatio = Math.max(...largeRuns.map((run) => run.rssDeltaBytes / run.stdoutBytes));
  const summary = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    host: { platform: process.platform, release: process.release.name, arch: process.arch },
    command: "node qa/runtime-delegation/benchmark-pi-json.mjs",
    cases,
    operationalThresholds,
    grouped,
    maxLargeRssRatio,
    passed: runs.every((run) => run.passed)
      && Object.values(grouped).every((group) => group.elapsedWithinTolerance && group.rssWithinTolerance)
      && maxLargeRssRatio <= operationalThresholds.maxRssToStdoutRatio,
    runs,
  };
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

if (process.argv.includes("--worker")) {
  await runWorker();
} else {
  await runSuite();
}
