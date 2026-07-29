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

1. Validate each local reference image path before generation.
2. Pass each image as a real attachment through the active runtime's native
   image-generation API; making it visible or writing its path into text is not
   sufficient.
3. State and preserve the reference role and invariants in the provider report.
4. If the runtime has no image-attachment path, stop the affected asset. Do not
   omit the reference, switch providers, or create a substitute image.
5. Use the planned `source_path` for the generated result.

## Handoff

After generation:

1. Verify the planned source path exists.
2. Run the production-unit processing or finalization steps.
3. Write provider notes to the unit report.
