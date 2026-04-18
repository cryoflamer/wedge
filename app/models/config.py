from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Config:
    alpha: float
    beta: float
    n_phase: int
    n_geom: int
    log_level: str = "INFO"
