# 技巧与说明

GodotMaker 中不那么显眼的设计决策和实现细节。
记录在这里是为了防止以后阅读代码时产生困惑。

## Git Worktree 需要初始提交（gm-scaffold）

**是什么：** `/gm-scaffold` 完成脚手架搭建后，必须创建一个初始 git 提交。

**为什么：** Worker 使用 `isolation: "worktree"` 实现并行执行。
Git worktree 要求至少有一个提交——没有提交时会报错：
```
fatal: not a valid object name: 'HEAD'
```
不需要推送到远端，只需要本地提交即可。

**发现经过：** 在 3 个游戏的测试中出现了 3 次失败。当时的应急方案是回退到顺序执行，但根本解决方案就是先提交一次。

## 用户确认使用 runtime 映射提问

**是什么：** 需要人工决策的角色技能（`/gm-scaffold` 询问项目参数、`/gm-gdd` 询问 GDD 审批、`/gm-asset` 询问美术方向确认、`/gm-accept` 询问最终通过/拒绝）必须使用 runtime mapping 中的 `ask_user_question` operation，不能假定当前一定存在 Claude Code 的 `AskUserQuestion` 工具。Claude Code 映射到 `AskUserQuestion`，Codex 映射到 `request_user_input` 或带 gate 的普通提问，OpenCode 映射到 `question`，Pi 使用其文档化的提问回退路径。

**为什么：** 纯文本问题在会话中间很容易被错过或忽略。映射后的 operation 会在 runtime 支持时使用结构化交互，否则停在明确问题或非交互 gate 上，防止角色在无人确认的情况下自行做出假设。
