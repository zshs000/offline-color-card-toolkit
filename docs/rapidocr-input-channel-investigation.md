# RapidOCR 输入类型导致 `9` 识别成 `6` 的调查记录

日期：2026-06-21

## 背景

横版 YOLO 接入测试时，`PU-6157(1).jpg` 的数字区域已经被完整裁剪出来，但 OCR 结果出现：

```text
1, 2, 3, 4, 5, 6, 7, 8, 6, 10, 11, ...
```

图片上第 9 个数字肉眼明确是 `9`，但 OCR 把它识别成了 `6`，导致 parser 报：

```text
疑似缺少：9
```

## 结论

这不是 YOLO 框的问题，也不是标注框的问题。

根因是当前安装的 `rapidocr-onnxruntime==1.4.4` 对不同输入类型走了不同的颜色通道处理路径：

- 传 `PIL.Image` 或图片文件路径：RapidOCR 会把 RGB 转成 BGR
- 传 `np.ndarray`：RapidOCR 原样使用，不做 RGB/BGR 转换
- 在 `PU-6157(1).jpg` 这张数字条上，BGR 输入会稳定把第 9 位 `9` 识别成 `6`
- RGB ndarray 或灰度 ndarray 输入能稳定识别成 `9`

因此，横版数字条 OCR 应优先传 `np.ndarray`，或者传灰度预处理后的 `np.ndarray`，不要直接传 `PIL.Image` 或文件路径。

## 源码依据

本地包路径：

```text
.venv/Lib/site-packages/rapidocr_onnxruntime/utils/load_image.py
```

关键代码：

```python
InputType = Union[str, np.ndarray, bytes, Path, Image.Image]

def load_img(self, img: InputType) -> np.ndarray:
    if isinstance(img, (str, Path)):
        self.verify_exist(img)
        img = self.img_to_ndarray(Image.open(img))
        return img

    if isinstance(img, np.ndarray):
        return img

    if isinstance(img, Image.Image):
        return self.img_to_ndarray(img)

def convert_img(self, img: np.ndarray, origin_img_type: Any) -> np.ndarray:
    if img.ndim == 3:
        channel = img.shape[2]
        if channel == 3:
            if issubclass(origin_img_type, (str, Path, bytes, Image.Image)):
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            return img
```

这说明：

- 文件路径和 `PIL.Image` 会被当成 RGB 来源，然后转成 BGR
- `np.ndarray` 不会被转色彩通道

## 实验 1：同一张图、同一个 crop，三种输入方式对照

实验对象：

```text
datasets/raw_images/horizontal/PU-6157(1).jpg
```

当前横版 YOLO 后处理得到的数字区 crop：

```text
crop_box = (0, 499, 4277, 632)
size = (4277, 133)
```

保存的临时 crop：

```text
tmp_pu6157_ocr_crops/01_raw_code_crop.png
```

实验脚本核心逻辑：

```python
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

from color_card_toolkit.core.layout_detection import detect_horizontal_layout, _crop_with_padding
from color_card_toolkit.core.ocr_engine import RapidOcrEngine

image_path = Path("datasets/raw_images/horizontal/PU-6157(1).jpg")
engine = RapidOcrEngine(intra_op_num_threads=1, inter_op_num_threads=1)
layout = detect_horizontal_layout(image_path, engine)
det = layout.code_detections[0]

with Image.open(image_path) as im:
    im = ImageOps.exif_transpose(im).convert("RGB")
    crop, offset = _crop_with_padding(im, det, pad_x=0.0, pad_y=0.01)

def summarize(blocks):
    ordered = sorted(blocks, key=lambda b: b.center_x)
    return [b.text for b in ordered]

for i in range(5):
    print("memory", i, summarize(engine.recognize_image_object(crop)))

for i in range(5):
    print("numpy", i, summarize(engine.recognize_image_object(np.array(crop))))

tmp_path = Path("tmp_pu6157_ocr_crops/recheck_memory_crop.png")
crop.save(tmp_path)
for i in range(5):
    print("file", i, summarize(engine.recognize(tmp_path)))
```

实验结果：

```text
memory 0 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
memory 1 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
memory 2 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
memory 3 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
memory 4 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]

numpy 0 ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]
numpy 1 ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]
numpy 2 ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]
numpy 3 ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]
numpy 4 ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]

file 0 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
file 1 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
file 2 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
file 3 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
file 4 ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
```

结论：

- `PIL.Image` 输入：稳定错
- 文件路径输入：稳定错
- `np.ndarray` 输入：稳定对

## 实验 2：确认是否就是 RGB/BGR 通道差异

实验脚本：

```python
import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageOps

from color_card_toolkit.core.layout_detection import detect_horizontal_layout, _crop_with_padding
from color_card_toolkit.core.ocr_engine import RapidOcrEngine

image_path = Path("datasets/raw_images/horizontal/PU-6157(1).jpg")
engine = RapidOcrEngine(intra_op_num_threads=1, inter_op_num_threads=1)
layout = detect_horizontal_layout(image_path, engine)
det = layout.code_detections[0]

with Image.open(image_path) as im:
    im = ImageOps.exif_transpose(im).convert("RGB")
    crop, _ = _crop_with_padding(im, det, pad_x=0.0, pad_y=0.01)

rgb = np.array(crop)
bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

def texts(inp):
    blocks = engine.recognize_image_object(inp)
    return [b.text for b in sorted(blocks, key=lambda b: b.center_x)]

print("PIL", texts(crop))
print("RGB ndarray", texts(rgb))
print("BGR ndarray", texts(bgr))
print("GRAY ndarray", texts(gray))
```

实验结果：

```text
PIL          ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
RGB ndarray  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]
BGR ndarray  ['1', '2', '3', '4', '5', '6', '7', '8', '6', '10', ...]
GRAY ndarray ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', ...]
```

结论：

- 错误和 BGR 输入高度相关
- RGB ndarray 和灰度 ndarray 都能把第 9 位识别成 `9`
- `PIL.Image` 和文件路径之所以错，是因为 RapidOCR 在内部把它们转成了 BGR

## 为什么会这样

RapidOCR 的输入管线对不同输入类型并不完全等价。

对于 `PIL.Image` / 文件路径，它假设来源是 RGB，然后转成 OpenCV 常用的 BGR。对于 `np.ndarray`，它默认调用者已经准备好了需要的数组，因此不再转换。

在这张横版数字条上，数字本身是深灰，背景是偏浅色，但局部有纸张纹理、边界线、压缩噪声。`9` 和 `6` 的形状本来接近，颜色通道变化会改变模型看到的局部灰度/对比特征，于是 BGR 路径稳定把 `9` 看成 `6`。

这不是说所有图片都必须用 RGB ndarray，也不是说 RapidOCR 整体有 bug。准确说法是：

> 在当前项目、当前 RapidOCR 版本、当前横版数字条 crop 上，RGB/GRAY ndarray 比 PIL/path 输入更稳定。

## 对项目的建议

横版 YOLO 接入时：

1. `code_area` 仍由 YOLO 定位上下边界
2. 横向按业务规则扩到整张图宽度
3. 数字条 crop 不要直接传 `PIL.Image` 给 OCR
4. 改为传 `np.array(crop)`，或者灰度/对比度增强后的 `np.ndarray`
5. parser 的连续序列修复只能作为兜底，不应作为这个问题的首选修复

推荐实现方向：

```python
crop_rgb = np.array(crop)
ocr_blocks = ocr_engine.recognize_image_object(crop_rgb)
```

更保守的版本：

```python
gray = ImageOps.grayscale(crop)
gray = ImageOps.autocontrast(gray)
ocr_blocks = ocr_engine.recognize_image_object(np.array(gray))
```

当前实验中，RGB ndarray 和灰度 ndarray 都能识别 `PU-6157(1)` 的第 9 位。

