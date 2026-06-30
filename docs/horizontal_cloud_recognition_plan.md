# Cloud Recognition Plan

## Scope

- Horizontal and vertical images use cloud vision recognition when cloud config is complete.
- Without cloud config, both orientations keep the current local YOLO + OCR flow.
- The cloud API must be OpenAI-compatible and configurable with `base_url`, `api_key`, and `model`.

## Routing

1. Detect image orientation locally.
2. If cloud config is incomplete, use the existing local recognizer.
3. For horizontal images with cloud config, try YOLO cropping with `conf=0.1`.
4. The UI setting can disable horizontal YOLO cropping; if disabled, send the full image directly.
5. If horizontal YOLO is enabled and both `name_area` and `code_area` exist at `conf >= 0.1`, send two cropped images to the model.
6. If either horizontal area is missing, send the full image to the model.
7. If cropped horizontal recognition returns invalid JSON or an unusable result, retry once with the full image.
8. For vertical images with cloud config, send the full image to the model.

## Prompt Strategy

- Use three prompt templates:
  - Horizontal cropped prompt: first image is `name_area`, second image is `code_area`.
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

- `cloud_crop`: recognized from cropped `name_area` + `code_area`.
- `cloud_full`: horizontal image recognized from the full image.
- `cloud_vertical_full`: vertical image recognized from the full image.
- `cloud_retry_full`: cropped recognition failed validation, then full image succeeded.
- `cloud_failed`: cloud recognition failed and the app used the existing manual fallback result.

The UI summary should report counts for horizontal cropped, horizontal full-image, vertical full-image, retry, and failed cloud recognitions.

## Observability

- Each cloud-recognized result stores API prompt tokens, completion tokens, total tokens, image/text token split when available, estimated cost, API elapsed seconds, and model name.
- The app writes a JSON batch log under `logs/recognition_YYYYMMDD_HHMMSS.json`.
- The log redacts the API key and records per-image recognition source, warnings, code count, returned codes, tokens, elapsed time, and estimated cost.
- After each cloud batch, the UI shows a summary dialog with input/output/total kToken, estimated RMB cost, aggregate API elapsed time, and the log path.
