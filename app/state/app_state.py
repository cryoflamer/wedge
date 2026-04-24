from __future__ import annotations

from dataclasses import dataclass

from app.models.config import SimulationConfig, ViewConfig


@dataclass
class AppState:
    simulation_config: SimulationConfig
    view_config: ViewConfig
    selected_trajectory_id: int | None = None
    selected_scene_item_name: str | None = None
    angle_units: str = "rad"
    base_angle_constraint_name: str | None = None
    active_angle_constraint_name: str | None = None
    symmetric_mode: bool = False
    show_phase_grid: bool = True
    show_phase_minor_grid: bool = False
    show_directrix: bool = True
    show_regions: bool = True
