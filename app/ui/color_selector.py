from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidgetAction,
    QHBoxLayout,
    QWidget,
)


DEFAULT_PRESET_COLORS: tuple[str, ...] = (
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#ff7f0e",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
)


class ColorSelector(QWidget):
    color_changed = Signal(str)

    def __init__(
        self,
        color: str = DEFAULT_PRESET_COLORS[0],
        preset_colors: Sequence[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._preset_colors = tuple(preset_colors or DEFAULT_PRESET_COLORS)
        self._color = self._normalize_color(color)
        self._preset_buttons: list[QToolButton] = []
        self._popup = QMenu(self)
        self._popup.setSeparatorsCollapsible(False)

        self._preview = QFrame()
        self._preview.setFrameShape(QFrame.Box)
        self._preview.setFixedSize(16, 16)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._trigger_button = QToolButton()
        self._trigger_button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._trigger_button.setArrowType(Qt.DownArrow)
        self._trigger_button.setText("")
        self._trigger_button.clicked.connect(self._show_popup)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._preview)
        layout.addWidget(self._trigger_button)
        layout.addStretch(1)

        self.set_preset_colors(self._preset_colors)
        self._refresh_preview()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        normalized = self._normalize_color(color)
        if normalized == self._color:
            self._refresh_preview()
            return
        self._color = normalized
        self._refresh_preview()
        self.color_changed.emit(self._color)

    def set_preset_colors(self, colors: Sequence[str]) -> None:
        normalized_colors = tuple(self._normalize_color(color) for color in colors)
        if not normalized_colors:
            normalized_colors = DEFAULT_PRESET_COLORS
        self._preset_colors = normalized_colors
        self._rebuild_preset_buttons()
        self._refresh_preview()

    def _rebuild_preset_buttons(self) -> None:
        self._popup.clear()
        self._preset_buttons.clear()
        palette_widget = QWidget(self._popup)
        palette_layout = QGridLayout(palette_widget)
        palette_layout.setContentsMargins(6, 6, 6, 6)
        palette_layout.setHorizontalSpacing(4)
        palette_layout.setVerticalSpacing(4)

        for index, color in enumerate(self._preset_colors):
            button = QToolButton()
            button.setAutoRaise(False)
            button.setCheckable(True)
            button.setFixedSize(22, 22)
            button.setToolTip(color)
            button.clicked.connect(
                lambda checked=False, selected=color: self._select_color_from_popup(selected)
            )
            self._apply_button_color(button, color)
            palette_layout.addWidget(button, index // 4, index % 4)
            self._preset_buttons.append(button)

        palette_action = QWidgetAction(self._popup)
        palette_action.setDefaultWidget(palette_widget)
        self._popup.addAction(palette_action)
        self._popup.addSeparator()
        custom_action = self._popup.addAction("Custom...")
        custom_action.triggered.connect(self._choose_custom_color)

    def _refresh_preview(self) -> None:
        self._preview.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #666666;"
        )
        self._trigger_button.setToolTip(self._color)
        for button, color in zip(self._preset_buttons, self._preset_colors):
            button.setChecked(color == self._color)

    def _show_popup(self) -> None:
        popup_pos = self.mapToGlobal(QPoint(0, self.height()))
        self._popup.popup(popup_pos)

    def _select_color_from_popup(self, color: str) -> None:
        self.set_color(color)
        self._popup.hide()

    def _choose_custom_color(self) -> None:
        selected = QColorDialog.getColor(QColor(self._color), self, "Select color")
        if selected.isValid():
            self.set_color(selected.name(QColor.NameFormat.HexRgb))
        self._popup.hide()

    def _apply_button_color(self, button: QToolButton, color: str) -> None:
        button.setStyleSheet(
            "\n".join(
                (
                    f"QToolButton {{ background-color: {color}; border: 1px solid #666666; border-radius: 3px; }}",
                    "QToolButton:checked { border: 2px solid #111111; }",
                )
            )
        )

    def _normalize_color(self, color: str) -> str:
        normalized = QColor(color)
        if not normalized.isValid():
            normalized = QColor(DEFAULT_PRESET_COLORS[0])
        return normalized.name(QColor.NameFormat.HexRgb)
