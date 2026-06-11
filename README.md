# 线下色卡采集工具集

本项目是一个本地桌面软件，用于线下色卡图片识别、重命名、截图和模板生成；当前四个首页入口均已完成。

## 当前范围

- 首页四个入口均已实现并可用。
- “叠贴转平贴模板生成”进入可用页面。
- “色卡扫描图改名”进入可用页面。
- “主图截图及名称更改”进入可用页面。
- “SPU名称生成不干胶模板”进入可用页面。
- 第一个功能包含图片选择、离线 OCR 接口、识别结果确认、分组校验、Word 模板生成。
- 图片改名功能会识别图片左上角名称，将原图复制到目标目录并改名。
- 主图截图功能会识别图片左上角名称，按 `10cm * 10cm` 或 `15cm * 15cm` 截图后改名保存。
- SPU 不干胶功能会读取 Excel 第一工作表指定列，写入固定 Word 不干胶模板。

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

## 图片改名与截图

### 色卡扫描图改名

1. 进入“色卡扫描图改名”。
2. 选择“色卡改名后扫描图片保存的地址”。
3. 选择需要改名的 `.jpg/.jpeg/.png` 色卡扫描图。
4. 点击“确认”。

软件会识别每张图片左上角的数字或文字作为文件名，将整张原图复制到目标目录，不重新压缩。遇到重名时自动追加 `-2`、`-3`。

### 主图截图及名称更改

1. 进入“主图截图及名称更改”。
2. 选择截图尺寸：`10cm * 10cm` 或 `15cm * 15cm`。
3. 选择截图及改名后图片保存的地址。
4. 选择对应要截图及改名的 `.jpg/.jpeg/.png` 图片。
5. 点击“确认”。

软件会识别图片左上角名称位置，以该位置为截图起点裁出指定尺寸并按识别名称保存。尺寸优先按图片 DPI 换算；图片没有 DPI 时按 `300 DPI` 处理。JPEG 输出使用最高质量保存，PNG 保持 PNG 格式。

## SPU 名称生成不干胶模板

1. 进入“SPU名称生成不干胶模板”。
2. 点击 `+` 选择要转换的 `.xlsx` 文件。
3. 输入 Excel 起始单元格的行和列，例如行 `2`、列 `2` 表示 `B2`。
4. 查看固定内置模板“8144-不干胶贴模板.docx”。模板只能查看，不能在软件里替换。
5. 输入转换后的 Word 名称，选择保存地址。
6. 点击“确定”。

软件只读取 Excel 第一个工作表，从起始单元格所在列往下读取连续非空内容，遇到空单元格停止。内置模板每页为 `24 行 * 6 列`，一页写满后自动复制第一页表格继续写入。

## 打包

```powershell
.\.venv\Scripts\python -m pip install -e .[packaging]
.\.venv\Scripts\pyinstaller packaging\pyinstaller.spec
```

打包产物名称为“线下色卡采集工具集”。

打包成功后，可执行文件位于：

`dist/线下色卡采集工具集/线下色卡采集工具集.exe`

内置 Word 模板会被打入：

`dist/线下色卡采集工具集/_internal/resources/templates/转平贴底纸模板.docx`

## Windows 本地安装

打包成功后执行：

```powershell
.\scripts\install_windows.ps1
```

安装脚本会：

- 将 `dist/线下色卡采集工具集` 复制到 `%LOCALAPPDATA%/线下色卡采集工具集`
- 在桌面创建 `线下色卡采集工具集.lnk`
- 不需要管理员权限

卸载：

```powershell
.\scripts\uninstall_windows.ps1
```

## 模板

内置平贴模板来自：

`docs/转平贴底纸模板.docx`

运行时使用打包资源：

`src/color_card_toolkit/resources/templates/转平贴底纸模板.docx`
