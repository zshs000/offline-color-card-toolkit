from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BoxInfo:
    role: str
    class_id: int
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass(frozen=True)
class ReviewItem:
    item_id: str
    orientation: str
    split: str
    source_image: str
    output_image: str
    preview_image: str
    label_path: str
    width: int
    height: int
    box_count: int
    boxes: list[BoxInfo]


@dataclass(frozen=True)
class BoxFeedback:
    role: str
    note: str = ""


@dataclass(frozen=True)
class ItemFeedback:
    item_id: str
    whole_image_bad: bool = False
    note: str = ""
    box_feedback: list[BoxFeedback] = field(default_factory=list)


@dataclass(frozen=True)
class ExportBundle:
    structured_text: str
    human_text: str


def load_review_items(dataset_root: Path) -> list[ReviewItem]:
    manifest_path = dataset_root / "manifest.csv"
    rows = list(csv.DictReader(manifest_path.open(encoding="utf-8-sig")))
    items: list[ReviewItem] = []
    for row in rows:
        label_path = Path(row["label"])
        boxes = _load_boxes(label_path, row["orientation"], int(row["box_count"]))
        items.append(
            ReviewItem(
                item_id=Path(row["output_image"]).stem,
                orientation=row["orientation"],
                split=row["split"],
                source_image=row["source_image"],
                output_image=row["output_image"],
                preview_image=row["preview"],
                label_path=row["label"],
                width=int(row["width"]),
                height=int(row["height"]),
                box_count=int(row["box_count"]),
                boxes=boxes,
            )
        )
    return items


def build_export_bundle(items: list[ItemFeedback]) -> ExportBundle:
    structured_lines: list[str] = []
    human_lines: list[str] = []
    for item in items:
        fragments: list[str] = []
        if item.whole_image_bad:
            line = f"{item.item_id} | whole_image_bad"
            if item.note.strip():
                line += f" | note={item.note.strip()}"
                fragments.append(f"whole image: {item.note.strip()}")
            else:
                fragments.append("whole image")
            structured_lines.append(line)
        for box in item.box_feedback:
            line = f"{item.item_id} | {box.role}"
            if box.note.strip():
                line += f" | note={box.note.strip()}"
                fragments.append(f"{box.role}: {box.note.strip()}")
            else:
                fragments.append(box.role)
            structured_lines.append(line)
        if fragments:
            human_lines.append(f"{item.item_id}: " + "; ".join(fragments))
    return ExportBundle(
        structured_text="\n".join(structured_lines),
        human_text="\n".join(human_lines),
    )


def _load_boxes(label_path: Path, orientation: str, box_count: int) -> list[BoxInfo]:
    raw_boxes: list[BoxInfo] = []
    for index, line in enumerate(label_path.read_text(encoding="utf-8").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        class_id_s, center_x_s, center_y_s, width_s, height_s = stripped.split()
        raw_boxes.append(
            BoxInfo(
                role=_role_for_box(index, orientation, box_count),
                class_id=int(class_id_s),
                center_x=float(center_x_s),
                center_y=float(center_y_s),
                width=float(width_s),
                height=float(height_s),
            )
        )
    return raw_boxes


def _role_for_box(index: int, orientation: str, box_count: int) -> str:
    if index == 0:
        return "name_area"
    if orientation == "horizontal":
        return "code_area"
    if box_count == 4:
        roles = ["name_area", "code_area_left", "code_area_middle", "code_area_right"]
        return roles[index]
    roles = ["name_area", "code_area_left", "code_area_right"]
    return roles[index]
