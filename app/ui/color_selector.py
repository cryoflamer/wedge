from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
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

        self._preview = QFrame()
        self._preview.setFrameShape(QFrame.Box)
        self._preview.setFixedSize(24, 24)
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self._value_label = QLabel(self._color)
        self._value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._custom_button = QPushButton("Custom...")
        self._custom_button.clicked.connect(self._choose_custom_color)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.setSpacing(6)
        preview_row.addWidget(QLabel("Current"))
        preview_row.addWidget(self._preview)
        preview_row.addWidget(self._value_label, 1)
        layout.addLayout(preview_row)

        presets_label = QLabel("Palette")
        layout.addWidget(presets_label)

        self._presets_layout = QGridLayout()
        self._presets_layout.setContentsMargins(0, 0, 0, 0)
        self._presets_layout.setHorizontalSpacing(4)
        self._presets_layout.setVerticalSpacing(4)
        layout.addLayout(self._presets_layout)
        layout.addWidget(self._custom_button, 0, Qt.AlignLeft)

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
        while self._presets_layout.count():
            item = self._presets_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._preset_buttons.clear()

        for index, color in enumerate(self._preset_colors):
            button = QToolButton()
            button.setAutoRaise(False)
            button.setCheckable(True)
            button.setFixedSize(22, 22)
            button.setToolTip(color)
            button.clicked.connect(
                lambda checked=False, selected=color: self.set_color(selected)
            )
            self._apply_button_color(button, color)
            self._presets_layout.addWidget(button, index // 4, index % 4)
            self._preset_buttons.append(button)

    def _refresh_preview(self) -> None:
        self._preview.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #666666;"
        )
        self._value_label.setText(self._color)
        for button, color in zip(self._preset_buttons, self._preset_colors):
            button.setChecked(color == self._color)

    def _choose_custom_color(self) -> None:
        selected = QColorDialog.getColor(QColor(self._color), self, "Select color")
        if selected.isValid():
            self.set_color(selected.name(QColor.NameFormat.HexRgb))

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
