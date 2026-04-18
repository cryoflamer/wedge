from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OrbitPoint:
    step_index: int
    d: float
    tau: float
    wall: int
    valid: bool = True
    invalid_reason: str | None = None
    branch: str | None = None


@dataclass
class ReplayFrame:
    frame_index: int
    orbit_point_index: int


@dataclass
class Orbit:
    trajectory_id: int
    points: list[OrbitPoint] = field(default_factory=list)
    replay_frames: list[ReplayFrame] = field(default_factory=list)
    valid: bool = True
    invalid_reason: str | None = None
    completed_steps: int = 0
    lyapunov_estimate: float | None = None
    lyapunov_running: list[float] = field(default_factory=list)
    lyapunov_valid: bool = False
    lyapunov_invalid_reason: str | None = None
    lyapunov_status: str = "not_computed"
    lyapunov_steps_used: int = 0
    lyapunov_wall_divergence_count: int = 0
