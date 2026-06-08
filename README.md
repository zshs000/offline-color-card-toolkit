# 线下色卡采集工具集

本项目是一个本地桌面软件，第一阶段实现“叠贴转平贴模板生成”。

## 当前范围

- 已实现首页三个入口。
- “叠贴转平贴模板生成”进入可用页面。
- “主图截图及名称更改”和“SPU名称生成不干胶模板”暂未开放。
- 第一个功能包含图片选择、离线 OCR 接口、识别结果确认、分组校验、Word 模板生成。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m color_card_toolkit.main
```

如果 `python` 或 `py` 指向 WindowsApps 占位入口，可以直接使用本机真实 Python 路径创建虚拟环境，例如：

```powershell
& 'C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe' -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
```

## 测试

```powershell
.\.venv\Scripts\python -m pytest
```

## 第一功能使用流程

1. 进入“叠贴转平贴模板生成”。
2. 确认内置模板为“转平贴底纸模板.docx”。
3. 输入输出 Word 名称，选择保存目录。
4. 选择 `.jpg/.jpeg/.png` 图片。
5. 点击“开始识别”。
6. 在识别结果表中修正组名、序号、色号列表。
7. 点击“生成 Word”。

OCR 初始化或单张图片识别失败时，软件会保留可编辑行，并默认使用图片文件名作为组名，用户可手动修正后继续生成。

## 打包

```powershell
.\.venv\Scripts\python -m pip install -e .[packaging]
.\.venv\Scripts\pyinstaller packaging\pyinstaller.spec
```

打包产物名称为“线下色卡采集工具集”。

## 模板

内置平贴模板来自：

`docs/转平贴底纸模板.docx`

运行时使用打包资源：

`src/color_card_toolkit/resources/templates/转平贴底纸模板.docx`
