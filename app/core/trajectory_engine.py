from __future__ import annotations

"""Facade for trajectory-related computation modules.

This module intentionally re-exports existing core building blocks without
changing formulas or behavior. It provides one stable import surface for UI
and orchestration code while keeping the underlying implementations in their
current modules.
"""

from copy import deepcopy

from app.core.geometry_builder import build_wedge_geometry
from app.core.lyapunov import LyapunovResult, compute_finite_time_lyapunov
from app.core.math_engine import (
    PhaseState,
    StepResult,
    ValidationResult,
    next_state,
    validate_state,
)
from app.core.orbit_builder import build_orbit as _build_orbit, iter_orbit_chunks
from app.core.region_eval import validate_scene_item_expression
from app.models.config import SimulationConfig
from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed
from app.services import cache


def build_orbit(
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
) -> Orbit:
    cache_key = (
        "orbit",
        seed.id,
        seed.wall_start,
        seed.d0,
        seed.tau0,
        seed.visible,
        seed.color,
        config.alpha,
        config.beta,
        config.n_phase_default,
        config.n_geom_default,
        config.eps,
        steps,
    )
    cached_orbit = cache.get(cache_key)
    if cached_orbit is not None:
        return deepcopy(cached_orbit)

    orbit = _build_orbit(seed=seed, config=config, steps=steps)
    cache.set(cache_key, deepcopy(orbit))
    return orbit

__all__ = [
    "LyapunovResult",
    "PhaseState",
    "StepResult",
    "ValidationResult",
    "build_orbit",
    "build_wedge_geometry",
    "compute_finite_time_lyapunov",
    "iter_orbit_chunks",
    "next_state",
    "validate_scene_item_expression",
    "validate_state",
]
