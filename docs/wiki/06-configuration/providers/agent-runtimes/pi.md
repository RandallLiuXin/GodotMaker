# Pi runtime

GodotMaker supports Pi `0.84.1` as a project-local runtime.

1. Install `@earendil-works/pi-coding-agent` and confirm `pi --version`.
2. Publish the project:

```bash
python tools/publish.py --agent pi /path/to/my-game
```

3. Start Pi in the project with `pi --approve`, then invoke a role with Pi's skill syntax, for example `/skill:gm-scaffold` or `/skill:gm-build`.

Pi projects use `.pi/skills`, `.pi/agents`, `.pi/templates`, `.pi/references`, and `.pi/godotmaker.yaml`. `--approve` trusts project resources for that run; it is not a sandbox or permission bypass.

Pi does not ship MCP or a native `Agent` tool. GodotMaker publishes a narrow project extension at `.pi/extensions/godotmaker-runtime.ts`. It provides the Godot runtime debug loop and runs worker/verifier/reviewer/decomposer roles as actual isolated Pi child processes. Worker-like requests receive git worktrees and return merge-candidate branches. If the extension, trust, Git HEAD, or configured Godot binary is unavailable, the dependent role stops with a setup error instead of silently continuing without verification.

Pi does not support GodotMaker runtime-native image generation or VQA. Configure `codex` or an API-backed selector for `asset_image_model` and `vqa_model`.

## Reproducible local smoke record

Validated on Windows with Pi `0.84.1`:

```powershell
pi --version
python tools/publish.py --agent pi --force --no-config-review <project>
pi --approve
# then type: /skill:gm-scaffold
```

The publish command is idempotent. A real model run remains opt-in: the smoke above verifies Pi installation, trusted project discovery, and the published skill/extension layout without sending a task to a model provider.
