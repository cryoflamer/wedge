from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
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


class ControlsPanel(QWidget):
    parameters_changed = Signal(float, float, int, int)
    trajectory_selected = Signal(int)
    trajectory_visibility_toggled = Signal(int)
    clear_selected_requested = Signal()
    clear_all_requested = Signal()
    replay_action_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._trajectory_list = QListWidget()
        self._alpha_edit = QLineEdit()
        self._beta_edit = QLineEdit()
        self._n_phase_edit = QLineEdit()
        self._n_geom_edit = QLineEdit()
        self._trajectory_info = QLabel("selected: -")

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._build_trajectory_box())
        main_layout.addWidget(self._build_parameters_box())
        main_layout.addWidget(self._build_controls_box())
        main_layout.addStretch(1)

        self._trajectory_list.currentItemChanged.connect(
            self._on_current_item_changed
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

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._emit_parameters)
        layout.addRow(apply_button)
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
        self.parameters_changed.emit(
            float(self._alpha_edit.text()),
            float(self._beta_edit.text()),
            int(self._n_phase_edit.text()),
            int(self._n_geom_edit.text()),
        )

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
