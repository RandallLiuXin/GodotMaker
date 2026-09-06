# Tag 归档

`seal_tag.py` 是 `/gm-finalize` 用来把一个已完成的 tag 变成 `docs/tags/<Tag>/`
下不可变归档的工具。通常你不需要手动运行它，唯一的例外是 `backfill`——用于给旧版本
GodotMaker 封存的归档补上索引文件。

## 封存后的归档长什么样

```text
docs/tags/
├── README.md                 所有已封存 tag 的父级索引
└── v0.1.0/
    ├── README.md             该 tag 的导航页
    ├── SUMMARY.md            有长度边界的检索摘要
    ├── CHANGELOG.md          由 /gm-finalize 写入的交付说明
    ├── GDD-snapshot.md
    ├── PLAN.md
    ├── STRUCTURE.md
    ├── STYLE.md
    ├── SCENES.md
    ├── MEMORY.md
    ├── memory/               MEMORY.md 索引的各子系统笔记
    ├── evaluation-final.json
    └── evidence/
        ├── manifest.json     每个归档文件的路径、类别、字节数、SHA-256
        ├── e2e/
        └── screenshots/
```

平铺的文档路径（`PLAN.md`、`STRUCTURE.md`、`SCENES.md` 等）与旧版本完全一致，
所以任何已经在读 `docs/tags/<Tag>/PLAN.md` 的流程都不受影响。

## 怎么读归档

1. **`docs/tags/README.md`** —— 有哪些 tag，按版本排序，附发布日期、主题和来源 revision。
2. **`docs/tags/<Tag>/SUMMARY.md`** —— 一屏之内讲清主题、交付的 mechanic、
   变更的系统与场景、验证结论、已知限制，并链接到其余所有内容。
3. **`docs/tags/<Tag>/README.md`** —— 逐文件的职责表，用来判断该打开哪份文档。
4. **canonical 文档和 `evidence/`** —— 内容完整但阅读成本高，只在摘要不够用时才打开。

`SUMMARY.md` 是检索入口，不是新的事实来源。它只复述 `CHANGELOG.md`、`PLAN.md`、
`evaluation-final.json` 和 `final_report.json` 中已确认的内容；Worker 的探索过程、
完整 Trace 和未经验证的 MEMORY learning 不会进入摘要。摘要与 canonical 文档冲突时，
以 canonical 文档为准。

## 不可变语义

一个 tag 完全封存后，`evidence/manifest.json` 中会带上 `"sealed": true`。此后
`archive` 和 `index` 都会拒绝改动该目录并以 `3` 退出。这就是重复执行
`/gm-finalize` 不会静默改写历史的原因。

如果 manifest 缺失或写着 `"sealed": false`，说明是一次未完成的 finalize——
重新运行 `archive` 就是既定的恢复路径，不需要任何额外参数。`--force` 只用于
明确要求重新封存的场景。

这条保证之所以成立，是因为 `sealed: true` 是**最后**才提交的：`index` 先写
`SUMMARY.md`、该 tag 的 `README.md` 和父级 `docs/tags/README.md`，之后才用一次
原子替换写入 manifest。磁盘写满或 I/O 出错发生在这之前时，该 tag 保持未封存、
可以直接重跑，而不会变成「已封存但索引缺失」的死状态。所有生成文件都先写到同目录
的临时文件再 rename 就位，因此写入中断不会把上一版文件截断。

`/gm-finalize` 的完成门禁校验同一个标记：归档必须有可解析的
`evidence/manifest.json` 且 `"sealed"` 严格为 `true`，父级索引必须已收录该 tag。
仅仅文件存在但未封存不算通过。

## 子命令

| 命令 | 作用 |
|---|---|
| `python tools/seal_tag.py archive <Tag>` | 把工作文档、`memory/` 子目录和 `e2e/` 证据复制到 `docs/tags/<Tag>/`，然后校验归档内 `MEMORY.md` 的链接。写入未封存的 manifest。 |
| `python tools/seal_tag.py index <Tag>` | 生成 `SUMMARY.md`、该 tag 的 `README.md`、已封存的 manifest 和父级 `docs/tags/README.md`。这一步才算封存。 |
| `python tools/seal_tag.py backfill <Tag>` / `--all` | 给旧版本封存的归档补上 `README.md`、`SUMMARY.md` 和 manifest；已封存的归档默认跳过，需要 `--force` 才会重新索引。 |
| `python tools/seal_tag.py bundle <Tag>` | 输出 `/gm-finalize` 写 CHANGELOG 所需的 JSON。 |
| `python tools/seal_tag.py reset` | 清空 `.godotmaker/stage.jsonl` 并删除 `metrics_current.jsonl`。 |

退出码：`0` 成功 · `1` 文件系统或运行时失败 · `2` 缺少来源文件、归档内链接无法解析
或用法错误 · `3` 该 tag 已封存。

## MEMORY 链接校验

`MEMORY.md` 通过 `memory/` 下的文件索引各子系统笔记。只归档索引而不归档这些文件，
等于冻结了一组失效链接，所以 `archive` 会一并复制 `memory/`，然后校验归档内的
`MEMORY.md`：

- 指向 `memory/…` 但归档内没有对应文件、使用绝对路径、或越出归档目录的链接会
  **阻止封存**（退出码 2）。修好根目录的 `MEMORY.md` 或补回缺失文件后重跑即可。
- 指向本来就不归档的项目文件（`src/player.gd`、`assets/…`）的链接会记录到
  manifest 的 `link_warnings`，不阻塞流程。

HTML 注释和代码块中的链接会被忽略，因此 `MEMORY.md` 模板自带的示例条目不会
让第一次 finalize 失败。

## 回填旧归档

在这套结构出现之前创建的归档只有平铺文档，没有 `README.md`、`SUMMARY.md` 和
manifest，因此不会出现在父级索引里。执行一次回填即可：

```bash
python tools/seal_tag.py backfill --all
```

回填只添加索引文件，绝不改写 canonical 文档——它会在前后分别计算这些文档的哈希，
一旦发现变化就报错退出。它也**不会**把今天的 `memory/` 复制进历史 tag：那会把
当下的内容注入过去的快照。缺失的子目录会被记录为 manifest warning，该 tag 的
README 中完整性显示为 `partial`。

已经带有 sealed manifest 的归档会被跳过——重新索引会用本次运行解析出的 revision
覆盖它原本记录的封存 revision。确实需要重新索引时加 `--force`。对于实际被索引的
归档，来源 revision 取自 `git tag <Tag>`（`/gm-finalize` 打的那个 commit），
而不是今天的 `HEAD`；没有对应 git tag 的归档记录为 `null`，不会编造一个 revision。

`/gm-finalize` 永远不会自动执行 `backfill`。改写历史始终是用户明确发起的操作。
