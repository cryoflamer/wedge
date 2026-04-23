from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QLabel, QToolTip, QVBoxLayout, QWidget

from app.core.point_constraints import (
    ActivePointConstraint,
    BoundarySegment,
    build_boundary_segments,
    project_point_to_constraint,
)
from app.models.constraint import ConstraintDescription
from app.core.region_eval import evaluate_scene_item
from app.models.config import ViewConfig
from app.models.scene_item import SceneItemDescription, is_boundary_scene_item


class AnglePanel(QWidget):
    point_selected = Signal(float, float)

    def __init__(
        self,
        view_config: ViewConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._view_config = view_config
        self._title = QLabel("α / β")
        self._hint = QLabel("parameter space")
        self._point_label = QLabel("point: -")
        self._alpha = 0.0
        self._beta = 0.0
        self._angle_units = "rad"
        self._active_constraint: ActivePointConstraint | None = None
        self._scene_items: list[SceneItemDescription] = []
        self._selected_scene_item_name: str | None = None
        self._boundary_item_names: set[str] = set()
        self._predicate_item_names: set[str] = set()
        self._constraints: list[ConstraintDescription] = []
        self._boundary_segments_cache: dict[str, tuple[BoundarySegment, ...]] = {}
        self._hover_point: QPointF | None = None
        self._dragging = False
        self._padding = 24
        self._top_margin = 16
        self._bottom_margin = 16
        self._header_spacing = 4

        for label in (self._title, self._hint, self._point_label):
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
        layout.addWidget(self._point_label)
        layout.addStretch(1)

        self.setMinimumHeight(220)
        self.setMouseTracking(True)
        self.setStyleSheet(
            "AnglePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )

    def set_angles(self, alpha: float, beta: float) -> None:
        self._alpha = alpha
        self._beta = beta
        self._point_label.setText(
            f"point: α={self._format_angle(alpha)}, β={self._format_angle(beta)}"
        )
        self.update()

    def set_regions(self, regions: list[SceneItemDescription]) -> None:
        self._scene_items = sorted(regions, key=lambda item: item.priority)
        self._boundary_segments_cache = {
            item.name: tuple(build_boundary_segments(item, self._is_inside_domain))
            for item in self._scene_items
            if is_boundary_scene_item(item)
        }
        self.update()

    def set_selected_scene_item(self, name: str | None) -> None:
        if name == self._selected_scene_item_name:
            return
        self._selected_scene_item_name = name
        self.update()

    def set_constraints(self, constraints: list[ConstraintDescription]) -> None:
        self._constraints = sorted(constraints, key=lambda item: item.priority)
        self.update()

    def set_angle_units(self, units: str) -> None:
        self._angle_units = units.strip().lower() if units.strip() else "rad"
        self._hint.setText(f"parameter space ({self._angle_units})")
        self._point_label.setText(
            f"point: α={self._format_angle(self._alpha)}, β={self._format_angle(self._beta)}"
        )
        self.update()

    def set_active_constraint(
        self,
        constraint: ActivePointConstraint | None,
    ) -> None:
        self._active_constraint = self._hydrate_constraint(constraint)
        self.update()

    def hydrated_constraint(
        self,
        constraint: ActivePointConstraint | None,
    ) -> ActivePointConstraint | None:
        return self._hydrate_constraint(constraint)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton or not self._plot_rect().contains(event.position()):
            return

        self._dragging = True
        self._apply_interaction_point(event.position(), commit=False)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        plot = self._plot_rect()
        self._hover_point = (
            QPointF(
                min(max(event.position().x(), plot.left()), plot.right()),
                min(max(event.position().y(), plot.top()), plot.bottom()),
            )
            if plot.contains(event.position())
            else None
        )
        if self._dragging:
            self._apply_interaction_point(event.position(), commit=False)
        if not self._view_config.angle_hover_tooltip:
            self.update()
            return

        hover_text = self._hover_overlay_text(self._hover_point)
        if hover_text:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                hover_text,
                self,
            )
        else:
            QToolTip.hideText()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._dragging:
            self._dragging = False
            self._apply_interaction_point(event.position(), commit=True)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_point = None
        self.update()
        QToolTip.hideText()
        super().leaveEvent(event)

    def _map_click(self, point: QPointF) -> tuple[float, float]:
        plot = self._plot_rect()
        if plot.width() <= 0 or plot.height() <= 0:
            return 0.0, 0.0

        x_ratio = min(max((point.x() - plot.left()) / plot.width(), 0.0), 1.0)
        y_ratio = min(max((point.y() - plot.top()) / plot.height(), 0.0), 1.0)
        alpha = x_ratio * (math.pi / 2.0)
        beta = (1.0 - y_ratio) * math.pi
        return alpha, beta

    def _plot_rect(self) -> QRectF:
        top = self._header_height() + 12.0
        left_margin, bottom_margin = self._axis_label_margins()
        available_left = self._padding + left_margin
        available_top = top
        available_width = max(self.width() - (2 * self._padding + left_margin), 1)
        available_height = max(
            self.height() - top - self._bottom_margin - bottom_margin,
            1,
        )
        side = max(min(available_width, available_height), 1)
        return QRectF(
            available_left + (available_width - side) / 2.0,
            available_top + (available_height - side) / 2.0,
            side,
            side,
        )

    def _header_height(self) -> float:
        return (
            self._top_margin
            + self._title.height()
            + self._hint.height()
            + self._point_label.height()
            + 2 * self._header_spacing
        )

    def _to_canvas(self, alpha: float, beta: float) -> QPointF:
        plot = self._plot_rect()
        x = plot.left() + (alpha / (math.pi / 2.0)) * plot.width()
        y = plot.bottom() - (beta / math.pi) * plot.height()
        return QPointF(x, y)

    def _is_inside_domain(self, alpha: float, beta: float) -> bool:
        return 0.0 < alpha <= math.pi / 2.0 and alpha < beta < math.pi - alpha

    def _selection_from_position(self, point: QPointF) -> tuple[float, float]:
        alpha, beta = self._map_click(point)
        return project_point_to_constraint(alpha, beta, self._active_constraint)

    def _hydrate_constraint(
        self,
        constraint: ActivePointConstraint | None,
    ) -> ActivePointConstraint | None:
        if constraint is None:
            return None
        if (
            constraint.kind == "boundary"
            and not constraint.boundary_segments
            and constraint.region_name is not None
        ):
            return ActivePointConstraint(
                kind="boundary",
                region_name=constraint.region_name,
                boundary_segments=self._boundary_segments_cache.get(
                    constraint.region_name,
                    (),
                ),
            )
        return constraint

    def _apply_interaction_point(
        self,
        point: QPointF,
        commit: bool,
    ) -> None:
        alpha, beta = self._selection_from_position(point)
        if not self._is_inside_domain(alpha, beta):
            return
        self.set_angles(alpha, beta)
        if commit:
            self.point_selected.emit(alpha, beta)

    def _format_angle(self, value: float) -> str:
        if self._angle_units == "deg":
            return f"{math.degrees(value):.3f} deg"
        return f"{value:.6f} rad"

    def _build_domain_path(self) -> QPainterPath:
        path = QPainterPath()
        first = True
        for step in range(0, 121):
            alpha = (math.pi / 2.0) * step / 120.0
            beta = math.pi - alpha
            point = self._to_canvas(alpha, beta)
            if first:
                path.moveTo(point)
                first = False
            else:
                path.lineTo(point)

        for step in range(120, -1, -1):
            alpha = (math.pi / 2.0) * step / 120.0
            beta = alpha
            point = self._to_canvas(alpha, beta)
            path.lineTo(point)

        path.closeSubpath()
        return path

    def _axis_tick_values(self) -> tuple[list[float], list[float]]:
        # Always include 0 and endpoint (π/2 for alpha, π for beta)
        alpha_ticks = [0.0, math.pi / 12.0, math.pi / 6.0, math.pi / 4.0, math.pi / 3.0, 5.0 * math.pi / 12.0, math.pi / 2.0]
        beta_ticks = [0.0, math.pi / 6.0, math.pi / 4.0, math.pi / 3.0, math.pi / 2.0, 2.0 * math.pi / 3.0, 3.0 * math.pi / 4.0, 5.0 * math.pi / 6.0, math.pi]
        return alpha_ticks, beta_ticks

    def _format_tick_label(self, value: float) -> str:
        if self._angle_units == "deg":
            return f"{round(math.degrees(value))}°"
        return self._format_pi_tick_label(value)

    def _format_pi_tick_label(self, value: float) -> str:
        # Special case for zero
        if abs(value) < 1e-8:
            return "0"
        # Special case for pi (endpoint)
        if abs(value - math.pi) < 1e-8:
            return "π"
        # Common fractions
        common_fractions = {
            round(math.pi / 12.0, 12): "π/12",
            round(math.pi / 6.0, 12): "π/6",
            round(math.pi / 4.0, 12): "π/4",
            round(math.pi / 3.0, 12): "π/3",
            round(5.0 * math.pi / 12.0, 12): "5π/12",
            round(math.pi / 2.0, 12): "π/2",
            round(2.0 * math.pi / 3.0, 12): "2π/3",
            round(3.0 * math.pi / 4.0, 12): "3π/4",
            round(5.0 * math.pi / 6.0, 12): "5π/6",
        }
        rounded = round(value, 12)
        if rounded in common_fractions:
            return common_fractions[rounded]
        # Fallback: format as a multiple of π
        coeff = value / math.pi
        if abs(coeff - round(coeff)) < 1e-8:
            return f"{int(round(coeff))}π"
        return f"{coeff:.2f}π"

    def _axis_label_margins(self) -> tuple[float, float]:
        metrics = self.fontMetrics()
        alpha_ticks, beta_ticks = self._axis_tick_values()
        x_labels = [self._format_tick_label(value) for value in alpha_ticks]
        y_labels = [self._format_tick_label(value) for value in beta_ticks]
        max_y_label_width = max(
            (metrics.horizontalAdvance(label) for label in y_labels),
            default=0,
        )
        x_label_height = metrics.height()
        tick_length = 5.0
        left_margin = max_y_label_width + tick_length + 8.0
        bottom_margin = x_label_height + tick_length + 6.0
        return left_margin, bottom_margin

    def _draw_grid_and_axes(self, painter: QPainter, plot: QRectF) -> None:
        alpha_ticks, beta_ticks = self._axis_tick_values()

        grid_pen = QPen(QColor(215, 215, 215, 180), 1)
        painter.setPen(grid_pen)
        for alpha in alpha_ticks:
            point = self._to_canvas(alpha, math.pi / 2.0)
            painter.drawLine(
                QPointF(point.x(), plot.top()),
                QPointF(point.x(), plot.bottom()),
            )
        for beta in beta_ticks:
            point = self._to_canvas(math.pi / 4.0, beta)
            painter.drawLine(
                QPointF(plot.left(), point.y()),
                QPointF(plot.right(), point.y()),
            )

        axis_pen = QPen(QColor("#8a8a8a"), 1)
        tick_pen = QPen(QColor("#7a7a7a"), 1)
        label_pen = QPen(QColor("#444444"), 1)
        metrics = painter.fontMetrics()
        tick_length = 5.0

        painter.setPen(axis_pen)
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.bottomLeft(), plot.topLeft())

        painter.setPen(tick_pen)
        for alpha in alpha_ticks:
            point = self._to_canvas(alpha, math.pi / 2.0)
            painter.drawLine(
                QPointF(point.x(), plot.bottom()),
                QPointF(point.x(), plot.bottom() + tick_length),
            )
            label = self._format_tick_label(alpha)
            label_width = metrics.horizontalAdvance(label)
            painter.setPen(label_pen)
            painter.drawText(
                QPointF(
                    point.x() - label_width / 2.0,
                    plot.bottom() + tick_length + metrics.ascent() + 2.0,
                ),
                label,
            )
            painter.setPen(tick_pen)

        for beta in beta_ticks:
            point = self._to_canvas(math.pi / 4.0, beta)
            painter.drawLine(
                QPointF(plot.left() - tick_length, point.y()),
                QPointF(plot.left(), point.y()),
            )
            label = self._format_tick_label(beta)
            label_width = metrics.horizontalAdvance(label)
            painter.setPen(label_pen)
            painter.drawText(
                QPointF(
                    plot.left() - tick_length - label_width - 4.0,
                    point.y() + metrics.ascent() / 2.5,
                ),
                label,
            )
            painter.setPen(tick_pen)

    def _draw_regions(self, painter: QPainter) -> None:
        if not self._scene_items or not self._view_config.show_regions:
            return

        legend_items: list[tuple[QColor, str, str]] = []
        for item in self._scene_items:
            if not item.visible:
                continue
            is_selected_scene_item = item.name == self._selected_scene_item_name

            sample_points: list[QPointF] = []
            boundary_segments: list[tuple[QPointF, QPointF]] = []
            if is_boundary_scene_item(item):
                is_active_boundary = (
                    self._active_constraint is not None
                    and self._active_constraint.kind == "boundary"
                    and self._active_constraint.region_name == item.name
                )
                boundary_segments = [
                    (
                        self._to_canvas(segment.start_alpha, segment.start_beta),
                        self._to_canvas(segment.end_alpha, segment.end_beta),
                    )
                    for segment in self._boundary_segments_cache.get(item.name, ())
                ]
                if not boundary_segments:
                    continue
                for start, end in boundary_segments:
                    sample_points.extend((start, end))
            else:
                for alpha_step in range(0, 41):
                    alpha = (math.pi / 2.0) * alpha_step / 40.0
                    for beta_step in range(0, 81):
                        beta = math.pi * beta_step / 80.0
                        if not self._is_inside_domain(alpha, beta):
                            continue
                        if evaluate_scene_item(item, alpha, beta):
                            sample_points.append(self._to_canvas(alpha, beta))

                if not sample_points:
                    continue

            color = QColor(item.style.fill)
            color.setAlphaF(max(0.0, min(item.style.alpha, 1.0)))
            border_color = QColor("#d62728") if (
                is_boundary_scene_item(item)
                and self._active_constraint is not None
                and self._active_constraint.kind == "boundary"
                and self._active_constraint.region_name == item.name
            ) else QColor(item.style.border)
            base_width = max(float(item.style.line_width), 0.5)
            if is_selected_scene_item:
                if item.relation == "=":
                    border_color = border_color.lighter(125)
                    base_width = max(base_width + 1.0, 2.0)
                else:
                    color.setAlphaF(min(color.alphaF() + 0.12, 0.75))
                    border_color = border_color.lighter(115)
                    base_width = max(base_width + 0.75, 1.25)
            if (
                is_boundary_scene_item(item)
                and self._active_constraint is not None
                and self._active_constraint.kind == "boundary"
                and self._active_constraint.region_name == item.name
            ):
                base_width = max(base_width, 2.0)
            border_pen = QPen(border_color, base_width)
            border_pen.setStyle(self._pen_style(item.style.line_style))
            painter.setPen(border_pen)
            painter.setBrush(self._region_brush(color, item.style.hatch))

            if is_boundary_scene_item(item):
                boundary_path = QPainterPath()
                for chain in self._ordered_boundary_chains(boundary_segments):
                    if len(chain) < 2:
                        continue
                    boundary_path.moveTo(chain[0])
                    for point in chain[1:]:
                        boundary_path.lineTo(point)
                painter.drawPath(boundary_path)
            else:
                for point in sample_points:
                    painter.drawEllipse(point, 2, 2)

            if (
                self._view_config.show_region_labels
                and self._view_config.show_labels_on_plot
            ):
                center_x = sum(point.x() for point in sample_points) / len(sample_points)
                center_y = sum(point.y() for point in sample_points) / len(sample_points)
                plot_label = self._plot_label_text(item)
                self._draw_text_overlay(
                    painter,
                    self._plot_rect(),
                    QPointF(center_x + 4.0, center_y - 4.0),
                    plot_label,
                    border_color=QColor(item.style.border),
                    anchor="top_left",
                )

            legend_items.append(
                (
                    QColor(item.style.border),
                    item.display_text,
                    item.legend_text,
                )
            )

        if self._view_config.show_region_legend and legend_items:
            self._draw_legend(painter, legend_items)

    def _draw_legend(
        self,
        painter: QPainter,
        legend_items: list[tuple[QColor, str, str]],
    ) -> None:
        plot = self._plot_rect()
        margin = 10.0
        line_x0 = 8.0
        line_x1 = 22.0
        text_x = 28.0
        top_padding = 8.0
        bottom_padding = 8.0
        metrics = painter.fontMetrics()
        row_height = float(max(metrics.height(), 14) + 4)
        line_texts = [f"{display_text}: {legend_text}" for _, display_text, legend_text in legend_items]
        text_width = max((metrics.horizontalAdvance(text) for text in line_texts), default=0)
        legend_width = min(
            max(text_x + text_width + 10.0, 120.0),
            max(plot.width() - 2.0 * margin, 40.0),
        )
        legend_height = top_padding + bottom_padding + row_height * len(legend_items)
        legend_rect = self._clamp_overlay_rect(
            plot,
            QRectF(
                plot.right() - legend_width - margin,
                plot.top() + margin,
                legend_width,
                legend_height,
            ),
        )
        painter.setPen(QPen(QColor("#888888"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(legend_rect, 6.0, 6.0)

        for index, (color, display_text, legend_text) in enumerate(legend_items):
            y = legend_rect.top() + top_padding + metrics.ascent() + row_height * index
            painter.setPen(QPen(color, 2))
            painter.drawLine(
                QPointF(legend_rect.left() + line_x0, y - metrics.ascent() * 0.35),
                QPointF(legend_rect.left() + line_x1, y - metrics.ascent() * 0.35),
            )
            painter.setPen(QColor("#222222"))
            painter.drawText(
                QPointF(legend_rect.left() + text_x, y),
                f"{display_text}: {legend_text}",
            )

    def _pen_style(self, line_style: str) -> Qt.PenStyle:
        normalized = line_style.strip().lower()
        if normalized == "dashed":
            return Qt.DashLine
        if normalized == "dotted":
            return Qt.DotLine
        if normalized == "dashdot":
            return Qt.DashDotLine
        return Qt.SolidLine

    def _region_brush(self, color: QColor, hatch: str) -> QBrush:
        brush = QBrush(color)
        normalized = hatch.strip()
        if normalized == "/":
            brush.setStyle(Qt.FDiagPattern)
        elif normalized == "\\":
            brush.setStyle(Qt.BDiagPattern)
        elif normalized == "|":
            brush.setStyle(Qt.VerPattern)
        elif normalized == "-":
            brush.setStyle(Qt.HorPattern)
        elif normalized == "+":
            brush.setStyle(Qt.CrossPattern)
        elif normalized in ("x", "X"):
            brush.setStyle(Qt.DiagCrossPattern)
        elif normalized == ".":
            brush.setStyle(Qt.Dense6Pattern)
        else:
            brush.setStyle(Qt.SolidPattern)
        return brush

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        plot = self._plot_rect()

        painter.setPen(QPen(Qt.gray, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.drawRect(plot)

        self._draw_grid_and_axes(painter, plot)

        painter.setPen(QPen(QColor("#8fb9e8"), 2))
        painter.setBrush(QColor(214, 231, 248, 80))
        painter.drawPath(self._build_domain_path())
        self._draw_regions(painter)
        self._draw_constraints(painter)

        if self._hover_point is not None:
            self._draw_crosshair_overlay(painter, plot, self._hover_point)

        if self._is_inside_domain(self._alpha, self._beta):
            painter.setPen(QPen(QColor("#111111"), 2))
            painter.setBrush(QColor("#111111"))
            point = self._to_canvas(self._alpha, self._beta)
            painter.drawEllipse(point, 5, 5)

    def _draw_constraints(self, painter: QPainter) -> None:
        if not self._constraints:
            return

        for constraint in self._constraints:
            if not constraint.visible:
                continue
            kind = constraint.constraint_type.strip().lower()
            if kind != "symmetry":
                continue
            is_active = (
                self._active_constraint is not None
                and self._active_constraint.kind == "symmetry"
                and self._active_constraint.region_name == constraint.name
            )
            painter.setPen(
                QPen(
                    QColor("#d62728" if is_active else "#cc8899"),
                    3 if is_active else 1.5,
                    Qt.DashLine,
                )
            )
            painter.drawLine(
                self._to_canvas(0.0, math.pi),
                self._to_canvas(math.pi / 2.0, math.pi / 2.0),
            )

    def _ordered_boundary_chains(
        self,
        segments: list[tuple[QPointF, QPointF]],
    ) -> list[list[QPointF]]:
        remaining = list(segments)
        chains: list[list[QPointF]] = []
        tolerance = 1.5

        while remaining:
            start, end = remaining.pop(0)
            chain = [start, end]
            extended = True
            while extended:
                extended = False
                for index, (segment_start, segment_end) in enumerate(remaining):
                    if self._points_close(chain[-1], segment_start, tolerance):
                        chain.append(segment_end)
                    elif self._points_close(chain[-1], segment_end, tolerance):
                        chain.append(segment_start)
                    elif self._points_close(chain[0], segment_end, tolerance):
                        chain.insert(0, segment_start)
                    elif self._points_close(chain[0], segment_start, tolerance):
                        chain.insert(0, segment_end)
                    else:
                        continue
                    remaining.pop(index)
                    extended = True
                    break
            chains.append(chain)
        return chains

    def _points_close(self, first: QPointF, second: QPointF, tolerance: float) -> bool:
        return (
            abs(first.x() - second.x()) <= tolerance
            and abs(first.y() - second.y()) <= tolerance
        )

    def _draw_crosshair_overlay(
        self,
        painter: QPainter,
        plot: QRectF,
        point: QPointF,
    ) -> None:
        alpha, beta = self._selection_from_position(point)
        if not self._is_inside_domain(alpha, beta):
            return

        painter.setPen(QPen(QColor(60, 60, 60, 120), 1, Qt.DashLine))
        painter.drawLine(
            QPointF(plot.left(), point.y()),
            QPointF(plot.right(), point.y()),
        )
        painter.drawLine(
            QPointF(point.x(), plot.top()),
            QPointF(point.x(), plot.bottom()),
        )

    def _hover_overlay_text(self, point: QPointF | None) -> str:
        if point is None:
            return ""
        alpha, beta = self._selection_from_position(point)
        if not self._is_inside_domain(alpha, beta):
            return ""

        active_text = self._active_point_hover_text(point)
        if active_text:
            return active_text

        boundary_text = self._boundary_hover_text(point)
        if boundary_text:
            return (
                f"Boundary: {boundary_text}\n"
                f"α={self._format_angle(alpha)}\n"
                f"β={self._format_angle(beta)}"
            )

        region_text = self._region_hover_text(alpha, beta)
        if region_text:
            return (
                f"Region: {region_text}\n"
                f"α={self._format_angle(alpha)}\n"
                f"β={self._format_angle(beta)}"
            )

        return (
            f"α={self._format_angle(alpha)}\n"
            f"β={self._format_angle(beta)}"
        )

    def _active_point_hover_text(self, point: QPointF) -> str | None:
        if not self._is_inside_domain(self._alpha, self._beta):
            return None
        active_point = self._to_canvas(self._alpha, self._beta)
        if self._canvas_distance(active_point, point) > 10.0:
            return None
        return (
            "Active point\n"
            f"α={self._format_angle(self._alpha)}\n"
            f"β={self._format_angle(self._beta)}"
        )

    def _boundary_hover_text(self, point: QPointF) -> str | None:
        best_item: SceneItemDescription | None = None
        best_distance = math.inf
        for item in self._scene_items:
            if not item.visible or not is_boundary_scene_item(item):
                continue
            for segment in self._boundary_segments_cache.get(item.name, ()):
                start = self._to_canvas(segment.start_alpha, segment.start_beta)
                end = self._to_canvas(segment.end_alpha, segment.end_beta)
                distance = self._distance_to_segment(point, start, end)
                if distance < best_distance:
                    best_distance = distance
                    best_item = item
        if best_item is None or best_distance > 8.0:
            return None
        return self._tooltip_label_text(best_item)

    def _region_hover_text(self, alpha: float, beta: float) -> str | None:
        for item in reversed(self._scene_items):
            if not item.visible or is_boundary_scene_item(item):
                continue
            if evaluate_scene_item(item, alpha, beta):
                return self._tooltip_label_text(item)
        return None

    def _plot_label_text(self, item: SceneItemDescription) -> str:
        mode = self._view_config.plot_label_mode.strip().lower()
        if mode == "alias":
            return item.display_text
        return item.legend_text

    def _tooltip_label_text(self, item: SceneItemDescription) -> str:
        mode = self._view_config.tooltip_label_mode.strip().lower()
        if mode == "alias":
            return item.display_text
        return item.legend_text

    def _draw_text_overlay(
        self,
        painter: QPainter,
        plot: QRectF,
        anchor_point: QPointF,
        text: str,
        *,
        border_color: QColor | None = None,
        anchor: str = "top_left",
    ) -> None:
        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(
            QRectF(0.0, 0.0, max(plot.width() - 16.0, 20.0), 1000.0).toRect(),
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
            text,
        )
        horizontal_padding = 6.0
        vertical_padding = 4.0
        overlay_rect = QRectF(
            0.0,
            0.0,
            text_rect.width() + 2.0 * horizontal_padding,
            text_rect.height() + 2.0 * vertical_padding,
        )
        if anchor == "bottom_left":
            overlay_rect.moveBottomLeft(anchor_point)
        else:
            overlay_rect.moveTopLeft(anchor_point)
        overlay_rect = self._clamp_overlay_rect(plot, overlay_rect)

        painter.setPen(QPen(border_color or QColor("#666666"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(overlay_rect, 4.0, 4.0)
        painter.setPen(QColor("#222222"))
        painter.drawText(
            overlay_rect.adjusted(
                horizontal_padding,
                vertical_padding,
                -horizontal_padding,
                -vertical_padding,
            ),
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
            text,
        )

    def _clamp_overlay_rect(self, plot: QRectF, rect: QRectF) -> QRectF:
        clamped = QRectF(rect)
        max_width = max(plot.width(), 20.0)
        max_height = max(plot.height(), 20.0)
        if clamped.width() > max_width:
            clamped.setWidth(max_width)
        if clamped.height() > max_height:
            clamped.setHeight(max_height)
        if clamped.left() < plot.left():
            clamped.moveLeft(plot.left())
        if clamped.right() > plot.right():
            clamped.moveRight(plot.right())
        if clamped.top() < plot.top():
            clamped.moveTop(plot.top())
        if clamped.bottom() > plot.bottom():
            clamped.moveBottom(plot.bottom())
        return clamped

    def _canvas_distance(self, first: QPointF, second: QPointF) -> float:
        return math.hypot(first.x() - second.x(), first.y() - second.y())

    def _distance_to_segment(
        self,
        point: QPointF,
        start: QPointF,
        end: QPointF,
    ) -> float:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length_sq = dx * dx + dy * dy
        if length_sq <= 1.0e-18:
            return self._canvas_distance(point, start)
        ratio = (
            ((point.x() - start.x()) * dx) + ((point.y() - start.y()) * dy)
        ) / length_sq
        ratio = min(max(ratio, 0.0), 1.0)
        projected = QPointF(start.x() + ratio * dx, start.y() + ratio * dy)
        return self._canvas_distance(point, projected)
