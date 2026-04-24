from __future__ import annotations

"""Facade for trajectory-related computation modules.

This module intentionally re-exports existing core building blocks without
changing formulas or behavior. It provides one stable import surface for UI
and orchestration code while keeping the underlying implementations in their
current modules.
"""

from app.core.geometry_builder import build_wedge_geometry
from app.core.lyapunov import LyapunovResult, compute_finite_time_lyapunov
from app.core.math_engine import (
    PhaseState,
    StepResult,
    ValidationResult,
    next_state,
    validate_state,
)
from app.core.orbit_builder import build_orbit, iter_orbit_chunks
from app.core.region_eval import validate_scene_item_expression

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
