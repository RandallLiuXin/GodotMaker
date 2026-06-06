# Changelog

---

## 已发布版本

完整详细的 Changelog 维护在仓库根目录：

[GitHub 上的 CHANGELOG.md](https://github.com/RandallLiuXin/GodotMaker/blob/main/CHANGELOG.md)

### 0.1.0 — 2026-04-26（首次公开发布）

- 以独立 `/gm-*` 斜线指令（`/gm-scaffold`、`/gm-gdd`、`/gm-asset`、`/gm-build`、`/gm-verify`、`/gm-evaluate`、`/gm-fixgap`、`/gm-accept`、`/gm-finalize`）交付 9 角色流水线，取代此前的单体协调器方案。
- Worker / Verifier / Reviewer / Analyst 子代理派发系统，含格式校验报告和防死锁保护。
- 9 个角色技能 + 12 个辅助技能 + 8 个审查员技能（物理、动画、UI、地图块、导航、着色器、音频、粒子）。
- 8 个 Hook 脚本，执行每角色文件写权限控制、阶段前置条件门控、子代理报告校验以及完成严谨性检查。
- `tools/publish.py` 将框架部署到目标 Godot 项目，支持语义版本追踪和升级提示。
- 静态检查：`check_project.py` 检查项目完整性，`check_classname.py` 检查与 Godot 内置名称的冲突。
- 资源流水线：`asset_source_generate.py`（Gemini / OpenAI / xAI source 生成）、`rembg_matting.py`。
- 覆盖 8 个分区的 Wiki 文档。
- 193 个以上针对 Hook 和工具的单元测试。

---

## 下一版本计划

下一个版本的待处理变更在 [`../../update/next.md`](../../update/next.md) 中追踪。

贡献者须知：每个 Pull Request 合并前，必须在 `next.md` 的对应分类下（`Added`、`Changed`、`Fixed`、`Removed`）添加一条记录。发布时，`next.md` 会归档为 `docs/update/vX.Y.Z.md`，并以空白版本替换。

---

## 迁移脚本

当升级需要在现有目标项目里改写文件时，迁移脚本会自动处理过渡。迁移脚本存放在 GodotMaker 仓库的 `migrations/` 目录下，按 UTC 时间戳命名（如 `migrations/20260429100000_fix_state_path.py`）。每个目标项目在 `.godotmaker/applied_migrations.json` 里追踪已应用过哪些；每次升级时 `tools/publish.py` 按时间序应用差集。整套机制与产品 MAJOR.MINOR.PATCH 完全解耦——任何非 MAJOR 升级都可以携带迁移。（MAJOR 升级跳过迁移，改用 `--force` 干净重装后重新 baseline。）

你也可以单独运行迁移脚本用于测试：

```bash
python tools/migrate.py /path/to/my-game
```

完整的升级和降级策略，包括 MAJOR 版本边界的处理，见 [`../../versioning.md`](../../versioning.md)。
