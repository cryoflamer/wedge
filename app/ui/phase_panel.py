from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.models.config import ViewConfig
from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed


class PhasePanel(QWidget):
    clicked = Signal(int, float, float)

    def __init__(
        self,
        wall: int,
        title: str,
        view_config: ViewConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.wall = wall
        self._view_config = view_config
        self._title = QLabel(title)
        self._hint = QLabel("phase space")
        self._last_click = QLabel("click: -")
        self._seeds: dict[int, TrajectorySeed] = {}
        self._orbits: dict[int, Orbit] = {}
        self._selected_trajectory_id: int | None = None
        self._active_frames: dict[int, int] = {}
        self._padding = 24
        self._top_margin = 16
        self._bottom_margin = 16
        self._header_spacing = 4

        for label in (self._title, self._hint, self._last_click):
            label.setFixedHeight(label.sizeHint().height())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self._padding,
            self._top_margin,
            self._padding,
            self._bottom_margin,
        )
        layout.setSpacing(self._header_spacing)
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
        active_frames: dict[int, int] | None = None,
    ) -> None:
        self._seeds = seeds
        self._orbits = orbits
        self._selected_trajectory_id = selected_trajectory_id
        self._active_frames = active_frames or {}
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
        available_width = max(self.width() - 2 * self._padding, 1)
        top = self._header_height() + 12.0
        available_height = max(self.height() - top - self._bottom_margin, 1)
        side = min(available_width, available_height)
        left = self._padding + (available_width - side) / 2.0
        plot_top = top + (available_height - side) / 2.0
        return QRectF(left, plot_top, side, side)

    def _header_height(self) -> float:
        return (
            self._top_margin
            + self._title.height()
            + self._hint.height()
            + self._last_click.height()
            + 2 * self._header_spacing
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
            painter.setPen(QPen(color, 1))

            for point in points:
                painter.setBrush(color)
                radius = self._view_config.phase_point_radius + (1 if is_selected else 0)
                painter.drawEllipse(point, radius, radius)

            active_index = self._active_frames.get(trajectory_id)
            if active_index is None:
                continue

            wall_points = [
                point for point in orbit.points if point.wall == self.wall
            ]
            if not wall_points:
                continue

            active_point = next(
                (
                    point
                    for point in wall_points
                    if point.step_index == active_index
                ),
                None,
            )
            if active_point is None:
                continue

            active_canvas_point = self._to_canvas(active_point.d, active_point.tau)
            painter.setPen(QPen(QColor("#111111"), 2))
            painter.setBrush(QColor("#ffffff"))
            active_radius = self._view_config.phase_point_radius + 2
            painter.drawEllipse(active_canvas_point, active_radius, active_radius)
