from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QGridLayout, QMainWindow, QWidget

from app.models.config import Config
from app.ui.angle_panel import AnglePanel
from app.ui.controls_panel import ControlsPanel
from app.ui.phase_panel import PhasePanel
from app.ui.wedge_panel import WedgePanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config

        self.setWindowTitle(config.app.title)
        self.resize(1440, 900)

        self.phase_panel_wall_1 = PhasePanel(wall=1, title="Phase Panel 1")
        self.phase_panel_wall_2 = PhasePanel(wall=2, title="Phase Panel 2")
        self.wedge_panel = WedgePanel()
        self.angle_panel = AnglePanel()
        self.controls_panel = ControlsPanel()

        self._build_layout()
        self._connect_signals()
        self.update_view()

    def _build_layout(self) -> None:
        central = QWidget()
        grid = QGridLayout(central)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(12)

        grid.addWidget(self.phase_panel_wall_1, 0, 0)
        grid.addWidget(self.phase_panel_wall_2, 0, 1)
        grid.addWidget(self.wedge_panel, 1, 0)
        grid.addWidget(self.angle_panel, 1, 1)
        grid.addWidget(self.controls_panel, 0, 2, 2, 1)

        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 2)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.phase_panel_wall_1.clicked.connect(self._on_phase_click)
        self.phase_panel_wall_2.clicked.connect(self._on_phase_click)
        self.angle_panel.point_selected.connect(self._on_angle_click)
        self.controls_panel.parameters_changed.connect(self._on_parameters_changed)

    def update_view(self) -> None:
        self.controls_panel.load_config(self._config)
        self.angle_panel.set_angles(
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )

    def _on_phase_click(self, wall: int, d_value: float, tau_value: float) -> None:
        logger.info(
            "Phase panel clicked: wall=%s d=%.6f tau=%.6f",
            wall,
            d_value,
            tau_value,
        )
        self.controls_panel.add_trajectory_item(
            f"seed wall={wall} d={d_value:.3f} tau={tau_value:.3f}"
        )

    def _on_angle_click(self, alpha: float, beta: float) -> None:
        logger.info("Angle panel clicked: alpha=%.6f beta=%.6f", alpha, beta)

    def _on_parameters_changed(
        self,
        alpha: float,
        beta: float,
        n_phase: int,
        n_geom: int,
    ) -> None:
        self._config.simulation.alpha = alpha
        self._config.simulation.beta = beta
        self._config.simulation.n_phase_default = n_phase
        self._config.simulation.n_geom_default = n_geom
        self.update_view()
        logger.info(
            "Parameters updated: alpha=%.6f beta=%.6f n_phase=%s n_geom=%s",
            alpha,
            beta,
            n_phase,
            n_geom,
        )


def run_app(config: Config) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    app.exec()
