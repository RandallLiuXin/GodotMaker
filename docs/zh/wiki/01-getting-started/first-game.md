# 你的第一款游戏

这篇教程带你从一个游戏想法，走到一个可以运行的 Godot 游戏。正常路径使用 `godotmaker-cli`：它会协助把想法整理成 GDD，然后自动驱动工作流，直到当前设计范围完成。

**大概要花多久：** 一个小型游戏通常需要 **3-5 小时 Agent 运行时间**。你不需要盯着每一步。带着想法来，启动工作流，结束后验收可运行结果。

高级用户仍然可以直接运行底层 `/gm-*` 命令。本页聚焦 CLI 路径。

## 开始前

先完成[安装](installation.md)。你需要：

- 已安装 `godotmaker-cli`
- Godot、Git、Node.js、Python 可用
- 已选择的 Agent runtime 已安装并登录
- 只有当配置选择 API provider 时，才需要可选 API key

## 创建游戏文件夹

```bash
mkdir my-first-game
cd my-first-game
```

你不需要提前写好完整 GDD。带着一个粗略游戏想法、几条笔记、参考图或约束条件来就行。GodotMaker 会在实现前协助把它整理成 `GDD.md`。

第一次可以简单到这样：

```text
做一个 2D 街机游戏，玩家控制一只小鸟穿过管道之间的空隙。
画面要明亮、简单、清楚，适合全年龄。
```

之后你可以继续把设计写得更详细。GodotMaker 会把整理后的 GDD 当作本轮运行的设计契约。

## 运行 GodotMaker

在游戏文件夹中运行：

```bash
godotmaker-cli --agent claude-code
```

同一个项目也可以使用 Codex：

```bash
godotmaker-cli --agent codex
```

CLI 会在需要时把框架发布进项目，协助把想法整理成 GDD，然后驱动规划、构建、验证、评估和修复循环，直到当前设计范围完成。

第一次发布时，CLI 会创建 `.godotmaker/config.yaml`。继续运行前你可以打开它检查或修改 `agent`、角色模型、VQA 模型和素材生成模型。

## 运行中会发生什么

GodotMaker 会：

1. 如果文件夹里还没有 Godot 项目，先创建脚手架。
2. 协助把你的游戏想法整理成 `GDD.md` 和当前 tag 的规划文档。
3. 生成或检查素材。
4. 派发实现 Agent。
5. 运行 gdUnit4 单元测试和机械验证。
6. 创建像玩家一样操作游戏的端到端测试。
7. 运行游戏、截图，并对照设计检查结果。
8. 把缺失玩法、UI 重叠、视觉不匹配或运行时失败送回修复循环。
9. 当前范围通过后 finalize 这个 tag。

终端输出会很多，这是正常的。重要产物都会写入游戏文件夹。

## 磁盘上会留下什么

成功运行后，你通常会看到：

- `project.godot`
- `src/` 游戏代码
- `scenes/` Godot 场景
- `assets/` 生成或提供的美术资源
- `test/` gdUnit4 单元测试
- `e2e/` 玩法测试和截图
- `GDD.md`、`PLAN.md`、`STRUCTURE.md`、`SCENES.md`、`ASSETS.md`
- `.godotmaker/` 运行状态和报告
- `docs/tags/<Tag>/` 归档后的规划文档

## 验收结果

用 Godot 打开项目：

```bash
godot --editor --path .
```

或者直接运行：

```bash
godot --path .
```

如果结果需要设计调整，修改 `GDD.md` 或补充新想法，然后再次运行 `godotmaker-cli`。下一轮会基于更新后的设计规划，并从现有项目状态继续。

## 手动角色命令

CLI 会替你驱动这些角色：

```text
gm-scaffold -> gm-gdd -> gm-asset -> gm-build -> gm-verify
-> gm-evaluate -> gm-fixgap loop -> gm-accept -> gm-finalize
```

高级用户可以用 `/gm-*` 运行。手动模式适合调试、框架开发或审查中间阶段，但已经不是推荐的新手首跑路径。

想了解项目文件夹里每个东西的含义，见[项目结构](project-layout.md)。
