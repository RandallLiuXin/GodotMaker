# 常见问题

快速查阅：症状、原因、解决办法。如果你遇到的是会话崩溃或中途中断的情况，请看 [恢复与继续](recovery-and-resume.md)。

---

## 环境配置问题

### API key 未设置

**症状**（来自 `check_env.py`）：

```
[FAIL] GOOGLE_API_KEY not set but config uses a Gemini model.
```

**原因：** `.godotmaker/config.yaml` 选择了 API 后端模型，但当前终端会话里没有对应环境变量。

**解决办法：** 设置当前选择器需要的 key，或者在运行时支持时把选择器改成 `native`。

| Selector | Key |
|---|---|
| `gemini:<model>` | `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` |
| `openai:<model>` | `OPENAI_API_KEY` |
| `grok:<model>` | `XAI_API_KEY` |

```bash
# macOS / Linux
export GOOGLE_API_KEY=your-key-here
export OPENAI_API_KEY=your-key-here
export XAI_API_KEY=your-key-here

# Windows (PowerShell)
$env:GOOGLE_API_KEY = "your-key-here"
$env:OPENAI_API_KEY = "your-key-here"
$env:XAI_API_KEY = "your-key-here"
```

如果想永久生效，把变量写入 shell 配置文件（`~/.bashrc`、`~/.zshrc`），或者写入 Windows 用户环境变量。

---

### Godot 找不到，或版本太旧

**症状：**

```
[WARN] Godot not found on PATH. Provide the full path when running publish,
       or add it to PATH.
```

或者：

```
[FAIL] Godot 4.3.x too old (>= 4.5 required)
```

**原因：** Godot 4.5 或更高版本没有安装，或者安装目录不在系统 PATH 里。

**解决办法：**

1. 从 https://godotengine.org/download 下载 Godot 4.5+
2. 要么把它的目录加进 PATH，要么打开你游戏项目里的 `.claude/godotmaker.yaml`，把 `godot_path` 字段设为 Godot 可执行文件的完整路径。

验证是否正常：

```bash
python tools/check_env.py
```

---

### Claude Code 找不到

**症状：**

```
[FAIL] Claude Code not found. Install: npm install -g @anthropic-ai/claude-code
```

**原因：** `claude` 命令不在 PATH 里。Claude Code 是一个 Node.js 包。

**解决办法：**

```bash
npm install -g @anthropic-ai/claude-code
claude --version   # should print a version number
```

如果连 `npm` 都没有，先去 https://nodejs.org 安装 Node.js 18+。

---

### Worker 提交代码失败——Git 身份未配置

**症状：** Worker 子 Agent 报错，提示 `Author identity unknown` 或 `git commit` 拒绝执行。

**原因：** Git 创建提交记录时必须知道 `user.name` 和 `user.email`。Worker 子 Agent 会代替你提交代码。

**解决办法：**

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

配完之后跑一下 `python tools/check_env.py`，两项都应该显示 `[PASS]`。

---

## 流水线阶段校验问题

这些报错会在你跳步执行 `/gm-*` 命令时出现。每个角色在启动前都会检查前置角色是否已经完成。

---

### "Role 'gdd' has not completed yet — run /gm-gdd first"

**症状：** 你运行了 `/gm-build`，结果被 hook 拦下来，提示 `gdd` 角色未完成。

**原因：** `/gm-build` 需要一份完整的游戏设计文档才知道要构建什么。它会检查 `.godotmaker/stage.jsonl` 里有没有 `gdd` 的完成记录，以及 `GDD.md`、`PLAN.md` 等输出文件是否存在。

**解决办法：** 先运行 `/gm-gdd` 并等它跑完，再运行 `/gm-build`。

---

### "Role 'evaluate' has not completed yet — run /gm-evaluate first"

**症状：** 你运行了 `/gm-fixgap`，被 hook 拦下来。

**原因：** `/gm-fixgap` 需要评估结果才知道要修什么。它会检查 `evaluate` 的完成记录以及 `.godotmaker/evaluation.json` 是否存在。

**解决办法：** 先运行 `/gm-evaluate` 等它跑完，然后再运行 `/gm-fixgap`。

---

### "Build already completed for the current tag..."

**症状：**

```
Build already completed for the current tag at <timestamp>. Recommended next: /gm-verify.
If you need to redo this step or have other plans, just tell me.
```

**原因：** `PLAN.md` 里的所有任务都已经是 `verified` 状态，没有剩余工作了。

**解决办法：** 如果你确实想继续，告诉 Claude Code "continue to /gm-verify" 或者直接运行 `/gm-verify`。如果你觉得还有东西没做完，打开 `PLAN.md` 看看——有些应该是 `pending` 的任务可能被提前标记成 `verified` 了。

---

### "Evaluate already ran... Recommended next: /gm-accept or /gm-fixgap"

**原因：** `.godotmaker/evaluation.json` 已经存在，而且上次 `/gm-verify` 之后游戏代码没有变化。评估器不会重复跑。

**解决办法：** 决定下一步方向：运行 `/gm-accept` 查看结果并确认，或者运行 `/gm-fixgap` 修复问题。如果你确实需要重新评估（比如手动改了代码），告诉 Claude Code "redo the evaluation"，它就会重新跑。

---

### "Cannot finish 'build' role — diligence issues: Dispatched N workers but 0 verifiers"

**症状：** 会话被阻止结束，提示缺少 verifier 或 reviewer。

**原因：** `/gm-build` 派发了 Worker 子 Agent，但会话在跑完 verifier 和 reviewer 之前就想结束了。`check_completion.py` hook 会强制执行这个检查——只有 Worker 完成还不算做完。

**解决办法：** 告诉 Claude Code 继续："run the verifier and reviewer now"。它会派发它们，等它们完成后阻拦就会解除。不要手动关掉会话，等验证这轮跑完。

---

## 构建问题

### 无头构建因 class_name 冲突失败

**症状：** Godot 无头构建时报错，提示 `Duplicate class name` 或 `Class name already exists`。

**原因：** 两个 `.gd` 文件声明了相同的 `class_name`。Godot 要求 class name 在整个项目里唯一。

**解决办法：**

```bash
python tools/check_classname.py <path-to-game>
```

这个命令会列出项目里所有 `class_name` 并标出重复的。把冲突的类改个名字（`.gd` 文件里和所有引用它的地方都要改）。

---

### Worker 看起来成功了，但测试结果一直没出来

**症状：** 构建完成了，但没有任何测试报告，或者 hook 把某个 Worker 报告标记为"内容过于简单"。

**原因：** `check_worker_report.py` 会验证 Worker 和 verifier 的报告里是否包含真实的测试输出，不能只写"测试通过"这种没有证据的话。这种报告会被拦截。

**解决办法：** 大多数情况下 hook 会自动触发重试。如果一直循环，告诉 Claude Code "the worker report is incomplete; retry the verifier"。也可以看一下最近的指标日志：

```bash
cat .godotmaker/metrics_*.jsonl | grep HOOK_BLOCK
```

---

### Reviewer 因为会话结束被跳过了

**症状：** `check_completion.py` 在下次会话启动时报阻，或者你发现指标里从没有派发过 reviewer。

**原因：** Reviewer 那轮还没跑，会话就关闭了。Hook 会在会话恢复时提醒技能补上这一步。

**解决办法：** 开一个新的 Claude Code 会话，重新运行 `/gm-build`。Resume Check 会发现任务处于 `completed`（而不是 `verified`）状态，然后自动派发 reviewer 轮来收尾。

---

### Worker 在任务中途挂了

**症状：** 某个 Worker 子 Agent 超时或报错。它的任务在 `PLAN.md` 里一直卡在 `in_progress`。

**原因：** 子 Agent 可能因为代码生成耗时太长、网络问题或上下文长度限制而失败。

**解决办法：** 打开 `PLAN.md`，把那个卡住的任务状态从 `in_progress` 手动改回 `pending`，然后重新运行 `/gm-build`——它会识别 pending 的任务并重新派发。

---

## 美术资源问题

### 图片生成失败

**症状：** `/gm-asset` 报错，比如 `API quota exceeded`、`invalid API key`，或者图片生成时网络超时。

**原因和对应处理：**

| 症状 | 原因 | 解决办法 |
|------|------|----------|
| `invalid API key` | `GOOGLE_API_KEY` 填错了或已过期 | 去 https://aistudio.google.com/apikey 重新获取 |
| `quota exceeded` | 触发了速率限制 | 等几分钟再重新运行 `/gm-asset` |
| 网络超时 | 网络连接有问题 | 检查网络，然后重新运行 `/gm-asset` |

也可以直接运行生成器单独测试：

```bash
python tools/asset_gen.py
```

---

### 生成的美术效果不对

**原因：** AI 图片生成本身就有随机性，每次跑出来的结果可能不一样。

**解决办法：** 重新运行 `/gm-asset`。每次只会重新生成缺失的或你明确标记要重新生成的资源。或者，你也可以把自己的图片直接放进 `assets/` 文件夹（文件名要和 `ASSETS.md` 里列出的一致），然后再运行 `/gm-asset`——分析子 Agent 会检测到你的文件，并跳过这些条目的生成。

---

### 想用自己的美术资源

**解决办法：** 把你的图片文件放进 `assets/` 文件夹，文件名要和 `ASSETS.md` 里列出的一致。然后运行 `/gm-asset`——分析子 Agent 会检查每个文件的尺寸和格式，并在 `ASSETS.md` 里把这些条目标记为"已提供"。不需要删除任何文件，已经存在的资源不会被覆盖。

---

## 评估问题

### 游戏在评估期间崩溃了

**原因：** 代码有 bug 导致 Godot 崩溃。`/gm-evaluate` 会把崩溃前观察到的内容（包括截图和部分测试结果）记录到 `.godotmaker/evaluation.json`。

**解决办法：** 评估器会自动给出低分，并写明失败原因。运行 `/gm-fixgap`——它会读取 `evaluation.json` 并派发 Worker 处理崩溃问题。如果多轮修复后还是崩溃，打开 `evaluation.json` 看 `issues` 数组里的具体报错信息来手动诊断。

---

### 评分太低，无法通过验收

**症状：** `/gm-evaluate` 跑完了，但分数低于验收门槛，`/gm-accept` 显示"拒绝"建议。

**解决办法：** 运行 `/gm-fixgap` 修复评估里列出的问题。fixgap 完成后，再依次运行 `/gm-verify` 和 `/gm-evaluate`。这个循环可以重复多次。分数达到要求后，运行 `/gm-accept` 确认通过。

---

## 发布和版本问题

### "MAJOR upgrade requires --force"

**症状：** 运行 `python tools/publish.py <target>` 时停住了，提示需要处理 MAJOR 版本升级。

**原因：** GodotMaker 仓库版本和游戏项目里已安装版本的主版本号不一致。主版本升级可能包含破坏性变更。

**解决办法：** 先读 `CHANGELOG.md` 了解有什么变化，确认没问题后加上 force 参数运行：

```bash
python tools/publish.py --force <target>
```

注意对 Claude Code 目标，`--force` 会覆盖游戏项目里的 `.claude/settings.json`。如果你对它做过自定义修改，先备份一下。

---

### 降级被阻止了

**症状：** `publish.py` 拒绝把旧版本的 GodotMaker 安装到已有新版本的项目上。

**原因：** 用旧版本覆盖新版本会让 hook 脚本和 skill 倒退，这可能破坏项目的 `.godotmaker/stage.jsonl` 时间线里已经写入的假设。

**解决办法：** 这是有意为之的设计。如果确实需要回退，请从游戏项目的 git 快照里恢复。`publish.py` 不支持降级操作。

---

### 迁移脚本在中途失败了

**症状：** 某个迁移脚本打印了报错并在任何非 MAJOR 的 publish（PATCH / MINOR / SAME 版本重新发布）执行 pending 迁移时中途停下来了。

**解决办法：** 看报错信息，修复根本原因（通常是文件缺失或路径不对），然后重新跑：

```bash
python tools/migrate.py <target>
```

迁移脚本设计上支持重复执行——已完成的步骤会被记录在 `.godotmaker/applied_migrations.json` 里，下次重跑会自动跳过。如果不确定哪一步失败了，运行 `python tools/check_project.py <target>` 查看必要文件的当前状态。

---

### `applied_migrations.json` 损坏了

**症状：** publish 或 `migrate.py` 抛出 `TrackerCorruptionError: ... cannot parse JSON` 或 `... missing required field` 或 `... source must be one of ...`。

**解决办法：** applied-tracker 文件（`<target>/.godotmaker/applied_migrations.json`）无法解析或 schema 不对。三种恢复方式：

1. **从版本控制恢复**（如果用户主动追踪了它）：`git checkout <target>/.godotmaker/applied_migrations.json`。注意 GodotMaker 默认的 `.gitignore` 排除了这个文件，只有用户主动覆盖才会进 VCS。
2. **从当前状态重新开始追踪**：`python tools/migrate.py <target> --baseline`。把当前所有 `migrations/<YYYYMMDDhhmmss>_<slug>.py` 标记为已应用、不实际执行——适合"实际项目状态已经是最新格式"的情况。
3. **删除该文件**：`rm <target>/.godotmaker/applied_migrations.json`。下次 publish 会把它当作 legacy target —— `migrate.py` 自动创建一个空 tracker，然后通过正常路径执行所有 pending 迁移。如果你在 legacy 版本上手动跑过其中某些迁移，它们会再跑一次；如果担心这种情况，请选方案 2（`--baseline`）。

系统在此处显式报错（而不是静默把 tracker 视为空），是因为静默回退会导致下次 publish 重跑全部历史迁移——可能破坏项目状态。
