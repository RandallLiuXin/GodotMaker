import * as fs from "node:fs";
import * as path from "node:path";


export const ROLE_POLICIES = Object.freeze({
  "analyst": Object.freeze({ modelKey: "analyst_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
  "asset-producer": Object.freeze({ modelKey: "asset_producer_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
  "decomposer": Object.freeze({ modelKey: "decomposer_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
  "gdd-auditor": Object.freeze({ modelKey: "auditor_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
  "reviewer": Object.freeze({ modelKey: "reviewer_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
  "verifier": Object.freeze({ modelKey: "verifier_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
  "worker": Object.freeze({ modelKey: "worker_model", defaultModel: "inherit", defaultIsolation: "worktree" }),
});

const INHERITED_MODEL_ALIASES = new Set(["inherit", "haiku", "sonnet", "opus"]);


function stripYamlInlineComment(value) {
  let quote = null;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (quote === '"' && character === "\\") {
      index += 1;
      continue;
    }
    if (character === "'" || character === '"') {
      if (quote === character) quote = null;
      else if (quote === null) quote = character;
      continue;
    }
    if (quote === null && character === "#" && (index === 0 || /\s/.test(value[index - 1]))) {
      return value.slice(0, index).trimEnd();
    }
  }
  return value;
}


function readYamlScalar(configPath, key) {
  if (!fs.existsSync(configPath)) return null;
  for (const line of fs.readFileSync(configPath, "utf8").split(/\r?\n/)) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#") || !stripped.includes(":")) continue;
    const separator = stripped.indexOf(":");
    if (stripped.slice(0, separator).trim() !== key) continue;
    const value = stripYamlInlineComment(stripped.slice(separator + 1).trim())
      .trim()
      .replace(/^(?:"([\s\S]*)"|'([\s\S]*)')$/, "$1$2");
    return value || null;
  }
  return null;
}


function normalizedModel(value, source) {
  const model = value.trim();
  if (!model) throw new Error(`${source} must be a non-empty model name`);
  return INHERITED_MODEL_ALIASES.has(model.toLowerCase()) ? null : model;
}


export function rolePolicy(role) {
  const policy = ROLE_POLICIES[role];
  if (!policy) throw new Error(`Unsupported GodotMaker Pi role: ${role}`);
  return policy;
}


export function resolveDelegateModel(root, role, explicitModel) {
  const policy = rolePolicy(role);
  if (explicitModel !== undefined) {
    return normalizedModel(explicitModel, "Pi dispatch model override");
  }

  const configPath = path.join(root, ".godotmaker", "config.yaml");
  const configured = readYamlScalar(configPath, policy.modelKey);
  return normalizedModel(configured ?? policy.defaultModel, `${policy.modelKey} role policy`);
}


export function buildDelegateArgs(role, task, promptFile, model) {
  const args = ["--approve", "--mode", "json", "--no-session"];
  if (model) args.push("--model", model);
  args.push(
    "-p",
    "--append-system-prompt", promptFile,
    `GodotMaker role: ${role}\n\nTask:\n${task}`,
  );
  return args;
}
