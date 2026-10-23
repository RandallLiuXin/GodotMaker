# Asset 技能

Asset Skill 会把资产请求转换成已验证的 Godot runtime 资源。
`/gm-asset` 选择 family，各 family 负责自己的 request 结构、source 处理、输出路径和
验证。权威 inventory 位于 `tools/asset_family_registry.py`；本页是该 registry 的
公开镜像。

## 已交付 family

| Family | Variant | Godot artifact 类型 | 终态 |
|---|---|---|---|
| background-map | default | Texture2D | ready |
| card-kit | default | AtlasTexture, StyleBoxTexture, Theme | ready |
| character-bundle | default | SpriteFrames | ready |
| compact-prop-pack | default | AtlasTexture | ready |
| fx-bundle | static, animated | SpriteFrames, Texture2D | ready |
| platform-strip | single, atlas | AtlasTexture, Texture2D | ready |
| scene-prop-set | default | AtlasTexture | ready |
| tileset | default | TileSet | ready |
| ui-kit | default | AtlasTexture, StyleBoxTexture, Theme | ready |

各 family 只有在完整验证路径成功后，才会返回一个或多个原生 Godot artifact。

要直接从真值来源查看或校验同一份 inventory，请运行：

```bash
python tools/asset_family_registry.py --output json
python tools/asset_family_registry.py --check
```

## L0-L4 验证

Runtime asset 按顺序通过以下层级。任一层失败，result 都不能登记进 `ASSETS.md`，
也不能交给 worker。

| 层级 | 证明内容 |
|---|---|
| L0 | 公开 request 与 result 符合该 family 的合同。 |
| L1 | 已处理 source 确实存在，并满足该 family 的图片或布局规则。 |
| L2 | 已登记的确定性 compiler 产出了声明的原生 artifact。 |
| L3 | 真实的 headless Godot 进程能够 import、加载并校验 artifact 类型。 |
| L4 | 类型专属结构与声明的 recipe 一致，例如 SpriteFrames 动画、Theme 值、atlas region，或 TileSet source 与 terrain 数据。 |

Runtime 输出只有在 L0-L4 全部通过后才会到达 `ready`。Provider 可用性与视觉质量属于独立证据：
结构验证全绿，并不代表远程 provider 一定可用，也不代表其美术符合特定创作方向。

## 相关页面

- [资产工具](../05-tools/asset-tools.md)说明登记、snapshot 和生产辅助工具。
- [Provider 配置](../06-configuration/providers/README.md)区分 coding-agent runtime
  与图片 / VQA provider。
- [Core 技能](core-skills.md)说明 `/gm-asset` 在角色流水线中的位置。
