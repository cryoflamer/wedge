from __future__ import annotations

import math

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
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
    branch_markers_changed = Signal(bool)
    heatmap_settings_changed = Signal(bool, str, int, str)
    compute_lyapunov_requested = Signal()
    export_data_requested = Signal()
    trajectory_selected = Signal(int)
    trajectory_visibility_toggled = Signal(int)
    clear_selected_requested = Signal()
    clear_all_requested = Signal()
    reset_phase_view_requested = Signal()
    phase_view_mode_changed = Signal(bool)
    replay_action_requested = Signal(str)
    scan_requested = Signal(str, int, int, float, float, float, float)
    manual_seed_requested = Signal(int, float, float)

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
        self._show_branch_markers_checkbox = QCheckBox("Show branch markers")
        self._show_heatmap_checkbox = QCheckBox("Show heatmap")
        self._heatmap_mode_combo = QComboBox()
        self._heatmap_resolution_combo = QComboBox()
        self._heatmap_normalization_combo = QComboBox()
        self._angle_units_combo = QComboBox()
        self._export_mode_combo = QComboBox()
        self._export_preset_combo = QComboBox()
        self._data_export_format_combo = QComboBox()
        self._scan_mode_combo = QComboBox()
        self._scan_wall_combo = QComboBox()
        self._scan_count_edit = QLineEdit("25")
        self._scan_d_min_edit = QLineEdit("0.0")
        self._scan_d_max_edit = QLineEdit("2.0")
        self._scan_tau_min_edit = QLineEdit("-1.0")
        self._scan_tau_max_edit = QLineEdit("1.0")
        self._manual_d_edit = QLineEdit()
        self._manual_tau_edit = QLineEdit()
        self._manual_wall_combo = QComboBox()
        self._trajectory_info = QLabel("selected: -")
        self._lyapunov_status = QLabel("Lyapunov: not computed")
        self._lyapunov_steps = QLabel("Lyapunov steps: -")
        self._lyapunov_value = QLabel("Lyapunov λ: -")
        self._parameter_status = QLabel("")
        self._angle_units = "rad"
        self._details_tabs = QTabWidget()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        main_layout.addWidget(self._build_trajectory_box())
        self._details_tabs.addTab(self._build_parameters_box(), "Parameters")
        self._details_tabs.addTab(self._build_controls_box(), "Controls")
        self._details_tabs.setDocumentMode(True)
        main_layout.addWidget(self._details_tabs, 1)

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
        for line_edit in (self._manual_d_edit, self._manual_tau_edit):
            line_edit.returnPressed.connect(self._emit_manual_seed)
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
        self._show_branch_markers_checkbox.toggled.connect(
            self.branch_markers_changed.emit
        )
        self._show_heatmap_checkbox.toggled.connect(self._emit_heatmap_settings)
        self._heatmap_mode_combo.addItems(["all", "selected"])
        self._heatmap_mode_combo.currentTextChanged.connect(
            self._emit_heatmap_settings
        )
        self._heatmap_resolution_combo.addItems(["24", "32", "48", "64"])
        self._heatmap_resolution_combo.currentTextChanged.connect(
            self._emit_heatmap_settings
        )
        self._heatmap_normalization_combo.addItems(["linear", "log"])
        self._heatmap_normalization_combo.currentTextChanged.connect(
            self._emit_heatmap_settings
        )
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
        self._scan_mode_combo.addItems(["grid", "random"])
        self._scan_wall_combo.addItems(["1", "2"])
        self._manual_wall_combo.addItems(["1", "2"])
        self._sync_export_preset_state()

    def _build_trajectory_box(self) -> QGroupBox:
        box = QGroupBox("Trajectories")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._trajectory_list)
        layout.addWidget(self._trajectory_info)

        actions_grid = QGridLayout()
        actions_grid.setHorizontalSpacing(6)
        actions_grid.setVerticalSpacing(4)

        toggle_button = QPushButton("Toggle visibility")
        toggle_button.clicked.connect(self._toggle_current_visibility)
        actions_grid.addWidget(toggle_button, 0, 0)

        clear_selected_button = QPushButton("Clear selected trajectory")
        clear_selected_button.clicked.connect(self.clear_selected_requested.emit)
        actions_grid.addWidget(clear_selected_button, 0, 1)

        clear_all_button = QPushButton("Clear all trajectories")
        clear_all_button.clicked.connect(self.clear_all_requested.emit)
        actions_grid.addWidget(clear_all_button, 1, 0)

        lyapunov_button = QPushButton("Compute Lyapunov")
        lyapunov_button.clicked.connect(self.compute_lyapunov_requested.emit)
        actions_grid.addWidget(lyapunov_button, 1, 1)

        export_data_button = QPushButton("Export Data")
        export_data_button.clicked.connect(self.export_data_requested.emit)
        actions_grid.addWidget(export_data_button, 2, 0)

        add_trajectory_button = QPushButton("Add trajectory")
        add_trajectory_button.clicked.connect(self._emit_manual_seed)
        actions_grid.addWidget(add_trajectory_button, 2, 1)

        layout.addLayout(actions_grid)
        layout.addWidget(self._lyapunov_status)
        layout.addWidget(self._lyapunov_steps)
        layout.addWidget(self._lyapunov_value)

        manual_form = QFormLayout()
        manual_form.setContentsMargins(0, 0, 0, 0)
        manual_form.setHorizontalSpacing(6)
        manual_form.setVerticalSpacing(4)
        manual_form.addRow("d", self._manual_d_edit)
        manual_form.addRow("tau", self._manual_tau_edit)
        manual_form.addRow("wall", self._manual_wall_combo)
        layout.addLayout(manual_form)
        return box

    def _build_parameters_box(self) -> QGroupBox:
        box = QGroupBox("Parameters")
        outer_layout = QVBoxLayout(box)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(6)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        left_layout = QFormLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addRow("Units", self._angle_units_combo)
        left_layout.addRow("alpha", self._alpha_edit)
        left_layout.addRow("beta", self._beta_edit)
        left_layout.addRow("N_phase", self._n_phase_edit)
        left_layout.addRow("N_geom", self._n_geom_edit)
        left_layout.addRow("Heatmap mode", self._heatmap_mode_combo)
        left_layout.addRow("Heatmap bins", self._heatmap_resolution_combo)
        left_layout.addRow("Heatmap norm", self._heatmap_normalization_combo)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(self._symmetric_mode_checkbox)
        right_layout.addWidget(self._fixed_domain_checkbox)
        right_layout.addWidget(self._show_regions_checkbox)
        right_layout.addWidget(self._show_region_labels_checkbox)
        right_layout.addWidget(self._show_region_legend_checkbox)
        right_layout.addWidget(self._show_branch_markers_checkbox)
        right_layout.addWidget(self._show_heatmap_checkbox)
        right_layout.addStretch(1)

        grid.addLayout(left_layout, 0, 0)
        grid.addLayout(right_layout, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer_layout.addLayout(grid)
        outer_layout.addWidget(self._parameter_status)

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._emit_parameters)
        reset_phase_view_button = QPushButton("Reset phase view")
        reset_phase_view_button.clicked.connect(
            self.reset_phase_view_requested.emit
        )

        button_row = QGridLayout()
        button_row.setHorizontalSpacing(6)
        button_row.addWidget(apply_button, 0, 0)
        button_row.addWidget(reset_phase_view_button, 0, 1)
        outer_layout.addLayout(button_row)
        return box

    def _build_controls_box(self) -> QGroupBox:
        box = QGroupBox("Controls")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        export_form = QFormLayout()
        export_form.setContentsMargins(0, 0, 0, 0)
        export_form.setHorizontalSpacing(6)
        export_form.setVerticalSpacing(4)
        export_form.addRow("Export mode", self._export_mode_combo)
        export_form.addRow("Mono preset", self._export_preset_combo)
        export_form.addRow("Data format", self._data_export_format_combo)
        export_form.addRow("Scan mode", self._scan_mode_combo)
        export_form.addRow("Scan wall", self._scan_wall_combo)
        export_form.addRow("Scan count", self._scan_count_edit)
        export_form.addRow("Scan d min", self._scan_d_min_edit)
        export_form.addRow("Scan d max", self._scan_d_max_edit)
        export_form.addRow("Scan tau min", self._scan_tau_min_edit)
        export_form.addRow("Scan tau max", self._scan_tau_max_edit)
        layout.addLayout(export_form)

        scan_button = QPushButton("Scan")
        scan_button.clicked.connect(self._emit_scan_request)
        layout.addWidget(scan_button)

        actions_grid = QGridLayout()
        actions_grid.setHorizontalSpacing(6)
        actions_grid.setVerticalSpacing(4)

        for index, action_name in enumerate((
            "replay_selected",
            "replay_all",
            "pause",
            "resume",
            "step",
            "reset_replay",
            "export_png",
            "save_session",
            "load_session",
        )):
            button = QPushButton(action_name.replace("_", " ").title())
            button.clicked.connect(
                lambda checked=False, name=action_name: self.replay_action_requested.emit(name)
            )
            actions_grid.addWidget(button, index // 2, index % 2)

        layout.addLayout(actions_grid)

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
        self.set_branch_markers_enabled(config.view.show_branch_markers)
        self.set_heatmap_settings(
            show_heatmap=config.view.show_heatmap,
            mode=config.view.heatmap_mode,
            resolution=config.view.heatmap_resolution,
            normalization=config.view.heatmap_normalization,
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

    def set_branch_markers_enabled(self, enabled: bool) -> None:
        blocker = QSignalBlocker(self._show_branch_markers_checkbox)
        self._show_branch_markers_checkbox.setChecked(enabled)
        del blocker

    def set_heatmap_settings(
        self,
        show_heatmap: bool,
        mode: str,
        resolution: int,
        normalization: str,
    ) -> None:
        blockers = [
            QSignalBlocker(self._show_heatmap_checkbox),
            QSignalBlocker(self._heatmap_mode_combo),
            QSignalBlocker(self._heatmap_resolution_combo),
            QSignalBlocker(self._heatmap_normalization_combo),
        ]
        self._show_heatmap_checkbox.setChecked(show_heatmap)
        self._set_combo_value(self._heatmap_mode_combo, mode, "all")
        self._set_combo_value(
            self._heatmap_resolution_combo,
            str(resolution),
            "32",
        )
        self._set_combo_value(
            self._heatmap_normalization_combo,
            normalization,
            "linear",
        )
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
        items: list[tuple[int, str, str, bool]],
        selected_trajectory_id: int | None,
    ) -> None:
        blocker = QSignalBlocker(self._trajectory_list)
        self._trajectory_list.clear()
        selected_item: QListWidgetItem | None = None

        for trajectory_id, label, color, visible in items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, trajectory_id)
            item.setIcon(self._color_icon(color, visible))
            if not visible:
                item.setForeground(QColor("#777777"))
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

    def _color_icon(self, color: str, visible: bool) -> QIcon:
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        qcolor = QColor(color)
        if not visible:
            qcolor.setAlpha(90)
        painter = QPainter(pixmap)
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolor)
        painter.drawEllipse(1, 1, 10, 10)
        painter.end()
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

    def _set_combo_value(
        self,
        combo: QComboBox,
        value: str,
        fallback: str,
    ) -> None:
        normalized_value = value.strip().lower() if value.strip() else fallback
        index = combo.findText(normalized_value)
        if index >= 0:
            combo.setCurrentIndex(index)
            return

        fallback_index = combo.findText(fallback)
        combo.setCurrentIndex(fallback_index if fallback_index >= 0 else 0)

    def _on_export_mode_changed(self, mode: str) -> None:
        self.export_mode_changed.emit(mode.strip().lower() or "color")

    def _emit_region_visibility(self) -> None:
        self.region_visibility_changed.emit(
            self._show_regions_checkbox.isChecked(),
            self._show_region_labels_checkbox.isChecked(),
            self._show_region_legend_checkbox.isChecked(),
        )

    def _emit_heatmap_settings(self) -> None:
        self.heatmap_settings_changed.emit(
            self._show_heatmap_checkbox.isChecked(),
            self._heatmap_mode_combo.currentText().strip().lower() or "all",
            int(self._heatmap_resolution_combo.currentText().strip() or "32"),
            self._heatmap_normalization_combo.currentText().strip().lower()
            or "linear",
        )

    def _emit_scan_request(self) -> None:
        self._clear_parameter_error()
        try:
            mode = self._scan_mode_combo.currentText().strip().lower() or "grid"
            wall = int(self._scan_wall_combo.currentText().strip() or "1")
            count = int(self._scan_count_edit.text().strip())
            d_min = parse_real_expression(self._scan_d_min_edit.text())
            d_max = parse_real_expression(self._scan_d_max_edit.text())
            tau_min = parse_real_expression(self._scan_tau_min_edit.text())
            tau_max = parse_real_expression(self._scan_tau_max_edit.text())
        except (ValueError, SyntaxError, ZeroDivisionError):
            self._set_parameter_error("Invalid scan parameter")
            return

        self.scan_requested.emit(mode, count, wall, d_min, d_max, tau_min, tau_max)

    def _emit_manual_seed(self) -> None:
        self._clear_parameter_error()
        try:
            wall = int(self._manual_wall_combo.currentText().strip() or "1")
            d_value = parse_real_expression(self._manual_d_edit.text())
            tau_value = parse_real_expression(self._manual_tau_edit.text())
        except (ValueError, SyntaxError, ZeroDivisionError):
            self._set_parameter_error("Invalid seed value")
            return

        self.manual_seed_requested.emit(wall, d_value, tau_value)
