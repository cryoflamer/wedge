from __future__ import annotations

import math
from dataclasses import dataclass

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
        self._padding = 24
        self._top_margin = 16
        self._bottom_margin = 16
        self._header_spacing = 4
        # Performance guard: bounds scan all geometry samples and are expensive.
        # These caches are the only data _to_canvas() may read for per-point
        # conversion. Do not replace them with paint-time bounds recomputation.
        self._geometry_bounds_cache: tuple[float, float, float, float] | None = None
        self._canvas_transform_cache: _CanvasTransform | None = None
        self._geometry_cache_signature: tuple[object, ...] | None = None
        self._geometry_cache_dirty = True
        self._canvas_transform_dirty = True

        for label in (self._title, self._hint):
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
        layout.addStretch(1)

        self.setMinimumHeight(220)
        self.setStyleSheet(
            "WedgePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )
        self._geometry_bounds_cache = self._default_geometry_bounds()
        self._rebuild_canvas_transform_cache()

    def set_geometries(
        self,
        seeds: dict[int, TrajectorySeed],
        geometries: dict[int, WedgeGeometry],
        selected_trajectory_id: int | None,
        active_segment_indices: dict[int, int] | None = None,
    ) -> None:
        geometry_signature = self._geometry_signature(geometries)
        geometry_changed = geometry_signature != self._geometry_cache_signature
        if geometry_signature != self._geometry_cache_signature:
            self._geometry_cache_signature = geometry_signature
            self._invalidate_geometry_cache()
        self._seeds = seeds
        self._geometries = geometries
        self._selected_trajectory_id = selected_trajectory_id
        self._active_segment_indices = active_segment_indices or {}
        if geometry_changed and self._geometry_cache_dirty:
            self._rebuild_geometry_cache()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._invalidate_canvas_transform_cache()
        if self._canvas_transform_dirty:
            self._rebuild_canvas_transform_cache()

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
            + self._header_spacing
        )

    def _all_points(self) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = [(0.0, 0.0)]
        if self._view_config.show_directrix:
            points.append((0.0, 1.0))
        for geometry in self._geometries.values():
            for wall in geometry.walls:
                points.append((wall.start.x, wall.start.y))
                points.append((wall.end.x, wall.end.y))
            for reflection in geometry.reflections:
                if reflection.point is not None:
                    points.append((reflection.point.x, reflection.point.y))
            for segment in geometry.segments:
                if segment.start_point is not None:
                    points.append((segment.start_point.x, segment.start_point.y))
                if segment.end_point is not None:
                    points.append((segment.end_point.x, segment.end_point.y))
                for sample in segment.samples:
                    points.append((sample.x, sample.y))
        return points

    def _invalidate_geometry_cache(self) -> None:
        # Geometry-data changes are the only reason to invalidate bounds.
        # Selection/highlight changes must not set this flag.
        self._geometry_cache_dirty = True
        self._invalidate_canvas_transform_cache()

    def _invalidate_canvas_transform_cache(self) -> None:
        # Widget-size changes affect only scale/offset; do not rescan samples.
        self._canvas_transform_dirty = True

    # IMPORTANT: geometry bounds computation is expensive because it scans all
    # walls, reflections, segments, and samples. Calling that scan from
    # _to_canvas(), inside per-point transforms, or from paint-time draw helpers
    # is forbidden: it causes severe trajectory-selection lag by turning a
    # simple repaint into repeated O(N_samples) work. Bounds and derived canvas
    # transform values must only be rebuilt from set_geometries() when geometry
    # data changes, or from resizeEvent() for size-dependent transform values.
    def _rebuild_geometry_cache(self) -> None:
        self._geometry_bounds_cache = self._compute_geometry_bounds()
        self._geometry_cache_dirty = False
        self._canvas_transform_dirty = True
        self._rebuild_canvas_transform_cache()

    def _rebuild_canvas_transform_cache(self) -> None:
        if self._geometry_bounds_cache is None:
            self._geometry_bounds_cache = self._default_geometry_bounds()
        self._canvas_transform_cache = self._build_canvas_transform(
            self._geometry_bounds_cache
        )
        self._canvas_transform_dirty = False

    def _geometry_signature(
        self,
        geometries: dict[int, WedgeGeometry],
    ) -> tuple[object, ...]:
        return (
            self._view_config.show_directrix,
            tuple(
                (trajectory_id, id(geometry))
                for trajectory_id, geometry in sorted(geometries.items())
            ),
        )

    def _to_canvas(self, x_value: float, y_value: float) -> QPointF:
        # Hot path: this must use cached transform only. Calling
        # _compute_geometry_bounds(), _all_points(), or any sample scan here is
        # forbidden and will reintroduce trajectory-selection lag.
        assert self._canvas_transform_cache is not None
        transform = self._canvas_transform_cache
        canvas_x = transform.offset_x + (x_value - transform.min_x) * transform.scale
        canvas_y = transform.offset_y + (transform.max_y - y_value) * transform.scale
        return QPointF(canvas_x, canvas_y)

    def _default_geometry_bounds(self) -> tuple[float, float, float, float]:
        return (0.0, 1.0, 0.0, 1.0)

    def _compute_geometry_bounds(self) -> tuple[float, float, float, float]:
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

    def _build_canvas_transform(
        self,
        bounds: tuple[float, float, float, float],
    ) -> "_CanvasTransform":
        plot = self._plot_rect()
        min_x, max_x, min_y, max_y = bounds
        data_width = max(max_x - min_x, 1.0e-6)
        data_height = max(max_y - min_y, 1.0e-6)
        inner_margin = 8.0
        available_width = max(plot.width() - 2.0 * inner_margin, 1.0)
        available_height = max(plot.height() - 2.0 * inner_margin, 1.0)
        scale = min(available_width / data_width, available_height / data_height)

        used_width = data_width * scale
        used_height = data_height * scale
        offset_x = plot.left() + (plot.width() - used_width) / 2.0
        offset_y = plot.top() + (plot.height() - used_height) / 2.0
        return _CanvasTransform(
            min_x=min_x,
            max_y=max_y,
            offset_x=offset_x,
            offset_y=offset_y,
            scale=scale,
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawRect(self._plot_rect())

        self._draw_axes(painter)
        self._draw_directrix(painter)
        self._draw_walls(painter)
        self._draw_segments(painter)
        self._draw_reflections(painter)

    def _draw_axes(self, painter: QPainter) -> None:
        assert self._geometry_bounds_cache is not None
        min_x, max_x, min_y, max_y = self._geometry_bounds_cache
        plot = self._plot_rect()
        tick_length = 5.0
        axis_color = QColor(125, 125, 125, 220)
        text_color = QColor(90, 90, 90)
        font_metrics = painter.fontMetrics()

        x_ticks = self._tick_values(min_x, max_x)
        y_ticks = self._tick_values(min_y, max_y)

        painter.save()
        painter.setPen(QPen(axis_color, 1))
        for tick in x_ticks:
            point = self._to_canvas(tick, min_y)
            painter.drawLine(
                QPointF(point.x(), plot.bottom() - tick_length),
                QPointF(point.x(), plot.bottom()),
            )
            label = self._format_tick_label(tick, x_ticks.step)
            label_width = font_metrics.horizontalAdvance(label)
            text_x = max(
                plot.left() + 2.0,
                min(point.x() - label_width / 2.0, plot.right() - label_width - 2.0),
            )
            painter.setPen(text_color)
            painter.drawText(
                QPointF(text_x, plot.bottom() - 6.0),
                label,
            )
            painter.setPen(QPen(axis_color, 1))

        for tick in y_ticks:
            point = self._to_canvas(min_x, tick)
            painter.drawLine(
                QPointF(plot.left(), point.y()),
                QPointF(plot.left() + tick_length, point.y()),
            )
            label = self._format_tick_label(tick, y_ticks.step)
            text_y = max(
                plot.top() + font_metrics.ascent() + 2.0,
                min(point.y() + font_metrics.ascent() / 2.5, plot.bottom() - 2.0),
            )
            painter.setPen(text_color)
            painter.drawText(
                QPointF(plot.left() + tick_length + 4.0, text_y),
                label,
            )
            painter.setPen(QPen(axis_color, 1))
        painter.restore()

    def _draw_directrix(self, painter: QPainter) -> None:
        if not self._view_config.show_directrix:
            return

        assert self._geometry_bounds_cache is not None
        min_x, max_x, _, _ = self._geometry_bounds_cache
        if abs(max_x - min_x) <= 1.0e-9:
            max_x = min_x + 1.0

        painter.setPen(QPen(QColor(136, 136, 136, 180), 1, Qt.DashLine))
        start = self._to_canvas(min_x, 1.0)
        end = self._to_canvas(max_x, 1.0)
        painter.drawLine(start, end)

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

    def _tick_values(self, min_value: float, max_value: float) -> "_TickValues":
        span = max(max_value - min_value, 1.0e-9)
        step = self._nice_tick_step(span / 4.0)
        start = math.ceil(min_value / step) * step
        values: list[float] = []
        current = start
        limit = max_value + step * 0.5
        while current <= limit:
            values.append(0.0 if abs(current) <= 1.0e-12 else current)
            current += step
        return _TickValues(values=values, step=step)

    def _nice_tick_step(self, raw_step: float) -> float:
        if raw_step <= 0.0:
            return 1.0

        exponent = math.floor(math.log10(raw_step))
        fraction = raw_step / (10 ** exponent)
        if fraction <= 1.0:
            nice_fraction = 1.0
        elif fraction <= 2.0:
            nice_fraction = 2.0
        elif fraction <= 5.0:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0
        return nice_fraction * (10 ** exponent)

    def _format_tick_label(self, value: float, step: float) -> str:
        if step >= 1.0:
            return f"{value:.0f}"
        if step >= 0.1:
            return f"{value:.1f}"
        if step >= 0.01:
            return f"{value:.2f}"
        return f"{value:.3f}"


class _TickValues:
    def __init__(self, values: list[float], step: float) -> None:
        self.values = values
        self.step = step

    def __iter__(self):
        return iter(self.values)


@dataclass(frozen=True)
class _CanvasTransform:
    min_x: float
    max_y: float
    offset_x: float
    offset_y: float
    scale: float
