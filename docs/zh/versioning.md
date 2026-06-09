# 版本控制与升级

GodotMaker 的版本追踪方式，以及版本之间的升级处理机制。

## 版本方案

GodotMaker 使用[语义化版本](https://semver.org/)：`MAJOR.MINOR.PATCH`

| 级别 | 含义 | 示例 | 升级行为 |
|------|------|------|----------|
| **PATCH** | 向后兼容的 bug 修复，无新行为 | `0.3.0 → 0.3.1` | 自动继续；执行所有未应用的迁移脚本 |
| **MINOR** | 向后兼容的新功能或行为变化 | `0.3.0 → 0.4.0` | 显示 Changelog，要求确认；执行所有未应用的迁移脚本 |
| **MAJOR** | 破坏性变更（不向后兼容） | `0.x → 1.x` | 强烈警告；必须使用 `--force` 进行干净的重新初始化（跳过迁移，改为 baseline） |

### 本项目中"向后兼容"的具体含义

GodotMaker 是一个把文件部署到目标项目里的框架，而不是带公开 API 的库。因此兼容性契约只有两条：

- **用户保留文件的格式不变。** `CLAUDE.md`、`.claude/godotmaker.yaml`、
  `.godotmaker/config.yaml` 以及用户自己写的游戏代码、场景、素材，都不会被静默改写；
  上一版本的 schema/格式必须在新版本里仍能解析。
- **运行时状态可被读懂。** 老 hook / skill 留下的状态文件（`state.json` 字段、
  `metrics*.jsonl` schema、`stage.jsonl`、`current_role` 等）必须能被新版本读懂——
  要么直接兼容，要么由迁移脚本在升级时改写。

框架托管文件（skills、hooks、agents、templates、tools）每次 publish 都会被覆盖，
所以**这些**的变更**永远不算 breaking**——它们只是被重新部署而已。

### 如何选择 bump 级别

给贡献者用的简短决策树：

1. 老项目重新 publish 即可生效，没有动到任何用户保留文件或运行时状态
   （或改动只是纯 bug 修复）→ **PATCH**
2. 加了新 skill / hook / 行为，但老项目的用户保留文件和运行时状态仍然可用
   → **MINOR**
3. 某个用户保留文件格式或运行时状态字段以无法被旧版本数据满足的方式改了
   → **MAJOR**

**迁移脚本与 bump 级别无关。** 迁移脚本是用来在已有目标项目里修复或改写
某些东西的工具；是否需要写迁移脚本，跟你应该选哪个 bump 级别是两个问题。
迁移系统本身按时间戳驱动（`migrations/<YYYYMMDDhhmmss>_<slug>.py`），
通过 `.godotmaker/applied_migrations.json` 在每个目标项目里独立追踪；
产品 `VERSION` 完全不参与决策。详见下文"版本迁移"。

## 版本文件位置

| 文件 | 位置 | 用途 |
|------|------|------|
| `VERSION` | GodotMaker 仓库根目录 | 当前版本的唯一真相来源 |
| `.godotmaker/version` | 目标游戏项目 | 记录上次发布的版本 |
| `CHANGELOG.md` | GodotMaker 仓库根目录 | 每个版本的人类可读变更记录 |
| `migrations/` | GodotMaker 仓库根目录 | 版本迁移脚本 |

## 发布与升级

### 全新安装

```bash
python tools/publish.py /path/to/my-game
```

目标中不存在版本记录——发布直接进行，并将版本号写入 `.godotmaker/version`。

### 升级（重新发布到已有项目）

```bash
python tools/publish.py /path/to/my-game
```

发布脚本将源码的 `VERSION` 与目标的 `.godotmaker/version` 进行比对，根据升级级别执行不同行为：

| 级别 | 行为 |
|------|------|
| **PATCH** | 自动继续；执行所有未应用的迁移脚本 |
| **MINOR** | 显示 Changelog，询问确认；执行所有未应用的迁移脚本 |
| **MAJOR** | 阻止增量迁移，需要 `--force` 才能进行干净的重新初始化 |

### 版本迁移

迁移脚本是 `migrations/` 下的带时间戳脚本，例如：

```
migrations/20260429100000_fix_state_path.py
migrations/20260430153000_rename_metrics_field.py
```

每个目标项目在 `.godotmaker/applied_migrations.json` 里记录已应用过的迁移 ID。
每次 publish 时，`migrate.py` 扫描磁盘上所有脚本，扣掉已记录的，按时间序执行剩下的。

**整套机制与 MAJOR.MINOR.PATCH 完全解耦。** 选择跑哪些迁移时不看产品版本号——
唯一的输入是"磁盘上有什么"和"目标项目里已应用了哪些"。这意味着 PATCH 版本可以
作为一等公民携带迁移脚本（比如某个 hook bug 在老项目里留下了孤儿文件，修这个 hook
的 PATCH 版本就可以附一个修复型迁移）。

全新安装和 MAJOR `--force` 重装走 **baseline**：把所有当前迁移直接标记为已应用，
不实际执行——因为目标项目本来就在最新格式上，没有"老格式"可迁移。

如果某个迁移脚本失败，整个链条立刻中止。已成功的脚本依然保留在
`applied_migrations.json` 里，所以重新运行 publish 时会从断点继续。

迁移脚本也可以独立运行（不需要重新 publish）：
```bash
python tools/migrate.py /path/to/my-game
```

新建一个迁移脚本：
```bash
python tools/migrate.py --new fix-state-path
# 创建 migrations/<当前-utc-时间戳>_fix_state_path.py
```

完整说明——命名规则、脚本约束、legacy target 自动 bootstrap 规则
（首次接触时自动创建空 tracker；pending 迁移走正常路径）——
见 `migrations/README.md`。

### MAJOR 升级

MAJOR 版本变更意味着无法通过增量迁移处理的破坏性变更。`publish.py` 拒绝跨 MAJOR 边界升级，除非使用 `--force`，该选项会执行干净的重新初始化。

全量重建会清除所有框架管理的内容：
- `.claude/skills/`、`.claude/agents/`、`.claude/config/`、`.claude/templates/`
- `.godotmaker/hooks/`、`.godotmaker/stage_schemas.json`
- `.godotmaker/state.json`、`.godotmaker/metrics*.jsonl`
- `.godotmaker/applied_migrations.json`（重新部署后会重建 baseline）
- `tools/`
- `.claude/settings.json`（强制覆盖）

保留（用户配置）：
- `CLAUDE.md`、`.claude/godotmaker.yaml`、`.godotmaker/config.yaml`

重新部署完后，`publish.py` 调用 `baseline_applied()` 把所有当前迁移
标记为已应用而不执行——跟全新安装一样。迁移时间戳序列本身是单调全局的，
旧脚本作为历史记录留在磁盘上。

### 降级

降级（如 `0.4.0 → 0.3.0`）默认被阻止。使用 `--force` 可以绕过限制：

```bash
python tools/publish.py --force /path/to/my-game
```

强制降级仍然调用 `run_migrations()`（保持路由一致性），但实际上是 no-op：
`applied_migrations.json` 记录的是高版本应用过的全部迁移，而老版本磁盘上只有
其中一个子集，所以 `pending = disk - applied` 恒为空。迁移不会"回滚"——
要回滚 schema 变更需要显式的反向迁移脚本，本系统不提供。如果确实需要回滚某次
schema 变更，请从 VCS 快照恢复目标项目。

### 重新发布相同版本

重新发布相同版本始终允许，在开发期间拾取本地变更时很有用。

## 会话中的版本显示

在已发布的项目中启动 Claude Code 会话时，`session_start.py` Hook 读取 `.godotmaker/version` 并将 `[GodotMaker vX.Y.Z]` 注入会话上下文。这让当前角色技能和用户都能知道部署的是哪个框架版本。

## 发布新版本的工作流程

1. 在 GodotMaker 仓库中做出你的修改
2. 按上面的决策树确定 bump 级别（PATCH / MINOR / MAJOR）
3. 如果修改需要在已有目标项目里改写某些东西，用 `python tools/migrate.py --new <slug>`
   生成一个新迁移脚本——详见 `migrations/README.md`。**任意 bump 级别都可以**。
4. 更新 `CHANGELOG.md`——在顶部添加新的 `## [X.Y.Z]` 分区
5. 更新 `VERSION`——改为新版本号
6. 提交并（可选）打标签：
   ```bash
   git add VERSION CHANGELOG.md migrations/
   git commit -m "release: vX.Y.Z"
   git tag vX.Y.Z
   ```
7. 发布到目标项目：
   ```bash
   python tools/publish.py /path/to/my-game
   ```

## 升级时会覆盖什么

每次发布都会覆盖：

| 目录 | 内容 |
|------|------|
| `.claude/skills/` | 所有技能（从 core + reviewer 展平） |
| `.claude/agents/` | 代理定义（worker、verifier、reviewer、analyst、asset-producer） |
| `.godotmaker/hooks/` | 所有 Hook 脚本 |
| `.claude/config/` | 配置文件（仅 `--force` 时覆盖 settings.json） |
| `.claude/templates/` | 文档模板 |
| `tools/` | Python 工具（check_project、check_env 等） |

以下**不会**被覆盖（仅在全新安装时创建）：

| 文件 | 原因 |
|------|------|
| `CLAUDE.md` | 用户可能已自定义 |
| `.claude/settings.json` | 用户 Hook 配置（仅 `--force` 时覆盖） |
| `.claude/godotmaker.yaml` | 主机特定路径 |
| `.godotmaker/config.yaml` | 项目特定设置 |

## 关于 addon_versions.json 的说明

`config/addon_versions.json` 追踪 Godot 插件版本（gecs、gdUnit4 等）——这与 GodotMaker 自身的版本是分开的。插件版本按 Godot 引擎版本锁定，独立管理。
