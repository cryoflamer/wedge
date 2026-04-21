from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QToolTip, QVBoxLayout, QWidget

from app.core.region_eval import evaluate_boundary_value, evaluate_region
from app.models.config import ViewConfig
from app.models.region import RegionDescription


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
        self._symmetric_mode = False
        self._regions: list[RegionDescription] = []
        self._hover_point: QPointF | None = None
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

    def set_regions(self, regions: list[RegionDescription]) -> None:
        self._regions = sorted(regions, key=lambda item: item.priority)
        self.update()

    def set_angle_units(self, units: str) -> None:
        self._angle_units = units.strip().lower() if units.strip() else "rad"
        self._hint.setText(f"parameter space ({self._angle_units})")
        self._point_label.setText(
            f"point: α={self._format_angle(self._alpha)}, β={self._format_angle(self._beta)}"
        )
        self.update()

    def set_symmetric_mode(self, enabled: bool) -> None:
        self._symmetric_mode = enabled
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return

        alpha, beta = self._selection_from_position(event.position())
        if not self._is_inside_domain(alpha, beta):
            return

        self._point_label.setText(
            f"point: α={self._format_angle(alpha)}, β={self._format_angle(beta)}"
        )
        self.point_selected.emit(alpha, beta)

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
        if not self._view_config.angle_hover_tooltip:
            self.update()
            return

        alpha, beta = self._selection_from_position(event.position())
        if self._is_inside_domain(alpha, beta):
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"α={self._format_angle(alpha)}\nβ={self._format_angle(beta)}",
                self,
            )
        else:
            QToolTip.hideText()
        self.update()

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
        return QRectF(
            self._padding,
            top,
            max(self.width() - 2 * self._padding, 1),
            max(self.height() - top - self._bottom_margin, 1),
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
        if not self._symmetric_mode:
            return alpha, beta

        projected_alpha = min(
            max(alpha, math.nextafter(0.0, 1.0)),
            math.nextafter(math.pi / 2.0, 0.0),
        )
        projected_beta = math.nextafter(math.pi - projected_alpha, projected_alpha)
        return projected_alpha, projected_beta

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

    def _build_boundary_segments(
        self,
        region: RegionDescription,
        alpha_steps: int = 160,
        beta_steps: int = 320,
    ) -> list[tuple[QPointF, QPointF]]:
        alpha_values = [
            (math.pi / 2.0) * index / alpha_steps
            for index in range(alpha_steps + 1)
        ]
        beta_values = [
            math.pi * index / beta_steps
            for index in range(beta_steps + 1)
        ]

        value_grid: list[list[float | None]] = []
        for alpha in alpha_values:
            row: list[float | None] = []
            for beta in beta_values:
                if not self._is_inside_domain(alpha, beta):
                    row.append(None)
                    continue
                row.append(evaluate_boundary_value(region, alpha, beta))
            value_grid.append(row)

        segments: list[tuple[QPointF, QPointF]] = []
        for alpha_index in range(alpha_steps):
            alpha0 = alpha_values[alpha_index]
            alpha1 = alpha_values[alpha_index + 1]
            for beta_index in range(beta_steps):
                beta0 = beta_values[beta_index]
                beta1 = beta_values[beta_index + 1]

                corners = [
                    (alpha0, beta0, value_grid[alpha_index][beta_index]),
                    (alpha1, beta0, value_grid[alpha_index + 1][beta_index]),
                    (alpha1, beta1, value_grid[alpha_index + 1][beta_index + 1]),
                    (alpha0, beta1, value_grid[alpha_index][beta_index + 1]),
                ]
                if any(value is None for _, _, value in corners):
                    continue

                crossings: list[tuple[float, float]] = []
                edge_pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
                for start_index, end_index in edge_pairs:
                    crossing = self._edge_crossing(
                        corners[start_index],
                        corners[end_index],
                    )
                    if crossing is not None:
                        crossings.append(crossing)

                if len(crossings) == 2:
                    segments.append(
                        (
                            self._to_canvas(crossings[0][0], crossings[0][1]),
                            self._to_canvas(crossings[1][0], crossings[1][1]),
                        )
                    )
                elif len(crossings) == 4:
                    center_alpha = 0.5 * (alpha0 + alpha1)
                    center_beta = 0.5 * (beta0 + beta1)
                    center_value = evaluate_boundary_value(
                        region,
                        center_alpha,
                        center_beta,
                    )
                    if center_value is None:
                        continue
                    if center_value >= 0.0:
                        pairings = ((0, 1), (2, 3))
                    else:
                        pairings = ((0, 3), (1, 2))
                    for start_index, end_index in pairings:
                        segments.append(
                            (
                                self._to_canvas(
                                    crossings[start_index][0],
                                    crossings[start_index][1],
                                ),
                                self._to_canvas(
                                    crossings[end_index][0],
                                    crossings[end_index][1],
                                ),
                            )
                        )

        return segments

    def _edge_crossing(
        self,
        start: tuple[float, float, float | None],
        end: tuple[float, float, float | None],
        epsilon: float = 1.0e-12,
    ) -> tuple[float, float] | None:
        alpha0, beta0, value0 = start
        alpha1, beta1, value1 = end
        if value0 is None or value1 is None:
            return None

        if abs(value0) <= epsilon and abs(value1) <= epsilon:
            return None
        if abs(value0) <= epsilon:
            return alpha0, beta0
        if abs(value1) <= epsilon:
            return alpha1, beta1
        if value0 * value1 > 0.0:
            return None

        ratio = value0 / (value0 - value1)
        alpha = alpha0 + ratio * (alpha1 - alpha0)
        beta = beta0 + ratio * (beta1 - beta0)
        if not self._is_inside_domain(alpha, beta):
            return None
        return alpha, beta

    def _draw_regions(self, painter: QPainter) -> None:
        if not self._regions or not self._view_config.show_regions:
            return

        legend_items: list[tuple[QColor, str, str]] = []
        for region in self._regions:
            if not region.visible:
                continue

            sample_points: list[QPointF] = []
            boundary_segments: list[tuple[QPointF, QPointF]] = []
            if region.region_type == "boundary":
                boundary_segments = self._build_boundary_segments(region)
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
                        if evaluate_region(region, alpha, beta):
                            sample_points.append(self._to_canvas(alpha, beta))

                if not sample_points:
                    continue

            color = QColor(region.style.fill)
            color.setAlphaF(max(0.0, min(region.style.alpha, 1.0)))
            border_pen = QPen(QColor(region.style.border), 1)
            border_pen.setStyle(self._pen_style(region.style.line_style))
            painter.setPen(border_pen)
            painter.setBrush(self._region_brush(color, region.style.hatch))

            if region.region_type == "boundary":
                for start, end in boundary_segments:
                    painter.drawLine(start, end)
            else:
                for point in sample_points:
                    painter.drawEllipse(point, 2, 2)

            if self._view_config.show_region_labels:
                center_x = sum(point.x() for point in sample_points) / len(sample_points)
                center_y = sum(point.y() for point in sample_points) / len(sample_points)
                painter.setPen(QColor(region.style.border))
                painter.drawText(
                    QPointF(center_x + 4.0, center_y - 4.0),
                    region.display_text,
                )

            legend_items.append(
                (
                    QColor(region.style.border),
                    region.display_text,
                    region.legend_text,
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
        row_height = 18.0
        legend_width = min(plot.width() * 0.48, 250.0)
        legend_height = 12.0 + row_height * len(legend_items)
        legend_rect = QRectF(
            plot.right() - legend_width - 10.0,
            plot.top() + 10.0,
            legend_width,
            legend_height,
        )
        painter.setPen(QPen(QColor("#888888"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(legend_rect, 6.0, 6.0)

        for index, (color, display_text, legend_text) in enumerate(legend_items):
            y = legend_rect.top() + 16.0 + row_height * index
            painter.setPen(QPen(color, 2))
            painter.drawLine(
                QPointF(legend_rect.left() + 8.0, y - 4.0),
                QPointF(legend_rect.left() + 22.0, y - 4.0),
            )
            painter.setPen(QColor("#222222"))
            painter.drawText(
                QPointF(legend_rect.left() + 28.0, y),
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

        painter.setPen(QPen(QColor("#c8c8c8"), 1))
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())
        painter.drawLine(plot.bottomLeft(), plot.topLeft())

        painter.setPen(QPen(QColor("#8fb9e8"), 2))
        painter.setBrush(QColor(214, 231, 248, 80))
        painter.drawPath(self._build_domain_path())
        self._draw_regions(painter)

        if self._symmetric_mode:
            painter.setPen(QPen(QColor("#d62728"), 2, Qt.DashLine))
            painter.drawLine(
                self._to_canvas(0.0, math.pi),
                self._to_canvas(math.pi / 2.0, math.pi / 2.0),
            )

        if self._hover_point is not None:
            self._draw_crosshair_overlay(painter, plot, self._hover_point)

        if self._is_inside_domain(self._alpha, self._beta):
            painter.setPen(QPen(QColor("#111111"), 2))
            painter.setBrush(QColor("#111111"))
            point = self._to_canvas(self._alpha, self._beta)
            painter.drawEllipse(point, 5, 5)

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

        label_rect = QRectF(plot.left() + 8.0, plot.bottom() - 28.0, 210.0, 20.0)
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawRoundedRect(label_rect, 4.0, 4.0)
        painter.setPen(QColor("#222222"))
        painter.drawText(
            label_rect.adjusted(6.0, 0.0, -6.0, 0.0),
            Qt.AlignVCenter | Qt.AlignLeft,
            f"alpha={self._format_angle(alpha)}, beta={self._format_angle(beta)}",
        )
