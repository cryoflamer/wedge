from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class AnglePanel(QWidget):
    point_selected = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("Alpha / Beta")
        self._hint = QLabel("placeholder: parameter space")
        self._point_label = QLabel("point: -")

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addWidget(self._point_label)
        layout.addStretch(1)

        self.setMinimumHeight(220)
        self.setStyleSheet(
            "AnglePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )

    def set_angles(self, alpha: float, beta: float) -> None:
        self._point_label.setText(f"point: alpha={alpha:.6f}, beta={beta:.6f}")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return

        alpha, beta = self._map_click(event.position())
        self._point_label.setText(f"point: alpha={alpha:.6f}, beta={beta:.6f}")
        self.point_selected.emit(alpha, beta)

    def _map_click(self, point: QPointF) -> tuple[float, float]:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        alpha = (point.x() / width) * (3.141592653589793 / 2.0)
        beta = alpha + (1.0 - point.y() / height) * (3.141592653589793 - alpha)
        return alpha, beta

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawLine(24, self.height() - 24, self.width() - 24, self.height() - 24)
        painter.drawLine(24, self.height() - 24, 24, 24)
