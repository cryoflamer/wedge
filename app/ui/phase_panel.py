from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed


class PhasePanel(QWidget):
    clicked = Signal(int, float, float)

    def __init__(self, wall: int, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.wall = wall
        self._title = QLabel(title)
        self._hint = QLabel("phase space")
        self._last_click = QLabel("click: -")
        self._seeds: dict[int, TrajectorySeed] = {}
        self._orbits: dict[int, Orbit] = {}
        self._selected_trajectory_id: int | None = None
        self._padding = 24

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
        if not self._is_inside_domain(d_value, tau_value):
            self._last_click.setText("click: outside domain")
            return

        self._last_click.setText(f"click: d={d_value:.3f}, tau={tau_value:.3f}")
        self.clicked.emit(self.wall, d_value, tau_value)
        self.update()

    def set_trajectories(
        self,
        seeds: dict[int, TrajectorySeed],
        orbits: dict[int, Orbit],
        selected_trajectory_id: int | None,
    ) -> None:
        self._seeds = seeds
        self._orbits = orbits
        self._selected_trajectory_id = selected_trajectory_id
        self.update()

    def _map_click(self, point: QPointF) -> tuple[float, float]:
        plot = self._plot_rect()
        if plot.width() <= 0 or plot.height() <= 0:
            return 0.0, 0.0

        x_ratio = min(max((point.x() - plot.left()) / plot.width(), 0.0), 1.0)
        y_ratio = min(max((point.y() - plot.top()) / plot.height(), 0.0), 1.0)
        d_value = 2.0 * x_ratio
        tau_value = 1.0 - 2.0 * y_ratio
        return d_value, tau_value

    def _plot_rect(self) -> QRectF:
        return QRectF(
            self._padding,
            52.0,
            max(self.width() - 2 * self._padding, 1),
            max(self.height() - 88.0, 1),
        )

    def _to_canvas(self, d_value: float, tau_value: float) -> QPointF:
        plot = self._plot_rect()
        x = plot.left() + (d_value / 2.0) * plot.width()
        y = plot.top() + ((1.0 - tau_value) / 2.0) * plot.height()
        return QPointF(x, y)

    def _is_inside_domain(self, d_value: float, tau_value: float) -> bool:
        return (1.0 - d_value) ** 2 + tau_value**2 < 1.0

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot_rect()

        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawRect(plot)

        painter.setPen(QPen(QColor("#c8c8c8"), 1))
        tau_zero_left = self._to_canvas(0.0, 0.0)
        tau_zero_right = self._to_canvas(2.0, 0.0)
        painter.drawLine(tau_zero_left, tau_zero_right)
        d_one_top = self._to_canvas(1.0, 1.0)
        d_one_bottom = self._to_canvas(1.0, -1.0)
        painter.drawLine(d_one_top, d_one_bottom)

        domain_rect = QRectF(plot.left(), plot.top(), plot.width(), plot.height())
        painter.setPen(QPen(QColor("#8fb9e8"), 2))
        painter.setBrush(QColor(214, 231, 248, 80))
        painter.drawEllipse(domain_rect)

        for trajectory_id, orbit in self._orbits.items():
            seed = self._seeds.get(trajectory_id)
            if seed is None or not seed.visible:
                continue

            points = [
                self._to_canvas(point.d, point.tau)
                for point in orbit.points
                if point.wall == self.wall
            ]
            if not points:
                continue

            is_selected = trajectory_id == self._selected_trajectory_id
            color = QColor(seed.color)
            pen = QPen(color, 3 if is_selected else 2)
            painter.setPen(pen)
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.drawPath(path)

            for point in points:
                painter.setBrush(color)
                radius = 4 if is_selected else 3
                painter.drawEllipse(point, radius, radius)
