# 发版流程

GodotMaker 使用语义版本控制。每次发版遵循一份简短的清单；本页是该清单的摘要。
完整清单见 [`docs/update/release-checklist.md`](../../update/release-checklist.md)。

关于版本方案细节以及 `publish.py` 如何处理目标项目的升级，请参阅 [../../versioning.md](../../versioning.md)。

---

## 何时升级哪个版本号

| 级别 | 场景 | 示例 |
|-------|------|---------|
| PATCH | 向后兼容的 bug 修复（无新行为） | `0.4.0 → 0.4.1` |
| MINOR | 向后兼容的新功能或行为变更 | `0.4.0 → 0.5.0` |
| MAJOR | 破坏性变更，无法通过增量迁移解决 | `0.x → 1.0.0` |
| PRERELEASE | 稳定版之前的迭代 | `1.0.0-alpha.1 → 1.0.0-alpha.2` |

`publish.py` 在 PATCH 升级时自动继续，在 MINOR 升级时弹出确认提示，在 MAJOR 升级时要求 `--force`。`migrations/` 下的迁移脚本（按时间戳命名，与版本号解耦）会在任何非 MAJOR 升级时执行——完整策略见 [`../../versioning.md`](../../versioning.md)。

---

## next.md 工作流

贡献者从不直接编辑 `CHANGELOG.md`。每个 Pull Request 都需要在 `docs/update/next.md` 的适当分类下至少添加一条记录：

```markdown
## Added
- 新增内容的简要说明 (#123) — @author

## Changed
- 发生了什么变化以及原因 (#124) — @author

## Fixed
- 修复了什么问题 (#125) — @author

## Removed
- 删除了什么内容 (#126) — @author
```

分类名称遵循 [Keep a Changelog](https://keepachangelog.com/) 规范。如果四个标准分类都不合适，可以新增一个。

发版时，`next.md` 会被归档，并从模板创建新的空 `next.md`。贡献者立即开始向新的 `next.md` 添加下一批变更记录。这意味着 `CHANGELOG.md` 每次发版只由负责发版的人修改一次。

---

## 执行发版

高层次清单。遵循
[`docs/update/release-checklist.md`](../../update/release-checklist.md) 中的完整步骤：

1. **合并所有待发布的 PR。** 确认 `next.md` 中包含所有 PR 的记录。

2. **归档 next.md。** 将 `docs/update/next.md` 重命名为
   `docs/update/v<VERSION>.md`，精确保留预发布后缀，然后从模板创建新的
   `docs/update/next.md`。

3. **更新 CHANGELOG.md。** 在文件开头插入新章节：

   ```markdown
   ## [<VERSION>] — YYYY-MM-DD

   ### Added
   - （来自 next.md 的条目）

   ### Changed / Fixed / Removed
   - ...
   ```

4. **升级 VERSION。** 将新版本号写入仓库根目录的 `VERSION` 文件。这是唯一的真实来源。

5. **添加迁移脚本**（如有需要）。如果任何变更需要在现有游戏项目里改写文件，用 `python tools/migrate.py --new <slug>` 创建——会生成 `migrations/<utc-时间戳>_<slug>.py`。bump 级别不限制迁移，**PATCH 和 MINOR 都适用**。脚本格式与 applied-tracking 机制见 `migrations/README.md`。

6. **发布到测试项目。** 在打 tag 前确认这个准确的 release checkout 和升级边界正常：

   ```bash
   python tools/publish.py /path/to/test-game
   ```

7. **提交并打标签。**

   ```bash
   git add VERSION CHANGELOG.md docs/update/ migrations/
   git commit -m "release: v<VERSION>"
   git tag v<VERSION>
   ```

   版本中包含 `-` 的 tag 会创建 GitHub Pre-release。已发布的 tag 不得移动；
   修复应发布下一个预发布标识符。

---

## 迁移脚本

发版时可以附带迁移脚本，自动修复现有游戏项目中的兼容性问题。脚本直接放在 `migrations/` 下，按 UTC 时间戳命名：

```
migrations/20260429100000_fix_state_path.py
migrations/20260430153000_rename_metrics_field.py
```

`tools/migrate.py` 读取每个目标项目的 `.godotmaker/applied_migrations.json`，按时间序应用差集。某个脚本失败时迁移链中止，publish 以错误退出；已成功的脚本仍保留在 `applied_migrations.json` 里，重新运行 publish 时从断点继续。

MAJOR 升级完全跳过迁移，改用 `--force` 干净重装；迁移追踪器会被重置并在重新部署后重新建立 baseline。时间戳序列本身是单调全局的——旧脚本作为历史记录留在磁盘上，新装项目或 MAJOR 重装时会被 baseline 为已应用。
