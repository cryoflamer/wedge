from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrajectorySeed:
    id: str
    wall_start: int
    d0: float
    tau0: float
