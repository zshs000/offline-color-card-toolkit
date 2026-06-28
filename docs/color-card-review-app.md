# 色卡标注工具（Review App）

本地 Web 应用，用于给色卡扫描图片手动绘制 YOLO 训练标注框并导出数据集。

## 启动

```powershell
.\scripts\start_review_app.ps1
```

或：

```powershell
.\.venv\Scripts\python -m color_card_toolkit.review_app
```

默认监听 `http://127.0.0.1:8765/`。

## 功能

- 浏览 `datasets/raw_images/` 下的原始色卡图片。
- 对图片绘制 name_area 和 code_area 标注框。
- 保存标注到 `datasets/manual_annotations/annotations.json`。
- 导出 YOLO 格式数据集到 `datasets/manual_annotations/exports/`。

## 自定义路径

```powershell
.\.venv\Scripts\python -m color_card_toolkit.review_app --raw-root <原始图片目录> --annotation-path <标注文件路径> --export-root <导出目录>
```

## 数据目录

| 目录 | 用途 |
|------|------|
| `datasets/raw_images/` | 原始色卡扫描图片 |
| `datasets/manual_annotations/annotations.json` | 标注数据 |
| `datasets/manual_annotations/exports/` | 导出的 YOLO 数据集 |
