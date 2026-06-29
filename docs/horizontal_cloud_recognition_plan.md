# Cloud Recognition Plan

## Scope

- Horizontal and vertical images use cloud vision recognition when cloud config is complete.
- Without cloud config, both orientations keep the current local YOLO + OCR flow.
- The cloud API must be OpenAI-compatible and configurable with `base_url`, `api_key`, and `model`.

## Routing

1. Detect image orientation locally.
2. If cloud config is incomplete, use the existing local recognizer.
3. For horizontal images with cloud config, try YOLO cropping with `conf=0.1`.
4. If both horizontal `name_area` and `code_area` exist at `conf >= 0.1`, send two cropped images to the model.
5. If either horizontal area is missing, send the full image to the model.
6. If cropped horizontal recognition returns invalid JSON or an unusable result, retry once with the full image.
7. For vertical images with cloud config, send the full image to the model.

## Prompt Strategy

- Use three prompt templates:
  - Horizontal cropped prompt: first image is `name_area`, second image is `code_area`.
  - Horizontal full-image prompt: one full color-card image.
  - Vertical full-image prompt: one full vertical color-card image; read code columns top-to-bottom, left-to-right.
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
