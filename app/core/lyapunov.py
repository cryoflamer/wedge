from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.math_engine import PhaseState, next_state, validate_state
from app.models.config import SimulationConfig
from app.models.trajectory import TrajectorySeed


@dataclass(frozen=True)
class LyapunovConfig:
    delta0: float = 1.0e-6
    transient_steps: int = 10
    renormalize_every: int = 1
    max_projection_attempts: int = 12


@dataclass
class LyapunovResult:
    estimate: float | None
    running_estimate: list[float] = field(default_factory=list)
    valid: bool = False
    reason: str | None = None
    steps_used: int = 0


def compute_finite_time_lyapunov(
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
    lyapunov_config: LyapunovConfig | None = None,
) -> LyapunovResult:
    options = lyapunov_config or LyapunovConfig()
    if steps <= 1:
        return LyapunovResult(
            estimate=None,
            valid=False,
            reason="insufficient_steps",
        )

    base_state = PhaseState(d=seed.d0, tau=seed.tau0, wall=seed.wall_start)
    base_validation = validate_state(base_state, config)
    if not base_validation.valid:
        return LyapunovResult(
            estimate=None,
            valid=False,
            reason=base_validation.reason,
        )

    companion_state = _build_initial_companion(base_state, config, options.delta0)
    if companion_state is None:
        return LyapunovResult(
            estimate=None,
            valid=False,
            reason="companion_initialization_failed",
        )

    sum_log = 0.0
    steps_used = 0
    running_estimate: list[float] = []

    for step_index in range(1, steps):
        base_step = next_state(base_state, config)
        companion_step = next_state(companion_state, config)
        if base_step.state is None:
            return LyapunovResult(
                estimate=None,
                running_estimate=running_estimate,
                valid=False,
                reason=base_step.reason or "base_step_failed",
                steps_used=steps_used,
            )
        if companion_step.state is None:
            return LyapunovResult(
                estimate=None,
                running_estimate=running_estimate,
                valid=False,
                reason=companion_step.reason or "companion_step_failed",
                steps_used=steps_used,
            )

        base_state = base_step.state
        companion_state = companion_step.state
        delta = _phase_distance(base_state, companion_state)
        if not math.isfinite(delta) or delta <= 0.0:
            return LyapunovResult(
                estimate=None,
                running_estimate=running_estimate,
                valid=False,
                reason="degenerate_separation",
                steps_used=steps_used,
            )

        if step_index > options.transient_steps:
            sum_log += math.log(delta / options.delta0)
            steps_used += 1
            running_estimate.append(sum_log / steps_used)

        if step_index % max(options.renormalize_every, 1) == 0:
            renormalized_state = _renormalize_companion(
                base_state=base_state,
                companion_state=companion_state,
                config=config,
                delta0=options.delta0,
                max_attempts=options.max_projection_attempts,
            )
            if renormalized_state is None:
                return LyapunovResult(
                    estimate=None,
                    running_estimate=running_estimate,
                    valid=False,
                    reason="renormalization_failed",
                    steps_used=steps_used,
                )
            companion_state = renormalized_state

    if steps_used == 0:
        return LyapunovResult(
            estimate=None,
            running_estimate=running_estimate,
            valid=False,
            reason="insufficient_post_transient_steps",
            steps_used=0,
        )

    return LyapunovResult(
        estimate=sum_log / steps_used,
        running_estimate=running_estimate,
        valid=True,
        steps_used=steps_used,
    )


def _build_initial_companion(
    base_state: PhaseState,
    config: SimulationConfig,
    delta0: float,
) -> PhaseState | None:
    candidates = (
        PhaseState(base_state.d + delta0, base_state.tau, base_state.wall),
        PhaseState(base_state.d - delta0, base_state.tau, base_state.wall),
        PhaseState(base_state.d, base_state.tau + delta0, base_state.wall),
        PhaseState(base_state.d, base_state.tau - delta0, base_state.wall),
    )
    for candidate in candidates:
        if validate_state(candidate, config).valid:
            return candidate
    return None


def _renormalize_companion(
    base_state: PhaseState,
    companion_state: PhaseState,
    config: SimulationConfig,
    delta0: float,
    max_attempts: int,
) -> PhaseState | None:
    dd = companion_state.d - base_state.d
    dtau = companion_state.tau - base_state.tau
    norm = math.hypot(dd, dtau)
    if not math.isfinite(norm) or norm <= 0.0:
        return _build_initial_companion(base_state, config, delta0)

    direction_d = dd / norm
    direction_tau = dtau / norm
    scale = delta0

    for _ in range(max_attempts):
        candidate = PhaseState(
            d=base_state.d + direction_d * scale,
            tau=base_state.tau + direction_tau * scale,
            wall=base_state.wall,
        )
        if validate_state(candidate, config).valid:
            return candidate
        scale *= 0.5

    return _build_initial_companion(base_state, config, delta0 * 0.5)


def _phase_distance(first: PhaseState, second: PhaseState) -> float:
    return math.hypot(second.d - first.d, second.tau - first.tau)
