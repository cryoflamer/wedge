from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.models.config import ViewConfig
from app.models.geometry import WedgeGeometry
from app.models.trajectory import TrajectorySeed


class WedgePanel(QWidget):
    def __init__(
        self,
        view_config: ViewConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._view_config = view_config
        self._title = QLabel("Wedge View")
        self._hint = QLabel("geometry view")
        self._geometries: dict[int, WedgeGeometry] = {}
        self._seeds: dict[int, TrajectorySeed] = {}
        self._selected_trajectory_id: int | None = None
        self._active_segment_indices: dict[int, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._hint)
        layout.addStretch(1)

        self.setMinimumHeight(220)
        self.setStyleSheet(
            "WedgePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )

    def set_geometries(
        self,
        seeds: dict[int, TrajectorySeed],
        geometries: dict[int, WedgeGeometry],
        selected_trajectory_id: int | None,
        active_segment_indices: dict[int, int] | None = None,
    ) -> None:
        self._seeds = seeds
        self._geometries = geometries
        self._selected_trajectory_id = selected_trajectory_id
        self._active_segment_indices = active_segment_indices or {}
        self.update()

    def _plot_rect(self) -> QRectF:
        top = self._header_bottom() + 12.0
        return QRectF(
            24.0,
            top,
            max(self.width() - 48.0, 1),
            max(self.height() - top - 16.0, 1),
        )

    def _header_bottom(self) -> float:
        labels = [self._title, self._hint]
        return max((label.geometry().bottom() for label in labels), default=0) + 1.0

    def _all_points(self) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = [(0.0, 0.0)]
        for geometry in self._geometries.values():
            for wall in geometry.walls:
                points.append((wall.start.x, wall.start.y))
                points.append((wall.end.x, wall.end.y))
            for reflection in geometry.reflections:
                if reflection.point is not None:
                    points.append((reflection.point.x, reflection.point.y))
            for segment in geometry.segments:
                if segment.focus is not None:
                    points.append((segment.focus.x, segment.focus.y))
                if segment.start_point is not None:
                    points.append((segment.start_point.x, segment.start_point.y))
                if segment.end_point is not None:
                    points.append((segment.end_point.x, segment.end_point.y))
                for sample in segment.samples:
                    points.append((sample.x, sample.y))
        return points

    def _to_canvas(self, x_value: float, y_value: float) -> QPointF:
        plot = self._plot_rect()
        min_x, max_x, min_y, max_y = self._geometry_bounds()
        data_width = max(max_x - min_x, 1.0e-6)
        data_height = max(max_y - min_y, 1.0e-6)
        inner_margin = 16.0
        available_width = max(plot.width() - 2.0 * inner_margin, 1.0)
        available_height = max(plot.height() - 2.0 * inner_margin, 1.0)
        scale = min(available_width / data_width, available_height / data_height)

        used_width = data_width * scale
        used_height = data_height * scale
        offset_x = plot.left() + (plot.width() - used_width) / 2.0
        offset_y = plot.top() + (plot.height() - used_height) / 2.0

        canvas_x = offset_x + (x_value - min_x) * scale
        canvas_y = offset_y + (max_y - y_value) * scale
        return QPointF(canvas_x, canvas_y)

    def _geometry_bounds(self) -> tuple[float, float, float, float]:
        points = self._all_points()
        min_x = min((point[0] for point in points), default=0.0)
        max_x = max((point[0] for point in points), default=1.0)
        min_y = min((point[1] for point in points), default=0.0)
        max_y = max((point[1] for point in points), default=1.0)

        if abs(max_x - min_x) <= 1.0e-9:
            max_x = min_x + 1.0
        if abs(max_y - min_y) <= 1.0e-9:
            max_y = min_y + 1.0

        return min_x, max_x, min_y, max_y

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawRect(self._plot_rect())

        self._draw_walls(painter)
        self._draw_segments(painter)
        self._draw_reflections(painter)

    def _draw_walls(self, painter: QPainter) -> None:
        if not self._geometries:
            return
        geometry = next(iter(self._geometries.values()))
        painter.setPen(QPen(QColor("#404040"), 2))
        for wall in geometry.walls:
            start = self._to_canvas(wall.start.x, wall.start.y)
            end = self._to_canvas(wall.end.x, wall.end.y)
            painter.drawLine(start, end)

    def _draw_segments(self, painter: QPainter) -> None:
        for trajectory_id, geometry in self._geometries.items():
            seed = self._seeds.get(trajectory_id)
            if seed is None or not seed.visible:
                continue

            is_selected = trajectory_id == self._selected_trajectory_id
            color = QColor(seed.color)
            pen = QPen(color, 3 if is_selected else 2)
            painter.setPen(pen)

            active_index = self._active_segment_indices.get(trajectory_id)
            for index, segment in enumerate(geometry.segments):
                if (
                    not segment.valid
                    or segment.start_point is None
                    or segment.end_point is None
                    or not segment.samples
                ):
                    continue
                if active_index is not None and index > active_index:
                    continue

                if active_index is not None and index == active_index:
                    painter.setPen(QPen(QColor("#111111"), 4))
                else:
                    painter.setPen(pen)

                first_point = self._to_canvas(
                    segment.samples[0].x,
                    segment.samples[0].y,
                )
                path = QPainterPath(first_point)
                for sample in segment.samples[1:]:
                    path.lineTo(self._to_canvas(sample.x, sample.y))
                painter.drawPath(path)

    def _draw_reflections(self, painter: QPainter) -> None:
        for trajectory_id, geometry in self._geometries.items():
            seed = self._seeds.get(trajectory_id)
            if seed is None or not seed.visible:
                continue

            active_index = self._active_segment_indices.get(trajectory_id)
            color = QColor(seed.color)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            radius = self._view_config.geometry_point_radius + (
                1 if trajectory_id == self._selected_trajectory_id else 0
            )

            for reflection in geometry.reflections:
                if not reflection.valid or reflection.point is None:
                    continue
                if active_index is not None and reflection.step_index > active_index + 1:
                    continue
                point = self._to_canvas(reflection.point.x, reflection.point.y)
                painter.drawEllipse(point, radius, radius)
