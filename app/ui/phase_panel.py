from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PhasePanel(QWidget):
    clicked = Signal(int, float, float)

    def __init__(self, wall: int, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.wall = wall
        self._title = QLabel(title)
        self._hint = QLabel("placeholder: phase space")
        self._last_click = QLabel("click: -")

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addWidget(self._last_click)
        layout.addStretch(1)

        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "PhasePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return

        d_value, tau_value = self._map_click(event.position())
        self._last_click.setText(f"click: d={d_value:.3f}, tau={tau_value:.3f}")
        self.clicked.emit(self.wall, d_value, tau_value)
        self.update()

    def _map_click(self, point: QPointF) -> tuple[float, float]:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        d_value = min(max(point.x() / width, 0.0), 1.0)
        tau_value = 1.0 - 2.0 * min(max(point.y() / height, 0.0), 1.0)
        return d_value, tau_value

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawLine(0, self.height() // 2, self.width(), self.height() // 2)
        painter.drawLine(self.width() // 2, 0, self.width() // 2, self.height())
