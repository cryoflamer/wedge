from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrajectorySeed:
    id: int
    wall_start: int
    d0: float
    tau0: float
    visible: bool = True
    color: str = "#1f77b4"
