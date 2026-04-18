from __future__ import annotations

from dataclasses import dataclass, field

from app.models.trajectory import TrajectorySeed


@dataclass(slots=True)
class Session:
    config_name: str
    trajectories: list[TrajectorySeed] = field(default_factory=list)
