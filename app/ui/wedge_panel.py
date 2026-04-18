from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class WedgePanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("Wedge View")
        self._hint = QLabel("placeholder: geometry")

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addStretch(1)

        self.setMinimumHeight(220)
        self.setStyleSheet(
            "WedgePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.darkGray, 2))
        origin_x = self.width() // 2
        origin_y = self.height() - 24
        painter.drawLine(origin_x, origin_y, 30, 24)
        painter.drawLine(origin_x, origin_y, self.width() - 30, 24)
