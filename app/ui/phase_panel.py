from __future__ import annotations

import logging
import math
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.models.config import ViewConfig
from app.models.orbit import Orbit, OrbitPoint
from app.models.trajectory import TrajectorySeed

logger = logging.getLogger(__name__)


class PhasePanel(QWidget):
    clicked = Signal(int, float, float)
    viewport_changed = Signal()

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
        self._fixed_domain = True
        self._viewport = (0.0, 2.0, -1.0, 1.0)
        self._pan_anchor_canvas: QPointF | None = None
        self._pan_anchor_viewport: tuple[float, float, float, float] | None = None
        self._zoom_anchor_canvas: QPointF | None = None
        self._zoom_rect_canvas: QRectF | None = None
        self._hover_point: QPointF | None = None
        self._click_threshold_px = 6.0
        self._padding = 24
        self._top_margin = 16
        self._bottom_margin = 16
        self._hover_label_margin = 30
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
        self._update_hint()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._fixed_domain and event.button() == Qt.RightButton:
            logger.info(
                "Phase interaction ignored: wall=%s fixed_domain=true button=%s",
                self.wall,
                int(event.button()),
            )
            self._last_click.setText("zoom/pan disabled: uncheck fixed domain")
            self._update_hint()
            self.update()

        if event.button() == Qt.RightButton and not self._fixed_domain:
            self._pan_anchor_canvas = event.position()
            self._pan_anchor_viewport = self._viewport
            self.setCursor(Qt.ClosedHandCursor)
            logger.info(
                "Phase viewport pan start: wall=%s viewport=%s",
                self.wall,
                self._viewport,
            )
            self._update_hint()
            self.update()
            return

        if event.button() == Qt.LeftButton and not self._fixed_domain:
            plot = self._plot_rect()
            if plot.contains(event.position()):
                self._zoom_anchor_canvas = event.position()
                return

        if event.button() != Qt.LeftButton:
            return

        d_value, tau_value = self._map_click(event.position())
        if not self._is_inside_domain(d_value, tau_value):
            self._last_click.setText("click: outside domain")
            return

        self._last_click.setText(f"click: d={d_value:.3f}, tau={tau_value:.3f}")
        self.clicked.emit(self.wall, d_value, tau_value)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        plot = self._plot_rect()
        previous_hover = self._hover_point
        self._hover_point = (
            self._clamp_to_plot(event.position(), plot)
            if plot.contains(event.position())
            else None
        )
        if (
            self._pan_anchor_canvas is None
            or self._pan_anchor_viewport is None
            or self._fixed_domain
        ):
            if (
                self._zoom_anchor_canvas is not None
                and not self._fixed_domain
            ):
                current = self._clamp_to_plot(event.position(), plot)
                delta = current - self._zoom_anchor_canvas
                if (
                    self._zoom_rect_canvas is None
                    and abs(delta.x()) < self._click_threshold_px
                    and abs(delta.y()) < self._click_threshold_px
                ):
                    return
                if self._zoom_rect_canvas is None:
                    logger.info(
                        "Phase viewport box-zoom start: wall=%s start=(%.3f, %.3f)",
                        self.wall,
                        self._zoom_anchor_canvas.x(),
                        self._zoom_anchor_canvas.y(),
                    )
                self._zoom_rect_canvas = QRectF(
                    self._zoom_anchor_canvas,
                    current,
                ).normalized()
                self._update_hint()
                self.update()
            elif previous_hover != self._hover_point:
                self.update()
            return

        plot = self._plot_rect()
        if plot.width() <= 0 or plot.height() <= 0:
            return

        delta = event.position() - self._pan_anchor_canvas
        d_min, d_max, tau_min, tau_max = self._pan_anchor_viewport
        d_span = d_max - d_min
        tau_span = tau_max - tau_min
        d_shift = -(delta.x() / plot.width()) * d_span
        tau_shift = (delta.y() / plot.height()) * tau_span
        self._viewport = (
            d_min + d_shift,
            d_max + d_shift,
            tau_min + tau_shift,
            tau_max + tau_shift,
        )
        logger.debug(
            "Phase viewport pan: wall=%s viewport=%s",
            self.wall,
            self._viewport,
        )
        self._update_hint()
        self.viewport_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            self._pan_anchor_canvas = None
            self._pan_anchor_viewport = None
            self.unsetCursor()
            self._update_hint()
            self.update()
        elif event.button() == Qt.LeftButton and not self._fixed_domain:
            if self._zoom_rect_canvas is not None:
                self._apply_zoom_rect()
            else:
                self._emit_click(event.position())
                self._zoom_anchor_canvas = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_point = None
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._fixed_domain:
            logger.info(
                "Phase wheel ignored: wall=%s fixed_domain=true delta=%s",
                self.wall,
                event.angleDelta().y(),
            )
            self._last_click.setText("zoom disabled: uncheck fixed domain")
            self._update_hint()
            self.update()
            return

        plot = self._plot_rect()
        if not plot.contains(event.position()):
            return

        delta_y = event.angleDelta().y()
        if delta_y == 0:
            return

        scale = 0.9 if delta_y > 0 else 1.1
        d_value, tau_value = self._map_click(event.position())
        d_min, d_max, tau_min, tau_max = self._viewport
        self._viewport = (
            d_value + (d_min - d_value) * scale,
            d_value + (d_max - d_value) * scale,
            tau_value + (tau_min - tau_value) * scale,
            tau_value + (tau_max - tau_value) * scale,
        )
        logger.info(
            "Phase viewport wheel: wall=%s d=%.6f tau=%.6f viewport=%s",
            self.wall,
            d_value,
            tau_value,
            self._viewport,
        )
        logger.debug(
            "Phase viewport wheel: wall=%s d=%.6f tau=%.6f viewport=%s",
            self.wall,
            d_value,
            tau_value,
            self._viewport,
        )
        self._update_hint()
        self.viewport_changed.emit()
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

    def set_fixed_domain_mode(self, fixed_domain: bool) -> None:
        self._fixed_domain = fixed_domain
        self._zoom_anchor_canvas = None
        self._zoom_rect_canvas = None
        self._pan_anchor_canvas = None
        self._pan_anchor_viewport = None
        if fixed_domain:
            self.reset_view()
        else:
            self._update_hint()
            self.update()

    def reset_view(self) -> None:
        self._viewport = (0.0, 2.0, -1.0, 1.0)
        self._zoom_anchor_canvas = None
        self._zoom_rect_canvas = None
        self._pan_anchor_canvas = None
        self._pan_anchor_viewport = None
        self._update_hint()
        self.viewport_changed.emit()
        self.update()

    def viewport(self) -> tuple[float, float, float, float] | None:
        if self._fixed_domain:
            return None
        return self._viewport

    def set_viewport(self, viewport: tuple[float, float, float, float] | None) -> None:
        self._viewport = viewport or (0.0, 2.0, -1.0, 1.0)
        self._update_hint()
        self.update()

    def is_fixed_domain_mode(self) -> bool:
        return self._fixed_domain

    def _map_click(self, point: QPointF) -> tuple[float, float]:
        plot = self._plot_rect()
        if plot.width() <= 0 or plot.height() <= 0:
            return 0.0, 0.0

        x_ratio = min(max((point.x() - plot.left()) / plot.width(), 0.0), 1.0)
        y_ratio = min(max((point.y() - plot.top()) / plot.height(), 0.0), 1.0)
        d_min, d_max, tau_min, tau_max = self._viewport
        d_value = d_min + (d_max - d_min) * x_ratio
        tau_value = tau_max - (tau_max - tau_min) * y_ratio
        return d_value, tau_value

    def _plot_rect(self) -> QRectF:
        available_width = max(self.width() - 2 * self._padding, 1)
        top = self._header_height() + 12.0
        available_height = max(
            self.height() - top - self._bottom_margin - self._hover_label_margin,
            1,
        )
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
        d_min, d_max, tau_min, tau_max = self._viewport
        d_span = max(d_max - d_min, 1.0e-9)
        tau_span = max(tau_max - tau_min, 1.0e-9)
        x = plot.left() + ((d_value - d_min) / d_span) * plot.width()
        y = plot.top() + ((tau_max - tau_value) / tau_span) * plot.height()
        return QPointF(x, y)

    def _is_inside_domain(self, d_value: float, tau_value: float) -> bool:
        return (1.0 - d_value) ** 2 + tau_value**2 < 1.0

    def _domain_canvas_rect(self) -> QRectF:
        top_left = self._to_canvas(0.0, 1.0)
        bottom_right = self._to_canvas(2.0, -1.0)
        return QRectF(top_left, bottom_right).normalized()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot_rect()

        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawRect(plot)

        painter.save()
        painter.setClipRect(plot)

        self._draw_phase_grid(painter, plot)

        painter.setPen(QPen(QColor("#c8c8c8"), 1))
        tau_zero_left = self._to_canvas(0.0, 0.0)
        tau_zero_right = self._to_canvas(2.0, 0.0)
        painter.drawLine(tau_zero_left, tau_zero_right)
        d_one_top = self._to_canvas(1.0, 1.0)
        d_one_bottom = self._to_canvas(1.0, -1.0)
        painter.drawLine(d_one_top, d_one_bottom)

        domain_rect = self._domain_canvas_rect()
        painter.setPen(QPen(QColor("#8fb9e8"), 2))
        painter.setBrush(QColor(214, 231, 248, 80))
        painter.drawEllipse(domain_rect)

        if self._view_config.show_heatmap:
            self._draw_heatmap_overlay(painter, domain_rect)

        badge_rect = QRectF(plot.left() + 8.0, plot.top() + 8.0, 172.0, 26.0)
        if self._fixed_domain:
            painter.setPen(QPen(QColor("#7a1f1f"), 1))
            painter.setBrush(QColor(255, 235, 235, 220))
            painter.drawRoundedRect(badge_rect, 6.0, 6.0)
            painter.setPen(QColor("#7a1f1f"))
            painter.drawText(
                badge_rect.adjusted(8.0, 0.0, -8.0, 0.0),
                Qt.AlignVCenter | Qt.AlignLeft,
                "fixed domain: zoom off",
            )
        else:
            painter.setPen(QPen(QColor("#1f5f2a"), 1))
            painter.setBrush(QColor(231, 247, 234, 220))
            painter.drawRoundedRect(badge_rect, 6.0, 6.0)
            painter.setPen(QColor("#1f5f2a"))
            painter.drawText(
                badge_rect.adjusted(8.0, 0.0, -8.0, 0.0),
                Qt.AlignVCenter | Qt.AlignLeft,
                "free zoom: on",
            )

        if self._zoom_rect_canvas is not None:
            selection = self._zoom_rect_canvas.intersected(plot)
            if selection.width() > 0 and selection.height() > 0:
                painter.setPen(QPen(QColor("#d62728"), 1, Qt.DashLine))
                painter.setBrush(QColor(214, 39, 40, 35))
                painter.drawRect(selection)

        hover_label_text: str | None = None
        if self._hover_point is not None:
            hover_label_text = self._draw_crosshair_overlay(painter, plot, self._hover_point)

        for trajectory_id, orbit in self._orbits.items():
            seed = self._seeds.get(trajectory_id)
            if seed is None or not seed.visible:
                continue

            active_index = self._active_frames.get(trajectory_id)
            wall_points = [
                point
                for point in orbit.points
                if point.wall == self.wall
                and (active_index is None or point.step_index <= active_index)
            ]
            points = [
                self._to_canvas(point.d, point.tau)
                for point in wall_points
            ]
            if not points:
                continue

            is_selected = trajectory_id == self._selected_trajectory_id
            color = QColor(seed.color)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            radius = self._view_config.phase_point_radius + (1 if is_selected else 0)

            for orbit_point, canvas_point in zip(wall_points, points):
                self._draw_point_marker(
                    painter,
                    orbit_point,
                    canvas_point,
                    radius,
                )

            if active_index is None:
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

        painter.restore()
        self._draw_axis_labels(painter, plot)
        if hover_label_text is not None:
            self._draw_hover_label(painter, plot, hover_label_text)

    def _draw_phase_grid(self, painter: QPainter, plot: QRectF) -> None:
        if not self._view_config.show_phase_grid:
            return

        grid = self._view_config.phase_grid
        major_d = self._grid_step(grid.major_step_d, self._viewport[1] - self._viewport[0])
        major_tau = self._grid_step(grid.major_step_tau, self._viewport[3] - self._viewport[2])
        if self._view_config.show_phase_minor_grid and grid.show_minor:
            minor_d = self._grid_step(grid.minor_step_d, self._viewport[1] - self._viewport[0])
            minor_tau = self._grid_step(grid.minor_step_tau, self._viewport[3] - self._viewport[2])
            self._draw_grid_lines(
                painter,
                d_values=self._grid_values(self._viewport[0], self._viewport[1], minor_d),
                tau_values=self._grid_values(self._viewport[2], self._viewport[3], minor_tau),
                color=self._with_alpha(grid.minor_color, grid.minor_alpha),
                width=grid.minor_width,
                style=grid.minor_style,
            )

        self._draw_grid_lines(
            painter,
            d_values=self._grid_values(self._viewport[0], self._viewport[1], major_d),
            tau_values=self._grid_values(self._viewport[2], self._viewport[3], major_tau),
            color=self._with_alpha(grid.major_color, grid.major_alpha),
            width=grid.major_width,
            style=grid.major_style,
        )

    def _draw_grid_lines(
        self,
        painter: QPainter,
        d_values: Iterable[float],
        tau_values: Iterable[float],
        color: QColor,
        width: float,
        style: str,
    ) -> None:
        painter.setPen(QPen(color, width, self._pen_style(style)))
        tau_min = self._viewport[2]
        tau_max = self._viewport[3]
        d_min = self._viewport[0]
        d_max = self._viewport[1]

        for d_value in d_values:
            start = self._to_canvas(d_value, tau_min)
            end = self._to_canvas(d_value, tau_max)
            painter.drawLine(start, end)

        for tau_value in tau_values:
            start = self._to_canvas(d_min, tau_value)
            end = self._to_canvas(d_max, tau_value)
            painter.drawLine(start, end)

    def _grid_step(self, configured_step: float, span: float) -> float:
        step = configured_step if configured_step > 1.0e-9 else 0.1
        if self._fixed_domain:
            return step

        target_lines = 8.0
        while span / step > target_lines * 1.5:
            step *= 2.0
        while span / step < target_lines / 2.5 and step > 1.0e-9:
            step /= 2.0
        return step

    def _grid_values(self, minimum: float, maximum: float, step: float) -> list[float]:
        if step <= 1.0e-12 or maximum <= minimum:
            return []

        start = math.ceil((minimum - 1.0e-12) / step) * step
        values: list[float] = []
        current = start
        limit = maximum + 1.0e-12
        while current <= limit:
            values.append(current)
            current += step
        return values

    def _with_alpha(self, color: str, alpha: float) -> QColor:
        qcolor = QColor(color)
        qcolor.setAlphaF(min(max(alpha, 0.0), 1.0))
        return qcolor

    def _pen_style(self, style: str) -> Qt.PenStyle:
        normalized = style.strip().lower()
        if normalized == "dotted":
            return Qt.DotLine
        if normalized == "dashed":
            return Qt.DashLine
        if normalized == "dashdot":
            return Qt.DashDotLine
        return Qt.SolidLine

    def _draw_axis_labels(self, painter: QPainter, plot: QRectF) -> None:
        if not self._view_config.show_phase_grid:
            return

        grid = self._view_config.phase_grid
        major_d = self._grid_step(
            grid.major_step_d,
            self._viewport[1] - self._viewport[0],
        )
        major_tau = self._grid_step(
            grid.major_step_tau,
            self._viewport[3] - self._viewport[2],
        )
        d_values = self._sparse_tick_values(
            self._grid_values(self._viewport[0], self._viewport[1], major_d),
            max_labels=6,
        )
        tau_values = self._sparse_tick_values(
            self._grid_values(self._viewport[2], self._viewport[3], major_tau),
            max_labels=5,
        )

        painter.save()
        painter.setPen(QColor("#5a5a5a"))
        metrics = painter.fontMetrics()
        bottom_y = min(plot.bottom() + metrics.height() + 2.0, self.height() - 2.0)
        left_x = max(2.0, plot.left() - 8.0)

        for d_value in d_values:
            point = self._to_canvas(d_value, self._viewport[2])
            text = self._format_tick_value(d_value)
            text_width = metrics.horizontalAdvance(text)
            text_x = min(
                max(point.x() - text_width / 2.0, 2.0),
                self.width() - text_width - 2.0,
            )
            painter.drawText(QPointF(text_x, bottom_y), text)

        for tau_value in tau_values:
            point = self._to_canvas(self._viewport[0], tau_value)
            text = self._format_tick_value(tau_value)
            text_width = metrics.horizontalAdvance(text)
            text_y = min(
                max(point.y() + metrics.ascent() / 2.0, metrics.height()),
                self.height() - 4.0,
            )
            painter.drawText(QPointF(left_x - text_width, text_y), text)

        painter.restore()

    def _sparse_tick_values(
        self,
        values: list[float],
        max_labels: int,
    ) -> list[float]:
        if len(values) <= max_labels:
            return values

        stride = max(math.ceil(len(values) / max_labels), 1)
        sparse = values[::stride]
        if values and sparse[-1] != values[-1]:
            sparse.append(values[-1])
        return sparse

    def _format_tick_value(self, value: float) -> str:
        rounded = round(value, 6)
        if abs(rounded) < 1.0e-9:
            rounded = 0.0
        text = f"{rounded:.3f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _draw_point_marker(
        self,
        painter: QPainter,
        orbit_point: OrbitPoint,
        canvas_point: QPointF,
        radius: int,
    ) -> None:
        if not self._view_config.show_branch_markers:
            painter.drawEllipse(canvas_point, radius, radius)
            return

        branch = (orbit_point.branch or "").strip().lower()
        if branch == "cross_wall":
            painter.drawRect(
                QRectF(
                    canvas_point.x() - radius,
                    canvas_point.y() - radius,
                    2.0 * radius,
                    2.0 * radius,
                )
            )
            return

        if branch == "same_wall":
            self._draw_diamond(painter, canvas_point, radius)
            return

        if branch == "seed":
            painter.drawEllipse(canvas_point, radius + 1, radius + 1)
            return

        painter.drawEllipse(canvas_point, radius, radius)

    def _draw_diamond(
        self,
        painter: QPainter,
        center: QPointF,
        radius: int,
    ) -> None:
        path = QPainterPath()
        path.moveTo(center.x(), center.y() - radius)
        path.lineTo(center.x() + radius, center.y())
        path.lineTo(center.x(), center.y() + radius)
        path.lineTo(center.x() - radius, center.y())
        path.closeSubpath()
        painter.drawPath(path)

    def _draw_heatmap_overlay(
        self,
        painter: QPainter,
        domain_rect: QRectF,
    ) -> None:
        points = self._heatmap_points()
        if not points:
            return

        resolution = max(int(self._view_config.heatmap_resolution), 4)
        d_min, d_max, tau_min, tau_max = self._viewport
        d_span = max(d_max - d_min, 1.0e-12)
        tau_span = max(tau_max - tau_min, 1.0e-12)
        bins = [[0 for _ in range(resolution)] for _ in range(resolution)]

        for d_value, tau_value in points:
            if d_value < d_min or d_value > d_max or tau_value < tau_min or tau_value > tau_max:
                continue
            x_ratio = min(max((d_value - d_min) / d_span, 0.0), 0.999999)
            y_ratio = min(max((tau_value - tau_min) / tau_span, 0.0), 0.999999)
            ix = min(int(x_ratio * resolution), resolution - 1)
            iy = min(int(y_ratio * resolution), resolution - 1)
            bins[iy][ix] += 1

        max_count = max((count for row in bins for count in row), default=0)
        if max_count <= 0:
            return

        clip_path = QPainterPath()
        clip_path.addEllipse(domain_rect)
        painter.save()
        painter.setClipPath(clip_path, Qt.IntersectClip)
        painter.setPen(Qt.NoPen)

        normalization = self._view_config.heatmap_normalization.strip().lower()
        for iy, row in enumerate(bins):
            tau_low = tau_min + (iy / resolution) * tau_span
            tau_high = tau_min + ((iy + 1) / resolution) * tau_span
            top = self._to_canvas(d_min, tau_high).y()
            bottom = self._to_canvas(d_min, tau_low).y()
            for ix, count in enumerate(row):
                if count <= 0:
                    continue

                if normalization == "log":
                    intensity = math.log1p(count) / math.log1p(max_count)
                else:
                    intensity = count / max_count

                d_left = d_min + (ix / resolution) * d_span
                d_right = d_min + ((ix + 1) / resolution) * d_span
                left = self._to_canvas(d_left, tau_min).x()
                right = self._to_canvas(d_right, tau_min).x()
                color = QColor(214, 39, 40, max(18, int(140 * intensity)))
                painter.fillRect(
                    QRectF(
                        min(left, right),
                        min(top, bottom),
                        abs(right - left),
                        abs(bottom - top),
                    ),
                    color,
                )

        painter.restore()

    def _heatmap_points(self) -> list[tuple[float, float]]:
        if self._view_config.heatmap_mode.strip().lower() == "selected":
            if self._selected_trajectory_id is None:
                return []
            trajectory_ids = [self._selected_trajectory_id]
        else:
            trajectory_ids = list(self._orbits.keys())

        points: list[tuple[float, float]] = []
        for trajectory_id in trajectory_ids:
            seed = self._seeds.get(trajectory_id)
            orbit = self._orbits.get(trajectory_id)
            if seed is None or orbit is None or not seed.visible:
                continue

            active_index = self._active_frames.get(trajectory_id)
            for point in orbit.points:
                if point.wall != self.wall:
                    continue
                if active_index is not None and point.step_index > active_index:
                    continue
                points.append((point.d, point.tau))

        return points

    def _apply_zoom_rect(self) -> None:
        plot = self._plot_rect()
        zoom_rect = self._zoom_rect_canvas
        self._zoom_anchor_canvas = None
        self._zoom_rect_canvas = None
        if zoom_rect is None:
            self._update_hint()
            self.update()
            return

        clipped = zoom_rect.intersected(plot)
        if clipped.width() < 8 or clipped.height() < 8:
            self._update_hint()
            self.update()
            return

        top_left = self._map_click(clipped.topLeft())
        bottom_right = self._map_click(clipped.bottomRight())
        d_min = min(top_left[0], bottom_right[0])
        d_max = max(top_left[0], bottom_right[0])
        tau_min = min(top_left[1], bottom_right[1])
        tau_max = max(top_left[1], bottom_right[1])
        if d_max - d_min < 1.0e-6 or tau_max - tau_min < 1.0e-6:
            self._update_hint()
            self.update()
            return

        self._viewport = (d_min, d_max, tau_min, tau_max)
        logger.info(
            "Phase viewport box-zoom applied: wall=%s viewport=%s",
            self.wall,
            self._viewport,
        )
        logger.debug(
            "Phase viewport box-zoom applied: wall=%s viewport=%s",
            self.wall,
            self._viewport,
        )
        self._update_hint()
        self.viewport_changed.emit()
        self.update()

    def _clamp_to_plot(self, point: QPointF, plot: QRectF) -> QPointF:
        return QPointF(
            min(max(point.x(), plot.left()), plot.right()),
            min(max(point.y(), plot.top()), plot.bottom()),
        )

    def _update_hint(self) -> None:
        if self._fixed_domain:
            self._hint.setText("fixed domain | disable in Parameters for zoom/pan")
            return

        d_min, d_max, tau_min, tau_max = self._viewport
        if self._pan_anchor_canvas is not None:
            self._hint.setText("free zoom | pan")
            return
        if self._zoom_rect_canvas is not None:
            self._hint.setText("free zoom | select area")
            return
        self._hint.setText(
            "free zoom | "
            f"d=[{d_min:.3f}, {d_max:.3f}] tau=[{tau_min:.3f}, {tau_max:.3f}]"
        )

    def _emit_click(self, point: QPointF) -> None:
        d_value, tau_value = self._map_click(point)
        if not self._is_inside_domain(d_value, tau_value):
            self._last_click.setText("click: outside domain")
            self.update()
            return

        self._last_click.setText(f"click: d={d_value:.3f}, tau={tau_value:.3f}")
        self.clicked.emit(self.wall, d_value, tau_value)
        self.update()

    def _draw_crosshair_overlay(
        self,
        painter: QPainter,
        plot: QRectF,
        point: QPointF,
    ) -> str:
        d_value, tau_value = self._map_click(point)
        label_text = f"d={d_value:.3f}, tau={tau_value:.3f}"
        painter.setPen(QPen(QColor(60, 60, 60, 120), 1, Qt.DashLine))
        painter.drawLine(QPointF(plot.left(), point.y()), QPointF(plot.right(), point.y()))
        painter.drawLine(QPointF(point.x(), plot.top()), QPointF(point.x(), plot.bottom()))

        return label_text

    def _draw_hover_label(
        self,
        painter: QPainter,
        plot: QRectF,
        label_text: str,
    ) -> None:
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(label_text)
        label_width = text_width + 16.0
        label_height = metrics.height() + 6.0
        label_rect = QRectF(
            plot.left() + 8.0,
            plot.bottom() + 6.0,
            label_width,
            label_height,
        )
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(label_rect, 4.0, 4.0)
        painter.setPen(QColor("#222222"))
        painter.drawText(
            label_rect.adjusted(6.0, 0.0, -6.0, 0.0),
            Qt.AlignVCenter | Qt.AlignLeft,
            label_text,
        )
