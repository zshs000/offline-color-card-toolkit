from __future__ import annotations

import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, JpegImagePlugin

import color_card_toolkit.core.image_rename as image_rename_module
from color_card_toolkit.core.image_rename import (
    crop_main_images,
    extract_top_left_name,
    rename_scan_images,
    unique_output_path,
)
from color_card_toolkit.core.models import OcrBlock
from color_card_toolkit.core.ocr_engine import FakeOcrEngine
from color_card_toolkit.core.ruler_detection import detect_ruler


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


def test_extract_top_left_name_uses_exif_transposed_display_size(tmp_path: Path) -> None:
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (100, 300), "white")
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, exif=exif)
    blocks = [
        block("0951", 20, 2, 80, 20),
    ]

    assert Image.open(image_path).size == (100, 300)
    assert ImageOps.exif_transpose(Image.open(image_path)).size == (300, 100)
    assert extract_top_left_name(image_path, blocks) == "0951"


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


def test_rename_scan_images_sends_exif_transposed_image_to_ocr(tmp_path: Path) -> None:
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (100, 300), "red")
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, exif=exif, quality=91)
    original_bytes = image_path.read_bytes()
    output_dir = tmp_path / "renamed"

    class RecordingEngine:
        seen_shape = None

        def recognize(self, image_path):
            raise AssertionError("path OCR should not be used when image-object OCR is available")

        def recognize_image_object(self, image):
            self.seen_shape = np.array(image).shape
            return [block("0951", 20, 2, 80, 20)]

    engine = RecordingEngine()

    results = rename_scan_images([image_path], output_dir, engine)

    assert engine.seen_shape[:2] == (100, 300)
    assert results[0].output_path == output_dir / "0951.jpg"
    assert results[0].output_path.read_bytes() == original_bytes


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


def test_crop_main_images_preserves_source_jpeg_compression(tmp_path: Path) -> None:
    image_path = tmp_path / "main.jpg"
    Image.new("RGB", (1600, 1400), "blue").save(
        image_path,
        dpi=(254, 254),
        quality=84,
        subsampling=2,
    )
    with Image.open(image_path) as source:
        source_qtables = source.quantization
        source_sampling = JpegImagePlugin.get_sampling(source)

    results = crop_main_images(
        [image_path],
        tmp_path / "cropped",
        FakeOcrEngine({str(image_path): [block("Main01", 100, 120)]}),
        crop_size_cm=10,
    )

    with Image.open(results[0].output_path) as cropped:
        assert cropped.size == (1000, 1000)
        assert cropped.quantization == source_qtables
        assert JpegImagePlugin.get_sampling(cropped) == source_sampling


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


def test_crop_main_images_keeps_top_and_left_rulers_when_detected(tmp_path: Path) -> None:
    image_path = tmp_path / "measured-main.png"
    image = Image.new("RGB", (1600, 1400), "white")
    pixels = image.load()
    for x in range(120, image.width):
        for y in range(100, image.height):
            pixels[x, y] = (0, 0, 255)
    image.save(image_path, dpi=(254, 254))
    output_dir = tmp_path / "cropped"

    results = crop_main_images(
        [image_path],
        output_dir,
        None,
        crop_size_cm=10,
        name_recognizer=lambda path: "P420",
    )

    assert results[0].output_path == output_dir / "P420.png"
    assert results[0].warnings == []
    with Image.open(results[0].output_path) as cropped:
        assert abs(cropped.width - 1120) <= 2
        assert abs(cropped.height - 1100) <= 2
        assert cropped.getpixel((20, 200)) == (255, 255, 255)
        assert cropped.getpixel((200, 200)) == (0, 0, 255)


def test_crop_main_images_uses_tick_ruler_origin_when_detected(tmp_path: Path) -> None:
    width, height = 5600, 5200
    origin_x, origin_y = 300, 250
    spacing = 800 / 25.4
    array = np.full((height, width, 3), 255, dtype=np.uint8)
    array[:origin_y, :, :] = 200
    array[:, :origin_x, :] = 200
    for index in range(156):
        x0 = round(origin_x + index * spacing)
        array[30:origin_y, x0 - 1 : x0 + 3, :] = 0
    for index in range(153):
        y0 = round(origin_y + index * spacing)
        array[y0 - 1 : y0 + 3, 30:origin_x, :] = 0
    image_path = tmp_path / "ruled-main.png"
    Image.fromarray(array, "RGB").save(image_path, dpi=(800, 800))
    output_dir = tmp_path / "cropped"

    results = crop_main_images(
        [image_path],
        output_dir,
        None,
        crop_size_cm=10,
        name_recognizer=lambda path: "RULER01",
    )

    assert results[0].output_path == output_dir / "RULER01.png"
    assert results[0].warnings == []
    with Image.open(results[0].output_path) as cropped:
        assert abs(cropped.width - 3450) <= 2
        assert abs(cropped.height - 3400) <= 2
        assert cropped.getpixel((0, 0)) == (200, 200, 200)
        assert cropped.getpixel((200, 200)) == (200, 200, 200)
        assert cropped.getpixel((400, 300)) == (255, 255, 255)


def _synthetic_ruler_image(ticks: int, tilt_degrees: float = 0.0) -> Image.Image:
    width, height = 5600, 5200
    origin_x, origin_y = 300, 250
    spacing = 800 / 25.4
    slope = math.tan(math.radians(tilt_degrees))
    array = np.full((height, width, 3), 255, dtype=np.uint8)
    array[:origin_y, :, :] = 200
    array[:, :origin_x, :] = 200
    for index in range(ticks):
        x0 = round(origin_x + index * spacing)
        y_end = round(origin_y + (x0 - origin_x) * slope)
        array[30:y_end, x0 - 1 : x0 + 3, :] = 0
    for index in range(ticks):
        y0 = round(origin_y + index * spacing)
        x_end = round(origin_x + (y0 - origin_y) * slope)
        array[y0 - 1 : y0 + 3, 30:x_end, :] = 0
    return Image.fromarray(array, "RGB")


def _crop_synthetic_ruler_to_span(span_mm: int) -> Image.Image:
    spacing = 800 / 25.4
    image = _synthetic_ruler_image(ticks=156)
    return image.crop(
        (
            0,
            0,
            round(300 + span_mm * spacing),
            round(250 + span_mm * spacing),
        )
    )


def test_detect_ruler_identifies_100mm_output_automatically() -> None:
    geometry = detect_ruler(_crop_synthetic_ruler_to_span(100))

    assert geometry is not None
    assert geometry.healthy
    assert geometry.span_mm == 100


def test_detect_ruler_identifies_150mm_output_automatically() -> None:
    geometry = detect_ruler(_crop_synthetic_ruler_to_span(150))

    assert geometry is not None
    assert geometry.healthy
    assert geometry.span_mm == 150


def test_crop_main_images_rotates_tilted_ruler_using_detected_geometry(tmp_path: Path) -> None:
    image_path = tmp_path / "tilted-ruler.png"
    _synthetic_ruler_image(ticks=156, tilt_degrees=0.8).save(image_path, dpi=(800, 800))
    output_dir = tmp_path / "cropped"

    results = crop_main_images(
        [image_path],
        output_dir,
        None,
        crop_size_cm=10,
        name_recognizer=lambda path: "TILT01",
    )

    assert results[0].warnings == []
    with Image.open(results[0].output_path) as cropped:
        assert abs(cropped.width - 3454) <= 4
        assert abs(cropped.height - 3474) <= 4


def test_crop_main_images_warns_when_ruler_detection_unhealthy(tmp_path: Path) -> None:
    image_path = tmp_path / "short-ruler.png"
    _synthetic_ruler_image(ticks=80).save(image_path, dpi=(800, 800))
    output_dir = tmp_path / "cropped"

    results = crop_main_images(
        [image_path],
        output_dir,
        None,
        crop_size_cm=10,
        name_recognizer=lambda path: "SHORT01",
    )

    assert results[0].output_path.exists()
    assert any("标尺刻度检测可靠性偏低" in warning for warning in results[0].warnings)


def test_crop_main_images_can_require_a_reliable_ruler(tmp_path: Path) -> None:
    image_path = tmp_path / "without-ruler.png"
    Image.new("RGB", (1600, 1400), "blue").save(image_path, dpi=(254, 254))
    output_dir = tmp_path / "cropped"

    results = crop_main_images(
        [image_path],
        output_dir,
        None,
        crop_size_cm=10,
        name_recognizer=lambda path: "NO-RULER",
        allow_ruler_fallback=False,
    )

    assert results == []
    assert not list(output_dir.glob("*"))
