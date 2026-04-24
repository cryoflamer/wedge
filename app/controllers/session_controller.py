from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.models.config import Config
from app.models.session import Session
from app.models.trajectory import TrajectorySeed
from app.services.session_service import load_session, save_session
from app.services.trajectory_service import TrajectoryService
from app.state.app_state import AppState


@dataclass(frozen=True)
class SessionRuntimeState:
    selected_trajectory_id: int | None
    angle_units: str
    symmetric_mode: bool
    export_mode: str
    phase_fixed_domain: bool
    active_angle_constraint: str | None
    phase_viewport_wall_1: tuple[float, float, float, float] | None
    phase_viewport_wall_2: tuple[float, float, float, float] | None


class SessionController:
    def __init__(
        self,
        *,
        app_state: AppState,
        config_path: str,
        trajectory_service: TrajectoryService,
        normalized_phase_steps: Callable[[int, int], int],
        default_symmetry_constraint_name: Callable[[], str | None],
        read_runtime_state: Callable[[], SessionRuntimeState],
        apply_runtime_state: Callable[[SessionRuntimeState], None],
    ) -> None:
        self._app_state = app_state
        self._config_path = config_path
        self._trajectory_service = trajectory_service
        self._normalized_phase_steps = normalized_phase_steps
        self._default_symmetry_constraint_name = default_symmetry_constraint_name
        self._read_runtime_state = read_runtime_state
        self._apply_runtime_state = apply_runtime_state

    def save_session_to(self, output_path: str | Path) -> Path:
        return save_session(self.build_session(), output_path)

    def load_session_from(
        self,
        input_path: str | Path,
        *,
        restore_simulation_parameters: bool = True,
    ) -> Session:
        session = load_session(input_path)
        self.apply_session_state(
            session,
            restore_simulation_parameters=restore_simulation_parameters,
        )
        return session

    def build_session(self) -> Session:
        runtime_state = self._read_runtime_state()
        config = self._app_state.config
        return Session(
            alpha=config.simulation.alpha,
            beta=config.simulation.beta,
            n_phase=config.simulation.n_phase_default,
            n_geom=config.simulation.n_geom_default,
            replay_delay_ms=config.replay.delay_ms,
            replay_selected_only=config.replay.selected_only_by_default,
            selected_trajectory_id=runtime_state.selected_trajectory_id,
            trajectories=list(self._trajectory_service.get_seeds().values()),
            angle_units=runtime_state.angle_units,
            symmetric_mode=runtime_state.symmetric_mode,
            export_mode=runtime_state.export_mode,
            phase_fixed_domain=runtime_state.phase_fixed_domain,
            show_phase_grid=config.view.show_phase_grid,
            show_phase_minor_grid=config.view.show_phase_minor_grid,
            show_seed_markers=config.view.show_seed_markers,
            show_stationary_point=config.view.show_stationary_point,
            show_directrix=config.view.show_directrix,
            show_regions=config.view.show_regions,
            show_region_labels=config.view.show_region_labels,
            show_region_legend=config.view.show_region_legend,
            show_branch_markers=config.view.show_branch_markers,
            show_heatmap=config.view.show_heatmap,
            heatmap_mode=config.view.heatmap_mode,
            heatmap_resolution=config.view.heatmap_resolution,
            heatmap_normalization=config.view.heatmap_normalization,
            active_angle_constraint=runtime_state.active_angle_constraint,
            fast_build=config.background.fast_build,
            phase_viewport_wall_1=runtime_state.phase_viewport_wall_1,
            phase_viewport_wall_2=runtime_state.phase_viewport_wall_2,
        )

    def apply_session_state(
        self,
        session: Session,
        *,
        restore_simulation_parameters: bool = True,
    ) -> None:
        config = self._app_state.config
        if restore_simulation_parameters:
            config.simulation.alpha = session.alpha
            config.simulation.beta = session.beta
        config.simulation.n_geom_default = session.n_geom
        config.simulation.n_phase_default = self._normalized_phase_steps(
            session.n_phase,
            session.n_geom,
        )
        config.replay.delay_ms = session.replay_delay_ms
        config.replay.selected_only_by_default = session.replay_selected_only
        config.export.default_mode = session.export_mode
        config.view.show_phase_grid = session.show_phase_grid
        config.view.show_phase_minor_grid = session.show_phase_minor_grid
        config.view.phase_grid.show_minor = session.show_phase_minor_grid
        config.view.show_seed_markers = session.show_seed_markers
        config.view.show_stationary_point = session.show_stationary_point
        config.view.show_directrix = session.show_directrix
        config.view.show_regions = session.show_regions
        config.view.show_region_labels = session.show_region_labels
        config.view.show_region_legend = session.show_region_legend
        config.view.show_branch_markers = session.show_branch_markers
        config.view.show_heatmap = session.show_heatmap
        config.view.heatmap_mode = session.heatmap_mode
        config.view.heatmap_resolution = session.heatmap_resolution
        config.view.heatmap_normalization = session.heatmap_normalization
        restored_constraint = session.active_angle_constraint
        if restored_constraint is None and session.symmetric_mode:
            restored_constraint = self._default_symmetry_constraint_name()
        config.view.active_angle_constraint = restored_constraint
        config.background.fast_build = session.fast_build

        self._trajectory_service.load_trajectories(
            {
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
        )
        self._apply_runtime_state(
            SessionRuntimeState(
                selected_trajectory_id=session.selected_trajectory_id,
                angle_units=session.angle_units,
                symmetric_mode=session.symmetric_mode,
                export_mode=session.export_mode,
                phase_fixed_domain=session.phase_fixed_domain,
                active_angle_constraint=restored_constraint,
                phase_viewport_wall_1=session.phase_viewport_wall_1,
                phase_viewport_wall_2=session.phase_viewport_wall_2,
            )
        )

    def autosave_session(self) -> Path | None:
        if not self._app_state.config.autosave.enabled:
            return None
        return save_session(self.build_session(), self.autosave_path())

    def restore_autosave_session(self) -> Session | None:
        if not self._app_state.config.autosave.enabled:
            return None
        autosave_path = self.autosave_path()
        if not autosave_path.exists():
            return None
        session = load_session(autosave_path)
        self.apply_session_state(
            session,
            restore_simulation_parameters=(
                self._app_state.config.autosave.restore_simulation_parameters
            ),
        )
        return session

    def autosave_path(self) -> Path:
        path = Path(self._app_state.config.autosave.path)
        if path.is_absolute():
            return path
        return Path(self._config_path).resolve().parent / path
