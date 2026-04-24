from __future__ import annotations

import math
from collections.abc import Sequence

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.trajectory_engine import validate_scene_item_expression
from app.models.config import Config
from app.services.parameter_parser import parse_real_expression
from app.ui.color_selector import ColorSelector
from app.ui.tooltips import apply_tooltip, tooltip_text


class CollapsibleSection(QWidget):
    def __init__(
        self,
        title: str,
        expanded: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._toggle = QToolButton()
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )

        self._content = QFrame()
        self._content.setVisible(expanded)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 4, 0, 0)
        self._content_layout.setSpacing(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._toggle)
        layout.addWidget(self._content)

        self._toggle.toggled.connect(self.set_expanded)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_tooltip(self, key: str) -> None:
        apply_tooltip(self._toggle, key)

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)
        self._toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._content.setVisible(expanded)

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()


class ControlsPanel(QWidget):
    parameters_changed = Signal(float, float, int, int)
    angle_units_changed = Signal(str)
    symmetric_mode_changed = Signal(bool)
    angle_constraint_mode_changed = Signal(str)
    angle_constraint_changed = Signal(str)
    export_mode_changed = Signal(str)
    phase_grid_visibility_changed = Signal(bool, bool)
    seed_markers_visibility_changed = Signal(bool)
    stationary_point_visibility_changed = Signal(bool)
    directrix_visibility_changed = Signal(bool)
    region_visibility_changed = Signal(bool, bool, bool)
    plot_labels_changed = Signal(bool, str, str)
    branch_markers_changed = Signal(bool)
    heatmap_settings_changed = Signal(bool, str, int, str)
    compute_lyapunov_requested = Signal()
    export_data_requested = Signal()
    trajectory_selected = Signal(int)
    selected_trajectory_color_changed = Signal(str)
    save_scene_requested = Signal()
    scene_item_selected = Signal(str)
    apply_scene_item_editor_requested = Signal(object)
    add_scene_item_requested = Signal()
    duplicate_scene_item_requested = Signal()
    delete_scene_item_requested = Signal()
    selected_seed_apply_requested = Signal(float, float)
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
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.MinimumExpanding,
        )

        self._trajectory_selector = QComboBox()
        self._alpha_edit = QLineEdit()
        self._beta_edit = QLineEdit()
        self._n_phase_edit = QLineEdit()
        self._n_geom_edit = QLineEdit()
        self._fixed_domain_checkbox = QCheckBox("Fixed domain")
        self._constraint_mode_combo = QComboBox()
        self._constraint_label = QLabel("Constraint")
        self._constraint_combo = QComboBox()
        self._save_scene_button = QPushButton("Save")
        self._scene_dirty_label = QLabel("Saved")
        self._symmetry_constraint_checkbox = QCheckBox("Symmetry constraint")
        self._show_phase_grid_checkbox = QCheckBox("Show grid")
        self._show_phase_minor_grid_checkbox = QCheckBox("Show minor grid")
        self._show_seed_markers_checkbox = QCheckBox("Show seed markers")
        self._show_stationary_point_checkbox = QCheckBox("Show stationary point")
        self._show_directrix_checkbox = QCheckBox("Show directrix")
        self._show_regions_checkbox = QCheckBox("Show regions")
        self._show_region_labels_checkbox = QCheckBox("Show region labels")
        self._show_region_legend_checkbox = QCheckBox("Show legend")
        self._show_labels_on_plot_checkbox = QCheckBox("Show labels on plot")
        self._plot_label_mode_combo = QComboBox()
        self._tooltip_label_mode_combo = QComboBox()
        self._native_enabled_checkbox = QCheckBox("Native backend enabled")
        self._native_sample_mode_combo = QComboBox()
        self._native_sample_step_spin = QSpinBox()
        self._native_status_label = QLabel("Native unavailable, using Python fallback")
        self._parameter_pending_label = QLabel("")
        self._show_branch_markers_checkbox = QCheckBox("Show branch markers")
        self._show_heatmap_checkbox = QCheckBox("Show heatmap")
        self._heatmap_mode_combo = QComboBox()
        self._heatmap_resolution_combo = QComboBox()
        self._heatmap_normalization_combo = QComboBox()
        self._scene_item_list = QListWidget()
        self._scene_item_status_label = QLabel("Nothing selected")
        self._scene_item_editor_placeholder = QLabel("Select an item to edit.")
        self._scene_item_editor_status = QLabel("")
        self._scene_item_expression_status = QLabel("")
        self._scene_item_name_edit = QLineEdit()
        self._scene_item_alias_edit = QLineEdit()
        self._scene_item_display_text_edit = QLineEdit()
        self._scene_item_legend_text_edit = QLineEdit()
        self._scene_item_expression_edit = QLineEdit()
        self._scene_item_relation_combo = QComboBox()
        self._scene_item_visible_checkbox = QCheckBox("Visible")
        self._scene_item_priority_edit = QLineEdit()
        self._scene_item_fill_color_selector = ColorSelector()
        self._scene_item_border_color_selector = ColorSelector()
        self._scene_item_line_width_combo = QComboBox()
        self._scene_item_line_style_combo = QComboBox()
        self._scene_item_editor_apply_button = QPushButton("Apply")
        self._scene_item_editor_section: CollapsibleSection | None = None
        self._scene_item_fill_row_label = QLabel("Fill")
        self._scene_item_fill_row_widget = self._scene_item_fill_color_selector
        self._add_scene_item_button = QPushButton("Add Item")
        self._duplicate_scene_item_button = QPushButton("Duplicate")
        self._delete_scene_item_button = QPushButton("Delete")
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
        self._compute_lyapunov_button = QPushButton("Lyapunov")
        self._lyapunov_status = QLabel("Lyapunov: not computed")
        self._lyapunov_steps = QLabel("Lyapunov steps: -")
        self._lyapunov_value = QLabel("Lyapunov λ: -")
        self._parameter_status = QLabel("")
        self._selected_seed_d_edit = QLineEdit()
        self._selected_seed_tau_edit = QLineEdit()
        self._selected_seed_wall_edit = QLineEdit()
        self._selected_seed_status = QLabel("")
        self._trajectory_color_selector = ColorSelector()
        self._trajectory_wall_summary = QLabel("wall: -")
        self._trajectory_d_summary = QLabel("d0: -")
        self._trajectory_tau_summary = QLabel("τ0: -")
        self._trajectory_state_summary = QLabel("status: -")
        self._trajectory_lyapunov_summary = QLabel("Lyapunov: -")
        self._angle_units = "rad"
        self._add_section: CollapsibleSection | None = None
        self._applied_parameter_state: tuple[int, int, bool, str, int] | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        main_layout.addWidget(self._build_trajectory_box())
        main_layout.addWidget(self._build_parameters_section())
        main_layout.addWidget(self._build_replay_section())
        for section in self._build_collapsible_sections():
            main_layout.addWidget(section)
        main_layout.addStretch(1)

        self._trajectory_selector.currentIndexChanged.connect(
            self._on_trajectory_selector_changed
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
        for line_edit in (self._selected_seed_d_edit, self._selected_seed_tau_edit):
            line_edit.returnPressed.connect(self._emit_selected_seed_apply)
        self._alpha_edit.textChanged.connect(self._sync_symmetric_beta_preview)
        self._fixed_domain_checkbox.toggled.connect(
            self.phase_view_mode_changed.emit
        )
        self._constraint_mode_combo.addItems(["Free", "Constraint"])
        self._constraint_mode_combo.currentTextChanged.connect(
            self._on_constraint_mode_changed
        )
        self._constraint_combo.currentIndexChanged.connect(
            self._on_constraint_changed
        )
        self._symmetry_constraint_checkbox.toggled.connect(
            self._on_symmetric_mode_toggled
        )
        self._show_regions_checkbox.toggled.connect(self._emit_region_visibility)
        self._show_phase_grid_checkbox.toggled.connect(
            self._emit_phase_grid_visibility
        )
        self._show_phase_minor_grid_checkbox.toggled.connect(
            self._emit_phase_grid_visibility
        )
        self._show_seed_markers_checkbox.toggled.connect(
            self.seed_markers_visibility_changed.emit
        )
        self._show_stationary_point_checkbox.toggled.connect(
            self.stationary_point_visibility_changed.emit
        )
        self._show_directrix_checkbox.toggled.connect(
            self.directrix_visibility_changed.emit
        )
        self._show_region_labels_checkbox.toggled.connect(self._emit_region_visibility)
        self._show_region_legend_checkbox.toggled.connect(self._emit_region_visibility)
        self._show_labels_on_plot_checkbox.toggled.connect(
            self._emit_plot_labels_changed
        )
        self._plot_label_mode_combo.addItems(["alias", "legend"])
        self._plot_label_mode_combo.currentTextChanged.connect(
            self._emit_plot_labels_changed
        )
        self._tooltip_label_mode_combo.addItems(["alias", "legend"])
        self._tooltip_label_mode_combo.currentTextChanged.connect(
            self._emit_plot_labels_changed
        )
        self._native_sample_mode_combo.addItems(["dense", "every_n", "final"])
        self._native_sample_step_spin.setRange(1, 1_000_000)
        self._native_sample_step_spin.setValue(1)
        self._native_enabled_checkbox.toggled.connect(
            self._on_native_backend_controls_changed
        )
        self._native_sample_mode_combo.currentTextChanged.connect(
            self._on_native_backend_controls_changed
        )
        self._native_sample_step_spin.valueChanged.connect(
            self._on_native_backend_controls_changed
        )
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
        self._scene_item_list.currentItemChanged.connect(
            self._on_scene_item_selection_changed
        )
        self._scene_item_relation_combo.addItems(["=", "<", "<=", ">", ">="])
        self._scene_item_relation_combo.currentTextChanged.connect(
            self._sync_scene_item_editor_mode
        )
        self._scene_item_line_width_combo.addItems(["1.0", "1.5", "2.0", "2.5", "3.0"])
        self._scene_item_line_style_combo.addItems(["solid", "dashed"])
        self._scene_item_editor_apply_button.clicked.connect(
            self._emit_scene_item_editor_apply
        )
        self._add_scene_item_button.clicked.connect(self.add_scene_item_requested.emit)
        self._duplicate_scene_item_button.clicked.connect(
            self.duplicate_scene_item_requested.emit
        )
        self._delete_scene_item_button.clicked.connect(
            self.delete_scene_item_requested.emit
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
        self._compute_lyapunov_button.clicked.connect(
            self.compute_lyapunov_requested.emit
        )
        self._trajectory_color_selector.color_changed.connect(
            self.selected_trajectory_color_changed.emit
        )
        self._trajectory_color_selector.setEnabled(False)
        self._save_scene_button.clicked.connect(
            self.save_scene_requested.emit
        )
        self._set_compact_button_policy(self._save_scene_button)
        self._scene_dirty_label.setStyleSheet("color: #666;")
        self._save_scene_button.setEnabled(False)
        self._set_compact_button_policy(self._scene_item_editor_apply_button)
        self._set_compact_button_policy(self._add_scene_item_button)
        self._set_compact_button_policy(self._duplicate_scene_item_button)
        self._set_compact_button_policy(self._delete_scene_item_button)
        self._scene_item_status_label.setStyleSheet("color: #666;")
        self._scene_item_editor_placeholder.setStyleSheet("color: #666;")
        self._scene_item_editor_status.setStyleSheet("color: #b00020;")
        self._scene_item_status_label.setWordWrap(True)
        self._scene_item_expression_status.setVisible(False)
        self._scene_item_editor_status.setVisible(False)
        self._scene_item_name_edit.setReadOnly(True)
        self._sync_export_preset_state()
        self._parameter_pending_label.setStyleSheet("color: #8a6d3b;")
        self._parameter_pending_label.setVisible(False)
        self._trajectory_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._trajectory_selector.setMinimumContentsLength(12)
        self._trajectory_selector.setIconSize(QSize(12, 12))
        self._n_phase_edit.textChanged.connect(self._update_parameter_pending_state)
        self._n_geom_edit.textChanged.connect(self._update_parameter_pending_state)
        self._apply_tooltips()

    def _build_trajectory_box(self) -> QGroupBox:
        box = QGroupBox("Trajectory")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        selector_form = QFormLayout()
        selector_form.setContentsMargins(0, 0, 0, 0)
        selector_form.setHorizontalSpacing(6)
        selector_form.setVerticalSpacing(4)
        selector_form.addRow("Selected", self._trajectory_selector)
        layout.addLayout(selector_form)

        seed_form = QFormLayout()
        seed_form.setContentsMargins(0, 0, 0, 0)
        seed_form.setHorizontalSpacing(6)
        seed_form.setVerticalSpacing(4)
        self._selected_seed_wall_edit.setReadOnly(True)
        self._selected_seed_d_edit.setPlaceholderText("-")
        self._selected_seed_tau_edit.setPlaceholderText("-")
        self._selected_seed_wall_edit.setPlaceholderText("-")
        seed_form.addRow("d", self._selected_seed_d_edit)
        seed_form.addRow("τ", self._selected_seed_tau_edit)
        seed_form.addRow("wall", self._selected_seed_wall_edit)
        seed_form.addRow("color", self._trajectory_color_selector)
        layout.addLayout(seed_form)
        layout.addWidget(self._selected_seed_status)

        actions_section = CollapsibleSection("Trajectory actions", expanded=False)
        actions_section.set_tooltip("apply_seed")
        apply_seed_button = QPushButton("Apply seed")
        apply_seed_button.clicked.connect(self._emit_selected_seed_apply)
        apply_tooltip(apply_seed_button, "apply_seed")
        self._set_compact_button_policy(apply_seed_button)
        actions_section.content_layout().addWidget(apply_seed_button)

        actions_grid = QGridLayout()
        actions_grid.setHorizontalSpacing(6)
        actions_grid.setVerticalSpacing(4)

        toggle_button = QPushButton("Toggle")
        toggle_button.clicked.connect(self._toggle_current_visibility)
        apply_tooltip(toggle_button, "toggle_visibility")
        actions_grid.addWidget(toggle_button, 0, 0)

        clear_selected_button = QPushButton("Clear")
        clear_selected_button.clicked.connect(self.clear_selected_requested.emit)
        apply_tooltip(clear_selected_button, "clear_selected")
        actions_grid.addWidget(clear_selected_button, 0, 1)

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._expand_add_section)
        apply_tooltip(add_button, "add_seed_shortcut")
        actions_grid.addWidget(add_button, 1, 0)

        actions_grid.addWidget(QWidget(), 1, 1)

        clear_all_button = QPushButton("Clear all")
        clear_all_button.clicked.connect(self.clear_all_requested.emit)
        apply_tooltip(clear_all_button, "clear_all")
        actions_grid.addWidget(clear_all_button, 2, 0, 1, 2)

        for button in (
            toggle_button,
            clear_selected_button,
            add_button,
            clear_all_button,
        ):
            self._set_compact_button_policy(button)
        actions_grid.setColumnStretch(0, 1)
        actions_grid.setColumnStretch(1, 1)

        actions_section.content_layout().addLayout(actions_grid)
        layout.addWidget(actions_section)

        summary_layout = QVBoxLayout()
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(2)
        for label in (
            self._trajectory_wall_summary,
            self._trajectory_d_summary,
            self._trajectory_tau_summary,
            self._trajectory_state_summary,
            self._trajectory_lyapunov_summary,
        ):
            label.setToolTip(tooltip_text("trajectory_summary"))
            summary_layout.addWidget(label)
        layout.addLayout(summary_layout)
        return box

    def _build_parameters_section(self) -> CollapsibleSection:
        section = CollapsibleSection("Parameters", expanded=False)
        outer_layout = section.content_layout()
        left_layout = QFormLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        left_layout.addRow("α", self._alpha_edit)
        left_layout.addRow("β", self._beta_edit)
        left_layout.addRow("N_phase", self._n_phase_edit)
        left_layout.addRow("N_geom", self._n_geom_edit)
        left_layout.addRow("", self._native_enabled_checkbox)
        left_layout.addRow("Native sample mode", self._native_sample_mode_combo)
        left_layout.addRow("Native sample step", self._native_sample_step_spin)
        left_layout.addRow("Backend status", self._native_status_label)

        outer_layout.addLayout(left_layout)
        outer_layout.addWidget(self._parameter_status)
        outer_layout.addWidget(self._parameter_pending_label)

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._emit_parameters)
        apply_tooltip(apply_button, "apply")
        self._set_compact_button_policy(apply_button)

        button_row = QVBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(4)
        button_row.addWidget(apply_button)
        outer_layout.addLayout(button_row)
        return section

    def _build_replay_section(self) -> CollapsibleSection:
        section = CollapsibleSection("Replay", expanded=True)
        layout = section.content_layout()

        actions_grid = QGridLayout()
        actions_grid.setHorizontalSpacing(6)
        actions_grid.setVerticalSpacing(4)
        action_labels = (
            ("replay_selected", "Play sel"),
            ("replay_all", "Play all"),
            ("pause", "Pause"),
            ("resume", "Resume"),
            ("step", "Step"),
            ("reset_replay", "Reset"),
        )
        for index, (action_name, label) in enumerate(action_labels):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, name=action_name: self.replay_action_requested.emit(name)
            )
            self._set_compact_button_policy(button)
            apply_tooltip(button, action_name)
            actions_grid.addWidget(button, index // 2, index % 2)
        actions_grid.setColumnStretch(0, 1)
        actions_grid.setColumnStretch(1, 1)
        layout.addLayout(actions_grid)

        return section

    def _build_collapsible_sections(self) -> list[QWidget]:
        sections: list[QWidget] = []

        self._add_section = CollapsibleSection("Add trajectory", expanded=False)
        self._add_section.set_tooltip("add_trajectory")
        add_form = QFormLayout()
        add_form.setContentsMargins(0, 0, 0, 0)
        add_form.setHorizontalSpacing(6)
        add_form.setVerticalSpacing(4)
        add_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        add_form.addRow("d", self._manual_d_edit)
        add_form.addRow("τ", self._manual_tau_edit)
        add_form.addRow("wall", self._manual_wall_combo)
        self._add_section.content_layout().addLayout(add_form)
        add_trajectory_button = QPushButton("Add trajectory")
        add_trajectory_button.clicked.connect(self._emit_manual_seed)
        apply_tooltip(add_trajectory_button, "add_trajectory")
        self._set_compact_button_policy(add_trajectory_button)
        self._add_section.content_layout().addWidget(add_trajectory_button)
        sections.append(self._add_section)

        scan_section = CollapsibleSection("Scan", expanded=False)
        scan_section.set_tooltip("run_scan")
        scan_form = QFormLayout()
        scan_form.setContentsMargins(0, 0, 0, 0)
        scan_form.setHorizontalSpacing(6)
        scan_form.setVerticalSpacing(4)
        scan_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scan_form.addRow("Mode", self._scan_mode_combo)
        scan_form.addRow("Wall", self._scan_wall_combo)
        scan_form.addRow("Count", self._scan_count_edit)
        scan_form.addRow("d min", self._scan_d_min_edit)
        scan_form.addRow("d max", self._scan_d_max_edit)
        scan_form.addRow("τ min", self._scan_tau_min_edit)
        scan_form.addRow("τ max", self._scan_tau_max_edit)
        scan_section.content_layout().addLayout(scan_form)
        scan_actions = QGridLayout()
        scan_actions.setHorizontalSpacing(6)
        scan_actions.setVerticalSpacing(4)
        scan_button = QPushButton("Run scan")
        scan_button.clicked.connect(self._emit_scan_request)
        apply_tooltip(scan_button, "run_scan")
        self._set_compact_button_policy(scan_button)
        scan_actions.addWidget(scan_button, 0, 0)
        scan_actions.setColumnStretch(0, 1)
        scan_section.content_layout().addLayout(scan_actions)
        sections.append(scan_section)

        phase_view_section = CollapsibleSection("Phase space options", expanded=False)
        phase_view_section.set_tooltip("show_phase_grid")
        phase_view_layout = phase_view_section.content_layout()
        for checkbox in (
            self._fixed_domain_checkbox,
            self._show_phase_grid_checkbox,
            self._show_phase_minor_grid_checkbox,
            self._show_seed_markers_checkbox,
            self._show_stationary_point_checkbox,
            self._show_branch_markers_checkbox,
        ):
            phase_view_layout.addWidget(checkbox)
        heatmap_section = CollapsibleSection("Heatmap", expanded=False)
        heatmap_section.set_tooltip("show_heatmap")
        heatmap_layout = heatmap_section.content_layout()
        heatmap_layout.addWidget(self._show_heatmap_checkbox)
        heatmap_form = QFormLayout()
        heatmap_form.setContentsMargins(0, 0, 0, 0)
        heatmap_form.setHorizontalSpacing(6)
        heatmap_form.setVerticalSpacing(4)
        heatmap_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        heatmap_form.addRow("Heatmap mode", self._heatmap_mode_combo)
        heatmap_form.addRow("Bins", self._heatmap_resolution_combo)
        heatmap_form.addRow("Norm", self._heatmap_normalization_combo)
        heatmap_layout.addLayout(heatmap_form)
        phase_view_layout.addWidget(heatmap_section)
        reset_phase_view_button = QPushButton("Reset view")
        reset_phase_view_button.clicked.connect(
            self.reset_phase_view_requested.emit
        )
        apply_tooltip(reset_phase_view_button, "reset_phase_view")
        self._set_compact_button_policy(reset_phase_view_button)
        phase_view_layout.addSpacing(4)
        phase_view_layout.addWidget(reset_phase_view_button)
        sections.append(phase_view_section)

        geometry_view_section = CollapsibleSection("Geometry view options", expanded=False)
        geometry_view_section.set_tooltip("show_directrix")
        geometry_view_section.content_layout().addWidget(self._show_directrix_checkbox)
        sections.append(geometry_view_section)

        parameter_view_section = CollapsibleSection("Parameter space options", expanded=False)
        parameter_view_section.set_tooltip("show_regions")
        parameter_view_layout = parameter_view_section.content_layout()
        parameter_view_form = QFormLayout()
        parameter_view_form.setContentsMargins(0, 0, 0, 0)
        parameter_view_form.setHorizontalSpacing(6)
        parameter_view_form.setVerticalSpacing(4)
        parameter_view_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        parameter_view_form.addRow("Interaction mode", self._constraint_mode_combo)
        parameter_view_form.addRow(self._constraint_label, self._constraint_combo)
        parameter_view_form.addRow("", self._symmetry_constraint_checkbox)
        parameter_view_form.addRow("Units", self._angle_units_combo)
        parameter_view_form.addRow("", self._show_labels_on_plot_checkbox)
        parameter_view_form.addRow("Plot label mode", self._plot_label_mode_combo)
        parameter_view_form.addRow("Tooltip label mode", self._tooltip_label_mode_combo)
        parameter_view_layout.addLayout(parameter_view_form)
        for checkbox in (
            self._show_regions_checkbox,
            self._show_region_labels_checkbox,
            self._show_region_legend_checkbox,
        ):
            parameter_view_layout.addWidget(checkbox)
        sections.append(parameter_view_section)

        scene_item_section = CollapsibleSection("SceneItems", expanded=False)
        scene_item_layout = scene_item_section.content_layout()
        self._scene_item_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        scene_item_layout.addWidget(self._scene_item_list)
        scene_item_layout.addWidget(self._scene_item_status_label)
        self._scene_item_editor_section = CollapsibleSection("SceneItem editor", expanded=False)
        scene_item_editor_layout = self._scene_item_editor_section.content_layout()
        scene_item_editor_layout.addWidget(self._scene_item_editor_placeholder)
        scene_item_editor_form = QFormLayout()
        scene_item_editor_form.setContentsMargins(0, 0, 0, 0)
        scene_item_editor_form.setHorizontalSpacing(6)
        scene_item_editor_form.setVerticalSpacing(4)
        scene_item_editor_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        scene_item_editor_form.addRow("Name", self._scene_item_name_edit)
        scene_item_editor_form.addRow("Alias", self._scene_item_alias_edit)
        scene_item_editor_form.addRow("Display text", self._scene_item_display_text_edit)
        scene_item_editor_form.addRow("Legend text", self._scene_item_legend_text_edit)
        scene_item_editor_form.addRow("Expression", self._scene_item_expression_edit)
        scene_item_editor_form.addRow("", self._scene_item_expression_status)
        scene_item_editor_form.addRow("Relation", self._scene_item_relation_combo)
        scene_item_editor_form.addRow("", self._scene_item_visible_checkbox)
        scene_item_editor_form.addRow("Priority", self._scene_item_priority_edit)
        scene_item_editor_form.addRow("Border", self._scene_item_border_color_selector)
        scene_item_editor_form.addRow(self._scene_item_fill_row_label, self._scene_item_fill_row_widget)
        scene_item_editor_form.addRow("Line width", self._scene_item_line_width_combo)
        scene_item_editor_form.addRow("Line style", self._scene_item_line_style_combo)
        scene_item_editor_layout.addLayout(scene_item_editor_form)
        scene_item_editor_layout.addWidget(self._scene_item_editor_status)
        scene_item_editor_layout.addWidget(self._scene_item_editor_apply_button)
        scene_item_layout.addWidget(self._scene_item_editor_section)
        scene_item_actions = QGridLayout()
        scene_item_actions.setHorizontalSpacing(6)
        scene_item_actions.setVerticalSpacing(4)
        scene_item_actions.addWidget(self._add_scene_item_button, 0, 0)
        scene_item_actions.addWidget(self._duplicate_scene_item_button, 0, 1)
        scene_item_actions.addWidget(self._delete_scene_item_button, 1, 0, 1, 2)
        scene_item_actions.setColumnStretch(0, 1)
        scene_item_actions.setColumnStretch(1, 1)
        scene_item_layout.addLayout(scene_item_actions)
        scene_item_save_row = QHBoxLayout()
        scene_item_save_row.setContentsMargins(0, 0, 0, 0)
        scene_item_save_row.setSpacing(6)
        scene_item_save_row.addWidget(self._scene_dirty_label)
        scene_item_save_row.addStretch(1)
        scene_item_save_row.addWidget(self._save_scene_button)
        scene_item_layout.addLayout(scene_item_save_row)
        sections.append(scene_item_section)
        self._set_scene_item_editor_enabled(False)

        lyapunov_section = CollapsibleSection("Lyapunov", expanded=False)
        lyapunov_section.set_tooltip("compute_lyapunov")
        apply_tooltip(self._compute_lyapunov_button, "compute_lyapunov")
        self._set_compact_button_policy(self._compute_lyapunov_button)
        lyapunov_section.content_layout().addWidget(self._compute_lyapunov_button)
        for label in (
            self._lyapunov_status,
            self._lyapunov_steps,
            self._lyapunov_value,
        ):
            lyapunov_section.content_layout().addWidget(label)
        sections.append(lyapunov_section)

        export_section = CollapsibleSection("Export", expanded=False)
        export_section.set_tooltip("export_png")
        export_form = QFormLayout()
        export_form.setContentsMargins(0, 0, 0, 0)
        export_form.setHorizontalSpacing(6)
        export_form.setVerticalSpacing(4)
        export_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        export_form.addRow("Mode", self._export_mode_combo)
        export_form.addRow("Mono", self._export_preset_combo)
        export_form.addRow("Data", self._data_export_format_combo)
        export_section.content_layout().addLayout(export_form)
        export_actions = QGridLayout()
        export_actions.setHorizontalSpacing(6)
        export_actions.setVerticalSpacing(4)
        export_data_button = QPushButton("Export data")
        export_data_button.clicked.connect(self.export_data_requested.emit)
        apply_tooltip(export_data_button, "export_data")
        self._set_compact_button_policy(export_data_button)
        export_actions.addWidget(export_data_button, 0, 0)
        export_actions.addWidget(QPushButton("PNG"), 0, 1)
        png_button = export_actions.itemAtPosition(0, 1).widget()
        if isinstance(png_button, QPushButton):
            self._set_compact_button_policy(png_button)
            png_button.clicked.connect(
                lambda checked=False: self.replay_action_requested.emit("export_png")
            )
            apply_tooltip(png_button, "export_png")
        export_actions.setColumnStretch(0, 1)
        export_actions.setColumnStretch(1, 1)
        export_section.content_layout().addLayout(export_actions)
        sections.append(export_section)

        session_section = CollapsibleSection("Session", expanded=False)
        session_section.set_tooltip("save_session")
        session_actions = QGridLayout()
        session_actions.setHorizontalSpacing(6)
        session_actions.setVerticalSpacing(4)
        save_button = QPushButton("Save")
        save_button.clicked.connect(
            lambda checked=False: self.replay_action_requested.emit("save_session")
        )
        apply_tooltip(save_button, "save_session")
        load_button = QPushButton("Load")
        load_button.clicked.connect(
            lambda checked=False: self.replay_action_requested.emit("load_session")
        )
        apply_tooltip(load_button, "load_session")
        self._set_compact_button_policy(save_button)
        self._set_compact_button_policy(load_button)
        session_actions.addWidget(save_button, 0, 0)
        session_actions.addWidget(load_button, 0, 1)
        session_actions.setColumnStretch(0, 1)
        session_actions.setColumnStretch(1, 1)
        session_section.content_layout().addLayout(session_actions)
        sections.append(session_section)

        return sections

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
        self.set_plot_label_options(
            show_labels_on_plot=config.view.show_labels_on_plot,
            mode=config.view.plot_label_mode,
            tooltip_mode=config.view.tooltip_label_mode,
        )
        self.set_branch_markers_enabled(config.view.show_branch_markers)
        self.set_phase_grid_options(
            show_grid=config.view.show_phase_grid,
            show_minor_grid=config.view.show_phase_minor_grid,
        )
        self.set_seed_markers_enabled(config.view.show_seed_markers)
        self.set_stationary_point_enabled(config.view.show_stationary_point)
        self.set_directrix_enabled(config.view.show_directrix)
        self.set_heatmap_settings(
            show_heatmap=config.view.show_heatmap,
            mode=config.view.heatmap_mode,
            resolution=config.view.heatmap_resolution,
            normalization=config.view.heatmap_normalization,
        )
        self.set_native_backend_options(
            enabled=config.native.enabled,
            sample_mode=config.native.sample_mode,
            sample_step=config.native.sample_step,
            status_text="Native unavailable, using Python fallback",
        )
        self._mark_parameters_applied()

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

    def set_constraint_mode(self, mode: str) -> None:
        normalized_mode = "constraint" if mode.strip().lower() == "constraint" else "free"
        blocker = QSignalBlocker(self._constraint_mode_combo)
        index = self._constraint_mode_combo.findText(
            normalized_mode.title()
        )
        self._constraint_mode_combo.setCurrentIndex(index if index >= 0 else 0)
        del blocker
        self._sync_constraint_controls()

    def constraint_mode(self) -> str:
        return self._constraint_mode_combo.currentText().strip().lower() or "free"

    def set_constraint_options(
        self,
        items: list[tuple[str, str, str]],
        selected_name: str | None,
    ) -> None:
        blocker = QSignalBlocker(self._constraint_combo)
        self._constraint_combo.clear()
        selected_index = -1
        for index, (name, label, constraint_type) in enumerate(items):
            self._constraint_combo.addItem(label, name)
            self._constraint_combo.setItemData(
                index,
                constraint_type.strip().lower(),
                Qt.UserRole + 1,
            )
            if name == selected_name:
                selected_index = index

        if selected_index >= 0:
            self._constraint_combo.setCurrentIndex(selected_index)
        elif self._constraint_combo.count() > 0:
            self._constraint_combo.setCurrentIndex(0)
        del blocker
        self._symmetry_constraint_checkbox.setVisible(
            any(
                constraint_type.strip().lower() == "symmetry"
                for _, _, constraint_type in items
            )
        )
        self._sync_constraint_controls()

    def active_constraint_name(self) -> str | None:
        if self._constraint_combo.count() <= 0:
            return None
        value = self._constraint_combo.currentData()
        return str(value) if value is not None else None

    def set_symmetric_mode(self, enabled: bool) -> None:
        blocker = QSignalBlocker(self._symmetry_constraint_checkbox)
        self._symmetry_constraint_checkbox.setChecked(enabled)
        del blocker
        self._sync_constraint_controls()

    def symmetric_mode(self) -> bool:
        return self.constraint_mode() == "constraint" and self._selected_constraint_type() == "symmetry"

    def _selected_constraint_type(self) -> str:
        if self._constraint_combo.count() <= 0:
            return ""
        value = self._constraint_combo.currentData(Qt.UserRole + 1)
        return str(value).strip().lower() if value is not None else ""

    def _sync_constraint_controls(self) -> None:
        is_constraint_mode = self.constraint_mode() == "constraint"
        self._constraint_label.setVisible(is_constraint_mode)
        self._constraint_combo.setVisible(is_constraint_mode)
        self._constraint_combo.setEnabled(
            is_constraint_mode and self._constraint_combo.count() > 0
        )
        is_symmetry = is_constraint_mode and self._selected_constraint_type() == "symmetry"
        self._beta_edit.setReadOnly(is_symmetry)
        self._beta_edit.setEnabled(not is_symmetry)
        self._sync_symmetric_beta_preview()

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

    def set_plot_label_options(
        self,
        show_labels_on_plot: bool,
        mode: str,
        tooltip_mode: str,
    ) -> None:
        blockers = [
            QSignalBlocker(self._show_labels_on_plot_checkbox),
            QSignalBlocker(self._plot_label_mode_combo),
            QSignalBlocker(self._tooltip_label_mode_combo),
        ]
        self._show_labels_on_plot_checkbox.setChecked(show_labels_on_plot)
        self._set_combo_value(self._plot_label_mode_combo, mode, "legend")
        self._set_combo_value(self._tooltip_label_mode_combo, tooltip_mode, "legend")
        del blockers
        self._plot_label_mode_combo.setEnabled(
            self._show_labels_on_plot_checkbox.isChecked()
        )

    def set_native_backend_options(
        self,
        *,
        enabled: bool,
        sample_mode: str,
        sample_step: int,
        status_text: str,
    ) -> None:
        blockers = [
            QSignalBlocker(self._native_enabled_checkbox),
            QSignalBlocker(self._native_sample_mode_combo),
            QSignalBlocker(self._native_sample_step_spin),
        ]
        self._native_enabled_checkbox.setChecked(enabled)
        self._set_combo_value(self._native_sample_mode_combo, sample_mode, "every_n")
        self._native_sample_step_spin.setValue(max(int(sample_step), 1))
        self._native_status_label.setText(status_text)
        del blockers
        self._sync_native_sample_step_enabled()
        self._update_parameter_pending_state()

    def native_backend_settings(self) -> tuple[bool, str, int]:
        return (
            self._native_enabled_checkbox.isChecked(),
            self._native_sample_mode_combo.currentText().strip().lower() or "every_n",
            max(self._native_sample_step_spin.value(), 1),
        )

    def mark_parameters_applied(self) -> None:
        self._mark_parameters_applied()

    def set_phase_grid_options(
        self,
        show_grid: bool,
        show_minor_grid: bool,
    ) -> None:
        blockers = [
            QSignalBlocker(self._show_phase_grid_checkbox),
            QSignalBlocker(self._show_phase_minor_grid_checkbox),
        ]
        self._show_phase_grid_checkbox.setChecked(show_grid)
        self._show_phase_minor_grid_checkbox.setChecked(show_minor_grid)
        self._show_phase_minor_grid_checkbox.setEnabled(show_grid)
        del blockers

    def set_seed_markers_enabled(self, enabled: bool) -> None:
        blocker = QSignalBlocker(self._show_seed_markers_checkbox)
        self._show_seed_markers_checkbox.setChecked(enabled)
        del blocker

    def set_stationary_point_enabled(self, enabled: bool) -> None:
        blocker = QSignalBlocker(self._show_stationary_point_checkbox)
        self._show_stationary_point_checkbox.setChecked(enabled)
        del blocker

    def set_directrix_enabled(self, enabled: bool) -> None:
        blocker = QSignalBlocker(self._show_directrix_checkbox)
        self._show_directrix_checkbox.setChecked(enabled)
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
        items: list[tuple[int, str, str, str, bool]],
        selected_trajectory_id: int | None,
    ) -> None:
        selector_blocker = QSignalBlocker(self._trajectory_selector)
        self._trajectory_selector.clear()
        selected_selector_index = -1

        for index, (trajectory_id, selector_label, tooltip_label, color, visible) in enumerate(items):
            self._trajectory_selector.addItem(
                self._color_icon(color, visible),
                selector_label,
                trajectory_id,
            )
            self._trajectory_selector.setItemData(
                index,
                tooltip_label,
                Qt.ToolTipRole,
            )
            if trajectory_id == selected_trajectory_id:
                selected_selector_index = index

        if selected_selector_index >= 0:
            self._trajectory_selector.setCurrentIndex(selected_selector_index)
        elif self._trajectory_selector.count() > 0:
            self._trajectory_selector.setCurrentIndex(0)
        del selector_blocker
        self._sync_selector_tooltip()

        selected_color = next(
            (
                color
                for trajectory_id, _, _, color, _ in items
                if trajectory_id == selected_trajectory_id
            ),
            None,
        )
        self.set_selected_trajectory_color(selected_color)

    def set_selected_trajectory_color(self, color: str | None) -> None:
        self._trajectory_color_selector.setEnabled(color is not None)
        if color is None:
            return
        blocker = QSignalBlocker(self._trajectory_color_selector)
        self._trajectory_color_selector.set_color(color)
        del blocker

    def set_selected_trajectory_id(
        self,
        trajectory_id: int | None,
        color: str | None = None,
    ) -> None:
        blocker = QSignalBlocker(self._trajectory_selector)
        selected_index = -1
        if trajectory_id is not None:
            for index in range(self._trajectory_selector.count()):
                item_data = self._trajectory_selector.itemData(index)
                if item_data is not None and int(item_data) == trajectory_id:
                    selected_index = index
                    break
        self._trajectory_selector.setCurrentIndex(selected_index)
        del blocker
        self._sync_selector_tooltip()
        self.set_selected_trajectory_color(color)

    def set_scene_item_items(
        self,
        items: list[tuple[str, str, str]],
        selected_item_name: str | None = None,
    ) -> None:
        self._scene_item_items = list(items)
        current_name = selected_item_name or self._current_scene_item_name()
        self._rebuild_scene_item_list(current_name)

    def set_scene_item_editor_values(
        self,
        item: tuple[str, str, str, str, str, str | None, bool, int, str, str, float, str] | None,
        *,
        sync_sections: bool = True,
    ) -> None:
        if item is None:
            self._show_scene_item_editor_placeholder(self._scene_item_empty_message())
            return
        if self._scene_item_editor_section is not None:
            self._scene_item_editor_section.setVisible(True)
        (
            name,
            alias,
            display_text,
            legend_text,
            expression,
            relation,
            visible,
            priority,
            fill,
            border,
            line_width,
            line_style,
        ) = item
        blockers = [
            QSignalBlocker(self._scene_item_fill_color_selector),
            QSignalBlocker(self._scene_item_border_color_selector),
            QSignalBlocker(self._scene_item_relation_combo),
            QSignalBlocker(self._scene_item_visible_checkbox),
            QSignalBlocker(self._scene_item_line_width_combo),
            QSignalBlocker(self._scene_item_line_style_combo),
        ]
        self._scene_item_name_edit.setText(name)
        self._scene_item_alias_edit.setText(alias)
        self._scene_item_display_text_edit.setText(display_text)
        self._scene_item_legend_text_edit.setText(legend_text)
        self._scene_item_expression_edit.setText(expression)
        self._set_combo_value(self._scene_item_relation_combo, relation or "<=", "<=")
        self._scene_item_visible_checkbox.setChecked(visible)
        self._scene_item_priority_edit.setText(str(priority))
        self._scene_item_fill_color_selector.set_color(fill)
        self._scene_item_border_color_selector.set_color(border)
        self._set_combo_value(self._scene_item_line_width_combo, f"{line_width:.1f}", "1.0")
        self._set_combo_value(
            self._scene_item_line_style_combo,
            line_style.strip().lower() or "solid",
            "solid",
        )
        del blockers
        self._scene_item_editor_placeholder.setVisible(False)
        self._scene_item_editor_status.clear()
        self._scene_item_editor_status.setVisible(False)
        self._scene_item_expression_status.clear()
        self._scene_item_expression_status.setVisible(False)
        self._set_scene_item_editor_enabled(True)
        self._sync_scene_item_editor_mode()
        if sync_sections and self._scene_item_editor_section is not None:
            self._scene_item_editor_section.set_expanded(True)

    def _rebuild_scene_item_list(self, selected_item_name: str | None = None) -> None:
        if selected_item_name is None:
            selected_item_name = self._current_scene_item_name()
        blocker = QSignalBlocker(self._scene_item_list)
        self._scene_item_list.clear()
        selected_row = -1
        for index, (name, label, relation) in enumerate(getattr(self, "_scene_item_items", [])):
            tag = f"[{relation or '?'}]"
            item = QListWidgetItem(f"{tag} {label}")
            item.setData(Qt.UserRole, (name, relation, label))
            self._scene_item_list.addItem(item)
            if name == selected_item_name:
                selected_row = index
        if selected_row >= 0:
            self._scene_item_list.setCurrentRow(selected_row)
        del blocker
        if selected_row < 0:
            self._scene_item_list.setCurrentRow(-1)
            self._show_scene_item_empty_state()

    def _current_scene_item_name(self) -> str | None:
        current_item = self._scene_item_list.currentItem()
        if current_item is None:
            return None
        data = current_item.data(Qt.UserRole)
        if (
            not isinstance(data, Sequence)
            or isinstance(data, (str, bytes))
            or len(data) != 3
        ):
            return None
        return str(data[0])

    def current_scene_item_name(self) -> str | None:
        return self._current_scene_item_name()

    def _show_scene_item_empty_state(self) -> None:
        self._scene_item_status_label.setText(self._scene_item_empty_message())
        self._show_scene_item_editor_placeholder(self._scene_item_empty_message())

    def _show_scene_item_editor_placeholder(self, text: str) -> None:
        has_items = bool(getattr(self, "_scene_item_items", []))
        self._scene_item_editor_placeholder.setText(text)
        self._scene_item_editor_placeholder.setVisible(True)
        self._scene_item_editor_status.clear()
        self._scene_item_editor_status.setVisible(False)
        self._scene_item_expression_status.clear()
        self._scene_item_expression_status.setVisible(False)
        self._set_scene_item_editor_enabled(False)
        self._scene_item_name_edit.clear()
        self._scene_item_alias_edit.clear()
        self._scene_item_display_text_edit.clear()
        self._scene_item_legend_text_edit.clear()
        self._scene_item_expression_edit.clear()
        self._scene_item_priority_edit.clear()
        if self._scene_item_editor_section is not None:
            self._scene_item_editor_section.setVisible(has_items)
            self._scene_item_editor_section.set_expanded(False)

    def _scene_item_empty_message(self) -> str:
        if not getattr(self, "_scene_item_items", []):
            return "No scene items defined. Click Add Item to create one."
        return "Select an item from the list"

    def editor_section_state(self) -> bool:
        return (
            self._scene_item_editor_section.is_expanded()
            if self._scene_item_editor_section is not None
            else False
        )

    def restore_editor_section_state(self, expanded: bool) -> None:
        if self._scene_item_editor_section is not None:
            self._scene_item_editor_section.set_expanded(expanded)

    def set_scene_item_expression_valid(self) -> None:
        self._scene_item_expression_status.setText("Valid")
        self._scene_item_expression_status.setStyleSheet("color: #0a7f27;")
        self._scene_item_expression_status.setVisible(True)

    def _set_scene_item_editor_enabled(self, enabled: bool) -> None:
        for widget in (
            self._scene_item_name_edit,
            self._scene_item_alias_edit,
            self._scene_item_display_text_edit,
            self._scene_item_legend_text_edit,
            self._scene_item_expression_edit,
            self._scene_item_expression_status,
            self._scene_item_relation_combo,
            self._scene_item_visible_checkbox,
            self._scene_item_priority_edit,
            self._scene_item_fill_color_selector,
            self._scene_item_border_color_selector,
            self._scene_item_line_width_combo,
            self._scene_item_line_style_combo,
            self._scene_item_editor_apply_button,
        ):
            widget.setEnabled(enabled)

    def _on_scene_item_selection_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._show_scene_item_empty_state()
            return
        data = current.data(Qt.UserRole)
        if (
            not isinstance(data, Sequence)
            or isinstance(data, (str, bytes))
            or len(data) != 3
        ):
            self._show_scene_item_empty_state()
            return
        name = str(data[0])
        relation = str(data[1])
        label = str(data[2])
        item_type = "boundary" if relation == "=" else "region"
        self._scene_item_status_label.setText(f"Editing {item_type}: {label}")
        self.scene_item_selected.emit(name)

    def _sync_scene_item_editor_mode(self) -> None:
        is_boundary = self._scene_item_relation_combo.currentText().strip() == "="
        self._scene_item_fill_row_label.setVisible(not is_boundary)
        self._scene_item_fill_row_widget.setVisible(not is_boundary)

    def _emit_scene_item_editor_apply(self) -> None:
        alias = self._scene_item_alias_edit.text().strip()
        if not alias:
            self._scene_item_editor_status.setText("Alias cannot be empty.")
            self._scene_item_editor_status.setVisible(True)
            return
        try:
            priority = int(self._scene_item_priority_edit.text().strip() or "0")
            line_width = float(
                self._scene_item_line_width_combo.currentText().strip() or "1.0"
            )
        except ValueError:
            self._scene_item_editor_status.setText("Priority or line width is invalid.")
            self._scene_item_editor_status.setVisible(True)
            return
        expression = self._scene_item_expression_edit.text().strip()
        is_valid, error = validate_scene_item_expression(expression)
        if not is_valid:
            self._scene_item_expression_status.setText(f"Error: {error}")
            self._scene_item_expression_status.setStyleSheet("color: #b00020;")
            self._scene_item_expression_status.setVisible(True)
            return
        self._scene_item_expression_status.setText("Valid")
        self._scene_item_expression_status.setStyleSheet("color: #0a7f27;")
        self._scene_item_expression_status.setVisible(True)
        self._scene_item_editor_status.clear()
        self._scene_item_editor_status.setVisible(False)
        self.apply_scene_item_editor_requested.emit(
            {
                "alias": alias,
                "display_text": self._scene_item_display_text_edit.text().strip() or alias,
                "legend_text": self._scene_item_legend_text_edit.text().strip() or alias,
                "expression": expression,
                "relation": self._scene_item_relation_combo.currentText().strip() or "=",
                "visible": self._scene_item_visible_checkbox.isChecked(),
                "priority": priority,
                "fill": self._scene_item_fill_color_selector.color(),
                "border": self._scene_item_border_color_selector.color(),
                "line_width": line_width,
                "line_style": self._scene_item_line_style_combo.currentText().strip().lower() or "solid",
            }
        )

    def set_scene_dirty(self, dirty: bool) -> None:
        self._scene_dirty_label.setText("Unsaved changes" if dirty else "Saved")
        self._scene_dirty_label.setStyleSheet(
            "color: #b00020;" if dirty else "color: #666;"
        )
        self._save_scene_button.setEnabled(dirty)

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

    def set_job_status(
        self,
        status: str,
        message: str,
        cancellable: bool,
        resumable: bool = False,
    ) -> None:
        del status, message, cancellable, resumable

    def set_selected_trajectory_summary(
        self,
        wall: str,
        d0: str,
        tau0: str,
        status: str,
        lyapunov: str,
    ) -> None:
        self._trajectory_wall_summary.setText(f"wall: {wall}")
        self._trajectory_d_summary.setText(f"d0: {d0}")
        self._trajectory_tau_summary.setText(f"τ0: {tau0}")
        self._trajectory_state_summary.setText(f"status: {status}")
        self._trajectory_lyapunov_summary.setText(f"Lyapunov: {lyapunov}")

    def set_selected_seed_fields(
        self,
        d_value: str,
        tau_value: str,
        wall: str,
    ) -> None:
        blockers = [
            QSignalBlocker(self._selected_seed_d_edit),
            QSignalBlocker(self._selected_seed_tau_edit),
            QSignalBlocker(self._selected_seed_wall_edit),
        ]
        self._selected_seed_d_edit.setText(d_value)
        self._selected_seed_tau_edit.setText(tau_value)
        self._selected_seed_wall_edit.setText(wall)
        del blockers
        self._clear_selected_seed_error()

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
        self._mark_parameters_applied()

    def _on_trajectory_selector_changed(self, index: int) -> None:
        if index < 0:
            self._trajectory_selector.setToolTip("")
            return
        trajectory_id = self._trajectory_selector.itemData(index)
        if trajectory_id is None:
            return
        self._sync_selector_tooltip()
        self.trajectory_selected.emit(int(trajectory_id))

    def _toggle_current_visibility(self) -> None:
        trajectory_id = self._current_trajectory_id()
        if trajectory_id is not None:
            self.trajectory_visibility_toggled.emit(int(trajectory_id))

    def _current_trajectory_id(self) -> int | None:
        index = self._trajectory_selector.currentIndex()
        if index < 0:
            return None
        trajectory_id = self._trajectory_selector.itemData(index)
        if trajectory_id is None:
            return None
        return int(trajectory_id)

    def _sync_selector_tooltip(self) -> None:
        index = self._trajectory_selector.currentIndex()
        if index < 0:
            self._trajectory_selector.setToolTip(tooltip_text("selected_trajectory"))
            return
        tooltip = self._trajectory_selector.itemData(index, Qt.ToolTipRole)
        details = str(tooltip) if tooltip is not None else ""
        prefix = tooltip_text("selected_trajectory")
        self._trajectory_selector.setToolTip(
            prefix if not details else f"{prefix}\n\n{details}"
        )

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

    def _parameter_state_snapshot(self) -> tuple[int, int, bool, str, int] | None:
        try:
            n_phase = int(self._n_phase_edit.text())
            n_geom = int(self._n_geom_edit.text())
        except ValueError:
            return None
        enabled, sample_mode, sample_step = self.native_backend_settings()
        return (n_phase, n_geom, enabled, sample_mode, sample_step)

    def _mark_parameters_applied(self) -> None:
        self._applied_parameter_state = self._parameter_state_snapshot()
        self._update_parameter_pending_state()

    def _update_parameter_pending_state(self, *_args: object) -> None:
        current_state = self._parameter_state_snapshot()
        is_pending = (
            current_state is not None
            and self._applied_parameter_state is not None
            and current_state != self._applied_parameter_state
        )
        self._parameter_pending_label.setText(
            "Parameters changed — press Apply" if is_pending else ""
        )
        self._parameter_pending_label.setVisible(is_pending)

    def _sync_native_sample_step_enabled(self) -> None:
        sample_mode = self._native_sample_mode_combo.currentText().strip().lower()
        self._native_sample_step_spin.setEnabled(sample_mode != "dense")

    def _set_selected_seed_error(self, message: str) -> None:
        self._selected_seed_status.setText(message)
        self._selected_seed_status.setStyleSheet("color: #b00020;")
        self._selected_seed_d_edit.setStyleSheet("border: 1px solid #b00020;")
        self._selected_seed_tau_edit.setStyleSheet("border: 1px solid #b00020;")

    def _clear_selected_seed_error(self) -> None:
        self._selected_seed_status.setText("")
        self._selected_seed_status.setStyleSheet("")
        self._selected_seed_d_edit.setStyleSheet("")
        self._selected_seed_tau_edit.setStyleSheet("")

    def _display_angles(self, alpha: float, beta: float) -> tuple[float, float]:
        if self._angle_units == "deg":
            return math.degrees(alpha), math.degrees(beta)
        return alpha, beta

    def _set_compact_button_policy(self, button: QPushButton) -> None:
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

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
        if enabled:
            symmetry_index = next(
                (
                    index
                    for index in range(self._constraint_combo.count())
                    if self._selected_constraint_type_at(index) == "symmetry"
                ),
                -1,
            )
            if symmetry_index >= 0:
                blocker = QSignalBlocker(self._constraint_combo)
                self._constraint_combo.setCurrentIndex(symmetry_index)
                del blocker
            self.set_constraint_mode("constraint")
        elif self.symmetric_mode():
            self.set_constraint_mode("free")
        self._sync_constraint_controls()
        self.angle_constraint_mode_changed.emit(self.constraint_mode())
        active_name = self.active_constraint_name()
        if self.constraint_mode() == "constraint" and active_name is not None:
            self.angle_constraint_changed.emit(active_name)
        self.symmetric_mode_changed.emit(enabled)

    def _on_constraint_mode_changed(self, mode: str) -> None:
        self._sync_constraint_controls()
        normalized_mode = mode.strip().lower() or "free"
        self.angle_constraint_mode_changed.emit(normalized_mode)
        self.symmetric_mode_changed.emit(
            normalized_mode == "constraint"
            and self._selected_constraint_type() == "symmetry"
        )

    def _on_constraint_changed(self, index: int) -> None:
        del index
        self._sync_constraint_controls()
        blocker = QSignalBlocker(self._symmetry_constraint_checkbox)
        self._symmetry_constraint_checkbox.setChecked(self.symmetric_mode())
        del blocker
        active_name = self.active_constraint_name()
        if active_name is not None:
            self.angle_constraint_changed.emit(active_name)
        self.symmetric_mode_changed.emit(self.symmetric_mode())

    def _selected_constraint_type_at(self, index: int) -> str:
        if index < 0:
            return ""
        value = self._constraint_combo.itemData(index, Qt.UserRole + 1)
        return str(value).strip().lower() if value is not None else ""

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

    def _emit_plot_labels_changed(self) -> None:
        enabled = self._show_labels_on_plot_checkbox.isChecked()
        self._plot_label_mode_combo.setEnabled(enabled)
        self.plot_labels_changed.emit(
            enabled,
            self._plot_label_mode_combo.currentText().strip().lower() or "legend",
            self._tooltip_label_mode_combo.currentText().strip().lower() or "legend",
        )

    def _on_native_backend_controls_changed(self, *_args: object) -> None:
        self._sync_native_sample_step_enabled()
        self._update_parameter_pending_state()

    def _emit_phase_grid_visibility(self) -> None:
        show_grid = self._show_phase_grid_checkbox.isChecked()
        self._show_phase_minor_grid_checkbox.setEnabled(show_grid)
        self.phase_grid_visibility_changed.emit(
            show_grid,
            show_grid and self._show_phase_minor_grid_checkbox.isChecked(),
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

    def _emit_selected_seed_apply(self) -> None:
        self._clear_selected_seed_error()
        try:
            d_value = parse_real_expression(self._selected_seed_d_edit.text())
            tau_value = parse_real_expression(self._selected_seed_tau_edit.text())
        except (ValueError, SyntaxError, ZeroDivisionError):
            self._set_selected_seed_error("Invalid seed value")
            return

        self.selected_seed_apply_requested.emit(d_value, tau_value)

    def _expand_add_section(self) -> None:
        if self._add_section is not None:
            self._add_section.set_expanded(True)
        self._manual_d_edit.setFocus()

    def _apply_tooltips(self) -> None:
        apply_tooltip(self._trajectory_selector, "selected_trajectory")
        apply_tooltip(self._selected_seed_d_edit, "selected_seed_d")
        apply_tooltip(self._selected_seed_tau_edit, "selected_seed_tau")
        apply_tooltip(self._selected_seed_wall_edit, "selected_seed_wall")
        apply_tooltip(self._angle_units_combo, "angle_units")
        apply_tooltip(self._alpha_edit, "alpha_edit")
        apply_tooltip(self._beta_edit, "beta_edit")
        apply_tooltip(self._n_phase_edit, "n_phase_edit")
        apply_tooltip(self._n_geom_edit, "n_geom_edit")
        self._constraint_mode_combo.setToolTip(
            "Choose free movement or movement constrained to one curve."
        )
        self._constraint_combo.setToolTip(
            "Select the active point constraint for the α/β panel."
        )
        self._symmetry_constraint_checkbox.setToolTip(
            "Quick switch to the symmetry constraint."
        )
        apply_tooltip(self._fixed_domain_checkbox, "fixed_domain")
        apply_tooltip(self._show_phase_grid_checkbox, "show_phase_grid")
        apply_tooltip(
            self._show_phase_minor_grid_checkbox,
            "show_phase_minor_grid",
        )
        apply_tooltip(self._show_seed_markers_checkbox, "show_seed_markers")
        apply_tooltip(
            self._show_stationary_point_checkbox,
            "show_stationary_point",
        )
        apply_tooltip(self._show_directrix_checkbox, "show_directrix")
        apply_tooltip(self._show_regions_checkbox, "show_regions")
        apply_tooltip(self._show_region_labels_checkbox, "show_region_labels")
        apply_tooltip(self._show_region_legend_checkbox, "show_region_legend")
        self._show_labels_on_plot_checkbox.setToolTip(
            "Show parameter-space labels directly on the plot."
        )
        self._plot_label_mode_combo.setToolTip(
            "Choose whether plot labels use SceneItem alias or legend text."
        )
        self._tooltip_label_mode_combo.setToolTip(
            "Choose whether hover tooltip uses SceneItem alias or legend text."
        )
        self._native_enabled_checkbox.setToolTip(
            "Enable the native backend when available; otherwise Python fallback is used."
        )
        self._native_sample_mode_combo.setToolTip(
            "Choose how many phase points the native backend returns."
        )
        self._native_sample_step_spin.setToolTip(
            "Return every N-th sampled point for native sparse modes."
        )
        self._native_status_label.setToolTip(
            "Current native backend availability and fallback status."
        )
        apply_tooltip(self._show_branch_markers_checkbox, "show_branch_markers")
        apply_tooltip(self._show_heatmap_checkbox, "show_heatmap")
        apply_tooltip(self._heatmap_mode_combo, "heatmap_mode")
        apply_tooltip(self._heatmap_resolution_combo, "heatmap_bins")
        apply_tooltip(self._heatmap_normalization_combo, "heatmap_norm")
        apply_tooltip(self._export_mode_combo, "export_mode")
        apply_tooltip(self._export_preset_combo, "mono_preset")
        apply_tooltip(self._data_export_format_combo, "data_export_format")
        apply_tooltip(self._scan_mode_combo, "scan_mode")
        apply_tooltip(self._scan_wall_combo, "scan_wall")
        apply_tooltip(self._scan_count_edit, "scan_count")
        apply_tooltip(self._scan_d_min_edit, "scan_d_min")
        apply_tooltip(self._scan_d_max_edit, "scan_d_max")
        apply_tooltip(self._scan_tau_min_edit, "scan_tau_min")
        apply_tooltip(self._scan_tau_max_edit, "scan_tau_max")
        apply_tooltip(self._manual_d_edit, "manual_d")
        apply_tooltip(self._manual_tau_edit, "manual_tau")
        apply_tooltip(self._manual_wall_combo, "manual_wall")
