from __future__ import annotations

from dataclasses import dataclass, field

from app.models.trajectory import TrajectorySeed


@dataclass
class Session:
    alpha: float
    beta: float
    n_phase: int
    n_geom: int
    replay_delay_ms: int = 120
    replay_selected_only: bool = True
    selected_trajectory_id: int | None = None
    trajectories: list[TrajectorySeed] = field(default_factory=list)
    angle_units: str = "rad"
    symmetric_mode: bool = False
    export_mode: str = "color"
    phase_fixed_domain: bool = True
    show_phase_grid: bool = True
    show_phase_minor_grid: bool = False
    show_seed_markers: bool = True
    show_directrix: bool = False
    show_regions: bool = True
    show_region_labels: bool = True
    show_region_legend: bool = True
    show_branch_markers: bool = False
    show_heatmap: bool = False
    heatmap_mode: str = "all"
    heatmap_resolution: int = 32
    heatmap_normalization: str = "linear"
    fast_build: bool = False
    phase_viewport_wall_1: tuple[float, float, float, float] | None = None
    phase_viewport_wall_2: tuple[float, float, float, float] | None = None
