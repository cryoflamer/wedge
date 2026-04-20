from __future__ import annotations

import math
import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QMainWindow,
    QScrollArea,
    QWidget,
)

from app.core.geometry_builder import build_wedge_geometry
from app.core.lyapunov import compute_finite_time_lyapunov
from app.core.orbit_builder import build_orbit
from app.models.config import Config
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.session import Session
from app.models.trajectory import TrajectorySeed
from app.services.config_loader import save_runtime_config
from app.services.data_export_service import export_orbit_data
from app.services.export_service import export_widget_bundle_png
from app.services.scan_sampler import generate_scan_points
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
        self._max_trajectory_count = 300

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
        self.controls_scroll = QScrollArea()
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.controls_scroll.setWidget(self.controls_panel)
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

        screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        width = min(self.width(), max(available.width() - 24, 1))
        height = min(self.height(), max(available.height() - 24, 1))
        if width != self.width() or height != self.height():
            self.resize(width, height)

        frame = self.frameGeometry()
        if self._window_position_restored:
            clamped_x = min(
                max(frame.x(), available.left()),
                max(available.right() - frame.width() + 1, available.left()),
            )
            clamped_y = min(
                max(frame.y(), available.top()),
                max(available.bottom() - frame.height() + 1, available.top()),
            )
            self.move(clamped_x, clamped_y)
            return

        frame.moveCenter(available.center())
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
        grid.addWidget(self.controls_scroll, 0, 2, 2, 1)

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
        self.controls_panel.export_mode_changed.connect(self._on_export_mode_changed)
        self.controls_panel.region_visibility_changed.connect(
            self._on_region_visibility_changed
        )
        self.controls_panel.branch_markers_changed.connect(
            self._on_branch_markers_changed
        )
        self.controls_panel.heatmap_settings_changed.connect(
            self._on_heatmap_settings_changed
        )
        self.controls_panel.compute_lyapunov_requested.connect(
            self._on_compute_lyapunov
        )
        self.controls_panel.export_data_requested.connect(self._on_export_data)
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
        self.controls_panel.scan_requested.connect(self._on_scan_requested)
        self.controls_panel.manual_seed_requested.connect(self._on_manual_seed_requested)
        self.replay_controller.state_changed.connect(self._on_replay_state_changed)

    def update_view(self) -> None:
        self.controls_panel.load_config(self._config)
        self.controls_panel.set_angle_units(self._angle_units)
        self.controls_panel.set_symmetric_mode(self._symmetric_mode)
        self.controls_panel.set_phase_view_mode(
            self.phase_panel_wall_1.is_fixed_domain_mode()
        )
        self.controls_panel.set_region_view_options(
            show_regions=self._config.view.show_regions,
            show_labels=self._config.view.show_region_labels,
            show_legend=self._config.view.show_region_legend,
        )
        self.controls_panel.set_branch_markers_enabled(
            self._config.view.show_branch_markers
        )
        self.controls_panel.set_heatmap_settings(
            show_heatmap=self._config.view.show_heatmap,
            mode=self._config.view.heatmap_mode,
            resolution=self._config.view.heatmap_resolution,
            normalization=self._config.view.heatmap_normalization,
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
                self._trajectory_selector_label(
                    seed=seed,
                    orbit=self._trajectory_orbits.get(seed.id),
                ),
                self._trajectory_tooltip_label(
                    seed=seed,
                    orbit=self._trajectory_orbits.get(seed.id),
                ),
                seed.color,
                seed.visible,
            )
            for seed in sorted(self._trajectory_seeds.values(), key=lambda item: item.id)
        ]
        self.controls_panel.set_trajectory_items(
            trajectory_items,
            self._selected_trajectory_id,
        )
        selected_orbit = (
            self._trajectory_orbits.get(self._selected_trajectory_id)
            if self._selected_trajectory_id is not None
            else None
        )
        if selected_orbit is None:
            self.controls_panel.set_lyapunov_status("not computed", 0, None)
        else:
            self.controls_panel.set_lyapunov_status(
                status=selected_orbit.lyapunov_status,
                steps_used=selected_orbit.lyapunov_steps_used,
                estimate=selected_orbit.lyapunov_estimate,
                reason=selected_orbit.lyapunov_invalid_reason,
                wall_divergence_count=selected_orbit.lyapunov_wall_divergence_count,
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
        trajectory_id = self._add_trajectory_seed(wall, d_value, tau_value)
        if trajectory_id is None:
            logger.info("Phase panel click ignored: trajectory limit reached")
            return

        logger.info(
            "Phase panel clicked: wall=%s d=%.6f tau=%.6f id=%s",
            wall,
            d_value,
            tau_value,
            trajectory_id,
        )
        self._autosave_session()
        self.update_view()

    def _on_manual_seed_requested(
        self,
        wall: int,
        d_value: float,
        tau_value: float,
    ) -> None:
        trajectory_id = self._add_trajectory_seed(wall, d_value, tau_value)
        if trajectory_id is None:
            logger.info("Manual seed ignored: trajectory limit reached")
            return

        logger.info(
            "Manual seed added: wall=%s d=%.6f tau=%.6f id=%s",
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

    def _on_export_mode_changed(self, mode: str) -> None:
        self._config.export.default_mode = mode

    def _on_region_visibility_changed(
        self,
        show_regions: bool,
        show_labels: bool,
        show_legend: bool,
    ) -> None:
        self._config.view.show_regions = show_regions
        self._config.view.show_region_labels = show_labels
        self._config.view.show_region_legend = show_legend
        self.update_view()

    def _on_branch_markers_changed(self, enabled: bool) -> None:
        self._config.view.show_branch_markers = enabled
        self.update_view()

    def _on_heatmap_settings_changed(
        self,
        enabled: bool,
        mode: str,
        resolution: int,
        normalization: str,
    ) -> None:
        self._config.view.show_heatmap = enabled
        self._config.view.heatmap_mode = mode
        self._config.view.heatmap_resolution = resolution
        self._config.view.heatmap_normalization = normalization
        self.update_view()

    def _on_compute_lyapunov(self) -> None:
        if self._selected_trajectory_id is None:
            self.controls_panel.set_lyapunov_status("failed", 0, None, "no_selection")
            return

        seed = self._trajectory_seeds.get(self._selected_trajectory_id)
        orbit = self._trajectory_orbits.get(self._selected_trajectory_id)
        if seed is None or orbit is None:
            self.controls_panel.set_lyapunov_status("failed", 0, None, "missing_orbit")
            return

        result = compute_finite_time_lyapunov(
            seed=seed,
            simulation_config=self._config.simulation,
            lyapunov_config=self._config.lyapunov,
        )
        orbit.lyapunov_estimate = result.estimate
        orbit.lyapunov_running = result.running_estimate
        orbit.lyapunov_valid = result.status in ("done", "partial")
        orbit.lyapunov_invalid_reason = result.reason
        orbit.lyapunov_status = result.status
        orbit.lyapunov_steps_used = result.steps_used
        orbit.lyapunov_wall_divergence_count = result.wall_divergence_count
        self.update_view()
        logger.info(
            "Lyapunov computed: id=%s status=%s steps=%s estimate=%s",
            self._selected_trajectory_id,
            result.status,
            result.steps_used,
            result.estimate,
        )

    def _on_export_data(self) -> None:
        if self._selected_trajectory_id is None:
            logger.info("Data export skipped: no selected trajectory")
            return

        orbit = self._trajectory_orbits.get(self._selected_trajectory_id)
        if orbit is None:
            logger.info("Data export skipped: selected orbit is missing")
            return

        export_format = self.controls_panel.data_export_format()
        suggested_name = f"wedge_trajectory_{self._selected_trajectory_id}.{export_format}"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Data",
            suggested_name,
            "CSV Files (*.csv);;JSON Files (*.json)",
        )
        if not output_path:
            return

        exported_path = export_orbit_data(
            orbit=orbit,
            output_path=output_path,
            export_format=export_format,
        )
        logger.info(
            "Trajectory data exported: id=%s format=%s path=%s",
            self._selected_trajectory_id,
            export_format,
            exported_path,
        )

    def _on_parameters_changed(
        self,
        alpha: float,
        beta: float,
        n_phase: int,
        n_geom: int,
    ) -> None:
        normalized_n_phase = self._normalized_phase_steps(n_phase, n_geom)
        self._config.simulation.alpha = alpha
        self._config.simulation.beta = beta
        self._config.simulation.n_phase_default = normalized_n_phase
        self._config.simulation.n_geom_default = n_geom
        self._rebuild_orbits()
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info(
            "Parameters updated: alpha=%.6f beta=%.6f n_phase=%s n_geom=%s",
            alpha,
            beta,
            normalized_n_phase,
            n_geom,
        )

    def _on_scan_requested(
        self,
        mode: str,
        count: int,
        wall: int,
        d_min: float,
        d_max: float,
        tau_min: float,
        tau_max: float,
    ) -> None:
        if wall not in (1, 2):
            logger.info("Scan skipped: invalid wall=%s", wall)
            return
        if count <= 0:
            logger.info("Scan skipped: non-positive count=%s", count)
            return
        if d_min >= d_max or tau_min >= tau_max:
            logger.info("Scan skipped: invalid bounds")
            return

        capacity = max(self._max_trajectory_count - len(self._trajectory_seeds), 0)
        if capacity <= 0:
            logger.info("Scan skipped: trajectory limit reached")
            return

        generated_points = generate_scan_points(
            mode=mode,
            count=min(count, capacity),
            d_min=d_min,
            d_max=d_max,
            tau_min=tau_min,
            tau_max=tau_max,
        )

        added = 0
        for d_value, tau_value in generated_points:
            if (1.0 - d_value) ** 2 + tau_value * tau_value >= 1.0:
                continue

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
            added += 1

        if added == 0:
            logger.info("Scan finished: no valid seeds inside domain")
            return

        if self._selected_trajectory_id is None:
            self._selected_trajectory_id = next(iter(self._trajectory_seeds.keys()), None)

        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info(
            "Scan finished: mode=%s wall=%s requested=%s added=%s",
            mode,
            wall,
            count,
            added,
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
                self._selected_trajectory_id: active_frame - 1
            }
        elif mode == "all":
            self._active_phase_frames = {
                trajectory_id: active_frame
                for trajectory_id in self._trajectory_orbits.keys()
            }
            self._active_segment_indices = {
                trajectory_id: active_frame - 1
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
            angle_units=self._angle_units,
            symmetric_mode=self._symmetric_mode,
            export_mode=self.controls_panel.export_mode(),
            phase_fixed_domain=self.phase_panel_wall_1.is_fixed_domain_mode(),
            phase_viewport_wall_1=self.phase_panel_wall_1.viewport(),
            phase_viewport_wall_2=self.phase_panel_wall_2.viewport(),
        )

    def _apply_session(
        self,
        session: Session,
        restore_simulation_parameters: bool = True,
    ) -> None:
        if restore_simulation_parameters:
            self._config.simulation.alpha = session.alpha
            self._config.simulation.beta = session.beta
        self._config.simulation.n_geom_default = session.n_geom
        self._config.simulation.n_phase_default = self._normalized_phase_steps(
            session.n_phase,
            session.n_geom,
        )
        self._config.replay.delay_ms = session.replay_delay_ms
        self._config.replay.selected_only_by_default = session.replay_selected_only
        self._angle_units = session.angle_units
        self._symmetric_mode = session.symmetric_mode
        self._config.export.default_mode = session.export_mode

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
        logger.info(
            "Session applied: runtime alpha=%.10f beta=%.10f",
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )

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
        self._apply_session(
            session,
            restore_simulation_parameters=(
                self._config.autosave.restore_simulation_parameters
            ),
        )
        logger.info(
            "Autosave restored: %s runtime alpha=%.10f beta=%.10f",
            autosave_path,
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )

    def _autosave_path(self) -> Path:
        path = Path(self._config.autosave.path)
        if path.is_absolute():
            return path
        return Path(self._config_path).resolve().parent / path

    def _build_orbit(self, seed: TrajectorySeed) -> Orbit:
        return build_orbit(
            seed=seed,
            config=self._config.simulation,
            steps=self._normalized_phase_steps(
                self._config.simulation.n_phase_default,
                self._config.simulation.n_geom_default,
            ),
        )

    def _build_geometry(self, orbit: Orbit) -> WedgeGeometry:
        return build_wedge_geometry(
            orbit=orbit,
            config=self._config.simulation,
            max_reflections=self._config.simulation.n_geom_default,
        )

    def _normalized_phase_steps(self, n_phase: int, n_geom: int) -> int:
        return max(n_phase, n_geom + 1)

    def _trajectory_selector_label(
        self,
        seed: TrajectorySeed,
        orbit: Orbit | None,
    ) -> str:
        invalid_suffix = " [invalid]" if orbit is not None and not orbit.valid else ""
        return (
            f"#{seed.id} | wall={seed.wall_start} | "
            f"d={seed.d0:.3f} | tau={seed.tau0:.3f}{invalid_suffix}"
        )

    def _trajectory_tooltip_label(
        self,
        seed: TrajectorySeed,
        orbit: Orbit | None,
    ) -> str:
        invalid_suffix = " [invalid]" if orbit is not None and not orbit.valid else ""
        status = "visible" if seed.visible else "hidden"
        reason = (
            f"\nreason: {orbit.invalid_reason}"
            if orbit is not None and orbit.invalid_reason
            else ""
        )
        return (
            f"id: {seed.id}\n"
            f"wall: {seed.wall_start}\n"
            f"d0: {seed.d0:.6f}\n"
            f"tau0: {seed.tau0:.6f}\n"
            f"status: {status}{invalid_suffix}{reason}"
        )

    def _add_trajectory_seed(
        self,
        wall: int,
        d_value: float,
        tau_value: float,
    ) -> int | None:
        if len(self._trajectory_seeds) >= self._max_trajectory_count:
            return None

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
        return trajectory_id


def run_app(config: Config, config_path: str) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config, config_path)
    window.show()
    app.exec()
