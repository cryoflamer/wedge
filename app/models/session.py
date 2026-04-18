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
    phase_fixed_domain: bool = True
    phase_viewport_wall_1: tuple[float, float, float, float] | None = None
    phase_viewport_wall_2: tuple[float, float, float, float] | None = None
