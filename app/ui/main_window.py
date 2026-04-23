from __future__ import annotations

from collections import deque
import math
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, QThread, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QWidget,
)

from app.core.geometry_builder import build_wedge_geometry
from app.core.orbit_builder import build_orbit
from app.core.point_constraints import ActivePointConstraint, project_point_to_constraint
from app.models.config import Config
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.region import RegionStyle
from app.models.session import Session
from app.models.scene_item import SceneItemDescription, is_boundary_scene_item
from app.models.trajectory import TrajectorySeed
from app.services.config_loader import save_runtime_config
from app.services.background_jobs import (
    JobFinished,
    JobProgress,
    LyapunovResultPayload,
    OrbitBuildWorker,
    OrbitPartialResult,
)
from app.services.data_export_service import export_orbit_data
from app.services.export_service import export_widget_bundle_png
from app.services.session_service import load_session, save_session
from app.ui.angle_panel import AnglePanel
from app.ui.controls_panel import ControlsPanel
from app.ui.phase_panel import PhasePanel
from app.ui.replay_controller import ReplayController
from app.ui.tooltips import apply_tooltip
from app.ui.wedge_panel import WedgePanel

logger = logging.getLogger(__name__)


class SceneItemCreateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Item")
        self._name_edit = QLineEdit()
        self._alias_edit = QLineEdit()

        layout = QFormLayout(self)
        layout.addRow("Name", self._name_edit)
        layout.addRow("Alias", self._alias_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[str, str]:
        return self._name_edit.text().strip(), self._alias_edit.text().strip()


class MainWindow(QMainWindow):
    def __init__(self, config: Config, config_path: str) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path
        self._window_position_restored = False
        self._next_trajectory_id = 1
        self._selected_trajectory_id: int | None = None
        self._selected_scene_item_name: str | None = None
        self._scene_dirty = False
        self._angle_units = "rad"
        self._base_angle_constraint_name = config.view.active_angle_constraint
        self._active_angle_constraint_name = config.view.active_angle_constraint
        self._symmetric_mode = self._constraint_name_is_symmetry(
            self._active_angle_constraint_name
        )
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
        self._job_generation = 0
        self._current_job_thread: QThread | None = None
        self._current_job_worker: OrbitBuildWorker | None = None
        self._job_status_state = "idle"
        self._job_status_message = "Idle"
        self._job_last_percent = 0
        self._pending_partial_results: deque[OrbitPartialResult] = deque()
        self._pending_finished_payload: JobFinished | None = None
        self._active_job_payload: dict[str, object] | None = None
        self._paused_job_payloads: list[dict[str, object]] = []
        self._next_job_payload_id = 1
        self._autosave_restore_scheduled = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(50)
        self._autosave_timer.timeout.connect(self._autosave_session)

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
        self._cancel_job_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._cancel_job_shortcut.setContext(Qt.ApplicationShortcut)
        self._cancel_job_shortcut.activated.connect(self._on_cancel_shortcut)
        self.replay_controller = ReplayController(
            delay_ms=config.replay.delay_ms,
            parent=self,
        )
        self._partial_update_timer = QTimer(self)
        self._partial_update_timer.setSingleShot(True)
        self._partial_update_timer.setInterval(33)
        self._partial_update_timer.timeout.connect(self._flush_partial_updates)

        self._build_layout()
        self._build_status_bar()
        self._apply_tooltips()
        QApplication.instance().installEventFilter(self)
        self._connect_signals()
        self.update_view()

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
            self._schedule_autosave_restore()
            return

        frame.moveCenter(available.center())
        self.move(frame.topLeft())
        self._window_position_restored = True
        self._schedule_autosave_restore()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._scene_dirty:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setWindowTitle("Unsaved Changes")
            dialog.setText("You have unsaved region or boundary changes.")
            dialog.setInformativeText("Do you want to save them before closing?")
            save_button = dialog.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
            discard_button = dialog.addButton(
                "Discard",
                QMessageBox.ButtonRole.DestructiveRole,
            )
            cancel_button = dialog.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(save_button)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked == cancel_button:
                event.ignore()
                return
            if clicked == save_button:
                self._on_save_scene()
            elif clicked != discard_button:
                event.ignore()
                return
        self._cancel_current_job()
        self._config.window.width = self.width()
        self._config.window.height = self.height()
        self._config.window.x = self.x()
        self._config.window.y = self.y()
        self._autosave_session()
        save_runtime_config(
            self._config,
            self._config_path,
        )
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            logger.info(
                "Escape keyPressEvent received: job_active=%s",
                self._current_job_worker is not None,
            )
            self._cancel_current_job()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key_Escape
        ):
            logger.info(
                "Escape eventFilter received: watched=%s job_active=%s",
                type(watched).__name__,
                self._current_job_worker is not None,
            )
            self._cancel_current_job()
            event.accept()
            return True
        return super().eventFilter(watched, event)

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

    def _build_status_bar(self) -> None:
        self._status_label = QLabel("Idle")
        self._status_job_button = QPushButton("Cancel")
        self._status_job_button.clicked.connect(self._on_status_job_button_clicked)
        self._status_job_button.hide()
        self._status_jobs_selector = QComboBox()
        self._status_jobs_selector.setMinimumWidth(180)
        self._status_jobs_selector.hide()
        self._status_progress = QProgressBar()
        self._status_progress.setRange(0, 100)
        self._status_progress.setValue(0)
        self._status_progress.setTextVisible(True)
        self._status_progress.setMaximumWidth(220)
        self._status_progress.hide()
        self._status_fast_build = QCheckBox("Fast build")
        self._status_fast_build.setChecked(self._config.background.fast_build)
        self._status_fast_build.toggled.connect(self._on_fast_build_changed)
        self.statusBar().addWidget(self._status_label, 1)
        self.statusBar().addPermanentWidget(self._status_jobs_selector)
        self.statusBar().addPermanentWidget(self._status_job_button)
        self.statusBar().addPermanentWidget(self._status_progress)
        self.statusBar().addPermanentWidget(self._status_fast_build)

    def _apply_tooltips(self) -> None:
        apply_tooltip(self.phase_panel_wall_1, "phase_panel_wall_1")
        apply_tooltip(self.phase_panel_wall_2, "phase_panel_wall_2")
        apply_tooltip(self.wedge_panel, "wedge_panel")
        self.angle_panel.setToolTip("")
        self.angle_panel.setStatusTip("")
        apply_tooltip(self._status_label, "status_label")
        apply_tooltip(self._status_jobs_selector, "status_jobs_selector")
        apply_tooltip(self._status_progress, "status_progress")
        apply_tooltip(self._status_fast_build, "status_fast_build")
        self._sync_status_job_button_tooltip()

    def _connect_signals(self) -> None:
        self.phase_panel_wall_1.clicked.connect(self._on_phase_click)
        self.phase_panel_wall_2.clicked.connect(self._on_phase_click)
        self.phase_panel_wall_1.seed_drag_started.connect(
            self._on_seed_drag_started
        )
        self.phase_panel_wall_2.seed_drag_started.connect(
            self._on_seed_drag_started
        )
        self.phase_panel_wall_1.seed_selected.connect(self._on_trajectory_selected)
        self.phase_panel_wall_2.seed_selected.connect(self._on_trajectory_selected)
        self.phase_panel_wall_1.seed_drag_finished.connect(
            self._on_seed_drag_finished
        )
        self.phase_panel_wall_2.seed_drag_finished.connect(
            self._on_seed_drag_finished
        )
        self.phase_panel_wall_1.viewport_changed.connect(self._on_phase_viewport_changed)
        self.phase_panel_wall_2.viewport_changed.connect(self._on_phase_viewport_changed)
        self.angle_panel.point_selected.connect(self._on_angle_click)
        self.controls_panel.parameters_changed.connect(self._on_parameters_changed)
        self.controls_panel.angle_units_changed.connect(self._on_angle_units_changed)
        self.controls_panel.angle_constraint_mode_changed.connect(
            self._on_angle_constraint_mode_changed
        )
        self.controls_panel.angle_constraint_changed.connect(
            self._on_angle_constraint_changed
        )
        self.controls_panel.export_mode_changed.connect(self._on_export_mode_changed)
        self.controls_panel.phase_grid_visibility_changed.connect(
            self._on_phase_grid_visibility_changed
        )
        self.controls_panel.seed_markers_visibility_changed.connect(
            self._on_seed_markers_visibility_changed
        )
        self.controls_panel.stationary_point_visibility_changed.connect(
            self._on_stationary_point_visibility_changed
        )
        self.controls_panel.directrix_visibility_changed.connect(
            self._on_directrix_visibility_changed
        )
        self.controls_panel.region_visibility_changed.connect(
            self._on_region_visibility_changed
        )
        self.controls_panel.plot_labels_changed.connect(
            self._on_plot_labels_changed
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
        self.controls_panel.selected_trajectory_color_changed.connect(
            self._on_selected_trajectory_color_changed
        )
        self.controls_panel.save_scene_requested.connect(
            self._on_save_scene
        )
        self.controls_panel.scene_item_selected.connect(
            self._on_scene_item_selected
        )
        self.controls_panel.apply_scene_item_editor_requested.connect(
            self._on_apply_scene_item_editor
        )
        self.controls_panel.add_scene_item_requested.connect(
            self._on_add_scene_item_requested
        )
        self.controls_panel.delete_scene_item_requested.connect(
            self._on_delete_scene_item_requested
        )
        self.controls_panel.selected_seed_apply_requested.connect(
            self._on_selected_seed_apply
        )
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
        self._update_controls_config_view()
        self._update_trajectory_views()
        self._update_panel_views()
        self._update_status_view()

    def _update_selected_trajectory_view(self) -> None:
        selected_seed = (
            self._trajectory_seeds.get(self._selected_trajectory_id)
            if self._selected_trajectory_id is not None
            else None
        )
        self.controls_panel.set_selected_trajectory_id(
            self._selected_trajectory_id,
            selected_seed.color if selected_seed is not None else None,
        )
        self._update_selected_trajectory_controls()
        self._update_panel_views()
        self._update_status_view()

    def _update_controls_config_view(self) -> None:
        self.controls_panel.load_config(self._config)
        self.controls_panel.set_angle_units(self._angle_units)
        self.controls_panel.set_constraint_options(
            [
                (
                    item.name,
                    item.display_text,
                    item.constraint_type,
                )
                for item in sorted(self._config.constraints, key=lambda entry: entry.priority)
                if item.visible
            ],
            self._base_angle_constraint_name,
        )
        self.controls_panel.set_constraint_mode(
            "constraint" if self._active_angle_constraint_name is not None else "free"
        )
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
        if self._selected_scene_item_name not in {
            item.name for item in self._config.regions
        }:
            self._selected_scene_item_name = (
                self._config.regions[0].name if self._config.regions else None
            )
        self.controls_panel.set_scene_item_items(
            [
                (
                    item.name,
                    item.display_text,
                    item.relation or "",
                )
                for item in sorted(self._config.regions, key=lambda entry: entry.priority)
            ],
            self._selected_scene_item_name,
        )
        self.controls_panel.set_scene_item_editor_values(
            self._selected_scene_item_editor_values(),
            sync_sections=False,
        )
        self.angle_panel.set_angle_units(self._angle_units)
        self.angle_panel.set_regions(self._config.regions)
        self.angle_panel.set_constraints(self._config.constraints)
        self.angle_panel.set_active_constraint(self._resolved_angle_constraint())
        self.angle_panel.set_angles(
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )

    def _update_trajectory_views(self) -> None:
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
        self._update_selected_trajectory_controls()

    def _update_selected_trajectory_controls(self) -> None:
        selected_orbit = (
            self._trajectory_orbits.get(self._selected_trajectory_id)
            if self._selected_trajectory_id is not None
            else None
        )
        selected_seed = (
            self._trajectory_seeds.get(self._selected_trajectory_id)
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
        if selected_seed is None:
            self.controls_panel.set_selected_trajectory_summary(
                wall="-",
                d0="-",
                tau0="-",
                status="-",
                lyapunov="-",
            )
            self.controls_panel.set_selected_seed_fields("-", "-", "-")
        else:
            status_text = "pending"
            if selected_orbit is not None:
                status_text = "valid" if selected_orbit.valid else (
                    selected_orbit.invalid_reason or "invalid"
                )
            lyapunov_text = "-"
            if selected_orbit is not None:
                if selected_orbit.lyapunov_estimate is not None:
                    lyapunov_text = f"{selected_orbit.lyapunov_estimate:.6f}"
                else:
                    lyapunov_text = selected_orbit.lyapunov_status
            self.controls_panel.set_selected_trajectory_summary(
                wall=str(selected_seed.wall_start),
                d0=f"{selected_seed.d0:.6f}",
                tau0=f"{selected_seed.tau0:.6f}",
                status=status_text,
                lyapunov=lyapunov_text,
            )
            self.controls_panel.set_selected_seed_fields(
                d_value=f"{selected_seed.d0:.6f}",
                tau_value=f"{selected_seed.tau0:.6f}",
                wall=str(selected_seed.wall_start),
            )

    def _update_panel_views(self) -> None:
        self.phase_panel_wall_1.set_trajectories(
            self._trajectory_seeds,
            self._trajectory_orbits,
            self._selected_trajectory_id,
            self._active_phase_frames,
        )
        self.phase_panel_wall_1.set_stationary_point(
            self._stationary_phase_point(1)
        )
        self.phase_panel_wall_2.set_trajectories(
            self._trajectory_seeds,
            self._trajectory_orbits,
            self._selected_trajectory_id,
            self._active_phase_frames,
        )
        self.phase_panel_wall_2.set_stationary_point(
            self._stationary_phase_point(2)
        )
        self.wedge_panel.set_geometries(
            self._trajectory_seeds,
            self._trajectory_geometries,
            self._selected_trajectory_id,
            self._active_segment_indices,
        )

    def _update_status_view(self) -> None:
        blocker = QSignalBlocker(self._status_fast_build)
        self._status_fast_build.setChecked(self._config.background.fast_build)
        del blocker
        self._sync_status_job_button_tooltip()
        self.controls_panel.set_job_status(
            status=self._job_status_state,
            message=self._job_status_message,
            cancellable=self._current_job_worker is not None,
            resumable=bool(self._paused_job_payloads) and self._current_job_worker is None,
        )

    def _sync_status_job_button_tooltip(self) -> None:
        if self._status_job_button.text().strip().lower() == "resume":
            apply_tooltip(self._status_job_button, "status_job_button_resume")
            return
        apply_tooltip(self._status_job_button, "status_job_button_cancel")

    def _on_phase_click(self, wall: int, d_value: float, tau_value: float) -> None:
        trajectory_id = self._queue_single_seed_build(wall, d_value, tau_value)
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
        trajectory_id = self._queue_single_seed_build(wall, d_value, tau_value)
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

    def _on_seed_drag_started(self, trajectory_id: int) -> None:
        if trajectory_id != self._selected_trajectory_id:
            self._selected_trajectory_id = trajectory_id
            self._reset_replay_views()
            self.update_view()

    def _on_seed_drag_finished(
        self,
        trajectory_id: int,
        d_value: float,
        tau_value: float,
    ) -> None:
        seed = self._trajectory_seeds.get(trajectory_id)
        if seed is None:
            return

        seed.d0 = d_value
        seed.tau0 = tau_value
        self._selected_trajectory_id = trajectory_id
        self._reset_replay_views()
        self._trajectory_orbits[trajectory_id] = Orbit(trajectory_id=trajectory_id)
        self._trajectory_geometries[trajectory_id] = WedgeGeometry()
        self.update_view()
        self._start_single_seed_rebuild(
            seed,
            start_message=f"Rebuilding trajectory #{trajectory_id}...",
        )
        self._autosave_session()

    def _on_selected_seed_apply(
        self,
        d_value: float,
        tau_value: float,
    ) -> None:
        if self._selected_trajectory_id is None:
            return
        seed = self._trajectory_seeds.get(self._selected_trajectory_id)
        if seed is None:
            return

        projected_d, projected_tau = self._constrain_seed_to_domain(d_value, tau_value)
        seed.d0 = projected_d
        seed.tau0 = projected_tau
        self._reset_replay_views()
        self._trajectory_orbits[seed.id] = Orbit(trajectory_id=seed.id)
        self._trajectory_geometries[seed.id] = WedgeGeometry()
        self.update_view()
        self._start_single_seed_rebuild(
            seed,
            start_message=f"Rebuilding trajectory #{seed.id}...",
        )
        self._autosave_session()

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

    def _on_angle_constraint_mode_changed(self, mode: str) -> None:
        self._set_angle_constraint_mode(mode)

    def _on_angle_constraint_changed(self, name: str) -> None:
        self._base_angle_constraint_name = name
        if self._active_angle_constraint_name is None:
            self._config.view.active_angle_constraint = None
            self.update_view()
            return
        if (
            self._active_angle_constraint_name == name
            and self._config.view.active_angle_constraint == name
            and self._symmetric_mode == self._constraint_name_is_symmetry(name)
        ):
            self.update_view()
            return
        self._active_angle_constraint_name = name
        self._config.view.active_angle_constraint = name
        self._symmetric_mode = self._constraint_name_is_symmetry(name)
        self._project_angles_to_active_constraint()
        self._start_rebuild_job()
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info("Angle constraint changed: %s", name)

    def _set_angle_constraint_mode(self, mode: str) -> None:
        normalized_mode = mode.strip().lower() if mode.strip() else "free"
        previous_active = self._active_angle_constraint_name
        previous_symmetric = self._symmetric_mode
        if normalized_mode == "constraint":
            selected_name = (
                self.controls_panel.active_constraint_name()
                or self._base_angle_constraint_name
                or self._default_symmetry_constraint_name()
            )
            self._base_angle_constraint_name = selected_name
            self._active_angle_constraint_name = selected_name
        else:
            self._active_angle_constraint_name = None
        self._config.view.active_angle_constraint = self._active_angle_constraint_name
        self._symmetric_mode = self._constraint_name_is_symmetry(
            self._active_angle_constraint_name
        )
        if (
            previous_active == self._active_angle_constraint_name
            and previous_symmetric == self._symmetric_mode
        ):
            self.update_view()
            return
        self._project_angles_to_active_constraint()
        self._start_rebuild_job()
        self._reset_replay_views()
        self._autosave_session()
        self.update_view()
        logger.info(
            "Angle constraint mode changed: mode=%s active=%s",
            normalized_mode,
            self._active_angle_constraint_name,
        )

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

    def _on_plot_labels_changed(
        self,
        enabled: bool,
        mode: str,
        tooltip_mode: str,
    ) -> None:
        self._config.view.show_labels_on_plot = enabled
        self._config.view.plot_label_mode = mode.strip().lower() or "legend"
        self._config.view.tooltip_label_mode = (
            tooltip_mode.strip().lower() or "legend"
        )
        self.update_view()

    def _on_phase_grid_visibility_changed(
        self,
        show_grid: bool,
        show_minor_grid: bool,
    ) -> None:
        self._config.view.show_phase_grid = show_grid
        self._config.view.show_phase_minor_grid = show_minor_grid
        self._config.view.phase_grid.show_minor = show_minor_grid
        self.update_view()

    def _on_seed_markers_visibility_changed(self, enabled: bool) -> None:
        self._config.view.show_seed_markers = enabled
        self.update_view()

    def _on_stationary_point_visibility_changed(self, enabled: bool) -> None:
        self._config.view.show_stationary_point = enabled
        self.update_view()

    def _on_directrix_visibility_changed(self, enabled: bool) -> None:
        self._config.view.show_directrix = enabled
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

    def _on_fast_build_changed(self, enabled: bool) -> None:
        self._config.background.fast_build = enabled
        self._status_fast_build.setChecked(enabled)
        self._autosave_session()
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

        self._start_lyapunov_job(seed)

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
        self._start_rebuild_job()
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

        self._start_scan_job(
            mode=mode,
            count=min(count, capacity),
            wall=wall,
            d_min=d_min,
            d_max=d_max,
            tau_min=tau_min,
            tau_max=tau_max,
        )

    def _on_trajectory_selected(self, trajectory_id: int) -> None:
        if trajectory_id == self._selected_trajectory_id:
            return
        self._selected_trajectory_id = trajectory_id
        self._reset_replay_views()
        self._update_selected_trajectory_view()

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
        self._schedule_autosave()

    def _rebuild_orbits(self) -> None:
        self._trajectory_orbits = {
            trajectory_id: self._build_orbit(seed)
            for trajectory_id, seed in self._trajectory_seeds.items()
        }
        self._trajectory_geometries = {
            trajectory_id: self._build_geometry(orbit)
            for trajectory_id, orbit in self._trajectory_orbits.items()
        }

    def _cancel_current_job(self) -> None:
        logger.info(
            "Cancel requested: worker_active=%s thread_active=%s",
            self._current_job_worker is not None,
            self._current_job_thread is not None,
        )
        if self._current_job_worker is None:
            return
        worker = self._current_job_worker
        worker.cancel()
        if self._active_job_payload is not None:
            paused_payload = dict(self._active_job_payload)
            paused_payload["paused"] = True
            self._store_paused_job(paused_payload)
        self._job_generation += 1
        self._current_job_worker = None
        self._current_job_thread = None
        self._pending_partial_results.clear()
        self._partial_update_timer.stop()
        self._pending_finished_payload = None
        self._active_job_payload = None
        self._job_status_state = "cancelled"
        self._job_status_message = (
            f"Job interrupted at {self._job_last_percent}%"
        )
        self._status_label.setText(self._job_status_message)
        self._update_status_job_controls()
        self.controls_panel.set_job_status(
            status=self._job_status_state,
            message=self._job_status_message,
            cancellable=False,
            resumable=bool(self._paused_job_payloads),
        )

    def _on_cancel_shortcut(self) -> None:
        logger.info(
            "Escape shortcut activated: job_active=%s",
            self._current_job_worker is not None,
        )
        self._cancel_current_job()

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

    def _on_selected_trajectory_color_changed(self, color: str) -> None:
        if self._selected_trajectory_id is None:
            return
        seed = self._trajectory_seeds.get(self._selected_trajectory_id)
        if seed is None or seed.color == color:
            return
        seed.color = color
        self._autosave_session()
        self.update_view()
        logger.info(
            "Trajectory color changed: id=%s color=%s",
            self._selected_trajectory_id,
            color,
        )

    def _on_scene_item_selected(self, item_name: str) -> None:
        self._selected_scene_item_name = item_name
        self.controls_panel.set_scene_item_editor_values(
            self._selected_scene_item_editor_values()
        )

    def _mark_scene_dirty(self) -> None:
        self._scene_dirty = True
        self.controls_panel.set_scene_dirty(True)

    def _clear_scene_dirty(self) -> None:
        self._scene_dirty = False
        self.controls_panel.set_scene_dirty(False)

    def _on_save_scene(self) -> None:
        saved_path = save_runtime_config(
            self._config,
            self._config_path,
            persist_scene_items=True,
        )
        self._clear_scene_dirty()
        logger.info("Scene saved to config: path=%s", saved_path)

    def _selected_scene_item(self) -> SceneItemDescription | None:
        if self._selected_scene_item_name is None:
            return None
        return next(
            (
                item
                for item in self._config.regions
                if item.name == self._selected_scene_item_name
            ),
            None,
        )

    def _selected_scene_item_editor_values(
        self,
    ) -> tuple[str, str, str, str, str, str | None, bool, int, str, str, float, str] | None:
        item = self._selected_scene_item()
        if item is None:
            return None
        return (
            item.name,
            item.alias,
            item.display_text,
            item.legend_text,
            item.expression,
            item.relation,
            item.visible,
            item.priority,
            item.style.fill,
            item.style.border,
            item.style.line_width,
            item.style.line_style,
        )

    def _refresh_scene_item_views(
        self,
        selected_name: str | None = None,
    ) -> None:
        if selected_name is not None:
            self._selected_scene_item_name = selected_name
        self.controls_panel.set_scene_item_items(
            [
                (
                    item.name,
                    item.display_text,
                    item.relation or "",
                )
                for item in sorted(self._config.regions, key=lambda entry: entry.priority)
            ],
            self._selected_scene_item_name,
        )
        self.controls_panel.set_scene_item_editor_values(
            self._selected_scene_item_editor_values(),
            sync_sections=False,
        )
        self.angle_panel.set_regions(self._config.regions)
        self.controls_panel.set_scene_dirty(self._scene_dirty)

    def _create_scene_item_dialog(self) -> tuple[str, str] | None:
        dialog = SceneItemCreateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        name, alias = dialog.values()
        if not name:
            return None
        if not alias:
            alias = name
        return name, alias

    def _on_add_scene_item_requested(self) -> None:
        values = self._create_scene_item_dialog()
        if values is None:
            return
        name, alias = values
        self._config.regions.append(
            SceneItemDescription(
                name=name,
                alias=alias,
                display_text=alias,
                legend_text=alias,
                expression="0",
                relation="=",
                visible=True,
                priority=0,
                style=RegionStyle(
                    fill="#cccccc",
                    alpha=0.3,
                    hatch="",
                    border="#333333",
                    line_style="solid",
                    line_width=1.0,
                ),
            )
        )
        self._selected_scene_item_name = name
        self._refresh_scene_item_views(name)
        self._mark_scene_dirty()
        logger.info("Scene item created: name=%s alias=%s", name, alias)

    def _on_delete_scene_item_requested(self) -> None:
        selected_name = self.controls_panel.current_scene_item_name()
        if selected_name is None:
            return
        selected_index = next(
            (
                index
                for index, item in enumerate(self._config.regions)
                if item.name == selected_name
            ),
            -1,
        )
        if selected_index < 0:
            return
        item = self._config.regions[selected_index]
        item_type = "boundary" if is_boundary_scene_item(item) else "region"
        item_label = item.display_text or item.name
        answer = QMessageBox.question(
            self,
            "Delete Item",
            f"Delete {item_type} '{item_label}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._config.regions.pop(selected_index)
        remaining_items = sorted(self._config.regions, key=lambda entry: entry.priority)
        next_name: str | None = None
        if remaining_items:
            next_index = min(selected_index, len(remaining_items) - 1)
            next_name = remaining_items[next_index].name

        self._selected_scene_item_name = next_name
        self._refresh_scene_item_views(next_name)
        if next_name is None:
            self.controls_panel.set_scene_item_editor_values(None)
        self._mark_scene_dirty()
        logger.info("Scene item deleted: name=%s type=%s", item.name, item_type)

    def _on_apply_scene_item_editor(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        section_expanded = self.controls_panel.editor_section_state()
        item = self._selected_scene_item()
        if item is None:
            return
        previous_name = item.name
        item.alias = str(payload.get("alias", item.alias)).strip() or item.alias
        item.display_text = (
            str(payload.get("display_text", item.display_text)).strip()
            or item.display_text
        )
        item.legend_text = (
            str(payload.get("legend_text", item.legend_text)).strip()
            or item.legend_text
        )
        item.expression = str(payload.get("expression", item.expression)).strip()
        item.relation = str(payload.get("relation", item.relation or "=")).strip() or "="
        item.visible = bool(payload.get("visible", item.visible))
        try:
            item.priority = int(payload.get("priority", item.priority))
        except (TypeError, ValueError):
            pass
        item.style.fill = (
            str(payload.get("fill", item.style.fill)).strip()
            or item.style.fill
        )
        item.style.border = (
            str(payload.get("border", item.style.border)).strip()
            or item.style.border
        )
        try:
            item.style.line_width = float(
                payload.get("line_width", item.style.line_width)
            )
        except (TypeError, ValueError):
            pass
        item.style.line_style = "dashed" if (
            str(payload.get("line_style", item.style.line_style)).strip().lower()
            == "dashed"
        ) else "solid"
        item.compatibility_predicate = False
        self._selected_scene_item_name = item.name
        self._refresh_scene_item_views(self._selected_scene_item_name)
        self.controls_panel.set_scene_item_editor_values(
            self._selected_scene_item_editor_values(),
            sync_sections=False,
        )
        self.controls_panel.restore_editor_section_state(section_expanded)
        self._mark_scene_dirty()
        logger.info(
            "Scene item editor applied: previous_name=%s name=%s relation=%s",
            previous_name,
            item.name,
            item.relation,
        )

    def _on_clear_selected_trajectory(self) -> None:
        if self._selected_trajectory_id is None:
            return
        trajectory_id = self._selected_trajectory_id
        self._trajectory_seeds.pop(trajectory_id, None)
        self._trajectory_orbits.pop(trajectory_id, None)
        self._trajectory_geometries.pop(trajectory_id, None)
        self._prune_job_payloads_for_existing_trajectories()
        self._selected_trajectory_id = (
            next(iter(self._trajectory_seeds.keys()))
            if self._trajectory_seeds
            else None
        )
        self._reset_replay_views()
        self._schedule_autosave()
        self.update_view()
        logger.info("Trajectory cleared: id=%s", trajectory_id)

    def _on_clear_all_trajectories(self) -> None:
        self._cancel_current_job()
        self._trajectory_seeds.clear()
        self._trajectory_orbits.clear()
        self._trajectory_geometries.clear()
        self._paused_job_payloads.clear()
        self._active_job_payload = None
        self._selected_trajectory_id = None
        self._reset_replay_views()
        self._schedule_autosave()
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
            show_phase_grid=self._config.view.show_phase_grid,
            show_phase_minor_grid=self._config.view.show_phase_minor_grid,
            show_seed_markers=self._config.view.show_seed_markers,
            show_stationary_point=self._config.view.show_stationary_point,
            show_directrix=self._config.view.show_directrix,
            show_regions=self._config.view.show_regions,
            show_region_labels=self._config.view.show_region_labels,
            show_region_legend=self._config.view.show_region_legend,
            show_branch_markers=self._config.view.show_branch_markers,
            show_heatmap=self._config.view.show_heatmap,
            heatmap_mode=self._config.view.heatmap_mode,
            heatmap_resolution=self._config.view.heatmap_resolution,
            heatmap_normalization=self._config.view.heatmap_normalization,
            active_angle_constraint=self._active_angle_constraint_name,
            fast_build=self._config.background.fast_build,
            phase_viewport_wall_1=self.phase_panel_wall_1.viewport(),
            phase_viewport_wall_2=self.phase_panel_wall_2.viewport(),
        )

    def _apply_session_state(
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
        self._config.export.default_mode = session.export_mode
        self._config.view.show_phase_grid = session.show_phase_grid
        self._config.view.show_phase_minor_grid = session.show_phase_minor_grid
        self._config.view.phase_grid.show_minor = session.show_phase_minor_grid
        self._config.view.show_seed_markers = session.show_seed_markers
        self._config.view.show_stationary_point = session.show_stationary_point
        self._config.view.show_directrix = session.show_directrix
        self._config.view.show_regions = session.show_regions
        self._config.view.show_region_labels = session.show_region_labels
        self._config.view.show_region_legend = session.show_region_legend
        self._config.view.show_branch_markers = session.show_branch_markers
        self._config.view.show_heatmap = session.show_heatmap
        self._config.view.heatmap_mode = session.heatmap_mode
        self._config.view.heatmap_resolution = session.heatmap_resolution
        self._config.view.heatmap_normalization = session.heatmap_normalization
        restored_constraint = session.active_angle_constraint
        if restored_constraint is None and session.symmetric_mode:
            restored_constraint = self._default_symmetry_constraint_name()
        self._base_angle_constraint_name = restored_constraint
        self._active_angle_constraint_name = restored_constraint
        self._config.view.active_angle_constraint = restored_constraint
        self._symmetric_mode = self._constraint_name_is_symmetry(
            self._active_angle_constraint_name
        )
        self._config.background.fast_build = session.fast_build

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

    def _default_symmetry_constraint_name(self) -> str | None:
        for constraint in sorted(
            self._config.constraints,
            key=lambda item: item.priority,
        ):
            if (
                constraint.visible
                and constraint.constraint_type.strip().lower() == "symmetry"
            ):
                return constraint.name
        return None

    def _constraint_name_is_symmetry(self, name: str | None) -> bool:
        if name is None:
            return False
        constraint = next(
            (item for item in self._config.constraints if item.name == name),
            None,
        )
        if constraint is None:
            return False
        return constraint.constraint_type.strip().lower() == "symmetry"

    def _resolved_angle_constraint(self) -> ActivePointConstraint | None:
        if self._active_angle_constraint_name is None:
            return None

        constraint = next(
            (
                item
                for item in self._config.constraints
                if item.name == self._active_angle_constraint_name
                and item.visible
            ),
            None,
        )
        if constraint is None:
            return None

        kind = constraint.constraint_type.strip().lower()
        if kind == "symmetry":
            return ActivePointConstraint(
                kind="symmetry",
                region_name=constraint.name,
            )
        if kind == "boundary" and constraint.target:
            return ActivePointConstraint(
                kind="boundary",
                region_name=constraint.target,
            )
        return None

    def _project_angles_to_active_constraint(self) -> None:
        constraint = self.angle_panel.hydrated_constraint(
            self._resolved_angle_constraint()
        )
        alpha, beta = project_point_to_constraint(
            self._config.simulation.alpha,
            self._config.simulation.beta,
            constraint,
        )
        self._config.simulation.alpha = alpha
        self._config.simulation.beta = beta

    def _apply_session(
        self,
        session: Session,
        restore_simulation_parameters: bool = True,
    ) -> None:
        self._apply_session_state(
            session,
            restore_simulation_parameters=restore_simulation_parameters,
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
        self._apply_session_state(
            session,
            restore_simulation_parameters=(
                self._config.autosave.restore_simulation_parameters
            ),
        )
        self._trajectory_orbits = {
            trajectory_id: Orbit(trajectory_id=trajectory_id)
            for trajectory_id in self._trajectory_seeds
        }
        self._trajectory_geometries = {
            trajectory_id: WedgeGeometry()
            for trajectory_id in self._trajectory_seeds
        }
        self.replay_controller.reset()
        self._reset_replay_views()
        self.update_view()
        if self._trajectory_seeds:
            self._start_rebuild_job(
                job_message="Restoring autosave session...",
            )
        logger.info(
            "Autosave restored: %s runtime alpha=%.10f beta=%.10f",
            autosave_path,
            self._config.simulation.alpha,
            self._config.simulation.beta,
        )

    def _schedule_autosave_restore(self) -> None:
        if self._autosave_restore_scheduled:
            return
        self._autosave_restore_scheduled = True
        QTimer.singleShot(0, self._restore_autosave_session)

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

    def _stationary_phase_point(
        self,
        wall: int,
    ) -> tuple[float, float] | None:
        alpha = self._config.simulation.alpha
        beta = self._config.simulation.beta
        own_angle = alpha if wall == 1 else beta
        other_angle = beta if wall == 1 else alpha
        denominator = (
            math.cos(2.0 * (own_angle - other_angle))
            - 3.0 * (math.cos(2.0 * own_angle) + math.cos(2.0 * other_angle))
            + 5.0
        )
        if abs(denominator) <= self._config.simulation.eps:
            return None

        d_value = 8.0 * (math.sin(other_angle) ** 2) / denominator
        tau_value = 0.0
        if not math.isfinite(d_value) or d_value <= self._config.simulation.eps:
            return None
        if (1.0 - d_value) ** 2 + tau_value**2 >= 1.0:
            return None
        return d_value, tau_value

    def _normalized_phase_steps(self, n_phase: int, n_geom: int) -> int:
        return max(n_phase, n_geom + 1)

    def _constrain_seed_to_domain(
        self,
        d_value: float,
        tau_value: float,
    ) -> tuple[float, float]:
        if (1.0 - d_value) ** 2 + tau_value**2 < 1.0:
            return d_value, tau_value

        dx = d_value - 1.0
        norm = math.hypot(dx, tau_value)
        if norm <= 1.0e-12:
            return 1.0, 0.0

        radius = 1.0 - 1.0e-6
        scale = radius / norm
        return 1.0 + dx * scale, tau_value * scale

    def _trajectory_selector_label(
        self,
        seed: TrajectorySeed,
        orbit: Orbit | None,
    ) -> str:
        del seed, orbit
        return ""

    def _trajectory_tooltip_label(
        self,
        seed: TrajectorySeed,
        orbit: Orbit | None,
    ) -> str:
        invalid_suffix = " [invalid]" if orbit is not None and not orbit.valid else ""
        status = "visible" if seed.visible else "hidden"
        steps_built = orbit.completed_steps if orbit is not None else 0
        point_count = len(orbit.points) if orbit is not None else 0
        reason = (
            f"\nreason: {orbit.invalid_reason}"
            if orbit is not None and orbit.invalid_reason
            else ""
        )
        return (
            f"id: {seed.id}\n"
            f"wall: {seed.wall_start}\n"
            f"d0: {seed.d0:.6f}\n"
            f"τ0: {seed.tau0:.6f}\n"
            f"steps built: {steps_built}\n"
            f"points: {point_count}\n"
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

    def _queue_single_seed_build(self, wall: int, d_value: float, tau_value: float) -> int | None:
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
        self._trajectory_orbits[trajectory_id] = Orbit(trajectory_id=trajectory_id)
        self._trajectory_geometries[trajectory_id] = WedgeGeometry()
        if self._selected_trajectory_id is None:
            self._selected_trajectory_id = trajectory_id
        self._reset_replay_views()
        self.update_view()
        self._start_single_seed_rebuild(
            seed,
            start_message=f"Building trajectory #{seed.id}",
        )
        return trajectory_id

    def _start_single_seed_rebuild(
        self,
        seed: TrajectorySeed,
        start_message: str,
    ) -> None:
        self._start_worker(
            OrbitBuildWorker(
                generation_id=self._next_generation_id(),
                job_kind="single_build",
                simulation_config=self._config.simulation,
                max_reflections=self._config.simulation.n_geom_default,
                phase_steps=self._normalized_phase_steps(
                    self._config.simulation.n_phase_default,
                    self._config.simulation.n_geom_default,
                ),
                chunk_size=self._config.background.build_chunk_size,
                seeds=[seed],
                existing_orbits={seed.id: self._trajectory_orbits.get(seed.id, Orbit(trajectory_id=seed.id))},
            ),
            start_message=start_message,
            resumable_payload={
                "job_kind": "single_build",
                "seeds": [seed],
                "start_message": start_message,
                "title": f"Trajectory #{seed.id}",
            },
        )

    def _start_rebuild_job(self, job_message: str = "Starting rebuild...") -> None:
        self._trajectory_orbits = {}
        self._trajectory_geometries = {}
        self.update_view()
        seeds = sorted(self._trajectory_seeds.values(), key=lambda item: item.id)
        self._start_worker(
            OrbitBuildWorker(
                generation_id=self._next_generation_id(),
                job_kind="rebuild",
                simulation_config=self._config.simulation,
                max_reflections=self._config.simulation.n_geom_default,
                phase_steps=self._normalized_phase_steps(
                    self._config.simulation.n_phase_default,
                    self._config.simulation.n_geom_default,
                ),
                chunk_size=self._config.background.build_chunk_size,
                seeds=seeds,
            ),
            start_message=job_message,
            resumable_payload={
                "job_kind": "rebuild",
                "seeds": list(seeds),
                "start_message": job_message,
                "title": job_message,
            },
        )

    def _start_scan_job(
        self,
        mode: str,
        count: int,
        wall: int,
        d_min: float,
        d_max: float,
        tau_min: float,
        tau_max: float,
    ) -> None:
        self._start_worker(
            OrbitBuildWorker(
                generation_id=self._next_generation_id(),
                job_kind="scan",
                simulation_config=self._config.simulation,
                max_reflections=self._config.simulation.n_geom_default,
                phase_steps=self._normalized_phase_steps(
                    self._config.simulation.n_phase_default,
                    self._config.simulation.n_geom_default,
                ),
                chunk_size=self._config.background.build_chunk_size,
                scan_mode=mode,
                scan_count=count,
                scan_wall=wall,
                scan_d_min=d_min,
                scan_d_max=d_max,
                scan_tau_min=tau_min,
                scan_tau_max=tau_max,
                next_trajectory_id=self._next_trajectory_id,
                palette=self._palette,
                max_trajectory_count=max(self._max_trajectory_count - len(self._trajectory_seeds), 0),
            )
        )

    def _start_lyapunov_job(self, seed: TrajectorySeed) -> None:
        self._start_worker(
            OrbitBuildWorker(
                generation_id=self._next_generation_id(),
                job_kind="lyapunov",
                simulation_config=self._config.simulation,
                max_reflections=self._config.simulation.n_geom_default,
                phase_steps=self._normalized_phase_steps(
                    self._config.simulation.n_phase_default,
                    self._config.simulation.n_geom_default,
                ),
                chunk_size=self._config.background.build_chunk_size,
                lyapunov_seed=seed,
                lyapunov_config=self._config.lyapunov,
            )
        )

    def _next_generation_id(self) -> int:
        self._job_generation += 1
        return self._job_generation

    def _start_worker(
        self,
        worker: OrbitBuildWorker,
        start_message: str = "Starting background job...",
        resumable_payload: dict[str, object] | None = None,
    ) -> None:
        self._cancel_current_job()
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_job_progress)
        worker.partial_result.connect(self._on_job_partial_result)
        worker.lyapunov_result.connect(self._on_lyapunov_result)
        worker.finished.connect(self._on_job_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._current_job_thread = thread
        self._current_job_worker = worker
        if resumable_payload is not None:
            payload = dict(resumable_payload)
            payload.setdefault("job_id", self._next_job_payload_id)
            if payload["job_id"] == self._next_job_payload_id:
                self._next_job_payload_id += 1
            payload["progress_percent"] = 0
            payload["message"] = start_message
            self._active_job_payload = payload
        else:
            self._active_job_payload = None
        self._set_job_progress(
            JobProgress(
                generation_id=self._job_generation,
                job_kind="start",
                status="running",
                current=0,
                total=0,
                message=start_message,
            )
        )
        thread.start()

    def _on_job_progress(self, progress: object) -> None:
        if not isinstance(progress, JobProgress):
            return
        if progress.generation_id != self._job_generation:
            return
        if progress.job_kind in ("single_build", "rebuild", "scan"):
            if progress.status in ("running", "partial"):
                self._job_status_state = progress.status
                self._job_status_message = (
                    f"{progress.message} | Press Esc to cancel"
                )
                self._status_label.setText(self._job_status_message)
                self._status_progress.setVisible(True)
                self.controls_panel.set_job_status(
                    status=self._job_status_state,
                    message=self._job_status_message,
                    cancellable=self._current_job_worker is not None,
                    resumable=bool(self._paused_job_payloads) and self._current_job_worker is None,
                )
            return
        self._set_job_progress(progress)

    def _set_job_progress(self, progress: JobProgress) -> None:
        total = max(progress.total, 0)
        current = min(max(progress.current, 0), total) if total > 0 else 0
        percent = int((current / total) * 100.0) if total > 0 else 0
        self._job_status_state = progress.status
        if progress.status in ("running", "partial"):
            self._job_last_percent = percent
        if self._active_job_payload is not None:
            self._active_job_payload["progress_percent"] = percent
            self._active_job_payload["message"] = progress.message
        if progress.status in ("running", "partial"):
            self._job_status_message = f"{progress.message} | Press Esc to cancel"
        else:
            self._job_status_message = progress.message
        self._status_label.setText(self._job_status_message)
        self._status_progress.setValue(percent)
        self._update_status_job_controls()
        self.controls_panel.set_job_status(
            status=self._job_status_state,
            message=self._job_status_message,
            cancellable=self._current_job_worker is not None and progress.status in ("running", "partial"),
            resumable=bool(self._paused_job_payloads) and self._current_job_worker is None,
        )

    def _on_job_partial_result(self, payload: object) -> None:
        if not isinstance(payload, OrbitPartialResult):
            return
        if payload.generation_id != self._job_generation:
            return
        if self._config.background.fast_build:
            self._apply_partial_payload(payload)
            self._set_job_progress(
                JobProgress(
                    generation_id=payload.generation_id,
                    job_kind="display",
                    status="running",
                    current=payload.current,
                    total=payload.total,
                    message=payload.message,
                )
            )
            return
        self._pending_partial_results.append(payload)
        if not self._partial_update_timer.isActive():
            self._partial_update_timer.start()

    def _flush_partial_updates(self) -> None:
        if not self._pending_partial_results:
            if self._pending_finished_payload is not None:
                self._finalize_finished_job(self._pending_finished_payload)
                self._pending_finished_payload = None
            return
        payload = self._pending_partial_results.popleft()
        self._apply_partial_payload(payload)
        self._set_job_progress(
            JobProgress(
                generation_id=payload.generation_id,
                job_kind="display",
                status="partial" if self._pending_partial_results else "running",
                current=payload.current,
                total=payload.total,
                message=payload.message,
            )
        )
        self._update_trajectory_views()
        self._update_panel_views()
        self._update_status_view()
        if self._pending_partial_results:
            self._partial_update_timer.start()
        elif self._pending_finished_payload is not None:
            self._finalize_finished_job(self._pending_finished_payload)
            self._pending_finished_payload = None

    def _apply_partial_payload(self, payload: OrbitPartialResult) -> None:
        self._trajectory_seeds[payload.trajectory_id] = payload.seed
        self._trajectory_orbits[payload.trajectory_id] = payload.orbit
        self._trajectory_geometries[payload.trajectory_id] = payload.geometry
        if self._selected_trajectory_id is None:
            self._selected_trajectory_id = payload.trajectory_id
        self._next_trajectory_id = max(
            self._next_trajectory_id,
            payload.trajectory_id + 1,
        )

    def _on_lyapunov_result(self, payload: object) -> None:
        if not isinstance(payload, LyapunovResultPayload):
            return
        if payload.generation_id != self._job_generation:
            return
        orbit = self._trajectory_orbits.get(payload.trajectory_id)
        if orbit is None:
            return
        orbit.lyapunov_estimate = payload.estimate
        orbit.lyapunov_running = payload.running_estimate
        orbit.lyapunov_valid = payload.status in ("done", "partial")
        orbit.lyapunov_invalid_reason = payload.reason
        orbit.lyapunov_status = payload.status
        orbit.lyapunov_steps_used = payload.steps_used
        orbit.lyapunov_wall_divergence_count = payload.wall_divergence_count
        self.update_view()

    def _on_job_finished(self, payload: object) -> None:
        if not isinstance(payload, JobFinished):
            return
        if payload.generation_id != self._job_generation:
            return
        if self._config.background.fast_build:
            self._finalize_finished_job(payload)
            return
        if self._pending_partial_results:
            self._pending_finished_payload = payload
            if not self._partial_update_timer.isActive():
                self._partial_update_timer.start()
            return
        self._finalize_finished_job(payload)

    def _finalize_finished_job(self, payload: JobFinished) -> None:
        self._job_status_state = payload.status
        if payload.status == "cancelled":
            self._job_status_message = (
                f"{payload.message} at {self._job_last_percent}%"
            )
        else:
            self._job_status_message = payload.message
        self._status_label.setText(self._job_status_message)
        self._status_progress.setValue(100 if payload.status == "done" else 0)
        self._active_job_payload = None
        self._current_job_worker = None
        self._current_job_thread = None
        self._update_status_job_controls()
        self.controls_panel.set_job_status(
            status=self._job_status_state,
            message=self._job_status_message,
            cancellable=False,
            resumable=bool(self._paused_job_payloads),
        )
        self._schedule_autosave()
        self._update_trajectory_views()
        self._update_panel_views()
        self._update_status_view()

    def _store_paused_job(self, payload: dict[str, object]) -> None:
        job_id = int(payload.get("job_id", 0))
        self._paused_job_payloads = [
            item for item in self._paused_job_payloads
            if int(item.get("job_id", -1)) != job_id
        ]
        self._paused_job_payloads.append(payload)

    def _latest_paused_job(self) -> dict[str, object] | None:
        if not self._paused_job_payloads:
            return None
        return self._paused_job_payloads[-1]

    def _prune_job_payloads_for_existing_trajectories(self) -> None:
        existing_ids = set(self._trajectory_seeds.keys())
        filtered_payloads: list[dict[str, object]] = []
        for payload in self._paused_job_payloads:
            seeds = payload.get("seeds")
            if not isinstance(seeds, list):
                continue
            filtered_seeds = [
                seed for seed in seeds
                if getattr(seed, "id", None) in existing_ids
            ]
            if not filtered_seeds:
                continue
            next_payload = dict(payload)
            next_payload["seeds"] = filtered_seeds
            filtered_payloads.append(next_payload)
        self._paused_job_payloads = filtered_payloads

    def _update_status_job_controls(self) -> None:
        running = self._current_job_worker is not None
        paused_count = len(self._paused_job_payloads)
        if running:
            self._status_job_button.show()
            self._status_job_button.setText("Cancel")
            self._status_progress.setVisible(True)
            self._status_jobs_selector.hide()
            return
        paused_payload = self._latest_paused_job()
        if paused_payload is None:
            self._status_job_button.hide()
            self._status_progress.setVisible(False)
            self._status_jobs_selector.hide()
            return
        self._status_job_button.show()
        percent = int(paused_payload.get("progress_percent", 0))
        self._status_progress.setVisible(True)
        self._status_progress.setValue(percent)
        title = str(paused_payload.get("title", "Paused job"))
        self._job_status_state = "paused"
        self._job_status_message = (
            f"{title} paused at {percent}%"
            if paused_count == 1
            else f"{paused_count} paused jobs"
        )
        self._status_label.setText(self._job_status_message)
        self._status_job_button.setText("Resume")
        if paused_count > 1:
            blocker = QSignalBlocker(self._status_jobs_selector)
            current_job_id = self._status_jobs_selector.currentData()
            self._status_jobs_selector.clear()
            selected_index = 0
            for index, payload in enumerate(self._paused_job_payloads):
                item_title = str(payload.get("title", "Paused job"))
                item_percent = int(payload.get("progress_percent", 0))
                job_id = int(payload.get("job_id", index))
                self._status_jobs_selector.addItem(
                    f"{item_title} ({item_percent}%)",
                    job_id,
                )
                if current_job_id == job_id:
                    selected_index = index
            self._status_jobs_selector.setCurrentIndex(selected_index)
            del blocker
            self._status_jobs_selector.show()
        else:
            self._status_jobs_selector.hide()

    def _on_status_job_button_clicked(self) -> None:
        if self._current_job_worker is not None:
            self._cancel_current_job()
            return
        if len(self._paused_job_payloads) == 1:
            self._resume_job(self._paused_job_payloads[0])
            return
        if len(self._paused_job_payloads) > 1:
            selected_job_id = self._status_jobs_selector.currentData()
            for payload in self._paused_job_payloads:
                if int(payload.get("job_id", -1)) == int(selected_job_id):
                    self._resume_job(payload)
                    return

    def _resume_last_job(self) -> None:
        if self._current_job_worker is not None:
            return
        latest = self._latest_paused_job()
        if latest is None:
            return
        self._resume_job(latest)

    def _resume_job(self, payload: dict[str, object]) -> None:
        if self._current_job_worker is not None:
            return
        job_kind = str(payload.get("job_kind", "")).strip()
        start_message = str(
            payload.get("start_message", "Resuming job...")
        )
        seeds = payload.get("seeds")
        if not isinstance(seeds, list):
            return
        job_id = int(payload.get("job_id", -1))
        self._paused_job_payloads = [
            item for item in self._paused_job_payloads
            if int(item.get("job_id", -2)) != job_id
        ]
        if job_kind == "rebuild":
            self._start_worker(
                OrbitBuildWorker(
                    generation_id=self._next_generation_id(),
                    job_kind="rebuild",
                    simulation_config=self._config.simulation,
                    max_reflections=self._config.simulation.n_geom_default,
                    phase_steps=self._normalized_phase_steps(
                        self._config.simulation.n_phase_default,
                        self._config.simulation.n_geom_default,
                    ),
                    chunk_size=self._config.background.build_chunk_size,
                    seeds=seeds,
                    existing_orbits=self._trajectory_orbits,
                ),
                start_message=start_message.replace("Starting", "Resuming"),
                resumable_payload=payload,
            )
            return
        if job_kind == "single_build":
            self._start_worker(
                OrbitBuildWorker(
                    generation_id=self._next_generation_id(),
                    job_kind="single_build",
                    simulation_config=self._config.simulation,
                    max_reflections=self._config.simulation.n_geom_default,
                    phase_steps=self._normalized_phase_steps(
                        self._config.simulation.n_phase_default,
                        self._config.simulation.n_geom_default,
                    ),
                    chunk_size=self._config.background.build_chunk_size,
                    seeds=seeds,
                    existing_orbits=self._trajectory_orbits,
                ),
                start_message=start_message.replace("Building", "Resuming"),
                resumable_payload=payload,
            )

    def _schedule_autosave(self) -> None:
        if not self._config.autosave.enabled:
            return
        self._autosave_timer.start()


def run_app(config: Config, config_path: str) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config, config_path)
    window.show()
    app.exec()
