# Pi runtime

GodotMaker 支持 Pi `0.84.1` 项目本地 runtime。

1. 安装 `@earendil-works/pi-coding-agent`，并确认 `pi --version`。
2. 发布项目：

```bash
python tools/publish.py --agent pi /path/to/my-game
```

3. 在项目目录运行 `pi --approve`，再使用 Pi 的技能语法调用角色，例如 `/skill:gm-scaffold`。

Pi 使用 `.pi/skills`、`.pi/agents`、`.pi/templates`、`.pi/references` 和 `.pi/godotmaker.yaml`。`--approve` 仅信任本次运行的项目资源，并不绕过 sandbox 或系统权限。

Pi 没有内建 MCP 或 `Agent` 工具。GodotMaker 发布 `.pi/extensions/godotmaker-runtime.ts`，用它提供 Godot 调试循环，以及真实隔离的 worker/verifier/reviewer/decomposer Pi 子进程。worker 默认使用 Git worktree，并返回待合并分支。委派前必须提交 `.pi/`、`.godotmaker/config.yaml` 与 hooks、`tools/`、`AGENTS.md`；扩展会检查每个 worktree 是否携带这些资源，缺失时 fail closed。缺扩展、信任、Git HEAD 或 Godot 可执行文件时，依赖阶段也会明确停止。Pi 不提供角色级硬文件权限；reviewer/verifier 的禁止修改是角色约束，不是 sandbox。Pi 子进程还会继承父环境和祖先 `AGENTS.md`，请在干净的项目环境中运行，避免继承 workspace 凭据。

Pi 不支持 GodotMaker runtime-native 生图或 VQA；请把 `asset_image_model` 和 `vqa_model` 配置为 `codex` 或 API 后端。
