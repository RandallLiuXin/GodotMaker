# Asset Curation Reference

Curation chooses visual candidates; it does not create a runtime authority.
The only runtime handoff is the validated Asset Skill result registered directly
into the matching rows of `ASSETS.md`.

## Curation records

Store optional candidate reports under `.godotmaker/asset-generation/curation/`.
Record candidate IDs, source images, selection state (`candidate`, `selected`,
`variant`, or `rejected`), and brief notes. Keep these reports as production
evidence only; no consumer resolves them.

## ASSETS.md handoff

Mark rows `generated` only when one complete request-owned output set has:

1. A passed result with every declared output present exactly once.
2. A matching `ASSETS.md` row for every logical output.
3. Existing project-local output files; runtime resources also load as their
   declared Godot type.
4. Curation that is selected when the family requires curation.

Use `tools/asset_result_registration.py` for the atomic update. If any output
is missing, duplicated, unknown, or invalid, leave every row unchanged.
