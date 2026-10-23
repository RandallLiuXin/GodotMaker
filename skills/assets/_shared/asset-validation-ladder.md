# Asset Validation Ladder

Validation proves a produced result before `/gm-asset` records it in
`ASSETS.md`. It never writes catalog rows, indexes, or worker handoff data.

Runtime outputs pass L0-L4 in order: contract/result shape, processed source,
native artifact compilation, real headless Godot load/type verification, and
type-specific structure verification. A failure prevents registration. Source
and reference outputs remain production evidence and do not enter worker
runtime handoff or create `ASSETS.md` rows.

Compile receipts, source layout details, provider traces, and validation reports
are production evidence. They remain in the result/report and never widen the
worker snapshot, which contains only final artifact type and path.
