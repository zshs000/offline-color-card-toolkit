from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, JpegImagePlugin

from color_card_toolkit import __version__
from color_card_toolkit.core.image_rename import crop_image_from_geometry
from color_card_toolkit.core.ruler_detection import RulerGeometry


@pytest.mark.parametrize("width_cm,height_cm", [(10, 10), (15, 15), (5, 5), (5, 10), (10, 5)])
@pytest.mark.parametrize("image_format", ["JPEG", "PNG"])
def test_crop_marker_matches_final_pixels_and_survives_copy(tmp_path, width_cm, height_cm, image_format):
    source = tmp_path / ("source.jpg" if image_format == "JPEG" else "source.png")
    output = tmp_path / ("crop" + source.suffix)
    image = Image.new("RGB", (1800, 1800), (80, 100, 120))
    # 带方向的输入先摆正；输出 EXIF 不再要求客户端旋转。
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, image_format, dpi=(254, 254), exif=exif)
    geometry = RulerGeometry(
        origin=(100, 120), rotation_degrees=0, spacing_x=10, spacing_y=10,
        span_mm=150, top_support=151, left_support=151,
        top_inlier_ratio=1, left_inlier_ratio=1,
    )
    crop_image_from_geometry(source, output, width_cm, height_cm, geometry)
    copied = tmp_path / ("改名后" + source.suffix)
    shutil.copy2(output, copied)
    assert copied.read_bytes() == output.read_bytes()
    with Image.open(copied) as cropped:
        marker = json.loads(cropped.getexif().get_ifd(34665)[37510][8:])
        assert marker == {
            "marker": "leather-main-image", "tool_version": __version__,
            "width_cm": width_cm, "height_cm": height_cm, "origin_x": 100, "origin_y": 120,
        }
        assert cropped.getexif().get(274, 1) == 1
        assert cropped.size == (100 + width_cm * 100, 120 + height_cm * 100)
        assert cropped.crop((100, 120, cropped.width, cropped.height)).size == (width_cm * 100, height_cm * 100)
        if image_format == "PNG":
            assert cropped.getpixel((100, 120)) == (80, 100, 120)
        else:
            with Image.open(source) as original:
                assert cropped.quantization == original.quantization
                assert JpegImagePlugin.get_sampling(cropped) == JpegImagePlugin.get_sampling(original)


def test_source_and_frozen_versions_follow_project_file(monkeypatch, tmp_path):
    from color_card_toolkit import _project_version

    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert f'version = "{__version__}"' in project.read_text(encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.1.2"\n', encoding="utf-8")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys._MEIPASS", str(tmp_path), raising=False)
    assert _project_version() == "1.1.2"
