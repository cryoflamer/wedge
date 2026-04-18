from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QGridLayout, QMainWindow, QWidget

from app.core.geometry_builder import build_wedge_geometry
from app.core.orbit_builder import build_orbit
from app.models.config import Config
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed
from app.ui.angle_panel import AnglePanel
from app.ui.controls_panel import ControlsPanel
from app.ui.phase_panel import PhasePanel
from app.ui.wedge_panel import WedgePanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._next_trajectory_id = 1
        self._selected_trajectory_id: int | None = None
        self._trajectory_seeds: dict[int, TrajectorySeed] = {}
        self._trajectory_orbits: dict[int, Orbit] = {}
        self._trajectory_geometries: dict[int, WedgeGeometry] = {}
        self._active_segment_index = 0
        self._palette = [
            "#1f77b4",
            "#d62728",
            "#2ca02c",
            "#ff7f0e",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#17becf",
        ]

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
        self.controls_panel.trajectory_selected.connect(self._on_trajectory_selected)

    def update_view(self) -> None:
        self.controls_panel.load_config(self._config)
        self.angle_panel.set_angles(
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )
        trajectory_items = [
            (
                seed.id,
                (
                    f"#{seed.id} wall={seed.wall_start} "
                    f"d0={seed.d0:.3f} tau0={seed.tau0:.3f}"
                ),
            )
            for seed in self._trajectory_seeds.values()
        ]
        self.controls_panel.set_trajectory_items(
            trajectory_items,
            self._selected_trajectory_id,
        )
        self.phase_panel_wall_1.set_trajectories(
            self._trajectory_seeds,
            self._trajectory_orbits,
            self._selected_trajectory_id,
        )
        self.phase_panel_wall_2.set_trajectories(
            self._trajectory_seeds,
            self._trajectory_orbits,
            self._selected_trajectory_id,
        )
        self.wedge_panel.set_geometries(
            self._trajectory_seeds,
            self._trajectory_geometries,
            self._selected_trajectory_id,
            self._active_segment_index,
        )

    def _on_phase_click(self, wall: int, d_value: float, tau_value: float) -> None:
        trajectory_id = self._next_trajectory_id
        self._next_trajectory_id += 1
        seed = TrajectorySeed(
            id=trajectory_id,
            wall_start=wall,
            d0=d_value,
            tau0=tau_value,
            color=self._palette[(trajectory_id - 1) % len(self._palette)],
        )
        orbit = build_orbit(
            seed=seed,
            config=self._config.simulation,
            steps=self._config.simulation.n_phase_default,
        )
        self._trajectory_seeds[trajectory_id] = seed
        self._trajectory_orbits[trajectory_id] = orbit
        self._trajectory_geometries[trajectory_id] = build_wedge_geometry(
            orbit=orbit,
            config=self._config.simulation,
            max_reflections=self._config.simulation.n_geom_default,
        )
        if self._selected_trajectory_id is None:
            self._selected_trajectory_id = trajectory_id

        logger.info(
            "Phase panel clicked: wall=%s d=%.6f tau=%.6f id=%s",
            wall,
            d_value,
            tau_value,
            trajectory_id,
        )
        self.update_view()

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
        self._rebuild_orbits()
        self.update_view()
        logger.info(
            "Parameters updated: alpha=%.6f beta=%.6f n_phase=%s n_geom=%s",
            alpha,
            beta,
            n_phase,
            n_geom,
        )

    def _on_trajectory_selected(self, trajectory_id: int) -> None:
        self._selected_trajectory_id = trajectory_id
        self._active_segment_index = 0
        self.update_view()

    def _rebuild_orbits(self) -> None:
        self._trajectory_orbits = {
            trajectory_id: build_orbit(
                seed=seed,
                config=self._config.simulation,
                steps=self._config.simulation.n_phase_default,
            )
            for trajectory_id, seed in self._trajectory_seeds.items()
        }
        self._trajectory_geometries = {
            trajectory_id: build_wedge_geometry(
                orbit=orbit,
                config=self._config.simulation,
                max_reflections=self._config.simulation.n_geom_default,
            )
            for trajectory_id, orbit in self._trajectory_orbits.items()
        }


def run_app(config: Config) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    app.exec()
