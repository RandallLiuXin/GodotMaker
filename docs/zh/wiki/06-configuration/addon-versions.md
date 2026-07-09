# Addon 版本管理

`addon_versions.json` 固定了 GodotMaker 所使用的 Godot addon 的精确版本——目前包括用于 ECS 的 `gecs`、用于单元测试的 `gdUnit4`，以及用于端到端测试的 `godot-e2e`。将版本与 Godot 引擎版本绑定，可以防止升级时悄无声息地破坏你的构建。

该文件位于 GodotMaker 仓库的 `config/addon_versions.json`，而不是你的游戏项目内部。

## 文件内容

这个文件将每个支持的 Godot 版本映射到一组 addon 条目。每个条目记录了 GitHub 仓库地址、要下载的精确 git tag，以及文件在项目中的安装位置。当前的版本锁定如下：

| Godot 版本 | gecs | gdUnit4 | godot-e2e |
|---|---|---|---|
| 4.3 | v7.1.0 | v5.1.1 | v1.1.0 |
| 4.4 | v7.1.0 | v5.1.1 | v1.1.0 |
| 4.5 | v7.1.0 | v6.1.0 | v1.3.0 |

重要规则：

- **gdUnit4** v5.x 兼容 Godot 4.3 和 4.4；v6.x 需要 Godot 4.5 或更高版本。
- **godot-e2e** v1.3.0 用于 Godot 4.5+；4.3/4.4 保持在 v1.1.0。

GodotMaker 会根据你安装的 Godot 版本自动选择对应的行。如果某个 Godot 版本没有列出，scaffold 会使用最接近的更低映射版本；如果没有任何更低映射，则会向用户报告问题，而不是猜测版本。Godot 4.5+ 在所有维度上都对应最新的 addon。

## 为什么要锁定版本

Godot addon 在不同版本之间可能会变更 API。GodotMaker 的 skill 和 hook 依赖 `gecs` 中的特定函数，以及 `gdUnit4` 中特定的 CLI 参数。如果某个 addon 悄悄改变了这些接口，构建就会以难以诊断的方式失败。锁定到已验证可用的 tag，意味着你拿到的始终是经过测试的组合。

## `/gm-scaffold` 阶段会发生什么

运行 `/gm-scaffold` 为新游戏项目搭建结构时，它会读取 `addon_versions.json`，判断你正在使用的 Godot 版本，然后从 GitHub 把对应 addon 版本下载到项目的 `addons/` 目录中。它还会在 `project.godot` 中将每个 addon 作为插件启用。你不需要手动下载或配置任何 addon。

## 如何获取升级后的版本

作为普通用户，你不需要直接编辑 `addon_versions.json`。当 GodotMaker 发布新版本并更新了 addon 版本时，重新发布即可获取新的锁定配置：

```bash
python tools/publish.py <your-game-project>
```

如果新版本中锁定的 addon 版本发生了变化，你还需要重新运行 `/gm-scaffold`（或手动更新 `addons/` 目录），才能将新的 addon 文件实际安装到游戏项目中。

## 贡献者须知：升级版本号

更新版本锁定是贡献者的任务。大致流程如下：

1. 修改 `config/addon_versions.json` 中对应条目的 `tag` 值。
2. 验证新 addon 版本能否与目标 Godot 版本正常配合——运行完整的测试套件，并跑一遍示例的 `/gm-scaffold` → `/gm-build` 流程。
3. 发布到测试项目，确认没有 hook 或 skill 出现问题。
4. 提交改动，并在 `CHANGELOG.md` 中记录变更。

关于这一步在完整发布流程中的位置，参见[发布流程](../07-contributing/release-process.md)。
