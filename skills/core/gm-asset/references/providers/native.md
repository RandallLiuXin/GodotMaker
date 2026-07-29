# Native Image Provider

Use this file only when `.godotmaker/config.yaml` sets
`asset_image_model: native`.

## Contract

1. Use the active coding-agent runtime's native image-generation path.
2. Generate the assigned source image from the production-unit prompt.
3. Save or copy the result to the planned `source_path`.
4. Do not select images by scanning generated-image directories.
5. Do not write outside the paths listed in the production-unit brief.
6. Report the source path, prompt path, and any provider error.

## Reference Images

When the production unit uses image references:

1. Verify that each path is a readable image and attach the actual image to the
   active runtime's native image-generation request.
2. State and preserve the reference role in the prompt and provider report.
3. Record attached path, role, attachment mechanism, and attachment count in
   the provider report.
4. STOP when the active native path cannot attach the supplied image; a textual
   path or a visual inspection by the agent is not an attachment.
5. Preserve the invariants listed by the production-unit doc.
6. Use the planned `source_path` for the generated result.

## Handoff

After generation:

1. Verify the planned source path exists.
2. Run the production-unit processing or finalization steps.
3. Write provider notes to the unit report.
