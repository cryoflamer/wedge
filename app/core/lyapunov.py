from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.math_engine import PhaseState, next_state, validate_state
from app.models.config import LyapunovConfig, SimulationConfig
from app.models.trajectory import TrajectorySeed


@dataclass
class LyapunovResult:
    estimate: float | None
    running_estimate: list[float] = field(default_factory=list)
    status: str = "failed"
    reason: str | None = None
    steps_used: int = 0
    wall_divergence_count: int = 0


def compute_finite_time_lyapunov(
    seed: TrajectorySeed,
    simulation_config: SimulationConfig,
    lyapunov_config: LyapunovConfig,
) -> LyapunovResult:
    if lyapunov_config.max_steps <= 1:
        return LyapunovResult(
            estimate=None,
            status="failed",
            reason="insufficient_max_steps",
        )

    base_state = PhaseState(
        d=seed.d0,
        tau=seed.tau0,
        wall=seed.wall_start,
    )
    validation = validate_state(base_state, simulation_config)
    if not validation.valid:
        return LyapunovResult(
            estimate=None,
            status="failed",
            reason=validation.reason,
        )

    companion_state = _build_initial_companion(
        base_state=base_state,
        simulation_config=simulation_config,
        delta0=lyapunov_config.delta0,
        eps=lyapunov_config.eps,
    )
    if companion_state is None:
        return LyapunovResult(
            estimate=None,
            status="failed",
            reason="companion_initialization_failed",
        )

    sum_log = 0.0
    steps_used = 0
    running_estimate: list[float] = []
    wall_divergence_count = 0

    for step_index in range(1, lyapunov_config.max_steps + 1):
        base_step = next_state(base_state, simulation_config)
        companion_step = next_state(companion_state, simulation_config)

        if base_step.state is None or companion_step.state is None:
            return _finish_result(
                sum_log=sum_log,
                steps_used=steps_used,
                running_estimate=running_estimate,
                wall_divergence_count=wall_divergence_count,
                reason=(base_step.reason or companion_step.reason or "step_failed"),
            )

        base_state = base_step.state
        companion_state = companion_step.state

        if base_state.wall != companion_state.wall:
            wall_divergence_count += 1

        delta = _phase_distance(base_state, companion_state)
        if not math.isfinite(delta):
            return _finish_result(
                sum_log=sum_log,
                steps_used=steps_used,
                running_estimate=running_estimate,
                wall_divergence_count=wall_divergence_count,
                reason="non_finite_delta",
            )

        if delta <= lyapunov_config.eps:
            return _finish_result(
                sum_log=sum_log,
                steps_used=steps_used,
                running_estimate=running_estimate,
                wall_divergence_count=wall_divergence_count,
                reason="delta_too_small",
            )

        if step_index > lyapunov_config.transient_steps:
            sum_log += math.log(delta / lyapunov_config.delta0)
            steps_used += 1
            running_estimate.append(sum_log / steps_used)

        if step_index % max(lyapunov_config.renormalization_interval, 1) == 0:
            renormalized = _renormalize_companion(
                base_state=base_state,
                companion_state=companion_state,
                simulation_config=simulation_config,
                delta0=lyapunov_config.delta0,
                eps=lyapunov_config.eps,
            )
            if renormalized is None:
                return _finish_result(
                    sum_log=sum_log,
                    steps_used=steps_used,
                    running_estimate=running_estimate,
                    wall_divergence_count=wall_divergence_count,
                    reason="renormalization_failed",
                )
            companion_state = renormalized

    return LyapunovResult(
        estimate=(sum_log / steps_used) if steps_used > 0 else None,
        running_estimate=running_estimate,
        status="done" if steps_used > 0 else "failed",
        reason=None if steps_used > 0 else "insufficient_post_transient_steps",
        steps_used=steps_used,
        wall_divergence_count=wall_divergence_count,
    )


def _finish_result(
    sum_log: float,
    steps_used: int,
    running_estimate: list[float],
    wall_divergence_count: int,
    reason: str,
) -> LyapunovResult:
    if steps_used > 0:
        return LyapunovResult(
            estimate=sum_log / steps_used,
            running_estimate=running_estimate,
            status="partial",
            reason=reason,
            steps_used=steps_used,
            wall_divergence_count=wall_divergence_count,
        )

    return LyapunovResult(
        estimate=None,
        running_estimate=running_estimate,
        status="failed",
        reason=reason,
        steps_used=0,
        wall_divergence_count=wall_divergence_count,
    )


def _build_initial_companion(
    base_state: PhaseState,
    simulation_config: SimulationConfig,
    delta0: float,
    eps: float,
) -> PhaseState | None:
    offsets = (
        (delta0, 0.0),
        (-delta0, 0.0),
        (0.0, delta0),
        (0.0, -delta0),
    )
    for delta_d, delta_tau in offsets:
        candidate = PhaseState(
            d=base_state.d + delta_d,
            tau=base_state.tau + delta_tau,
            wall=base_state.wall,
        )
        if _is_usable_state(candidate, simulation_config, eps):
            return candidate
    return None


def _renormalize_companion(
    base_state: PhaseState,
    companion_state: PhaseState,
    simulation_config: SimulationConfig,
    delta0: float,
    eps: float,
) -> PhaseState | None:
    delta_d = companion_state.d - base_state.d
    delta_tau = companion_state.tau - base_state.tau
    norm = math.hypot(delta_d, delta_tau)
    if not math.isfinite(norm) or norm <= eps:
        return _build_initial_companion(base_state, simulation_config, delta0, eps)

    direction_d = delta_d / norm
    direction_tau = delta_tau / norm
    scale = delta0

    for _ in range(16):
        candidate = PhaseState(
            d=base_state.d + direction_d * scale,
            tau=base_state.tau + direction_tau * scale,
            wall=base_state.wall,
        )
        if _is_usable_state(candidate, simulation_config, eps):
            return candidate
        scale *= 0.5

    return _build_initial_companion(base_state, simulation_config, delta0 * 0.5, eps)


def _is_usable_state(
    state: PhaseState,
    simulation_config: SimulationConfig,
    eps: float,
) -> bool:
    del eps
    validation = validate_state(state, simulation_config)
    return validation.valid


def _phase_distance(first: PhaseState, second: PhaseState) -> float:
    return math.hypot(second.d - first.d, second.tau - first.tau)
