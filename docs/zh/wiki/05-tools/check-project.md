# 检查项目

`check_project.py` 检查已生成的游戏项目，查找缺失文件、结构损坏及其他不一致问题。构建结果异常时，或在封口 tag 之前，都可以运行它。

```bash
python tools/check_project.py /path/to/my-game
```

不加任何标志时，所有检查都会运行。也可以只运行特定类别：

```bash
python tools/check_project.py /path/to/my-game --ecs --tests
python tools/check_project.py /path/to/my-game --all
```

## 类别标志

| 标志 | 检查内容 |
|------|----------|
| `--build` | `project.godot` 存在、必需插件已安装、git `HEAD` 可解析，且 Godot 无头解析没有阻断性诊断 |
| `--ecs` | 所选 ECS 后端可检查；GDScript/gecs 项目需要 Component 和 System 文件 |
| `--tests` | 所选测试后端可检查；GDScript 项目使用 gdUnit4 覆盖率，C#/.NET 项目使用配置的项目相对 .NET 测试目标 |
| `--e2e` | godot-e2e 插件已启用；`e2e/` 中有真实测试函数，而不是占位文件 |
| `--plan` | `PLAN.md` 和 `STRUCTURE.md` 存在，且包含正确章节 |
| `--mcp` | `godot-mcp` 服务已注册到 `.mcp.json` |
| `--all` | 执行以上全部检查 |

## 能发现哪些问题

**构建就绪** — 确认 `project.godot` 存在且结构有效，必需插件目录是正确的 addon-only 形态，git `HEAD` 可以解析，并且 `<godot_path> --headless --quit` 没有阻断性诊断。C# 后端还要求 `<godot_path> --version` 明确报告 Mono/.NET 构建；标准非 .NET Godot 可执行文件不会被接受。Godot shutdown notes 会单独报告；其他 Godot diagnostics 会让检查失败。

**ECS 配置** — 确认所选后端具有可检查的 ECS 形状。对 GDScript/gecs 项目，这意味着 `addons/gecs/` 已安装，并且游戏代码中存在 `extend Component` 和 `extend System` 文件。对 C#/.NET 后端，C# ECS 静态验证目前是 N/A，直到实现 C# 扫描器；不要把 GDScript 扫描结果当作 C# 项目的权威结论。

**单元测试覆盖率** — 使用配置的 unit test backend。GDScript 项目检查每个 System 是否有对应的 gdUnit 测试文件；C#/.NET 后端使用 `unit_test_backend`、可选项目相对 `dotnet_target` 和标准 `dotnet test` 结果，而不是 gdUnit4 XML。

**C#/.NET 后端** — 通过 `.godotmaker/config.yaml` 中的 `language_backend`、`unit_test_backend`、可选项目相对 `dotnet_target` 和可选项目相对 `godot_csharp_project` 识别已有 Godot .NET 项目。当前版本的 C# ECS 静态验证是 N/A；build 和 unit verification 是 C# 项目的权威检查。

**端到端测试** — 检查 `e2e/conftest.py` 是否存在，`e2e/` 目录下是否有 `test_*.py` 文件，以及这些文件中是否包含真实的 `def test_` 函数，而不是空的桩代码。文件过短或含有 "todo" / "stub" 关键字的占位文件会触发警告。

**规划文档** — 确认 `PLAN.md` 存在且包含任务状态标记（`pending`、`in_progress`、`completed` 等），`STRUCTURE.md` 包含 Component Registry 和 System Schedule。这两份文档是 `/gm-build` 和 `/gm-fixgap` 的执行依据。

**MCP 注册** — 检查 `.mcp.json` 中是否包含 `"godot"` 服务条目，这是由 `publish.py` 创建的。没有它，Claude Code 就无法向 Godot 编辑器发送命令。

## 何时运行

- 构建出现报错或意外行为之后。
- 运行 `/gm-finalize` 之前，确认项目已经完整。
- 搁置较久后重新打开项目时，了解当前状态。
- 手动添加或重命名文件之后，确认没有引入问题。

## 读懂输出结果

```text
[PASS] project.godot exists
[FAIL] No System files found (files extending System)
[WARN] MEMORY.md not found (optional but recommended)
```

失败项会在末尾汇总展示：

```text
==================================================
Total: 18 checks
  PASS: 15
  FAIL: 2
  WARN: 1

Result: CHECKS FAILED
Failed checks:
  - No System files found (files extending System)
  - Systems without test files: movement_system, spawn_system
```

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 所有检查通过 |
| 1 | 一项或多项检查失败 |
| 2 | 项目目录不存在 |
