# 线下色卡采集工具集

本项目是一个本地桌面软件，第一阶段实现“叠贴转平贴模板生成”。

## 当前范围

- 已实现首页三个入口。
- “叠贴转平贴模板生成”进入可用页面。
- “主图截图及名称更改”和“SPU名称生成不干胶模板”暂未开放。
- 第一个功能包含图片选择、离线 OCR 接口、识别结果确认、分组校验、Word 模板生成。

## 本地运行

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m color_card_toolkit.main
```

## 测试

```powershell
.\.venv\Scripts\python -m pytest
```

## 模板

内置平贴模板来自：

`docs/转平贴底纸模板.docx`

运行时使用打包资源：

`src/color_card_toolkit/resources/templates/转平贴底纸模板.docx`

