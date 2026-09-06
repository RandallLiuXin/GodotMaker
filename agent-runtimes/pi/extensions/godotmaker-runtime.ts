/**
 * GodotMaker's deliberately small Pi bridge.
 *
 * Pi has neither MCP nor a built-in Agent tool.  This extension exposes the
 * two GodotMaker capabilities that require more than Pi's read/bash/edit/write
 * surface: managed Godot runtime inspection and isolated role delegation.
 */
import { spawn, execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const ROLES = new Set([
  "worker", "verifier", "reviewer", "analyst", "asset-producer", "decomposer", "gdd-auditor",
]);
const MAX_PARALLEL = 3;
const DEFAULT_DELEGATE_TIMEOUT_SECONDS = 15 * 60;
const MAX_DELEGATE_TIMEOUT_SECONDS = 60 * 60;
const REQUIRED_RUNTIME_PATHS = [
  ".pi/skills",
  ".pi/agents",
  ".pi/godotmaker.yaml",
  ".pi/references/runtime-mapping.md",
  ".pi/extensions/godotmaker-runtime.ts",
  ".godotmaker/config.yaml",
  "tools",
  "AGENTS.md",
];

type DelegateRequest = { role: string; task: string; isolation?: string; timeoutSeconds?: number };

function projectRoot(cwd: string): string {
  let current = path.resolve(cwd);
  while (true) {
    if (fs.existsSync(path.join(current, "project.godot"))) return current;
    const parent = path.dirname(current);
    if (parent === current) return path.resolve(cwd);
    current = parent;
  }
}

function readGodotPath(root: string): string | null {
  const config = path.join(root, ".pi", "godotmaker.yaml");
  if (!fs.existsSync(config)) return null;
  const match = fs.readFileSync(config, "utf8").match(/^\s*godot_path\s*:\s*["']?([^\n"']+)/m);
  return match?.[1].trim() || null;
}

function piInvocation(args: string[]): { command: string; args: string[] } | null {
  const script = process.argv[1];
  if (script && fs.existsSync(script)) return { command: process.execPath, args: [script, ...args] };
  const packageDir = process.env.PI_PACKAGE_DIR;
  const packageCli = packageDir && path.join(packageDir, "dist", "cli.js");
  if (packageCli && fs.existsSync(packageCli)) return { command: process.execPath, args: [packageCli, ...args] };
  return null;
}

function finalAssistantText(jsonl: string): string {
  let text = "";
  for (const line of jsonl.split(/\r?\n/)) {
    try {
      const event = JSON.parse(line);
      const message = event.message;
      if (event.type === "message_end" && message?.role === "assistant") {
        for (const part of message.content || []) if (part.type === "text") text = part.text;
      }
    } catch { /* Ignore non-JSON diagnostics. */ }
  }
  return text || "(Pi delegate returned no assistant summary)";
}

function createWorktree(root: string, role: string): { cwd: string; branch: string } {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const branch = `godotmaker/pi-${role}-${suffix}`;
  const directory = path.join(root, ".godotmaker", "pi-worktrees", branch.replaceAll("/", "-"));
  fs.mkdirSync(path.dirname(directory), { recursive: true });
  execFileSync("git", ["worktree", "add", "-b", branch, directory, "HEAD"], {
    cwd: root, stdio: "pipe", windowsHide: true,
  });
  return { cwd: directory, branch };
}

function missingRuntimePaths(root: string): string[] {
  return REQUIRED_RUNTIME_PATHS.filter((relative) => !fs.existsSync(path.join(root, relative)));
}

function removeWorktree(root: string, directory: string): void {
  try {
    execFileSync("git", ["worktree", "remove", "--force", directory], {
      cwd: root, stdio: "pipe", windowsHide: true,
    });
  } catch { /* Preserve the original gate failure; cleanup is best effort. */ }
}

async function runDelegate(root: string, request: DelegateRequest, signal?: AbortSignal) {
  if (!ROLES.has(request.role)) throw new Error(`Unsupported GodotMaker Pi role: ${request.role}`);
  const rootMissing = missingRuntimePaths(root);
  if (rootMissing.length) {
    throw new Error(`Pi delegation requires published runtime resources: ${rootMissing.join(", ")}. Re-run publish with --agent pi.`);
  }
  const roleFile = path.join(root, ".pi", "agents", `${request.role}.md`);
  if (!fs.existsSync(roleFile)) throw new Error(`Missing Pi role definition: ${roleFile}. Re-run publish with --agent pi.`);

  let cwd = root;
  let branch: string | undefined;
  if ((request.isolation ?? "worktree") === "worktree") {
    try {
      const isolated = createWorktree(root, request.role);
      cwd = isolated.cwd;
      branch = isolated.branch;
      const isolatedMissing = missingRuntimePaths(cwd);
      if (isolatedMissing.length) {
        removeWorktree(root, cwd);
        throw new Error(
          `Pi worktree is missing published runtime resources: ${isolatedMissing.join(", ")}. `
          + "Commit .pi/, .godotmaker/config.yaml and hooks, tools/, and AGENTS.md before delegating."
        );
      }
    } catch (error) {
      throw new Error(`Pi delegation requires a git worktree for ${request.role}: ${String(error)}`);
    }
  }

  const promptDir = fs.mkdtempSync(path.join(os.tmpdir(), "godotmaker-pi-"));
  const promptFile = path.join(promptDir, "role.md");
  fs.writeFileSync(promptFile, [
    fs.readFileSync(roleFile, "utf8"),
    "\n\n# Pi runtime contract\n",
    "This is an isolated Pi role. Use only Pi built-in tools and project-local GodotMaker resources. ",
    "Do not delegate again. If working in a worktree, commit completed changes before reporting. ",
    "Never write the project memory notebook: root MEMORY.md or any memory/*.md sub-file is owned by the lead session. ",
    "Report execution results and failure evidence instead, and reference large command output by log path rather than pasting it. ",
    "Return an explicit PASS/FAIL summary with commands run and changed files.\n",
  ].join(""), "utf8");

  const invocation = piInvocation([
    "--approve", "--mode", "json", "--no-session", "-p",
    "--append-system-prompt", promptFile,
    `GodotMaker role: ${request.role}\n\nTask:\n${request.task}`,
  ]);
  if (!invocation) {
    fs.rmSync(promptDir, { recursive: true, force: true });
    if (branch) removeWorktree(root, cwd);
    throw new Error("Could not resolve Pi's JavaScript CLI. Run the delegate from an active Pi session with PI_PACKAGE_DIR available.");
  }
  const timeoutSeconds = Math.max(
    1,
    Math.min(request.timeoutSeconds ?? DEFAULT_DELEGATE_TIMEOUT_SECONDS, MAX_DELEGATE_TIMEOUT_SECONDS),
  );
  try {
    const result = await new Promise<{ code: number; stdout: string; stderr: string }>((resolve) => {
      const child = spawn(invocation.command, invocation.args, { cwd, shell: false, windowsHide: true });
      let stdout = "";
      let stderr = "";
      let timedOut = false;
      const timeout = setTimeout(() => {
        timedOut = true;
        child.kill();
      }, timeoutSeconds * 1000);
      const finish = (code: number) => {
        clearTimeout(timeout);
        resolve({
          code,
          stdout,
          stderr: timedOut ? `${stderr}\nTimed out after ${timeoutSeconds}s` : stderr,
        });
      };
      child.stdout.on("data", (chunk) => { stdout += chunk.toString(); });
      child.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
      child.on("close", (code) => finish(code ?? 1));
      child.on("error", (error) => {
        stderr += `\n${error}`;
        finish(1);
      });
      const abort = () => child.kill();
      if (signal?.aborted) abort(); else signal?.addEventListener("abort", abort, { once: true });
    });
    if (result.code !== 0) throw new Error(`Pi ${request.role} exited ${result.code}: ${result.stderr.trim() || finalAssistantText(result.stdout)}`);
    return { role: request.role, cwd, branch, summary: finalAssistantText(result.stdout) };
  } finally {
    fs.rmSync(promptDir, { recursive: true, force: true });
  }
}

function runtimeStatePath(root: string): string {
  return path.join(root, ".godotmaker", "pi-runtime.json");
}

function toolText(text: string, details: Record<string, unknown> = {}) {
  return { content: [{ type: "text" as const, text }], details };
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "godotmaker_delegate",
    label: "GodotMaker Delegate",
    description: "Run GodotMaker worker, verifier, reviewer, or decomposition roles in isolated Pi processes. Worker-like requests default to separate git worktrees; merge their returned branches only after review.",
    parameters: Type.Object({
      role: Type.Optional(Type.String()),
      task: Type.Optional(Type.String()),
      isolation: Type.Optional(Type.Union([Type.Literal("worktree"), Type.Literal("shared")])),
      timeoutSeconds: Type.Optional(Type.Number({ minimum: 1, maximum: MAX_DELEGATE_TIMEOUT_SECONDS })),
      requests: Type.Optional(Type.Array(Type.Object({
        role: Type.String(), task: Type.String(),
        isolation: Type.Optional(Type.Union([Type.Literal("worktree"), Type.Literal("shared")])),
        timeoutSeconds: Type.Optional(Type.Number({ minimum: 1, maximum: MAX_DELEGATE_TIMEOUT_SECONDS })),
      }))),
    }),
    async execute(_id, params, signal, _update, ctx) {
      const root = projectRoot(ctx.cwd);
      const requests: DelegateRequest[] = params.requests ?? (params.role && params.task
        ? [{ role: params.role, task: params.task, isolation: params.isolation, timeoutSeconds: params.timeoutSeconds }] : []);
      if (!requests.length || requests.length > MAX_PARALLEL) {
        return { ...toolText(`Provide one role/task or 1-${MAX_PARALLEL} requests.`), isError: true };
      }
      if (requests.length > 1 && requests.some((request) => (request.isolation ?? "worktree") !== "worktree")) {
        return { ...toolText("Parallel Pi delegation requires worktree isolation."), isError: true };
      }
      try {
        const results = await Promise.all(requests.map((request) => runDelegate(root, request, signal)));
        const summary = results.map((result) => [
          `${result.role}: ${result.summary}`,
          result.branch ? `Merge candidate: ${result.branch} (${result.cwd})` : "Shared working tree",
        ].join("\n")).join("\n\n");
        return toolText(summary, { results });
      } catch (error) {
        return { ...toolText(`Pi delegation failed closed: ${String(error)}`), isError: true };
      }
    },
  });

  pi.registerTool({
    name: "godotmaker_runtime",
    label: "GodotMaker Runtime",
    description: "Narrow replacement for the Godot MCP debug loop: inspect a project, run a bounded headless command, start a project with captured logs, read debug output, or stop that managed process.",
    parameters: Type.Object({
      action: Type.Union([Type.Literal("project_info"), Type.Literal("headless"), Type.Literal("start"), Type.Literal("debug_output"), Type.Literal("stop")]),
      scene: Type.Optional(Type.String()),
      args: Type.Optional(Type.Array(Type.String())),
    }),
    async execute(_id, params, signal, _update, ctx) {
      const root = projectRoot(ctx.cwd);
      const statePath = runtimeStatePath(root);
      if (params.action === "project_info") {
        const scenes = fs.readdirSync(root, { recursive: true }).filter((item) => String(item).endsWith(".tscn")).length;
        const scripts = fs.readdirSync(root, { recursive: true }).filter((item) => String(item).endsWith(".gd")).length;
        return toolText(`Project: ${root}\nScenes: ${scenes}\nScripts: ${scripts}`, { root, scenes, scripts });
      }
      if (params.action === "debug_output") {
        if (!fs.existsSync(statePath)) return { ...toolText("No Pi-managed Godot runtime is active."), isError: true };
        const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
        const output = fs.existsSync(state.log) ? fs.readFileSync(state.log, "utf8") : "(log file not created yet)";
        return toolText(output.slice(-50000), state);
      }
      if (params.action === "stop") {
        if (!fs.existsSync(statePath)) return { ...toolText("No Pi-managed Godot runtime is active."), isError: true };
        const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
        try { process.kill(state.pid); } catch { /* It may already be gone. */ }
        fs.rmSync(statePath, { force: true });
        return toolText(`Stopped Pi-managed Godot process ${state.pid}.`, state);
      }

      const godot = readGodotPath(root);
      if (!godot) return { ...toolText("Godot unavailable: .pi/godotmaker.yaml has no godot_path. Re-run publish with --agent pi."), isError: true };
      const args = params.action === "headless"
        ? ["--headless", "--path", root, ...(params.args ?? []), "--quit"]
        : ["--path", root, ...(params.scene ? [params.scene] : []), ...(params.args ?? [])];
      if (params.action === "headless") {
        return await new Promise((resolve) => {
          const child = spawn(godot, args, { cwd: root, shell: false, windowsHide: true });
          let output = "";
          child.stdout.on("data", (chunk) => { output += chunk.toString(); });
          child.stderr.on("data", (chunk) => { output += chunk.toString(); });
          child.on("close", (code) => resolve({ ...toolText(output || "(no Godot output)", { code }), isError: code !== 0 }));
          if (signal) signal.addEventListener("abort", () => child.kill(), { once: true });
        });
      }
      fs.mkdirSync(path.dirname(statePath), { recursive: true });
      const log = path.join(root, ".godotmaker", "pi-runtime.log");
      const logFd = fs.openSync(log, "w");
      return await new Promise((resolve) => {
        const child = spawn(godot, args, { cwd: root, shell: false, windowsHide: true, detached: true, stdio: ["ignore", logFd, logFd] });
        child.once("error", (error) => {
          fs.closeSync(logFd);
          resolve({ ...toolText(`Godot start failed: ${error.message}`), isError: true });
        });
        child.once("spawn", () => {
          fs.closeSync(logFd);
          child.unref();
          fs.writeFileSync(statePath, JSON.stringify({ pid: child.pid, log, started_at: new Date().toISOString() }) + "\n");
          resolve(toolText(`Started Pi-managed Godot process ${child.pid}. Use godotmaker_runtime debug_output or stop.`, { pid: child.pid, log }));
        });
      });
    },
  });
}
