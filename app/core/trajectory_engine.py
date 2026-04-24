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
from app.core.native_backend import (
    is_native_available,
    native_build_dense_orbit,
    native_build_sparse_orbit,
)
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
from app.models.orbit import Orbit, OrbitPoint, ReplayFrame
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
        getattr(config, "performance_trace", False),
        getattr(config, "native_enabled", False),
        getattr(config, "native_sample_mode", "every_n"),
        getattr(config, "native_sample_step", 1),
        steps,
    )
    cached_orbit = cache.get(cache_key)
    if cached_orbit is not None:
        return deepcopy(cached_orbit)

    use_native = (
        getattr(config, "native_enabled", False)
        and is_native_available()
        and int(getattr(config, "native_sample_step", 1)) >= 1
        and str(getattr(config, "native_sample_mode", "every_n")) in {"dense", "every_n", "final"}
    )
    if use_native:
        orbit = _native_orbit_to_python(
            trajectory_id=seed.id,
            native_result=native_build_sparse_orbit(
                d0=seed.d0,
                tau0=seed.tau0,
                wall0=seed.wall_start,
                alpha=config.alpha,
                beta=config.beta,
                steps=steps,
                sample_step=int(getattr(config, "native_sample_step", 1)),
                sample_mode=str(getattr(config, "native_sample_mode", "every_n")),
            ),
        )
    else:
        orbit = _build_orbit(seed=seed, config=config, steps=steps)
    cache.set(cache_key, deepcopy(orbit))
    return orbit


def build_dense_orbit_for_geometry(
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
) -> Orbit:
    use_native_dense = (
        getattr(config, "native_enabled", False)
        and is_native_available()
        and (
            int(getattr(config, "native_sample_step", 1)) > 1
            or str(getattr(config, "native_sample_mode", "every_n")) != "dense"
        )
    )
    if not use_native_dense:
        return build_orbit(seed=seed, config=config, steps=steps)
    return _native_orbit_to_python(
        trajectory_id=seed.id,
        native_result=native_build_dense_orbit(
            d0=seed.d0,
            tau0=seed.tau0,
            wall0=seed.wall_start,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
        ),
    )


def is_native_backend_available() -> bool:
    return is_native_available()


def _native_orbit_to_python(trajectory_id: int, native_result: dict[str, object]) -> Orbit:
    steps = [int(value) for value in native_result["steps"]]
    d_values = [float(value) for value in native_result["d"]]
    tau_values = [float(value) for value in native_result["tau"]]
    walls = [int(value) for value in native_result["wall"]]
    orbit = Orbit(
        trajectory_id=trajectory_id,
        valid=bool(native_result["valid"]),
        invalid_reason=native_result["invalid_reason"],
    )
    for index, (step_index, d_value, tau_value, wall) in enumerate(
        zip(steps, d_values, tau_values, walls)
    ):
        is_last = index == len(steps) - 1
        point_valid = orbit.valid or not is_last
        point_reason = orbit.invalid_reason if (is_last and not orbit.valid) else None
        orbit.points.append(
            OrbitPoint(
                step_index=step_index,
                d=d_value,
                tau=tau_value,
                wall=wall,
                valid=point_valid,
                invalid_reason=point_reason,
                branch=None,
            )
        )
        orbit.replay_frames.append(
            ReplayFrame(
                frame_index=step_index,
                orbit_point_index=index,
            )
        )
    final_step = native_result.get("final_step")
    orbit.completed_steps = int(final_step) + 1 if final_step is not None else len(orbit.points)
    return orbit

__all__ = [
    "LyapunovResult",
    "PhaseState",
    "StepResult",
    "ValidationResult",
    "build_orbit",
    "build_dense_orbit_for_geometry",
    "build_wedge_geometry",
    "compute_finite_time_lyapunov",
    "is_native_backend_available",
    "iter_orbit_chunks",
    "next_state",
    "validate_scene_item_expression",
    "validate_state",
]
