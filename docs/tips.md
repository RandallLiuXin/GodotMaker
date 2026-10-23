# Tips & Tricks

Non-obvious design decisions and implementation tricks in GodotMaker.
These exist to prevent future confusion when reading the code.

## Git Worktree Requires Initial Commit (gm-scaffold)

**What:** `/gm-scaffold` must create an initial git commit after scaffolding.

**Why:** Workers use `isolation: "worktree"` for parallel execution.
Git worktree requires at least one commit — without it:
```
fatal: not a valid object name: 'HEAD'
```
Push is NOT required, only a local commit.

**Discovered:** 3 failures across 3-game testing. Workaround was falling
back to sequential execution, but the root fix is simply committing first.

## Runtime-Mapped Questions for User Confirmations

**What:** Role skills that need a human decision (`/gm-scaffold` for project
parameters, `/gm-gdd` for GDD approval, `/gm-asset` for art-direction confirmation,
`/gm-accept` for the final go/no-go) must use the runtime mapping's
`ask_user_question` operation, not assume Claude Code's `AskUserQuestion` tool.
Claude Code maps it to `AskUserQuestion`, Codex to `request_user_input` or a
gated normal question, OpenCode to `question`, and Pi to its documented prompt
fallback.

**Why:** Plain-text questions are easy to miss or ignore mid-session.
The mapped operation uses a structured interaction when the runtime provides
one and otherwise stops at an explicit question or non-interactive gate, so the
role does not drift into assumptions.
