from __future__ import annotations

import math
import logging
import sys
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QMainWindow,
    QWidget,
)

from app.core.geometry_builder import build_wedge_geometry
from app.core.orbit_builder import build_orbit
from app.models.config import Config
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.session import Session
from app.models.trajectory import TrajectorySeed
from app.services.config_loader import save_runtime_config
from app.services.export_service import export_widget_bundle_png
from app.services.session_service import load_session, save_session
from app.ui.angle_panel import AnglePanel
from app.ui.controls_panel import ControlsPanel
from app.ui.phase_panel import PhasePanel
from app.ui.replay_controller import ReplayController
from app.ui.wedge_panel import WedgePanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config: Config, config_path: str) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._window_position_restored = False
        self._next_trajectory_id = 1
        self._selected_trajectory_id: int | None = None
        self._angle_units = "rad"
        self._symmetric_mode = False
        self._trajectory_seeds: dict[int, TrajectorySeed] = {}
        self._trajectory_orbits: dict[int, Orbit] = {}
        self._trajectory_geometries: dict[int, WedgeGeometry] = {}
        self._active_segment_indices: dict[int, int] = {}
        self._active_phase_frames: dict[int, int] = {}
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
        self.resize(config.window.width, config.window.height)
        if config.window.x is not None and config.window.y is not None:
            self.move(config.window.x, config.window.y)
            self._window_position_restored = True

        self.phase_panel_wall_1 = PhasePanel(
            wall=1,
            title="Phase Panel 1",
            view_config=config.view,
        )
        self.phase_panel_wall_2 = PhasePanel(
            wall=2,
            title="Phase Panel 2",
            view_config=config.view,
        )
        self.wedge_panel = WedgePanel(view_config=config.view)
        self.angle_panel = AnglePanel(view_config=config.view)
        self.controls_panel = ControlsPanel()
        self.replay_controller = ReplayController(
            delay_ms=config.replay.delay_ms,
            parent=self,
        )

        self._build_layout()
        self._connect_signals()
        self.update_view()
        self._restore_autosave_session()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._window_position_restored:
            return

        frame = self.frameGeometry()
        screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())
        self._window_position_restored = True

    def closeEvent(self, event: QCloseEvent) -> None:
        self._config.window.width = self.width()
        self._config.window.height = self.height()
        self._config.window.x = self.x()
        self._config.window.y = self.y()
        self._autosave_session()
        save_runtime_config(self._config, self._config_path)
        super().closeEvent(event)

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
        self.phase_panel_wall_1.viewport_changed.connect(self._on_phase_viewport_changed)
        self.phase_panel_wall_2.viewport_changed.connect(self._on_phase_viewport_changed)
        self.angle_panel.point_selected.connect(self._on_angle_click)
        self.controls_panel.parameters_changed.connect(self._on_parameters_changed)
        self.controls_panel.angle_units_changed.connect(self._on_angle_units_changed)
        self.controls_panel.symmetric_mode_changed.connect(
            self._on_symmetric_mode_changed
        )
        self.controls_panel.trajectory_selected.connect(self._on_trajectory_selected)
        self.controls_panel.trajectory_visibility_toggled.connect(
            self._on_trajectory_visibility_toggled
        )
        self.controls_panel.phase_view_mode_changed.connect(
            self._on_phase_view_mode_changed
        )
        self.controls_panel.reset_phase_view_requested.connect(
            self._on_reset_phase_view
        )
        self.controls_panel.clear_selected_requested.connect(
            self._on_clear_selected_trajectory
        )
        self.controls_panel.clear_all_requested.connect(self._on_clear_all_trajectories)
        self.controls_panel.replay_action_requested.connect(self._on_replay_action)
        self.replay_controller.state_changed.connect(self._on_replay_state_changed)

    def update_view(self) -> None:
        self.controls_panel.load_config(self._config)
        self.controls_panel.set_angle_units(self._angle_units)
        self.controls_panel.set_symmetric_mode(self._symmetric_mode)
        self.controls_panel.set_phase_view_mode(
            self.phase_panel_wall_1.is_fixed_domain_mode()
        )
        self.angle_panel.set_angle_units(self._angle_units)
        self.angle_panel.set_symmetric_mode(self._symmetric_mode)
        self.angle_panel.set_angles(
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )
        self.angle_panel.set_regions(self._config.regions)
        trajectory_items = [
            (
                seed.id,
                (
                    f"#{seed.id} wall={seed.wall_start} "
                    f"d0={seed.d0:.3f} tau0={seed.tau0:.3f} "
                    f"{'visible' if seed.visible else 'hidden'}"
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
            self._active_phase_frames,
        )
        self.phase_panel_wall_2.set_trajectories(
            self._trajectory_seeds,
            self._trajectory_orbits,
            self._selected_trajectory_id,
            self._active_phase_frames,
        )
        self.wedge_panel.set_geometries(
            self._trajectory_seeds,
            self._trajectory_geometries,
            self._selected_trajectory_id,
            self._active_segment_indices,
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
        self._trajectory_seeds[trajectory_id] = seed
        self._trajectory_orbits[trajectory_id] = self._build_orbit(seed)
        self._trajectory_geometries[trajectory_id] = self._build_geometry(
            self._trajectory_orbits[trajectory_id]
        )
        if self._selected_trajectory_id is None:
            self._selected_trajectory_id = trajectory_id
        self._reset_replay_views()

        logger.info(
            "Phase panel clicked: wall=%s d=%.6f tau=%.6f id=%s",
            wall,
            d_value,
            tau_value,
            trajectory_id,
        )
        self._autosave_session()
        self.update_view()

    def _on_angle_click(self, alpha: float, beta: float) -> None:
        self._on_parameters_changed(
            alpha=alpha,
            beta=beta,
            n_phase=self._config.simulation.n_phase_default,
            n_geom=self._config.simulation.n_geom_default,
        )
        logger.info("Angle panel clicked: alpha=%.6f beta=%.6f", alpha, beta)

    def _on_angle_units_changed(self, units: str) -> None:
        self._angle_units = units
        self.update_view()
        logger.info("Angle units changed: %s", units)

    def _on_symmetric_mode_changed(self, enabled: bool) -> None:
        self._symmetric_mode = enabled
        if enabled:
            self._config.simulation.beta = math.nextafter(
                math.pi - self._config.simulation.alpha,
                self._config.simulation.alpha,
            )
            self._rebuild_orbits()
            self._reset_replay_views()
            self._autosave_session()
        self.update_view()
        logger.info("Symmetric mode changed: %s", enabled)

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
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info(
            "Parameters updated: alpha=%.6f beta=%.6f n_phase=%s n_geom=%s",
            alpha,
            beta,
            n_phase,
            n_geom,
        )

    def _on_trajectory_selected(self, trajectory_id: int) -> None:
        if trajectory_id == self._selected_trajectory_id:
            return
        self._selected_trajectory_id = trajectory_id
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()

    def _on_phase_view_mode_changed(self, fixed_domain: bool) -> None:
        self.phase_panel_wall_1.set_fixed_domain_mode(fixed_domain)
        self.phase_panel_wall_2.set_fixed_domain_mode(fixed_domain)
        self._autosave_session()
        self.update_view()

    def _on_reset_phase_view(self) -> None:
        self.phase_panel_wall_1.reset_view()
        self.phase_panel_wall_2.reset_view()
        self._autosave_session()
        self.update_view()

    def _on_phase_viewport_changed(self) -> None:
        self._autosave_session()
        self.update_view()

    def _rebuild_orbits(self) -> None:
        self._trajectory_orbits = {
            trajectory_id: self._build_orbit(seed)
            for trajectory_id, seed in self._trajectory_seeds.items()
        }
        self._trajectory_geometries = {
            trajectory_id: self._build_geometry(orbit)
            for trajectory_id, orbit in self._trajectory_orbits.items()
        }

    def _on_trajectory_visibility_toggled(self, trajectory_id: int) -> None:
        seed = self._trajectory_seeds.get(trajectory_id)
        if seed is None:
            return
        seed.visible = not seed.visible
        self._autosave_session()
        self.update_view()
        logger.info(
            "Trajectory visibility toggled: id=%s visible=%s",
            trajectory_id,
            seed.visible,
        )

    def _on_clear_selected_trajectory(self) -> None:
        if self._selected_trajectory_id is None:
            return
        trajectory_id = self._selected_trajectory_id
        self._trajectory_seeds.pop(trajectory_id, None)
        self._trajectory_orbits.pop(trajectory_id, None)
        self._trajectory_geometries.pop(trajectory_id, None)
        self._selected_trajectory_id = (
            next(iter(self._trajectory_seeds.keys()))
            if self._trajectory_seeds
            else None
        )
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info("Trajectory cleared: id=%s", trajectory_id)

    def _on_clear_all_trajectories(self) -> None:
        self._trajectory_seeds.clear()
        self._trajectory_orbits.clear()
        self._trajectory_geometries.clear()
        self._selected_trajectory_id = None
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info("All trajectories cleared")

    def _on_replay_action(self, action_name: str) -> None:
        if action_name == "replay_selected":
            max_frame = self._max_frame_for_selected()
            self.replay_controller.start("selected", max_frame)
        elif action_name == "replay_all":
            max_frame = self._max_frame_for_all()
            self.replay_controller.start("all", max_frame)
        elif action_name == "pause":
            self.replay_controller.pause()
        elif action_name == "resume":
            self.replay_controller.resume()
        elif action_name == "step":
            self.replay_controller.step()
        elif action_name == "reset_replay":
            self.replay_controller.reset()
            self._reset_replay_views()
            self.update_view()
        elif action_name == "export_png":
            self._export_png()
        elif action_name == "save_session":
            self._save_session()
        elif action_name == "load_session":
            self._load_session()
        else:
            logger.info("Replay/control action requested: %s", action_name)

    def _on_replay_state_changed(
        self,
        mode: str,
        active_frame: int,
        running: bool,
    ) -> None:
        del running
        if not mode:
            self._reset_replay_views()
            self.update_view()
            return

        if mode == "selected" and self._selected_trajectory_id is not None:
            self._active_phase_frames = {self._selected_trajectory_id: active_frame}
            self._active_segment_indices = {
                self._selected_trajectory_id: max(active_frame - 1, 0)
            }
        elif mode == "all":
            self._active_phase_frames = {
                trajectory_id: active_frame
                for trajectory_id in self._trajectory_orbits.keys()
            }
            self._active_segment_indices = {
                trajectory_id: max(active_frame - 1, 0)
                for trajectory_id in self._trajectory_geometries.keys()
            }
        self.update_view()

    def _reset_replay_views(self) -> None:
        self._active_phase_frames = {}
        self._active_segment_indices = {}

    def _max_frame_for_selected(self) -> int:
        if self._selected_trajectory_id is None:
            return 0
        orbit = self._trajectory_orbits.get(self._selected_trajectory_id)
        if orbit is None:
            return 0
        return max(len(orbit.points) - 1, 0)

    def _max_frame_for_all(self) -> int:
        if not self._trajectory_orbits:
            return 0
        return max(max(len(orbit.points) - 1, 0) for orbit in self._trajectory_orbits.values())

    def _export_png(self) -> None:
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PNG",
            "wedge_export.png",
            "PNG Files (*.png)",
        )
        if not output_path:
            return

        mode = self.controls_panel.export_mode()
        self._config.export.default_mode = mode
        preset = self.controls_panel.export_preset()
        monochrome = mode == "monochrome"
        exported_paths = export_widget_bundle_png(
            widgets={
                "layout": self.centralWidget(),
                "phase_wall_1": self.phase_panel_wall_1,
                "phase_wall_2": self.phase_panel_wall_2,
                "wedge": self.wedge_panel,
                "angle": self.angle_panel,
            },
            base_path=output_path,
            dpi=self._config.export.dpi,
            monochrome=monochrome,
        )
        logger.info(
            "PNG export completed: mode=%s preset=%s files=%s",
            mode or "color",
            preset or "-",
            ", ".join(str(path) for path in exported_paths),
        )

    def _save_session(self) -> None:
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            "wedge_session.yaml",
            "YAML Files (*.yaml *.yml)",
        )
        if not output_path:
            return

        session = self._build_session()
        saved_path = save_session(session, output_path)
        logger.info("Session saved: %s", saved_path)

    def _load_session(self) -> None:
        input_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            "",
            "YAML Files (*.yaml *.yml)",
        )
        if not input_path:
            return

        session = load_session(input_path)
        self._apply_session(session)
        self._autosave_session()
        logger.info("Session loaded: %s", input_path)

    def _build_session(self) -> Session:
        return Session(
            alpha=self._config.simulation.alpha,
            beta=self._config.simulation.beta,
            n_phase=self._config.simulation.n_phase_default,
            n_geom=self._config.simulation.n_geom_default,
            replay_delay_ms=self._config.replay.delay_ms,
            replay_selected_only=self._config.replay.selected_only_by_default,
            selected_trajectory_id=self._selected_trajectory_id,
            trajectories=list(self._trajectory_seeds.values()),
            phase_fixed_domain=self.phase_panel_wall_1.is_fixed_domain_mode(),
            phase_viewport_wall_1=self.phase_panel_wall_1.viewport(),
            phase_viewport_wall_2=self.phase_panel_wall_2.viewport(),
        )

    def _apply_session(self, session: Session) -> None:
        self._config.simulation.alpha = session.alpha
        self._config.simulation.beta = session.beta
        self._config.simulation.n_phase_default = session.n_phase
        self._config.simulation.n_geom_default = session.n_geom
        self._config.replay.delay_ms = session.replay_delay_ms
        self._config.replay.selected_only_by_default = session.replay_selected_only

        self._trajectory_seeds = {
            seed.id: TrajectorySeed(
                id=seed.id,
                wall_start=seed.wall_start,
                d0=seed.d0,
                tau0=seed.tau0,
                visible=seed.visible,
                color=seed.color,
            )
            for seed in session.trajectories
        }
        self._selected_trajectory_id = session.selected_trajectory_id
        self.phase_panel_wall_1.set_fixed_domain_mode(session.phase_fixed_domain)
        self.phase_panel_wall_2.set_fixed_domain_mode(session.phase_fixed_domain)
        self.phase_panel_wall_1.set_viewport(session.phase_viewport_wall_1)
        self.phase_panel_wall_2.set_viewport(session.phase_viewport_wall_2)
        if self._selected_trajectory_id not in self._trajectory_seeds:
            self._selected_trajectory_id = next(
                iter(self._trajectory_seeds.keys()),
                None,
            )

        self._next_trajectory_id = (
            max(self._trajectory_seeds.keys(), default=0) + 1
        )
        self._rebuild_orbits()
        self.replay_controller.reset()
        self._reset_replay_views()
        self.update_view()

    def _autosave_session(self) -> None:
        if not self._config.autosave.enabled:
            return

        save_session(
            self._build_session(),
            self._autosave_path(),
        )

    def _restore_autosave_session(self) -> None:
        if not self._config.autosave.enabled:
            return

        autosave_path = self._autosave_path()
        if not autosave_path.exists():
            return

        session = load_session(autosave_path)
        self._apply_session(session)
        logger.info("Autosave restored: %s", autosave_path)

    def _autosave_path(self) -> Path:
        path = Path(self._config.autosave.path)
        if path.is_absolute():
            return path
        return Path(self._config_path).resolve().parent / path

    def _build_orbit(self, seed: TrajectorySeed) -> Orbit:
        return build_orbit(
            seed=seed,
            config=self._config.simulation,
            steps=self._config.simulation.n_phase_default,
        )

    def _build_geometry(self, orbit: Orbit) -> WedgeGeometry:
        return build_wedge_geometry(
            orbit=orbit,
            config=self._config.simulation,
            max_reflections=self._config.simulation.n_geom_default,
        )


def run_app(config: Config, config_path: str) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config, config_path)
    window.show()
    app.exec()
