from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from color_card_toolkit.ui.stack_to_flat_page import StackToFlatPage


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("线下色卡采集工具集")
        self.resize(980, 640)

        self._stack = QStackedWidget()
        self._home_page = HomePage()
        self._stack_to_flat_page = StackToFlatPage(on_back=self.show_home)

        self._home_page.stack_to_flat_requested.connect(self.show_stack_to_flat)
        self._home_page.unavailable_requested.connect(self.show_unavailable)

        self._stack.addWidget(self._home_page)
        self._stack.addWidget(self._stack_to_flat_page)
        self.setCentralWidget(self._stack)

    def show_home(self) -> None:
        self._stack.setCurrentWidget(self._home_page)

    def show_stack_to_flat(self) -> None:
        self._stack.setCurrentWidget(self._stack_to_flat_page)

    def show_unavailable(self) -> None:
        QMessageBox.information(self, "暂未开放", "该功能暂未开放，第一阶段先实现叠贴转平贴模板生成。")


class HomePage(QWidget):
    stack_to_flat_requested = Signal()
    unavailable_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(72, 72, 72, 72)
        layout.setSpacing(36)

        title = QLabel("线下色卡采集工具集")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(48)
        grid.setVerticalSpacing(24)
        layout.addLayout(grid)
        layout.addStretch(1)

        entries = [
            ("叠贴转平贴模板生成", self.stack_to_flat_requested.emit),
            ("主图截图及名称更改", self.unavailable_requested.emit),
            ("SPU名称生成不干胶模板", self.unavailable_requested.emit),
        ]
        for column, (text, callback) in enumerate(entries):
            grid.addWidget(_HomeEntry(text, callback), 0, column)


class _HomeEntry(QFrame):
    def __init__(self, text: str, callback) -> None:
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame { border: 1px solid #d7dde5; border-radius: 8px; background: #ffffff; }"
            "QPushButton { border: 0; font-size: 15px; padding: 16px; }"
            "QPushButton:hover { background: #f2f6fb; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        button = QPushButton(text)
        button.setMinimumSize(220, 120)
        button.clicked.connect(callback)
        layout.addWidget(button)
