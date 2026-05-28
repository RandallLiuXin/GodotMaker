# Verifier Dispatch Protocol

When dispatching a verifier, fill in this EXACT template.

**Agent definition:** `.claude/agents/verifier.md` — system prompt loaded automatically via `subagent_type: "verifier"`.

## Agent Call

```
Agent({
  subagent_type: "verifier",
  description: "Verifier: validate {task_name}",
  model: "{verifier_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{verifier brief below}"
})
```

## Verifier Brief Template

```
## Verify: {what is being checked}                      [REQUIRED]

### Project Path                                         [REQUIRED]
{Absolute path to the Godot project}

### Godot Path                                           [REQUIRED]
{Absolute path read from .claude/godotmaker.yaml}

### Commands to Run (run ALL, do not skip)               [REQUIRED]
1. Build: "<godot_path>" --headless --quit 2>&1
2. Unit tests: "<godot_path>" --headless --path . -s res://addons/gdUnit4/bin/GdUnitCmdTool.gd --add res://{test_file} --ignoreHeadlessMode
3. {additional commands}

### Success Criteria                                     [REQUIRED]
- [ ] Build: zero errors
- [ ] Unit tests: all pass
- [ ] {additional specific criteria}

### Visual Verification                                  [REQUIRED when requested]
- Scene/reference/capture paths: {visual_checks scene, reference, captures[], and latest vqa_calls[].files from evaluation.json}
- Visual-qa context: {latest vqa_calls[].context or scene Acceptance criteria}
- Asset contract rows: {relevant SCENES.md Asset bindings and ASSETS.md Visual Asset Contract rows}
- VQA log: {visual_checks.<scene>.vqa_log or latest vqa_calls[].log}
- Worker self-check result: {visual-qa verdict and output from the worker report, if present}
- Required result: {pass, warning, or explicit non-blocking notes}

### Negative Tests                                       [OPTIONAL]
- [ ] {input that should fail and how}

### Focus Areas                                          [OPTIONAL]
{Specific files, systems, or interactions to stress-test}

```

For visual gaps, include a command that runs visual-qa on evaluator captures.
If a fresh capture, VQA log, or helper script is needed, write it only under
`reports/verifier-temp/`.

## Spot-Check Protocol

After EVERY verifier returns:
1. Read the verifier's full report
2. Pick 2-3 commands from the "Command run" sections
3. Re-run them yourself in Bash
4. Compare your output to the verifier's reported output
5. If outputs match: accept the report
6. If outputs differ: reject the report, note the discrepancy, re-dispatch verifier
