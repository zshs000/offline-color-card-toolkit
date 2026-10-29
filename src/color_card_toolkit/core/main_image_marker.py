"""最终带标尺主图的 EXIF 处理信息。"""

import json

from PIL import Image

from color_card_toolkit import __version__


def marker_exif(width_cm: int, height_cm: int, origin_x: int, origin_y: int) -> Image.Exif:
    payload = {
        "marker": "leather-main-image",
        "tool_version": __version__,
        "width_cm": width_cm,
        "height_cm": height_cm,
        "origin_x": origin_x,
        "origin_y": origin_y,
    }
    exif = Image.Exif()
    # 使用新 EXIF，避免把扫描原图的方向标记带到已经摆正的输出图。
    exif[34665] = {37510: b"ASCII\x00\x00\x00" + json.dumps(payload).encode("ascii")}
    return exif
