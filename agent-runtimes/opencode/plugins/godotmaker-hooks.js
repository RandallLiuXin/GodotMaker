import { spawnSync } from "node:child_process"
import { existsSync } from "node:fs"
import path from "node:path"

const PYTHON = process.env.GODOTMAKER_HOOK_PYTHON || "python"

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {}
}

function hookPath(projectRoot, script) {
  return path.join(projectRoot, ".godotmaker", "hooks", script)
}

function parseJson(text) {
  const trimmed = (text || "").trim()
  if (!trimmed) return null
  try {
    return JSON.parse(trimmed)
  } catch {
    return null
  }
}

function blockReason(parsed) {
  if (!parsed) return null
  if (parsed.decision === "block") return parsed.reason || "GodotMaker hook blocked this action."
  const specific = asObject(parsed.hookSpecificOutput)
  if (specific.permissionDecision === "deny") {
    return specific.permissionDecisionReason || "GodotMaker hook denied this action."
  }
  return null
}

function runHook(projectRoot, script, payload, options = {}) {
  const scriptPath = hookPath(projectRoot, script)
  if (!existsSync(scriptPath)) return null

  const result = spawnSync(PYTHON, [scriptPath], {
    cwd: projectRoot,
    input: JSON.stringify(payload),
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONDONTWRITEBYTECODE: "1",
    },
    maxBuffer: 1024 * 1024 * 4,
  })

  const parsed = parseJson(result.stdout)
  const reason = blockReason(parsed)
  if (reason) {
    if (options.blockDecision === "return") return parsed
    throw new Error(reason)
  }
  if (result.error) {
    throw new Error(`GodotMaker hook ${script} failed: ${result.error.message}`)
  }
  if (result.status !== 0 && options.failOnNonZero !== false) {
    const stderr = (result.stderr || "").trim()
    throw new Error(`GodotMaker hook ${script} exited ${result.status}${stderr ? `: ${stderr}` : ""}`)
  }
  return parsed
}

function runStopHook(projectRoot, script, payload) {
  const parsed = runHook(projectRoot, script, payload, {
    blockDecision: "return",
    failOnNonZero: false,
  })
  const reason = blockReason(parsed)
  return reason ? { script, reason } : null
}

function stopNoticeText(blocks) {
  const details = blocks.map((block) => `- ${block.script}: ${block.reason}`).join("\n\n")
  return [
    "GodotMaker Stop hooks blocked this stage from finishing.",
    "",
    details,
    "",
    "Address the hook feedback, then finish the active GodotMaker stage again.",
  ].join("\n")
}

async function sendStopNotice(client, sessionID, blocks) {
  if (!blocks.length || !sessionID) return
  const text = stopNoticeText(blocks)
  try {
    await client?.session?.prompt?.({
      path: { id: sessionID },
      body: {
        parts: [{ type: "text", text }],
      },
    })
    return
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    console.warn(`[GodotMaker] failed to send Stop hook prompt: ${message}`)
  }
  try {
    await client?.tui?.showToast?.({
      body: {
        title: "GodotMaker Stop hook blocked",
        message: text.slice(0, 1800),
        variant: "warning",
      },
    })
  } catch {
    // Toast is best-effort. The log line above is the final fallback.
  }
}

function claudeToolName(tool) {
  const normalized = String(tool || "").toLowerCase()
  if (normalized === "read") return "Read"
  if (normalized === "write") return "Write"
  if (normalized === "edit") return "Edit"
  if (normalized === "task") return "Agent"
  return tool || ""
}

function claudeToolInput(args) {
  const input = { ...asObject(args) }
  if (input.filePath && !input.file_path) input.file_path = input.filePath
  if (input.oldString && !input.old_string) input.old_string = input.oldString
  if (input.newString && !input.new_string) input.new_string = input.newString
  if (input.replaceAll !== undefined && input.replace_all === undefined) {
    input.replace_all = input.replaceAll
  }
  return input
}

function basePayload(eventName, input, args) {
  return {
    hook_event_name: eventName,
    tool_name: claudeToolName(input.tool),
    tool_input: claudeToolInput(args),
    tool_use_id: input.callID || "",
    session_id: input.sessionID || "",
    agent_id: "",
  }
}

function taskPayload(input, args) {
  const payload = basePayload("PreToolUse", input, args)
  const toolInput = asObject(payload.tool_input)
  payload.agent_type = toolInput.subagent_type || ""
  return payload
}

function runPreToolHooks(projectRoot, input, output) {
  const tool = String(input.tool || "").toLowerCase()
  const args = asObject(output.args)

  if (tool === "write" || tool === "edit") {
    const payload = basePayload("PreToolUse", input, args)
    runHook(projectRoot, "check_file_permissions.py", payload)
    runHook(projectRoot, "stage_reminder.py", payload)
    return
  }

  if (tool === "read") {
    runHook(projectRoot, "check_asset_access.py", basePayload("PreToolUse", input, args))
    return
  }

  if (tool === "task") {
    const payload = taskPayload(input, args)
    runHook(projectRoot, "check_stage_prerequisites.py", payload)
    runHook(projectRoot, "log_agent_tool.py", payload, { failOnNonZero: false })
    runHook(projectRoot, "log_subagent.py", {
      ...payload,
      hook_event_name: "SubagentStart",
      agent_id: input.callID || "",
      agent_type: payload.agent_type || "",
    }, { failOnNonZero: false })
  }
}

function runPostToolHooks(projectRoot, input, output) {
  const tool = String(input.tool || "").toLowerCase()
  if (tool !== "task") return

  const args = asObject(input.args)
  const response = {
    title: output?.title || "",
    output: output?.output || "",
    metadata: output?.metadata || {},
  }
  const payload = {
    ...taskPayload(input, args),
    hook_event_name: "PostToolUse",
    tool_response: response,
  }
  runHook(projectRoot, "log_agent_tool.py", payload, { failOnNonZero: false })
  runHook(projectRoot, "on_subagent_stop.py", {
    ...payload,
    hook_event_name: "SubagentStop",
    agent_id: input.callID || "",
    agent_type: args.subagent_type || "",
    last_assistant_message: response.output || "",
  })
}

async function runSessionEventHooks(projectRoot, client, event, rootSessions) {
  const type = event?.type || ""
  if (type === "session.created") {
    const info = asObject(event?.properties?.info)
    const sessionID = info.id || event?.properties?.sessionID || ""
    if (info.parentID) return
    if (sessionID) rootSessions.add(sessionID)
    runHook(projectRoot, "session_start.py", {
      hook_event_name: "SessionStart",
      session_id: sessionID,
    }, { failOnNonZero: false })
    return
  }

  const status = event?.properties?.status?.type
  if (type === "session.idle" || (type === "session.status" && status === "idle")) {
    const sessionID = event?.properties?.sessionID || ""
    if (!rootSessions.has(sessionID)) return
    const payload = {
      hook_event_name: "Stop",
      session_id: sessionID,
      agent_id: "",
    }
    const blocks = [
      runStopHook(projectRoot, "check_completion.py", payload),
      runStopHook(projectRoot, "check_clean_workspace.py", payload),
    ].filter(Boolean)
    await sendStopNotice(client, sessionID, blocks)
  }
}

export const GodotMakerHooks = async (ctx) => {
  const projectRoot = ctx.directory
  const client = ctx.client
  const rootSessions = new Set()
  return {
    event: async (input) => {
      await runSessionEventHooks(projectRoot, client, input.event, rootSessions)
    },
    "tool.execute.before": async (input, output) => {
      runPreToolHooks(projectRoot, input, output)
    },
    "tool.execute.after": async (input, output) => {
      runPostToolHooks(projectRoot, input, output)
    },
    "experimental.session.compacting": async (input) => {
      runHook(projectRoot, "log_compaction.py", {
        hook_event_name: "PreCompact",
        session_id: input.sessionID || "",
      }, { failOnNonZero: false })
    },
  }
}
