from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.core.region_eval import evaluate_region_predicate
from app.models.region import RegionDescription


class AnglePanel(QWidget):
    point_selected = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("Alpha / Beta")
        self._hint = QLabel("parameter space")
        self._point_label = QLabel("point: -")
        self._alpha = 0.0
        self._beta = 0.0
        self._regions: list[RegionDescription] = []
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
        self.setStyleSheet(
            "AnglePanel { background: #ffffff; border: 1px solid #a0a0a0; }"
        )

    def set_angles(self, alpha: float, beta: float) -> None:
        self._alpha = alpha
        self._beta = beta
        self._point_label.setText(f"point: alpha={alpha:.6f}, beta={beta:.6f}")
        self.update()

    def set_regions(self, regions: list[RegionDescription]) -> None:
        self._regions = sorted(regions, key=lambda item: item.priority)
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return

        alpha, beta = self._map_click(event.position())
        if not self._is_inside_domain(alpha, beta):
            return

        self._point_label.setText(f"point: alpha={alpha:.6f}, beta={beta:.6f}")
        self.point_selected.emit(alpha, beta)

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

    def _draw_regions(self, painter: QPainter) -> None:
        if not self._regions:
            return

        for region in self._regions:
            sample_points: list[QPointF] = []
            for alpha_step in range(0, 41):
                alpha = (math.pi / 2.0) * alpha_step / 40.0
                for beta_step in range(0, 81):
                    beta = math.pi * beta_step / 80.0
                    if not self._is_inside_domain(alpha, beta):
                        continue
                    if evaluate_region_predicate(region, alpha, beta):
                        sample_points.append(self._to_canvas(alpha, beta))

            if not sample_points:
                continue

            color = QColor(region.style.fill)
            color.setAlphaF(max(0.0, min(region.style.alpha, 1.0)))
            painter.setPen(QPen(QColor(region.style.border), 1))
            painter.setBrush(color)
            for point in sample_points:
                painter.drawEllipse(point, 2, 2)

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

        if self._is_inside_domain(self._alpha, self._beta):
            painter.setPen(QPen(QColor("#111111"), 2))
            painter.setBrush(QColor("#111111"))
            point = self._to_canvas(self._alpha, self._beta)
            painter.drawEllipse(point, 5, 5)
