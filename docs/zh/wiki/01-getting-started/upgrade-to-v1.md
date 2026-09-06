# 将 0.x 工作区升级到 1.0

GodotMaker 1.0 是一次不兼容的框架更新。现有 0.x 工作区不能通过旧迁移脚本
增量升级到 1.0，但可以继续使用原目录：`publish.py --force` 会干净地重新初始化
框架管理层，同时保留游戏本体和持久化的项目历史。

这条命令并不了解某个游戏的设计意图，也不会转换 `GDD.md`、`PLAN.md` 或
`ASSETS.md`，不会修复 Godot 场景，更不能判断旧生成素材是否满足 1.0 的运行时
契约。因此，恢复流水线前应由本地 coding agent 检查这些项目专属内容。

## 干净重新初始化会做什么

请从 GodotMaker `v1.0.0` checkout 中运行：

```bash
python tools/publish.py --agent <current-agent> --force "<target>"
```

除非你明确要另做一次 runtime 迁移，否则 `<current-agent>` 必须保持工作区原本的
`claude-code`、`codex`、`opencode` 或 `pi` 选择。

该命令会：

- 重新部署所选 runtime 的 Skills、agents、templates、hooks 或 adapter、共享资产
  runtime 和工具；
- 清除不兼容的当前流水线状态和报告；
- 不执行旧增量迁移，直接为 1.0 重建 migration baseline；
- 更新 `.gitignore`、`.gitattributes`，并为 Claude Code 目标更新
  `.worktreeinclude`；
- 保留根目录 Agent 指令、所选 runner 的 `godotmaker.yaml`、
  `.godotmaker/config.yaml`、游戏代码、场景、素材、规划文档，以及历史 evaluation、
  gap 和 asset-generation 证据。

Skills、agents、config、templates、hooks、plugins、extensions、runtime references、
asset runtime 或 `tools/` 等受管理路径内的自定义文件不会被保留。其中一些路径通常
被 Git 忽略，因此干净工作区本身不能证明这些文件可以恢复。

对于 Claude Code、Codex 和 OpenCode，publish 还会通过 Agent CLI 更新 `godot` MCP
注册。这份状态可能位于仓库之外，目标目录的 Git 历史无法恢复它。

精确的管理与保留路径见[版本管理](../../versioning.md)，命令选项见
[Publish 工具](../05-tools/publish.md)。

## 需要审查的项目契约

0.8.2 到 1.0 最大的项目文档变化是资产交接方式：

- `ASSETS.md` 现在是 worker 唯一可见的运行时资产目录。
- 每个逻辑运行时输出占一行，并包含最终 Godot `Runtime Type` 和可加载的
  `res://` `Runtime Path`。
- 角色动画由 `character-bundle` 产出 `SpriteFrames`。角色基准图与动作源图属于
  生产证据，不再是单独交给 worker 的运行时行。
- `ui-kit`、`card-kit`、`compact-prop-pack` 等多输出 family 会原子注册所有声明的
  运行时输出。
- 仅作参考的素材在 `source_ready` 结束，不能作为可加载资源交给 worker。
- 生成素材通常位于 `assets/generated/<asset-family>/<asset-id>/`，且只有通过对应
  Asset Skill 验证后才能标记为 `generated`。
- `generated` 和 `source_ready` 必须由 1.0 的 validated request/result 和原子注册链
  写入，不能根据旧路径或旧证据手工恢复。

本地 Agent 还应核对 `GDD.md`、当前 tag 的 `PLAN.md`、`STRUCTURE.md`、
`SCENES.md`、`STYLE.md`、`MEMORY.md`、`ROADMAP.md`、现有 Godot 资源绑定、
addons 和自定义 runtime 配置。并非每个工作区都需要修改所有项目；磁盘上的真实
游戏才是判断依据。

## 可复制的 Agent Prompt

把下面的 Prompt 交给平时负责该游戏仓库的 coding agent，并先替换两个路径占位符。

```text
请把这个现有 GodotMaker 工作区从 0.x 升级到 GodotMaker v1.0.0。

输入：
- GodotMaker v1.0.0 checkout：<absolute-framework-path>
- 目标游戏工作区：<absolute-target-path>

目标：
保持游戏位于当前目录，干净地重新初始化 GodotMaker 管理的框架层，然后只根据
真实的 1.0 契约调整项目自有文档和运行时绑定。

硬性门禁：
1. 先做只读审计。在向我展示审计结果并获得明确批准前，不要修改文件或运行
   publish。
2. 确认目标中存在有效的 0.x `.godotmaker/version`。如果缺失则停止：那只能证明
   fresh install，不能证明完成了 0.x 升级。
3. 证明 v1.0.0 publish 将删除或覆盖的每个路径和外部 runtime registration 要么没有
   自定义内容，要么已进入可恢复的 Git checkpoint，要么具备经过验证的备份与恢复
   步骤。对于 ignored、untracked 或 Agent 全局状态，干净工作区或升级分支本身并不
   足够。未经授权，不要创建提交、备份或丢弃修改。
4. 从已部署工作区判断当前 agent 并保持该选择，只能是 `claude-code`、`codex`、
   `opencode` 或 `pi`。
5. 确认框架 worktree 干净，并且 `git rev-parse HEAD` 等于
   `git rev-list -n 1 v1.0.0`。不要从持续变化的任意分支或 dirty release checkout
   publish。
6. 不要用模板整体覆盖项目文档，应比较并迁移其含义。没有对应文件与验证证据时，
   绝不能声称资产已就绪。

阶段 A——只读审计：
- 记录 Git 状态、`.godotmaker/version`、所选 agent、Godot 路径/配置，以及框架管理
  runtime 目录内的任何自定义修改。
- 枚举所选 runtime 的精确风险路径：Skills、agents、config、templates、
  plugins/extensions、runtime references、`.godotmaker/hooks/`、
  `.godotmaker/asset-runtime/`、`tools/`、当前状态/报告文件，以及 publish 会覆盖的
  hook config 或 adapter。逐项证明自定义内容的恢复来源，否则停止。
- 检查 `.gitignore`、`.gitattributes`，以及 Claude Code 使用的
  `.worktreeinclude`；在不修改它们的前提下记录内容或 hash 与仓库当前的 Git 初始化
  状态。Publish 会追加必要元数据，并移除旧的 `.godotmaker/` blanket rule 和 Codex
  的 `.agents/` rule；批准前应列出哪些原本被忽略的文件会因此变为可见，并在现有
  恢复来源无法覆盖时请求备份授权。
- 对 Claude Code、Codex 或 OpenCode，使用对应 runtime 的 CLI 记录当前完整的
  `godot` MCP entry 和精确恢复命令。不能只依赖 `.mcp.json` 或
  `check_project.py`：有效 MCP 状态可能存于仓库之外。还要注明 Claude Code 与 Codex
  publish 会先移除旧 entry 再添加新 entry，因此 add 失败后可能没有任何注册。
- 存在时读取 `GDD.md`、`PLAN.md`、`ASSETS.md`、`STRUCTURE.md`、`SCENES.md`、
  `STYLE.md`、`MEMORY.md` 和 `ROADMAP.md`。
- 检查 `project.godot`、addons、场景、脚本、资源路径、生成资产，以及
  `.godotmaker/` 中保留的历史证据。
- 将现有项目文档与 v1.0.0 模板作只读比较。
- 特别检查 1.0 资产契约：
  * `ASSETS.md` 是 worker 唯一可见的运行时目录。
  * 一个逻辑运行时输出对应一行。
  * 运行时行需要最终 Godot Runtime Type 和可加载的 `res://` Runtime Path，通常
    位于 `assets/generated/<asset-family>/<asset-id>/`。
  * 角色玩法动画应通过 `character-bundle` 解析到 `SpriteFrames`；基准参考图与动作
    源图是证据，不是额外运行时行。
  * 仅参考输出使用 `source_ready`，不能当作运行时资源。
  * 不要把旧 manifest/stable-entry 指针保留成兼容层；找到场景和 worker 真正加载的
    1.0 资源。
- 输出一张审计表，包含：项目、当前状态、所需变化、证据、风险、建议动作。分开列出
  确定性的框架重新初始化和需要理解项目语义的迁移，然后停下来等待批准。

阶段 B——框架重新初始化，仅在批准后执行：
- Publish 前，创建并验证阶段 A 报告中已明确获批的每份备份。任一必要备份或恢复
  检查失败都必须停止。
- 在 `<absolute-framework-path>` 中运行：
  `python tools/publish.py --agent <current-agent> --force "<absolute-target-path>"`
- 记录完整命令和结果。出现任何错误就停止，不得掩盖部分 publish，也不得改用其他
  agent 重试。若旧 MCP entry 已移除后注册失败，必须先恢复记录下来的 entry，再做
  其他操作。
- 验证 `.godotmaker/version` 为 `1.0.0`、所选 runtime 文件和
  `.godotmaker/asset-runtime/` 存在、不兼容的当前流水线状态已清理、
  `.godotmaker/applied_migrations.json` 已重建 baseline。
- 证明游戏代码、场景、素材、项目文档、项目配置和保留的历史证据没有丢失。

阶段 C——项目语义迁移：
- 只做阶段 A 证据支持的最小、可 review 修改。
- 让 `ASSETS.md` 的结构符合 1.0 Runtime Type / Runtime Path 表。保留有价值的
  provenance，但应移除过时的 worker-facing 行或指针，而不是增加兼容读取层。若没有
  有效的 1.0 证据链证明某项输出，应让它保持 `MISSING` 或 `deferred`。
- 绝不能手改 Runtime Type、Runtime Path 或 Status 来绕过注册。`generated` 或
  `source_ready` 必须拥有 validated v1.0 request 和匹配 result，并通过
  `tools/asset_result_registration.py` 校验声明的 Godot 类型与资源、原子注册整个
  production unit；多输出 family 必须整组成功或整组失败。若旧证据无法重建这条链，
  应报告 blocker，或请求重新运行对应 Asset Skill。
- 当场景或脚本仍指向已废弃资产输出时，更新资源绑定。若验证过的确定性转换足够，
  不要只为了改路径就重新生成已接受的美术素材。
- 让 GDD、当前 tag 计划、结构、场景、风格、路线图和记忆文档与真实游戏一致。
  如果通过 `/gm-gdd` 或其他流水线阶段重新生成会改变产品意图，先提出方案并等待批准。
- Provider 凭证缺失或模型不可用属于 blocker，不能以此为理由伪造生成资产或验证证据。

阶段 D——验证和交接：
- 在升级后的工作区运行 `python tools/check_env.py`。
- 对 Claude Code、Codex 或 OpenCode，直接查询所选 Agent CLI，确认有效的 `godot`
  MCP entry 使用预期命令和 `GODOT_PATH`；只检查项目内文件并不足够。
- 在 v1.0.0 框架 checkout 中运行
  `python tools/check_project.py "<absolute-target-path>" --all`。
- 运行本地可用的项目单元测试、Godot/headless 测试和 E2E；不可用的检查单独报告。
- 检查修改过的 Godot 资源，并对每种迁移后的运行时资产 family 至少检查一个真实消费
  它的场景路径。
- 除了我在阶段 C 明确批准的 Asset Skill 重验，在我批准迁移报告前，不要恢复正常
  流水线。
- 最终报告必须包含：原始/最终版本、精确命令、保留路径、修改文件、已迁移资产行与
  绑定、自动化结果、仍需人工检查的项目、blocker 和回滚方式。
```

## 预期交接标准

干净重新初始化成功，只能证明 1.0 框架已安全部署。只有本地 Agent 同时证明项目自有
契约与现有游戏一致，而且游戏仍能构建和运行，升级才算完成。最终报告中应把这两个
结论分开。
