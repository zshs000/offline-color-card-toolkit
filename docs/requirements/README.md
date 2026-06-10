# 线下色卡采集工具集需求说明

## 1. 项目定位

线下色卡采集工具集是一个本地桌面软件。软件安装后，需要在电脑上生成快捷入口，快捷入口名称为“线下色卡采集工具集”。

用户点击快捷入口后进入首页，首页提供四个功能入口：

1. 叠贴转平贴模板生成
2. 色卡扫描图改名
3. 主图截图及名称更改
4. SPU名称生成不干胶模板

当前四个功能入口均已实现。

## 2. 技术与运行要求

- 客户端形态：本地桌面软件。
- 首选技术栈：Python + PySide6。
- OCR 要求：完全离线运行，不依赖联网服务。
- OCR 引擎候选：优先验证 RapidOCR；如中文、低清图片或复杂版式识别效果不足，再切换或兼容 PaddleOCR。
- Word 处理：使用内置固定 Word 模板生成输出文档。
- 第一阶段目标平台：Windows 优先。
- 跨平台策略：代码结构尽量保持 Windows、macOS、Linux 可迁移，但安装包和快捷入口优先满足 Windows。

## 3. 功能文档索引

| 功能 | 状态 | 文档 |
| --- | --- | --- |
| 叠贴转平贴模板生成 | 已实现 | [feature-01-stack-to-flat-template.md](feature-01-stack-to-flat-template.md) |
| 色卡扫描图改名 | 已实现 | [feature-04-color-card-scan-rename.md](feature-04-color-card-scan-rename.md) |
| 主图截图及名称更改 | 已实现 | [feature-02-main-image-crop-rename.md](feature-02-main-image-crop-rename.md) |
| SPU名称生成不干胶模板 | 已实现 | [feature-03-spu-label-template.md](feature-03-spu-label-template.md) |

## 4. 当前实现范围

当前交付范围：

- 首页展示四个入口。
- 完成叠贴转平贴模板生成的图片选择、离线 OCR 识别、识别结果确认、分组校验、Word 模板生成。
- 完成色卡扫描图改名的输出目录选择、图片批量选择、左上角名称识别、原图复制改名保存。
- 完成主图截图及名称更改的截图尺寸选择、输出目录选择、图片批量选择、左上角名称识别、截图改名保存。
- 完成 SPU 名称生成不干胶模板的 Excel 第一工作表读取、固定模板展示、Word 模板分页写入。
- 内置平贴 Word 模板随软件一起打包。

## 5. 暂不包含

- 不接入在线 OCR 或云端识别服务。
- 不训练专用目标检测模型；当前优先使用 OCR 坐标、规则聚类和人工确认页兜底。
