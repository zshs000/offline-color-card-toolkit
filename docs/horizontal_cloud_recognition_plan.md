# Horizontal Cloud Recognition Plan

## Scope

- Only horizontal images use cloud vision recognition.
- Vertical images keep the current local YOLO + OCR flow.
- The cloud API must be OpenAI-compatible and configurable with `base_url`, `api_key`, and `model`.

## Routing

1. Detect image orientation locally.
2. For vertical images, use the existing local recognizer.
3. For horizontal images, try YOLO cropping with `conf=0.1`.
4. If both `name_area` and `code_area` exist at `conf >= 0.1`, send two cropped images to the model.
5. If either area is missing, send the full image to the model.
6. If cropped recognition returns invalid JSON or an unusable result, retry once with the full image.

## Prompt Strategy

- Use two prompt templates:
  - Cropped prompt: first image is `name_area`, second image is `code_area`.
  - Full-image prompt: one full color-card image.
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
- The app does not compute or warn about suspected missing codes for cloud-recognized horizontal images.

## Metrics

Each horizontal cloud result records:

- `cloud_crop`: recognized from cropped `name_area` + `code_area`.
- `cloud_full`: recognized from the full image.
- `cloud_retry_full`: cropped recognition failed validation, then full image succeeded.
- `cloud_failed`: cloud recognition failed and the app used the existing manual fallback result.

The UI summary should report counts for cropped, full-image, retry, and failed cloud recognitions.
