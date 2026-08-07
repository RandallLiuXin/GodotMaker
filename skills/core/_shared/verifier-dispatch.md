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

### Backend Selection                                    [REQUIRED]
- Language backend: {resolved language_backend from .godotmaker/config.yaml}
- Unit-test backend: {resolved unit_test_backend from .godotmaker/config.yaml}
- Godot C# project: {godot_csharp_project for C#, or N/A for GDScript}
- .NET target: {dotnet_target for C#, or N/A for GDScript}

### Commands to Run (run ALL, do not skip)               [REQUIRED]
1. Build: {exact backend-selected build command(s)}
2. Unit tests: {exact backend-selected unit-test command}
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
Resolve the commands from `.godotmaker/config.yaml` before dispatch:

- GDScript/gdUnit: Godot headless build plus
  `"<godot_path>" --headless --quit`, then
  `"<godot_path>" --headless --path . -s res://addons/gdUnit4/bin/GdUnitCmdTool.gd`
  `--add res://{test_file} --ignoreHeadlessMode`.
- C#/.NET: `dotnet build <dotnet_target>`, separately
  `dotnet build <godot_csharp_project>` when the game project is not already
  covered by that target, then Godot headless build and
  `dotnet test <dotnet_target> --no-build --no-restore --logger trx`.

Never leave both alternatives in a verifier brief. Fill in only the selected
backend's exact commands so every listed command can be run and spot-checked.

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
