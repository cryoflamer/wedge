from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.config import Config


class ControlsPanel(QWidget):
    parameters_changed = Signal(float, float, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._trajectory_list = QListWidget()
        self._alpha_edit = QLineEdit()
        self._beta_edit = QLineEdit()
        self._n_phase_edit = QLineEdit()
        self._n_geom_edit = QLineEdit()

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._build_trajectory_box())
        main_layout.addWidget(self._build_parameters_box())
        main_layout.addWidget(self._build_controls_box())
        main_layout.addStretch(1)

    def _build_trajectory_box(self) -> QGroupBox:
        box = QGroupBox("Trajectories")
        layout = QVBoxLayout(box)
        layout.addWidget(self._trajectory_list)
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
        for label in (
            "Replay selected",
            "Replay all",
            "Pause",
            "Resume",
            "Step",
            "Reset replay",
            "Export PNG",
            "Save session",
            "Load session",
            "Clear selected trajectory",
            "Clear all trajectories",
        ):
            layout.addWidget(QPushButton(label))

        footer = QHBoxLayout()
        footer.addWidget(QLabel("UI skeleton"))
        footer.addStretch(1)
        layout.addLayout(footer)
        return box

    def load_config(self, config: Config) -> None:
        self._alpha_edit.setText(str(config.simulation.alpha))
        self._beta_edit.setText(str(config.simulation.beta))
        self._n_phase_edit.setText(str(config.simulation.n_phase_default))
        self._n_geom_edit.setText(str(config.simulation.n_geom_default))

    def add_trajectory_item(self, label: str) -> None:
        self._trajectory_list.addItem(label)

    def _emit_parameters(self) -> None:
        self.parameters_changed.emit(
            float(self._alpha_edit.text()),
            float(self._beta_edit.text()),
            int(self._n_phase_edit.text()),
            int(self._n_geom_edit.text()),
        )
