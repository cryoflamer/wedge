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


@dataclass
class Orbit:
    trajectory_id: int
    points: list[OrbitPoint] = field(default_factory=list)
    valid: bool = True
    invalid_reason: str | None = None
