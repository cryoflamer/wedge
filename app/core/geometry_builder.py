from __future__ import annotations

import logging
import math

from app.core.math_engine import PhaseState
from app.models.config import SimulationConfig
from app.models.geometry import (
    GeometryPoint,
    ParabolicSegment,
    ReflectionPoint,
    WedgeGeometry,
    WedgeWall,
)
from app.models.orbit import Orbit

logger = logging.getLogger(__name__)
_DEBUG_SEGMENT_LOG_LIMIT = 8
_debug_segment_logs_emitted = 0
_PARABOLA_MATCH_TOLERANCE = 1.0e-5


def build_wedge_geometry(
    orbit: Orbit,
    config: SimulationConfig,
    max_reflections: int,
) -> WedgeGeometry:
    geometry = WedgeGeometry(walls=_build_walls(config))

    if max_reflections <= 0:
        return geometry

    segment_count = min(max_reflections, max(len(orbit.points) - 1, 0))
    reflection_count = min(len(orbit.points), segment_count + 1)
    reflection_points = orbit.points[:reflection_count]
    segment_points = reflection_points[:segment_count]
    states = [
        PhaseState(d=point.d, tau=point.tau, wall=point.wall)
        for point in reflection_points
    ]

    for orbit_point, state in zip(reflection_points, states):
        geometry.reflections.append(
            _build_reflection_point(
                step_index=orbit_point.step_index,
                state=state,
                config=config,
                valid=orbit_point.valid,
                invalid_reason=orbit_point.invalid_reason,
            )
        )

    for orbit_point, left, right, current_state, next_state in zip(
        segment_points,
        geometry.reflections,
        geometry.reflections[1 : segment_count + 1],
        states[:segment_count],
        states[1 : segment_count + 1],
    ):
        geometry.segments.append(
            _build_segment(
                step_index=orbit_point.step_index,
                left=left,
                right=right,
                current_state=current_state,
                next_state=next_state,
                config=config,
            )
        )

    return geometry


def _build_walls(config: SimulationConfig) -> list[WedgeWall]:
    return [
        WedgeWall(
            wall=1,
            angle=config.alpha,
            start=GeometryPoint(x=0.0, y=0.0),
            end=_point_on_wall(config.alpha, y=1.0),
        ),
        WedgeWall(
            wall=2,
            angle=config.beta,
            start=GeometryPoint(x=0.0, y=0.0),
            end=_point_on_wall(config.beta, y=1.0),
        ),
    ]


def _point_on_wall(angle: float, y: float) -> GeometryPoint:
    tangent = math.tan(angle)
    if abs(tangent) <= 1.0e-12:
        return GeometryPoint(x=0.0, y=y)
    return GeometryPoint(x=y / tangent, y=y)


def _build_reflection_point(
    step_index: int,
    state: PhaseState,
    config: SimulationConfig,
    valid: bool,
    invalid_reason: str | None,
) -> ReflectionPoint:
    if not valid:
        return ReflectionPoint(
            step_index=step_index,
            wall=state.wall,
            point=None,
            valid=False,
            invalid_reason=invalid_reason,
        )

    point = _reflection_point_from_state(state, config)
    if point is None:
        return ReflectionPoint(
            step_index=step_index,
            wall=state.wall,
            point=None,
            valid=False,
            invalid_reason="reflection_reconstruction_failed",
        )

    return ReflectionPoint(
        step_index=step_index,
        wall=state.wall,
        point=point,
        valid=True,
    )


class _SharedParabola:
    def __init__(
        self,
        x: float,
        y: float,
        u_start: float,
        u_end: float,
    ) -> None:
        self.x = x
        self.y = y
        self.u_start = u_start
        self.u_end = u_end


def _invalid_segment(
    step_index: int,
    left: ReflectionPoint,
    right: ReflectionPoint,
    reason: str,
) -> ParabolicSegment:
    return ParabolicSegment(
        step_index=step_index,
        wall_from=left.wall,
        wall_to=right.wall,
        focus=None,
        start_point=left.point,
        end_point=right.point,
        samples=[],
        valid=False,
        invalid_reason=reason,
    )


def _build_segment(
    step_index: int,
    left: ReflectionPoint,
    right: ReflectionPoint,
    current_state: PhaseState,
    next_state: PhaseState,
    config: SimulationConfig,
) -> ParabolicSegment:
    if not left.valid or not right.valid:
        return _invalid_segment(
            step_index=step_index,
            left=left,
            right=right,
            reason=left.invalid_reason or right.invalid_reason or "segment_reconstruction_failed",
        )

    start_point = left.point
    end_point = right.point
    if start_point is None or end_point is None:
        return _invalid_segment(
            step_index=step_index,
            left=left,
            right=right,
            reason="segment_boundary_resolution_failed",
        )

    shared = _shared_parabola_from_states(current_state, next_state, config)
    if shared is None:
        return _invalid_segment(
            step_index=step_index,
            left=left,
            right=right,
            reason="parabola_match_failed",
        )

    samples = _build_parabola_samples(shared, start_point, end_point, config)
    if not samples:
        return _invalid_segment(
            step_index=step_index,
            left=left,
            right=right,
            reason="segment_sampling_failed",
        )

    return ParabolicSegment(
        step_index=step_index,
        wall_from=left.wall,
        wall_to=right.wall,
        focus=GeometryPoint(x=shared.x, y=shared.y),
        start_point=start_point,
        end_point=end_point,
        samples=samples,
        valid=True,
    )


def _reflection_point_from_state(
    state: PhaseState,
    config: SimulationConfig,
) -> GeometryPoint | None:
    if state.d <= config.eps:
        return None

    angle = _wall_angle(state.wall, config)
    tangent = math.tan(angle)
    if abs(tangent) <= config.eps:
        return None

    y_coord = 1.0 - (state.d * state.d + state.tau * state.tau) / (2.0 * state.d)
    x_coord = y_coord / tangent
    if (
        not math.isfinite(x_coord)
        or not math.isfinite(y_coord)
        or y_coord < -config.eps
    ):
        return None

    return GeometryPoint(x=x_coord, y=y_coord)


def _shared_parabola_from_states(
    current_state: PhaseState,
    next_state: PhaseState,
    config: SimulationConfig,
) -> _SharedParabola | None:
    theta_current = _wall_angle(current_state.wall, config)
    theta_next = _wall_angle(next_state.wall, config)

    current = _parabola_parameters(current_state.d, current_state.tau, theta_current, -1, config)
    next_params = _parabola_parameters(next_state.d, next_state.tau, theta_next, +1, config)
    if current is None or next_params is None:
        return None

    x_current, y_current, u_current = current
    x_next, y_next, u_next = next_params

    mismatch = math.hypot(x_current - x_next, y_current - y_next)
    if mismatch > _PARABOLA_MATCH_TOLERANCE:
        logger.warning(
            "Shared parabola mismatch at walls %s -> %s: %.6e",
            current_state.wall,
            next_state.wall,
            mismatch,
        )

    _log_segment_debug(
        current_x=x_current,
        current_y=y_current,
        current_u=u_current,
        next_x=x_next,
        next_y=y_next,
        next_u=u_next,
        mismatch=mismatch,
    )

    return _SharedParabola(
        x=x_current,
        y=y_current,
        u_start=u_current,
        u_end=u_next,
    )


def _parabola_parameters(
    d_value: float,
    tau_value: float,
    theta: float,
    sigma: int,
    config: SimulationConfig,
) -> tuple[float, float, float] | None:
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    sin_2_theta = math.sin(2.0 * theta)
    if abs(sin_2_theta) <= config.eps or d_value <= config.eps:
        return None

    a_term = d_value * sin_theta + sigma * tau_value * cos_theta
    y_coord = 1.0 - (a_term * a_term) / d_value
    x_coord = ((1.0 - d_value + math.cos(2.0 * theta)) / sin_2_theta) - (
        (math.cos(2.0 * theta) / sin_2_theta) * (a_term * a_term / d_value)
    )
    u_value = (
        (d_value * sigma * cos_theta - tau_value * sin_theta)
        * (d_value * sigma * sin_theta + tau_value * cos_theta)
    ) / d_value

    if not (
        math.isfinite(x_coord)
        and math.isfinite(y_coord)
        and math.isfinite(u_value)
    ):
        return None

    return x_coord, y_coord, u_value


def _build_parabola_samples(
    shared: _SharedParabola,
    start_point: GeometryPoint | None,
    end_point: GeometryPoint | None,
    config: SimulationConfig,
    num_samples: int = 48,
) -> list[GeometryPoint]:
    if start_point is None or end_point is None:
        return []

    denominator = 2.0 * (1.0 - shared.y)
    if abs(denominator) <= config.eps:
        return []

    samples: list[GeometryPoint] = []
    for index in range(num_samples + 1):
        ratio = index / num_samples
        u_value = shared.u_start + (shared.u_end - shared.u_start) * ratio
        x_coord = shared.x + u_value
        y_coord = ((1.0 + shared.y) / 2.0) - ((u_value * u_value) / denominator)

        if not math.isfinite(x_coord) or not math.isfinite(y_coord):
            continue
        samples.append(GeometryPoint(x=x_coord, y=y_coord))

    if samples:
        samples[0] = start_point
        samples[-1] = end_point
    return samples


def _log_segment_debug(
    current_x: float,
    current_y: float,
    current_u: float,
    next_x: float,
    next_y: float,
    next_u: float,
    mismatch: float,
) -> None:
    global _debug_segment_logs_emitted

    if _debug_segment_logs_emitted >= _DEBUG_SEGMENT_LOG_LIMIT:
        return

    logger.info(
        (
            "Wedge segment: current=(X=%.6f, Y=%.6f, u=%.6f) "
            "next=(X=%.6f, Y=%.6f, u=%.6f) "
            "match=%.6e"
        ),
        current_x,
        current_y,
        current_u,
        next_x,
        next_y,
        next_u,
        mismatch,
    )
    _debug_segment_logs_emitted += 1


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
