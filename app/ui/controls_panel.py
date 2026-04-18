from __future__ import annotations

import math

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.config import Config
from app.services.parameter_parser import parse_real_expression


class ControlsPanel(QWidget):
    parameters_changed = Signal(float, float, int, int)
    angle_units_changed = Signal(str)
    symmetric_mode_changed = Signal(bool)
    export_mode_changed = Signal(str)
    region_visibility_changed = Signal(bool, bool, bool)
    compute_lyapunov_requested = Signal()
    export_data_requested = Signal()
    trajectory_selected = Signal(int)
    trajectory_visibility_toggled = Signal(int)
    clear_selected_requested = Signal()
    clear_all_requested = Signal()
    reset_phase_view_requested = Signal()
    phase_view_mode_changed = Signal(bool)
    replay_action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._trajectory_list = QListWidget()
        self._alpha_edit = QLineEdit()
        self._beta_edit = QLineEdit()
        self._n_phase_edit = QLineEdit()
        self._n_geom_edit = QLineEdit()
        self._fixed_domain_checkbox = QCheckBox("Fixed domain (disable for zoom/pan)")
        self._symmetric_mode_checkbox = QCheckBox("Symmetric wedge mode")
        self._show_regions_checkbox = QCheckBox("Show regions")
        self._show_region_labels_checkbox = QCheckBox("Show region labels")
        self._show_region_legend_checkbox = QCheckBox("Show legend")
        self._angle_units_combo = QComboBox()
        self._export_mode_combo = QComboBox()
        self._export_preset_combo = QComboBox()
        self._data_export_format_combo = QComboBox()
        self._trajectory_info = QLabel("selected: -")
        self._lyapunov_status = QLabel("Lyapunov: not computed")
        self._lyapunov_steps = QLabel("Lyapunov steps: -")
        self._lyapunov_value = QLabel("Lyapunov λ: -")
        self._parameter_status = QLabel("")
        self._angle_units = "rad"

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._build_trajectory_box())
        main_layout.addWidget(self._build_parameters_box())
        main_layout.addWidget(self._build_controls_box())
        main_layout.addStretch(1)

        self._trajectory_list.currentItemChanged.connect(
            self._on_current_item_changed
        )
        for line_edit in (
            self._alpha_edit,
            self._beta_edit,
            self._n_phase_edit,
            self._n_geom_edit,
        ):
            line_edit.returnPressed.connect(self._emit_parameters)
        self._alpha_edit.textChanged.connect(self._sync_symmetric_beta_preview)
        self._fixed_domain_checkbox.toggled.connect(
            self.phase_view_mode_changed.emit
        )
        self._symmetric_mode_checkbox.toggled.connect(
            self._on_symmetric_mode_toggled
        )
        self._show_regions_checkbox.toggled.connect(self._emit_region_visibility)
        self._show_region_labels_checkbox.toggled.connect(self._emit_region_visibility)
        self._show_region_legend_checkbox.toggled.connect(self._emit_region_visibility)
        self._angle_units_combo.addItems(["rad", "deg"])
        self._angle_units_combo.currentTextChanged.connect(
            self._on_angle_units_changed
        )
        self._export_mode_combo.addItems(["color", "monochrome"])
        self._export_mode_combo.currentTextChanged.connect(
            self._sync_export_preset_state
        )
        self._export_mode_combo.currentTextChanged.connect(
            self._on_export_mode_changed
        )
        self._data_export_format_combo.addItems(["csv", "json"])
        self._sync_export_preset_state()

    def _build_trajectory_box(self) -> QGroupBox:
        box = QGroupBox("Trajectories")
        layout = QVBoxLayout(box)
        layout.addWidget(self._trajectory_list)
        layout.addWidget(self._trajectory_info)

        toggle_button = QPushButton("Toggle visibility")
        toggle_button.clicked.connect(self._toggle_current_visibility)
        layout.addWidget(toggle_button)

        clear_selected_button = QPushButton("Clear selected trajectory")
        clear_selected_button.clicked.connect(self.clear_selected_requested.emit)
        layout.addWidget(clear_selected_button)

        clear_all_button = QPushButton("Clear all trajectories")
        clear_all_button.clicked.connect(self.clear_all_requested.emit)
        layout.addWidget(clear_all_button)

        lyapunov_button = QPushButton("Compute Lyapunov")
        lyapunov_button.clicked.connect(self.compute_lyapunov_requested.emit)
        layout.addWidget(lyapunov_button)
        layout.addWidget(self._lyapunov_status)
        layout.addWidget(self._lyapunov_steps)
        layout.addWidget(self._lyapunov_value)

        export_data_button = QPushButton("Export Data")
        export_data_button.clicked.connect(self.export_data_requested.emit)
        layout.addWidget(export_data_button)
        return box

    def _build_parameters_box(self) -> QGroupBox:
        box = QGroupBox("Parameters")
        layout = QFormLayout(box)
        layout.addRow("Units", self._angle_units_combo)
        layout.addRow("alpha", self._alpha_edit)
        layout.addRow("beta", self._beta_edit)
        layout.addRow("N_phase", self._n_phase_edit)
        layout.addRow("N_geom", self._n_geom_edit)
        layout.addRow(self._symmetric_mode_checkbox)
        layout.addRow(self._fixed_domain_checkbox)
        layout.addRow(self._show_regions_checkbox)
        layout.addRow(self._show_region_labels_checkbox)
        layout.addRow(self._show_region_legend_checkbox)
        layout.addRow(self._parameter_status)

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._emit_parameters)
        layout.addRow(apply_button)

        reset_phase_view_button = QPushButton("Reset phase view")
        reset_phase_view_button.clicked.connect(
            self.reset_phase_view_requested.emit
        )
        layout.addRow(reset_phase_view_button)
        return box

    def _build_controls_box(self) -> QGroupBox:
        box = QGroupBox("Controls")
        layout = QVBoxLayout(box)

        export_form = QFormLayout()
        export_form.addRow("Export mode", self._export_mode_combo)
        export_form.addRow("Mono preset", self._export_preset_combo)
        export_form.addRow("Data format", self._data_export_format_combo)
        layout.addLayout(export_form)

        for action_name in (
            "replay_selected",
            "replay_all",
            "pause",
            "resume",
            "step",
            "reset_replay",
            "export_png",
            "save_session",
            "load_session",
        ):
            button = QPushButton(action_name.replace("_", " ").title())
            button.clicked.connect(
                lambda checked=False, name=action_name: self.replay_action_requested.emit(name)
            )
            layout.addWidget(button)

        footer = QHBoxLayout()
        footer.addWidget(QLabel("UI skeleton"))
        footer.addStretch(1)
        layout.addLayout(footer)
        return box

    def load_config(self, config: Config) -> None:
        current_preset = self.export_preset()
        alpha_value, beta_value = self._display_angles(
            config.simulation.alpha,
            config.simulation.beta,
        )
        self._alpha_edit.setText(f"{alpha_value:.6f}")
        self._beta_edit.setText(f"{beta_value:.6f}")
        self._n_phase_edit.setText(str(config.simulation.n_phase_default))
        self._n_geom_edit.setText(str(config.simulation.n_geom_default))
        self.set_export_options(
            mode=config.export.default_mode,
            presets=config.export.monochrome_line_styles,
            selected_preset=current_preset,
        )
        self.set_region_view_options(
            show_regions=config.view.show_regions,
            show_labels=config.view.show_region_labels,
            show_legend=config.view.show_region_legend,
        )

    def set_angle_units(self, units: str) -> None:
        normalized_units = units.strip().lower() if units.strip() else "rad"
        blocker = QSignalBlocker(self._angle_units_combo)
        index = self._angle_units_combo.findText(normalized_units)
        self._angle_units_combo.setCurrentIndex(index if index >= 0 else 0)
        del blocker
        self._angle_units = self._angle_units_combo.currentText().strip().lower() or "rad"
        self._sync_symmetric_beta_preview()

    def angle_units(self) -> str:
        return self._angle_units

    def set_symmetric_mode(self, enabled: bool) -> None:
        blocker = QSignalBlocker(self._symmetric_mode_checkbox)
        self._symmetric_mode_checkbox.setChecked(enabled)
        del blocker
        self._beta_edit.setReadOnly(enabled)
        self._beta_edit.setEnabled(not enabled)
        self._sync_symmetric_beta_preview()

    def symmetric_mode(self) -> bool:
        return self._symmetric_mode_checkbox.isChecked()

    def set_phase_view_mode(self, fixed_domain: bool) -> None:
        blocker = QSignalBlocker(self._fixed_domain_checkbox)
        self._fixed_domain_checkbox.setChecked(fixed_domain)
        del blocker

    def set_region_view_options(
        self,
        show_regions: bool,
        show_labels: bool,
        show_legend: bool,
    ) -> None:
        blockers = [
            QSignalBlocker(self._show_regions_checkbox),
            QSignalBlocker(self._show_region_labels_checkbox),
            QSignalBlocker(self._show_region_legend_checkbox),
        ]
        self._show_regions_checkbox.setChecked(show_regions)
        self._show_region_labels_checkbox.setChecked(show_labels)
        self._show_region_legend_checkbox.setChecked(show_legend)
        del blockers

    def set_export_options(
        self,
        mode: str,
        presets: list[str],
        selected_preset: str,
    ) -> None:
        mode_blocker = QSignalBlocker(self._export_mode_combo)
        preset_blocker = QSignalBlocker(self._export_preset_combo)

        normalized_mode = mode.strip().lower() if mode.strip() else "color"
        mode_index = self._export_mode_combo.findText(normalized_mode)
        if mode_index >= 0:
            self._export_mode_combo.setCurrentIndex(mode_index)
        else:
            self._export_mode_combo.setCurrentText("color")

        self._export_preset_combo.clear()
        self._export_preset_combo.addItems(presets)
        if presets:
            preset_index = self._export_preset_combo.findText(selected_preset)
            self._export_preset_combo.setCurrentIndex(
                preset_index if preset_index >= 0 else 0
            )

        del preset_blocker
        del mode_blocker
        self._sync_export_preset_state()

    def export_mode(self) -> str:
        return self._export_mode_combo.currentText().strip().lower() or "color"

    def export_preset(self) -> str:
        return self._export_preset_combo.currentText().strip()

    def data_export_format(self) -> str:
        return self._data_export_format_combo.currentText().strip().lower() or "csv"

    def set_trajectory_items(
        self,
        items: list[tuple[int, str, str]],
        selected_trajectory_id: int | None,
    ) -> None:
        blocker = QSignalBlocker(self._trajectory_list)
        self._trajectory_list.clear()
        selected_item: QListWidgetItem | None = None

        for trajectory_id, label, color in items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, trajectory_id)
            item.setIcon(self._color_icon(color))
            self._trajectory_list.addItem(item)
            if trajectory_id == selected_trajectory_id:
                selected_item = item

        if selected_item is not None:
            self._trajectory_list.setCurrentItem(selected_item)
        elif self._trajectory_list.count() > 0:
            self._trajectory_list.setCurrentRow(0)
        else:
            self._trajectory_info.setText("selected: -")
        del blocker

        current = self._trajectory_list.currentItem()
        if current is not None:
            trajectory_id = current.data(Qt.UserRole)
            if trajectory_id is not None:
                self._trajectory_info.setText(f"selected: #{int(trajectory_id)}")

    def _color_icon(self, color: str) -> QIcon:
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        qcolor = QColor(color)
        for x in range(12):
            for y in range(12):
                pixmap.setPixelColor(x, y, qcolor)
        return QIcon(pixmap)

    def set_lyapunov_status(
        self,
        status: str,
        steps_used: int,
        estimate: float | None,
        reason: str | None = None,
        wall_divergence_count: int = 0,
    ) -> None:
        status_text = status
        if reason:
            status_text = f"{status} ({reason})"
        if wall_divergence_count > 0:
            status_text = f"{status_text}, wall div={wall_divergence_count}"
        self._lyapunov_status.setText(f"Lyapunov: {status_text}")
        self._lyapunov_steps.setText(f"Lyapunov steps: {steps_used}")
        if estimate is None:
            self._lyapunov_value.setText("Lyapunov λ: -")
        else:
            self._lyapunov_value.setText(f"Lyapunov λ: {estimate:.6f}")

    def _emit_parameters(self) -> None:
        self._clear_parameter_error()
        try:
            alpha = self._parse_angle(self._alpha_edit.text())
            if self.symmetric_mode():
                beta = self._symmetric_beta(alpha)
            else:
                beta = self._parse_angle(self._beta_edit.text())
            n_phase = int(self._n_phase_edit.text())
            n_geom = int(self._n_geom_edit.text())
        except (ValueError, SyntaxError, ZeroDivisionError):
            self._set_parameter_error("Invalid parameter value")
            return

        self.parameters_changed.emit(alpha, beta, n_phase, n_geom)

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._trajectory_info.setText("selected: -")
            return
        trajectory_id = current.data(Qt.UserRole)
        if trajectory_id is not None:
            self._trajectory_info.setText(f"selected: #{int(trajectory_id)}")
            self.trajectory_selected.emit(int(trajectory_id))

    def _toggle_current_visibility(self) -> None:
        current = self._trajectory_list.currentItem()
        if current is None:
            return
        trajectory_id = current.data(Qt.UserRole)
        if trajectory_id is not None:
            self.trajectory_visibility_toggled.emit(int(trajectory_id))

    def _set_parameter_error(self, message: str) -> None:
        self._parameter_status.setText(message)
        self._parameter_status.setStyleSheet("color: #b00020;")
        self._alpha_edit.setStyleSheet("border: 1px solid #b00020;")
        self._beta_edit.setStyleSheet("border: 1px solid #b00020;")

    def _clear_parameter_error(self) -> None:
        self._parameter_status.setText("")
        self._parameter_status.setStyleSheet("")
        self._alpha_edit.setStyleSheet("")
        self._beta_edit.setStyleSheet("")

    def _display_angles(self, alpha: float, beta: float) -> tuple[float, float]:
        if self._angle_units == "deg":
            return math.degrees(alpha), math.degrees(beta)
        return alpha, beta

    def _parse_angle(self, text: str) -> float:
        value = parse_real_expression(text)
        if self._angle_units == "deg":
            return math.radians(value)
        return value

    def _symmetric_beta(self, alpha: float) -> float:
        return math.nextafter(math.pi - alpha, alpha)

    def _on_angle_units_changed(self, units: str) -> None:
        self._angle_units = units.strip().lower() or "rad"
        self.angle_units_changed.emit(self._angle_units)

    def _on_symmetric_mode_toggled(self, enabled: bool) -> None:
        self._beta_edit.setReadOnly(enabled)
        self._beta_edit.setEnabled(not enabled)
        self._sync_symmetric_beta_preview()
        self.symmetric_mode_changed.emit(enabled)

    def _sync_symmetric_beta_preview(self) -> None:
        if not self.symmetric_mode():
            return
        try:
            alpha = self._parse_angle(self._alpha_edit.text())
        except (ValueError, SyntaxError, ZeroDivisionError):
            return

        beta = self._symmetric_beta(alpha)
        beta_value = math.degrees(beta) if self._angle_units == "deg" else beta
        blocker = QSignalBlocker(self._beta_edit)
        self._beta_edit.setText(f"{beta_value:.6f}")
        del blocker

    def _sync_export_preset_state(self) -> None:
        is_monochrome = self._export_mode_combo.currentText().strip().lower() == "monochrome"
        self._export_preset_combo.setEnabled(
            is_monochrome and self._export_preset_combo.count() > 0
        )

    def _on_export_mode_changed(self, mode: str) -> None:
        self.export_mode_changed.emit(mode.strip().lower() or "color")

    def _emit_region_visibility(self) -> None:
        self.region_visibility_changed.emit(
            self._show_regions_checkbox.isChecked(),
            self._show_region_labels_checkbox.isChecked(),
            self._show_region_legend_checkbox.isChecked(),
        )
