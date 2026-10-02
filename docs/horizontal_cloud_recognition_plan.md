# Cloud Recognition Plan

> Historical plan: local YOLO fallback and optional horizontal YOLO cropping are retired by the [2026-10-02 decision](decisions/2026-10-02-remove-yolo-runtime.md). Both orientations now use full-image cloud recognition; trained models remain archived.

## Scope

- Horizontal and vertical images always use full-image cloud vision recognition when cloud config is complete.
- Without cloud config, the UI asks the user to configure Base URL, API Key, and Model; it does not start local YOLO/OCR recognition.
- The cloud API must be OpenAI-compatible and configurable with `base_url`, `api_key`, and `model`.

## Routing

1. Detect image orientation locally.
2. If cloud config is incomplete, show a configuration warning and stop.
3. For horizontal images, send the full image to the model with the full-image prompt.
4. For vertical images, send the full image to the model with the vertical prompt.

## Prompt Strategy

- Use two prompt templates:
  - Horizontal full-image prompt: one full color-card image.
  - Vertical full-image prompt: one full vertical color-card image; detect whether there are 2 or 3 code columns, preserve skipped numeric codes, preserve alphanumeric codes such as `A1`, and return the `codes` array column-by-column from left to right, each column top-to-bottom.
- The model returns only JSON:

```json
{
  "raw_name": "",
  "base_name": "",
  "sequence": null,
  "codes": []
}
```

## Validation

- JSON must parse successfully.
- `raw_name` must be non-empty.
- `codes` must contain at least three values.
- Codes are stored as strings.
- The app does not compute or warn about suspected missing codes for cloud-recognized images.

## Metrics

Each cloud result records:

- `cloud_full`: horizontal image recognized from the full image.
- `cloud_vertical_full`: vertical image recognized from the full image.
- `cloud_failed`: cloud recognition failed and the app used the existing manual fallback result.

The UI summary reports counts for horizontal full-image, vertical full-image, and failed cloud recognitions.

## Observability

- Each cloud-recognized result stores API prompt tokens, completion tokens, total tokens, image/text token split when available, estimated cost, API elapsed seconds, and model name.
- The app writes a JSON batch log under `logs/recognition_YYYYMMDD_HHMMSS.json`.
- The log redacts the API key and records per-image recognition source, warnings, code count, returned codes, tokens, elapsed time, and estimated cost.
- After each cloud batch, the UI shows a summary dialog with input/output/total kToken, estimated RMB cost, aggregate API elapsed time, and the log path.
