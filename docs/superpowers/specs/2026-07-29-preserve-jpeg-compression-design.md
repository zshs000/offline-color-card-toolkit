# Preserve source JPEG compression when cropping

## Goal

Prevent cropped main images from becoming unnecessarily large while keeping the existing crop geometry and pixel dimensions unchanged.

## Design

- For JPEG input, reuse the source image's JPEG quantization tables and chroma subsampling when saving the cropped image.
- Do not force `quality=100` or `subsampling=0`.
- Leave PNG and other supported formats on their current save path.
- Do not change ruler detection, crop bounds, DPI handling, cloud recognition, naming, concurrency, or UI behavior.

## Verification

- Use local images only; no cloud API calls.
- Confirm a cropped JPEG retains the requested pixel dimensions and can be reopened.
- Confirm output size no longer increases solely because of forced maximum-quality JPEG encoding.

