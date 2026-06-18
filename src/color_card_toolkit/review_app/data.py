from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class AnnotationBox:
    role: str
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass(frozen=True)
class AnnotationItem:
    item_id: str
    file_name: str
    source_image: str
    default_orientation: str
    orientation: str
    code_column_count: int
    width: int
    height: int
    boxes: list[AnnotationBox]
    complete: bool


def load_annotation_payload(raw_root: Path, annotation_path: Path, repo_root: Path) -> dict[str, object]:
    annotations = load_annotations(annotation_path)
    items = build_annotation_items(raw_root, annotations, repo_root)
    completed = sum(1 for item in items if item.complete)
    return {
        "rawRoot": _to_repo_path(raw_root, repo_root),
        "annotationFile": _to_repo_path(annotation_path, repo_root),
        "items": [
            {
                "itemId": item.item_id,
                "fileName": item.file_name,
                "sourceImage": item.source_image,
                "defaultOrientation": item.default_orientation,
                "orientation": item.orientation,
                "codeColumnCount": item.code_column_count,
                "width": item.width,
                "height": item.height,
                "boxes": [
                    {
                        "role": box.role,
                        "centerX": box.center_x,
                        "centerY": box.center_y,
                        "width": box.width,
                        "height": box.height,
                    }
                    for box in item.boxes
                ],
                "complete": item.complete,
            }
            for item in items
        ],
        "summary": {
            "total": len(items),
            "completed": completed,
            "pending": len(items) - completed,
        },
    }


def load_annotations(annotation_path: Path) -> dict[str, dict[str, object]]:
    if not annotation_path.exists():
        return {}
    try:
        payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    items = payload.get("items", {})
    return items if isinstance(items, dict) else {}


def save_item_annotation(
    annotation_path: Path,
    item_id: str,
    orientation: str,
    boxes: dict[str, dict[str, float]],
    code_column_count: int | None = None,
) -> None:
    payload = load_annotations(annotation_path)
    item_payload: dict[str, object] = {
        "orientation": orientation,
        "boxes": boxes,
    }
    if orientation == "vertical":
        item_payload["codeColumnCount"] = 3 if code_column_count == 3 else 2
    payload[item_id] = item_payload
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(
        json.dumps({"items": payload}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_yolo_dataset(
    raw_root: Path,
    annotation_path: Path,
    export_root: Path,
    repo_root: Path,
) -> dict[str, object]:
    annotations = load_annotations(annotation_path)
    items = build_annotation_items(raw_root, annotations, repo_root)
    if export_root.exists():
        shutil.rmtree(export_root)
    export_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, dict[str, int]] = {
        "horizontal": {"train": 0, "val": 0},
        "vertical": {"train": 0, "val": 0},
    }

    by_orientation = {
        "horizontal": [item for item in items if item.complete and item.orientation == "horizontal"],
        "vertical": [item for item in items if item.complete and item.orientation == "vertical"],
    }

    for orientation, orientation_items in by_orientation.items():
        orientation_root = export_root / orientation
        _prepare_export_dirs(orientation_root)
        manifest_rows: list[list[str]] = []

        for index, item in enumerate(sorted(orientation_items, key=lambda value: value.file_name.lower())):
            split = "val" if index % 5 == 4 else "train"
            summary[orientation][split] += 1

            source_path = repo_root / item.source_image
            image_target = orientation_root / "images" / split / item.file_name
            label_target = orientation_root / "labels" / split / f"{Path(item.file_name).stem}.txt"

            shutil.copy2(source_path, image_target)
            label_target.write_text(_build_yolo_label_text(item), encoding="utf-8")

            manifest_rows.append(
                [
                    item.item_id,
                    orientation,
                    split,
                    item.source_image,
                    _to_repo_path(image_target, repo_root),
                    _to_repo_path(label_target, repo_root),
                    str(item.width),
                    str(item.height),
                    str(len(item.boxes)),
                ]
            )

        _write_manifest(orientation_root / "manifest.csv", manifest_rows)
        _write_data_yaml(orientation_root / "data.yaml", orientation)

    completed_count = sum(1 for item in items if item.complete)
    return {
        "exportRoot": _to_repo_path(export_root, repo_root),
        "annotationFile": _to_repo_path(annotation_path, repo_root),
        "completed": completed_count,
        "total": len(items),
        "summary": summary,
    }


def build_annotation_items(
    raw_root: Path,
    annotations: dict[str, dict[str, object]],
    repo_root: Path,
) -> list[AnnotationItem]:
    items: list[AnnotationItem] = []
    for orientation_dir in ("horizontal", "vertical"):
        folder = raw_root / orientation_dir
        if not folder.exists():
            continue
        for image_path in sorted(_iter_image_files(folder), key=lambda value: value.name.lower()):
            width, height = _read_image_size(image_path)
            item_id = f"{orientation_dir}/{image_path.name}"
            saved = annotations.get(item_id, {})
            orientation = str(saved.get("orientation", orientation_dir))
            raw_boxes = saved.get("boxes", {})
            raw_boxes = raw_boxes if isinstance(raw_boxes, dict) else {}
            code_column_count = _code_column_count(orientation, saved, raw_boxes)
            roles = required_roles(orientation, code_column_count)
            boxes = [
                AnnotationBox(
                    role=role,
                    center_x=float(box["centerX"]),
                    center_y=float(box["centerY"]),
                    width=float(box["width"]),
                    height=float(box["height"]),
                )
                for role, box in sorted(raw_boxes.items(), key=lambda item: roles.index(item[0]) if item[0] in roles else 99)
            ]
            complete = all(role in raw_boxes for role in roles)
            items.append(
                AnnotationItem(
                    item_id=item_id,
                    file_name=image_path.name,
                    source_image=_to_repo_path(image_path, repo_root),
                    default_orientation=orientation_dir,
                    orientation=orientation,
                    code_column_count=code_column_count,
                    width=width,
                    height=height,
                    boxes=boxes,
                    complete=complete,
                )
            )
    return items


def required_roles(orientation: str, code_column_count: int = 2) -> list[str]:
    if orientation == "vertical":
        if code_column_count == 3:
            return ["name_area", "code_area_left", "code_area_middle", "code_area_right"]
        return ["name_area", "code_area_left", "code_area_right"]
    return ["name_area", "code_area"]


def role_label(role: str) -> str:
    labels = {
        "name_area": "左上标签",
        "code_area": "数字区域",
        "code_area_left": "左数字",
        "code_area_middle": "中数字",
        "code_area_right": "右数字",
    }
    return labels.get(role, role)


def _iter_image_files(folder: Path) -> list[Path]:
    return [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]


def _read_image_size(image_path: Path) -> tuple[int, int]:
    with Image.open(image_path) as image:
        return image.size


def _prepare_export_dirs(root: Path) -> None:
    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)


def _build_yolo_label_text(item: AnnotationItem) -> str:
    role_to_box = {box.role: box for box in item.boxes}

    lines = []
    for role in required_roles(item.orientation, item.code_column_count):
        box = role_to_box[role]
        class_id = 0 if role == "name_area" else 1
        lines.append(
            f"{class_id} {box.center_x:.6f} {box.center_y:.6f} {box.width:.6f} {box.height:.6f}"
        )
    return "\n".join(lines) + "\n"


def _write_manifest(manifest_path: Path, rows: list[list[str]]) -> None:
    header = "item_id,orientation,split,source_image,image,label,width,height,box_count\n"
    body = "\n".join(",".join(_csv_escape(value) for value in row) for row in rows)
    manifest_path.write_text(header + body + ("\n" if body else ""), encoding="utf-8-sig")


def _write_data_yaml(yaml_path: Path, orientation: str) -> None:
    names = ["0: name_area", "1: code_area"]
    yaml_path.write_text(
        "\n".join(
            [
                "path: .",
                "train: images/train",
                "val: images/val",
                "names:",
                *[f"  {line}" for line in names],
                "",
            ]
        ),
        encoding="utf-8",
    )


def _csv_escape(value: str) -> str:
    if any(char in value for char in [",", '"', "\n"]):
        return '"' + value.replace('"', '""') + '"'
    return value


def _code_column_count(
    orientation: str,
    saved: dict[str, object],
    raw_boxes: dict[str, object],
) -> int:
    if orientation != "vertical":
        return 2
    saved_count = saved.get("codeColumnCount")
    if saved_count in {3, "3"}:
        return 3
    if saved_count in {2, "2"}:
        return 2
    return 3 if "code_area_middle" in raw_boxes else 2


def _to_repo_path(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
