from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
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
        self._trajectory_info = QLabel("selected: -")
        self._parameter_status = QLabel("")

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
        self._fixed_domain_checkbox.toggled.connect(
            self.phase_view_mode_changed.emit
        )

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
        return box

    def _build_parameters_box(self) -> QGroupBox:
        box = QGroupBox("Parameters")
        layout = QFormLayout(box)
        layout.addRow("alpha", self._alpha_edit)
        layout.addRow("beta", self._beta_edit)
        layout.addRow("N_phase", self._n_phase_edit)
        layout.addRow("N_geom", self._n_geom_edit)
        layout.addRow(self._fixed_domain_checkbox)
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
        self._alpha_edit.setText(f"{config.simulation.alpha:.6f}")
        self._beta_edit.setText(f"{config.simulation.beta:.6f}")
        self._n_phase_edit.setText(str(config.simulation.n_phase_default))
        self._n_geom_edit.setText(str(config.simulation.n_geom_default))

    def set_phase_view_mode(self, fixed_domain: bool) -> None:
        blocker = QSignalBlocker(self._fixed_domain_checkbox)
        self._fixed_domain_checkbox.setChecked(fixed_domain)
        del blocker

    def set_trajectory_items(
        self,
        items: list[tuple[int, str]],
        selected_trajectory_id: int | None,
    ) -> None:
        blocker = QSignalBlocker(self._trajectory_list)
        self._trajectory_list.clear()
        selected_item: QListWidgetItem | None = None

        for trajectory_id, label in items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, trajectory_id)
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

    def _emit_parameters(self) -> None:
        self._clear_parameter_error()
        try:
            alpha = parse_real_expression(self._alpha_edit.text())
            beta = parse_real_expression(self._beta_edit.text())
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
