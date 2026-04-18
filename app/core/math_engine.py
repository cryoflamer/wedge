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
    focus = _reconstruct_focus(state, source_angle, eps)
    if focus is None:
        return math.nan

    x_coord, y_coord = focus
    return 1.0 - x_coord * math.sin(2.0 * target_angle) + y_coord * math.cos(
        2.0 * target_angle
    )


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

    return -d_next * math.tan(target_angle) + (
        math.copysign(math.sqrt(radicand), numerator) / cos_target
    )


def _reconstruct_focus(
    state: PhaseState,
    source_angle: float,
    eps: float,
) -> tuple[float, float] | None:
    sin_2_source = math.sin(2.0 * source_angle)
    if abs(sin_2_source) <= eps or state.d <= eps:
        return None

    y_coord = 1.0 - (
        (state.tau * math.cos(source_angle) + state.d * math.sin(source_angle)) ** 2
        / state.d
    )
    x_coord = (1.0 + y_coord * math.cos(2.0 * source_angle) - state.d) / sin_2_source

    if not math.isfinite(x_coord) or not math.isfinite(y_coord):
        return None

    return x_coord, y_coord


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

    same_wall_state = PhaseState(
        d=state.d,
        tau=state.tau - 2.0 * state.d * math.tan(source_angle),
        wall=state.wall,
    )
    same_wall_validation = validate_state(same_wall_state, config)

    cross_wall_state: PhaseState | None = None
    cross_wall_validation = ValidationResult(valid=False, reason="cross_wall_not_available")
    if d_candidate > eps:
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

        cross_wall_state = PhaseState(
            d=d_candidate,
            tau=tau_candidate,
            wall=target_wall,
        )
        cross_wall_validation = validate_state(cross_wall_state, config)

    prefer_same_wall = _should_stay_on_same_wall(state, config, d_candidate)
    if prefer_same_wall:
        next_phase_state = same_wall_state
        next_validation = same_wall_validation
        branch = "same_wall"
        if not next_validation.valid and cross_wall_state is not None and cross_wall_validation.valid:
            next_phase_state = cross_wall_state
            next_validation = cross_wall_validation
            branch = "cross_wall"
    else:
        next_phase_state = cross_wall_state
        next_validation = cross_wall_validation
        branch = "cross_wall"
        if (
            (next_phase_state is None or not next_validation.valid)
            and same_wall_validation.valid
        ):
            next_phase_state = same_wall_state
            next_validation = same_wall_validation
            branch = "same_wall"

    if next_phase_state is None or not next_validation.valid:
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


def _should_stay_on_same_wall(
    state: PhaseState,
    config: SimulationConfig,
    d_candidate: float,
) -> bool:
    if d_candidate <= config.eps:
        return True

    # In the inclined wedge case from README/article, trajectories from the
    # upper wall go next to the lower wall, while same-wall returns can happen
    # from the lower wall inside the ellipse region from (28)-(29).
    if not (0.0 < config.alpha < config.beta < math.pi / 2.0):
        return False
    if state.wall != 1:
        return False

    delta = config.beta - config.alpha
    sin_delta = math.sin(delta)
    if abs(sin_delta) <= config.eps or abs(math.cos(config.alpha)) <= config.eps:
        return False

    a_coeff = (
        math.sin(config.beta)
        / (math.cos(config.alpha) * sin_delta)
        * (math.tan(config.beta) / math.tan(delta))
    )
    b_coeff = math.sin(config.beta) / (math.cos(config.alpha) * sin_delta)
    d0 = sin_delta * math.cos(config.alpha) / math.sin(config.beta)
    tau0 = sin_delta * math.sin(config.alpha) / math.sin(config.beta)

    rot_cos = math.cos(config.alpha - config.beta)
    rot_sin = math.sin(config.alpha - config.beta)
    u_coord = (state.d - d0) * rot_cos + (state.tau - tau0) * rot_sin
    v_coord = (state.d - d0) * rot_sin - (state.tau - tau0) * rot_cos
    quadratic_form = a_coeff * u_coord * u_coord + b_coeff * v_coord * v_coord

    return quadratic_form <= 1.0 + config.eps
