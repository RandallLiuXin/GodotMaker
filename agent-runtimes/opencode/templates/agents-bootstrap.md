Before executing any GodotMaker stage skill in OpenCode, apply the OpenCode
runtime mapping at `.opencode/references/runtime-mapping.md`. Shared
GodotMaker docs may use `/gm-*` and Claude-shaped paths as surface vocabulary;
resolve them through that mapping before acting.

For `.godotmaker/*` and `.opencode/*` state files, follow the OpenCode
dot-directory file-check rule in the runtime mapping before treating a missing
Glob result as authoritative.
