from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from app.models.config import SimulationConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhaseState:
    d: float
    tau: float
    wall: int


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class StepResult:
    state: PhaseState | None
    valid: bool
    reason: str | None = None
    branch: str | None = None


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    if wall == 1:
        return config.alpha
    if wall == 2:
        return config.beta
    raise ValueError(f"Unsupported wall index: {wall}")


def validate_state(state: PhaseState, config: SimulationConfig) -> ValidationResult:
    eps = config.eps

    if state.wall not in (1, 2):
        return ValidationResult(valid=False, reason="unsupported_wall")

    if state.d <= eps:
        return ValidationResult(valid=False, reason="non_positive_d")

    if not math.isfinite(state.d) or not math.isfinite(state.tau):
        return ValidationResult(valid=False, reason="non_finite_state")

    if not (0.0 < config.alpha <= math.pi / 2.0):
        return ValidationResult(valid=False, reason="invalid_alpha")

    if not (config.alpha < config.beta < math.pi - config.alpha):
        return ValidationResult(valid=False, reason="invalid_beta")

    residual = domain_residual(state.d, state.tau)
    if residual >= -eps:
        return ValidationResult(valid=False, reason="outside_domain")

    return ValidationResult(valid=True)


def domain_residual(d: float, tau: float) -> float:
    return (1.0 - d) ** 2 + tau**2 - 1.0


def _cross_wall_target(wall: int) -> int:
    return 2 if wall == 1 else 1


def _compute_cross_wall_d(
    state: PhaseState,
    source_angle: float,
    target_angle: float,
    eps: float,
) -> float:
    sin_2_source = math.sin(2.0 * source_angle)
    if abs(sin_2_source) <= eps:
        return math.nan

    delta = target_angle - source_angle
    numerator = math.sin(2.0 * target_angle)
    correction = (
        math.sin(2.0 * delta) ** 2
        * (state.d * math.sin(source_angle) - state.tau * math.cos(source_angle)) ** 2
        / state.d
    )

    return 1.0 + numerator * (state.d - 1.0) / sin_2_source + correction / sin_2_source - 1.0


def _compute_cross_wall_tau(
    state: PhaseState,
    d_next: float,
    source_angle: float,
    target_angle: float,
    eps: float,
) -> float:
    cos_target = math.cos(target_angle)
    if abs(cos_target) <= eps:
        return math.nan

    numerator = state.d * math.sin(source_angle) - state.tau * math.cos(source_angle)
    radicand = numerator * numerator * state.d / d_next
    if radicand < 0.0:
        if radicand > -eps:
            radicand = 0.0
        else:
            return math.nan

    return -d_next * math.tan(target_angle) + math.sqrt(radicand) / cos_target


def next_state(state: PhaseState, config: SimulationConfig) -> StepResult:
    validation = validate_state(state, config)
    if not validation.valid:
        logger.warning("Invalid phase state: %s", validation.reason)
        return StepResult(
            state=None,
            valid=False,
            reason=validation.reason,
        )

    source_angle = _wall_angle(state.wall, config)
    target_wall = _cross_wall_target(state.wall)
    target_angle = _wall_angle(target_wall, config)
    eps = config.eps

    d_candidate = _compute_cross_wall_d(
        state=state,
        source_angle=source_angle,
        target_angle=target_angle,
        eps=eps,
    )

    if not math.isfinite(d_candidate):
        logger.warning("Cross-wall transition is non-finite")
        return StepResult(
            state=None,
            valid=False,
            reason="non_finite_cross_wall",
        )

    if d_candidate <= eps:
        next_phase_state = PhaseState(
            d=state.d,
            tau=state.tau - 2.0 * state.d * math.tan(source_angle),
            wall=state.wall,
        )
        branch = "same_wall"
    else:
        tau_candidate = _compute_cross_wall_tau(
            state=state,
            d_next=d_candidate,
            source_angle=source_angle,
            target_angle=target_angle,
            eps=eps,
        )
        if not math.isfinite(tau_candidate):
            logger.warning("Cross-wall tau is non-finite")
            return StepResult(
                state=None,
                valid=False,
                reason="non_finite_cross_wall_tau",
            )

        next_phase_state = PhaseState(
            d=d_candidate,
            tau=tau_candidate,
            wall=target_wall,
        )
        branch = "cross_wall"

    next_validation = validate_state(next_phase_state, config)
    if not next_validation.valid:
        logger.warning("Next phase state is invalid: %s", next_validation.reason)
        return StepResult(
            state=next_phase_state,
            valid=False,
            reason=next_validation.reason,
            branch=branch,
        )

    return StepResult(
        state=next_phase_state,
        valid=True,
        branch=branch,
    )
