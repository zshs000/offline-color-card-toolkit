from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

import color_card_toolkit.core.image_rename as image_rename_module
from color_card_toolkit.core.image_rename import (
    crop_main_images,
    extract_top_left_name,
    rename_scan_images,
    unique_output_path,
)
from color_card_toolkit.core.models import OcrBlock
from color_card_toolkit.core.ocr_engine import FakeOcrEngine


def block(text: str, x: float, y: float, w: float = 80, h: float = 30) -> OcrBlock:
    return OcrBlock(
        text=text,
        confidence=0.97,
        box=((x, y), (x + w, y), (x + w, y + h), (x, y + h)),
    )


def test_extract_top_left_name_uses_only_top_left_text(tmp_path: Path) -> None:
    image_path = tmp_path / "scan.png"
    Image.new("RGB", (1600, 1000), "white").save(image_path)
    blocks = [
        block("PU6159", 42, 36, 120, 34),
        block("厂家直销", 58, 110, 220, 40),
        block("2024", 1320, 38, 80, 32),
    ]

    assert extract_top_left_name(image_path, blocks) == "PU6159"


def test_unique_output_path_adds_numeric_suffix_for_duplicates(tmp_path: Path) -> None:
    existing = tmp_path / "PU6159.jpg"
    existing.write_bytes(b"existing")

    assert unique_output_path(tmp_path, "PU6159", ".jpg") == tmp_path / "PU6159-2.jpg"


def test_rename_scan_images_copies_original_bytes_with_recognized_name(tmp_path: Path) -> None:
    image_path = tmp_path / "original.jpg"
    Image.new("RGB", (800, 600), "red").save(image_path, quality=91)
    original_bytes = image_path.read_bytes()
    output_dir = tmp_path / "renamed"
    engine = FakeOcrEngine({str(image_path): [block("PU6159", 30, 20)]})

    results = rename_scan_images([image_path], output_dir, engine)

    assert results[0].output_path == output_dir / "PU6159.jpg"
    assert results[0].output_path.read_bytes() == original_bytes
    assert results[0].recognized_name == "PU6159"


def test_parallel_rename_scan_images_reserves_duplicate_output_names(monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    Image.new("RGB", (800, 600), "red").save(first)
    Image.new("RGB", (800, 600), "blue").save(second)
    output_dir = tmp_path / "renamed"
    engine = FakeOcrEngine(
        {
            str(first): [block("PU6159", 30, 20)],
            str(second): [block("PU6159", 30, 20)],
        }
    )
    copy_barrier = threading.Barrier(2)

    def slow_copy(source, destination):
        try:
            copy_barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        Path(destination).write_bytes(Path(source).read_bytes())

    monkeypatch.setattr(image_rename_module.shutil, "copy2", slow_copy)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda path: rename_scan_images([path], output_dir, engine)[0],
                [first, second],
            )
        )

    assert sorted(result.output_path.name for result in results) == ["PU6159-2.jpg", "PU6159.jpg"]


def test_crop_main_images_uses_image_dpi_to_crop_requested_centimeters(tmp_path: Path) -> None:
    image_path = tmp_path / "main.jpg"
    Image.new("RGB", (1600, 1400), "blue").save(image_path, dpi=(254, 254), quality=95)
    output_dir = tmp_path / "cropped"
    engine = FakeOcrEngine({str(image_path): [block("Main01", 100, 120)]})

    results = crop_main_images([image_path], output_dir, engine, crop_size_cm=10)

    assert results[0].output_path == output_dir / "Main01.jpg"
    with Image.open(results[0].output_path) as cropped:
        assert cropped.size == (1000, 1000)
        assert cropped.format == "JPEG"


def test_crop_main_images_crops_from_image_center_not_ocr_text_position(tmp_path: Path) -> None:
    image_path = tmp_path / "main.png"
    image = Image.new("RGB", (1600, 1400), "white")
    for x in range(100, 150):
        for y in range(120, 170):
            image.putpixel((x, y), (255, 0, 0))
    for x in range(300, 350):
        for y in range(200, 250):
            image.putpixel((x, y), (0, 0, 255))
    image.save(image_path, dpi=(254, 254))
    output_dir = tmp_path / "cropped"
    engine = FakeOcrEngine({str(image_path): [block("Main01", 100, 120)]})

    results = crop_main_images([image_path], output_dir, engine, crop_size_cm=10)

    with Image.open(results[0].output_path) as cropped:
        assert cropped.size == (1000, 1000)
        assert cropped.getpixel((0, 0)) == (0, 0, 255)
