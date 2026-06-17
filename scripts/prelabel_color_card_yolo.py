from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
CLASSES = ["name_area", "code_area"]
COLORS = {
    0: (255, 80, 80),
    1: (60, 140, 255),
}


@dataclass(frozen=True)
class SourceSet:
    orientation: str
    folder: Path


@dataclass(frozen=True)
class Box:
    class_id: int
    x1: float
    y1: float
    x2: float
    y2: float

    def to_yolo(self) -> str:
        cx = (self.x1 + self.x2) / 2
        cy = (self.y1 + self.y2) / 2
        width = self.x2 - self.x1
        height = self.y2 - self.y1
        return f"{self.class_id} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-label color-card ROI boxes in YOLO format.")
    parser.add_argument("--output", type=Path, default=Path("datasets/color_card_roi"))
    parser.add_argument("--horizontal", type=Path, default=Path("\u6a2a\u7248\u6d4b\u8bd5"))
    parser.add_argument("--vertical", type=Path, default=Path("\u7ad6\u7248\u6d4b\u8bd5"))
    parser.add_argument("--val-every", type=int, default=5)
    args = parser.parse_args()

    source_sets = [
        SourceSet("horizontal", args.horizontal),
        SourceSet("vertical", args.vertical),
    ]
    output = args.output
    _ensure_dirs(output)
    rows: list[dict[str, str]] = []
    for source_set in source_sets:
        paths = _image_paths(source_set.folder)
        for index, source_path in enumerate(paths, start=1):
            split = "val" if index % args.val_every == 0 else "train"
            image_name = _output_image_name(source_set.orientation, index, source_path)
            image_output = output / "images" / split / image_name
            label_output = output / "labels" / split / f"{Path(image_name).stem}.txt"
            preview_output = output / "preview" / source_set.orientation / f"{Path(image_name).stem}_preview.jpg"

            shutil.copy2(source_path, image_output)
            boxes = _boxes_for_image(source_set.orientation, source_path)
            label_output.write_text("\n".join(box.to_yolo() for box in boxes) + "\n", encoding="utf-8")
            _draw_preview(image_output, boxes, preview_output)

            with Image.open(source_path) as image:
                width, height = image.size
            rows.append(
                {
                    "output_image": image_output.as_posix(),
                    "label": label_output.as_posix(),
                    "preview": preview_output.as_posix(),
                    "source_image": source_path.as_posix(),
                    "orientation": source_set.orientation,
                    "split": split,
                    "width": str(width),
                    "height": str(height),
                    "box_count": str(len(boxes)),
                }
            )

    _write_data_yaml(output)
    _write_manifest(output, rows)
    print(f"Wrote {len(rows)} images to {output.as_posix()}")
    return 0


def _ensure_dirs(output: Path) -> None:
    for relative in [
        "images/train",
        "images/val",
        "labels/train",
        "labels/val",
        "preview/horizontal",
        "preview/vertical",
    ]:
        (output / relative).mkdir(parents=True, exist_ok=True)


def _image_paths(folder: Path) -> list[Path]:
    if not folder.exists():
        raise FileNotFoundError(folder)
    return sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)


def _output_image_name(orientation: str, index: int, source_path: Path) -> str:
    digest = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:8]
    return f"{orientation}_{index:04d}_{digest}{source_path.suffix.lower()}"


def _boxes_for_image(orientation: str, source_path: Path) -> list[Box]:
    if orientation == "horizontal":
        return [
            Box(0, 0.010, 0.000, 0.129, 0.100),
            Box(1, 0.000, 0.340, 1.000, 0.420),
        ]
    if orientation == "vertical":
        return [
            Box(0, 0.026, 0.000, 0.150, 0.045),
            Box(1, 0.132, 0.238, 0.178, 0.962),
            Box(1, 0.879, 0.238, 0.943, 0.962),
        ]
    raise ValueError(f"Unknown orientation: {orientation}")


def _draw_preview(image_path: Path, boxes: list[Box], output_path: Path) -> None:
    with Image.open(image_path) as image:
        width, height = image.size
        preview = image.convert("RGB")
    draw = ImageDraw.Draw(preview)
    line_width = max(4, min(width, height) // 250)
    for box in boxes:
        color = COLORS[box.class_id]
        x1 = _clamp(box.x1 * width, 0, width)
        y1 = _clamp(box.y1 * height, 0, height)
        x2 = _clamp(box.x2 * width, 0, width)
        y2 = _clamp(box.y2 * height, 0, height)
        draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)
        _draw_label(draw, CLASSES[box.class_id], x1, y1, color)
    preview.save(output_path, quality=92)


def _draw_label(draw: ImageDraw.ImageDraw, text: str, x: float, y: float, color: tuple[int, int, int]) -> None:
    text_box = draw.textbbox((x, y), text)
    pad = 6
    label_width = text_box[2] - text_box[0] + pad * 2
    label_height = text_box[3] - text_box[1] + pad * 2
    top = max(0.0, y - label_height)
    draw.rectangle((x, top, x + label_width, max(top, y)), fill=color)
    draw.text((x + pad, top + pad), text, fill=(255, 255, 255))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _write_data_yaml(output: Path) -> None:
    dataset_path = output.resolve().as_posix()
    output.joinpath("data.yaml").write_text(
        "\n".join(
            [
                f"path: {dataset_path}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: name_area",
                "  1: code_area",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_manifest(output: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "output_image",
        "label",
        "preview",
        "source_image",
        "orientation",
        "split",
        "width",
        "height",
        "box_count",
    ]
    with output.joinpath("manifest.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def redraw_preview(image_path: Path, label_path: Path, output_path: Path) -> None:
    boxes: list[Box] = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        class_id_s, cx_s, cy_s, width_s, height_s = stripped.split()
        class_id = int(class_id_s)
        cx = float(cx_s)
        cy = float(cy_s)
        width = float(width_s)
        height = float(height_s)
        boxes.append(
            Box(
                class_id=class_id,
                x1=cx - width / 2,
                y1=cy - height / 2,
                x2=cx + width / 2,
                y2=cy + height / 2,
            )
        )
    _draw_preview(image_path, boxes, output_path)


if __name__ == "__main__":
    raise SystemExit(main())
