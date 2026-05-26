# 开发环境搭建

本页面帮你从零克隆仓库到跑通测试套件，并介绍你在开发 GodotMaker 过程中会反复用到的操作流程。

## 获取源码

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker
pip install -r tools/requirements.txt
```

你还需要将 **Godot 4.5 或更高版本**加入 `PATH`。开始之前先运行以下命令确认环境就绪：

```bash
python tools/check_env.py
```

## 仓库结构速览

```
GodotMaker/
├── hooks/          8 个 hook 脚本，强制执行流水线规则 + hooks/metrics/ 子系统
├── skills/
│   ├── core/       角色技能 + 辅助技能 + _shared/ 跨技能共享参考文档
│   └── reviewer/   8 个领域审查技能 (physics, animation, ui, ...)
├── tools/          CLI 工具：publish.py, check_env.py, check_project.py, asset_gen.py, migrate.py
├── config/         config.yaml.default, stage_schemas.json, addon_versions.json
├── agent-runtimes/ runner 专属 reference、template 和 hook config
├── templates/      部署到生成的游戏项目中的文档模板
├── tests/          ~320 个 hook 和工具的单元测试
├── docs/           Wiki、贡献指南、版本参考、hooks 参考
├── shell/          publish.sh / publish.ps1, report.sh / report.bat
├── migrations/     跨版本迁移脚本
├── VERSION         语义版本号 (MAJOR.MINOR.PATCH)——唯一真实来源
└── CHANGELOG.md    每次发版的变更说明
```

一句话概括每个目录的职责：`hooks/` 是规则执行层；`skills/` 是 AI 指令层；`tools/` 包含贡献者和用户直接运行的 Python 脚本；`config/` 同时驱动前两者；`tests/` 保证一切都正确运转。

## 常见开发流程

### 运行测试套件

```bash
python -m pytest tests/ -x -q
```

`-x` 参数在第一次失败时立即停止。去掉它可以一次看到所有失败。当前测试套件约有 320 个测试，覆盖全部 8 个 hook、publish、check_project、迁移脚本以及端到端流水线。

运行单个文件：

```bash
python -m pytest tests/hooks/test_check_worker_report.py -x -q
```

按测试名称运行：

```bash
python -m pytest tests/ -k "test_blocks_missing_sections" -x -q
```

### 在真实项目中验证改动

如果你想端到端地验证某项改动：

1. 找一个 Godot 项目目录（或新建一个临时目录）。
2. 将当前工作树推送进去：

   ```bash
   python tools/publish.py /path/to/my-test-game
   ```

3. 在 Claude Code 中打开该项目目录，执行相关的 `/gm-*` 命令。
4. 检查输出（`.godotmaker/`、`PLAN.md`、所选 agent 技能目录下的技能文件等），确认行为符合预期。

对同一版本重复发布始终被允许，因此在开发阶段无需每次都提升版本号。

### 代码风格

仓库没有强制执行代码格式化工具。请保持与你正在编辑的文件一致的风格：Python 中使用 4 空格缩进、字符串用双引号、顶层定义之间空一行。

## 分支策略

`main` 是主干分支，所有 Pull Request 都合并到这里。保持改动精简，尽早开 PR，不要在本地积累大型分支。每个 PR 都必须在 `docs/update/next.md` 的适当分类下至少添加一条记录。完整工作流程见 [发版流程](release-process.md)。
