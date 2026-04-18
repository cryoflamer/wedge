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

    for orbit_point, state, next_state, left, right in zip(
        segment_points,
        states[:segment_count],
        states[1 : segment_count + 1],
        geometry.reflections,
        geometry.reflections[1 : segment_count + 1],
    ):
        segment = _build_segment(
            step_index=orbit_point.step_index,
            state=state,
            next_state=next_state,
            left=left,
            right=right,
            config=config,
        )
        geometry.segments.append(segment)

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


def _build_segment(
    step_index: int,
    state: PhaseState,
    next_state: PhaseState,
    left: ReflectionPoint,
    right: ReflectionPoint,
    config: SimulationConfig,
) -> ParabolicSegment:
    if not left.valid or not right.valid:
        return ParabolicSegment(
            step_index=step_index,
            wall_from=left.wall,
            wall_to=right.wall,
            focus=None,
            start_point=left.point,
            end_point=right.point,
            samples=[],
            valid=False,
            invalid_reason=left.invalid_reason or right.invalid_reason or "segment_reconstruction_failed",
        )

    start_point = left.point
    end_point = right.point
    if start_point is None or end_point is None:
        return ParabolicSegment(
            step_index=step_index,
            wall_from=left.wall,
            wall_to=right.wall,
            focus=None,
            start_point=start_point,
            end_point=end_point,
            samples=[],
            valid=False,
            invalid_reason="segment_boundary_resolution_failed",
        )

    segment_math = _segment_math_from_states(
        state=state,
        next_state=next_state,
        config=config,
    )
    if segment_math is None:
        return ParabolicSegment(
            step_index=step_index,
            wall_from=left.wall,
            wall_to=right.wall,
            focus=None,
            start_point=start_point,
            end_point=end_point,
            samples=[],
            valid=False,
            invalid_reason="segment_parameterization_failed",
        )

    focus = GeometryPoint(x=segment_math.x, y=segment_math.y)
    samples = _build_parabola_samples(
        segment_math=segment_math,
        start_point=start_point,
        end_point=end_point,
        config=config,
    )
    if not samples:
        return ParabolicSegment(
            step_index=step_index,
            wall_from=left.wall,
            wall_to=right.wall,
            focus=focus,
            start_point=start_point,
            end_point=end_point,
            samples=[],
            valid=False,
            invalid_reason="segment_sampling_failed",
        )

    return ParabolicSegment(
        step_index=step_index,
        wall_from=left.wall,
        wall_to=right.wall,
        focus=focus,
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


class _SegmentMath:
    def __init__(
        self,
        x: float,
        y: float,
        t_start: float,
        t_end: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> None:
        self.x = x
        self.y = y
        self.t_start = t_start
        self.t_end = t_end
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2


def _segment_math_from_states(
    state: PhaseState,
    next_state: PhaseState,
    config: SimulationConfig,
) -> _SegmentMath | None:
    segment_1 = _segment_parameters_from_state(state, config)
    segment_2 = _segment_parameters_from_state(next_state, config)
    if segment_1 is None or segment_2 is None:
        return None

    x1, y1, t1 = segment_1
    x2, y2, t2 = segment_2
    mismatch_tolerance = max(config.eps * 100.0, 1.0e-6)
    if abs(x1 - x2) > mismatch_tolerance or abs(y1 - y2) > mismatch_tolerance:
        logger.warning(
            "Wedge parabola mismatch: dX=%.6e dY=%.6e",
            abs(x1 - x2),
            abs(y1 - y2),
        )
    x_segment = 0.5 * (x1 + x2)
    y_segment = 0.5 * (y1 + y2)
    return _SegmentMath(
        x=x_segment,
        y=y_segment,
        t_start=t1,
        t_end=t2,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def _segment_parameters_from_state(
    state: PhaseState,
    config: SimulationConfig,
) -> tuple[float, float, float] | None:
    theta = _wall_angle(state.wall, config)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    sin_2_theta = math.sin(2.0 * theta)
    if abs(sin_2_theta) <= config.eps or state.d <= config.eps:
        return None

    cot_2_theta = math.cos(2.0 * theta) / sin_2_theta
    sigma_term = state.d * sin_theta + state.tau * cos_theta
    x_value = (
        (1.0 - state.d + math.cos(2.0 * theta)) / sin_2_theta
        - 4.0 * cot_2_theta * (sigma_term * sigma_term) / state.d
    )
    y_value = 1.0 - 4.0 * (sigma_term * sigma_term) / state.d
    t_value = (
        (state.d * cos_theta - state.tau * sin_theta) * sigma_term
    ) / state.d
    if (
        not math.isfinite(x_value)
        or not math.isfinite(y_value)
        or not math.isfinite(t_value)
    ):
        return None
    return x_value, y_value, t_value


def _build_parabola_samples(
    segment_math: _SegmentMath,
    start_point: GeometryPoint | None,
    end_point: GeometryPoint | None,
    config: SimulationConfig,
    num_samples: int = 48,
) -> list[GeometryPoint]:
    if start_point is None or end_point is None:
        return []

    denominator = 2.0 * (1.0 - segment_math.y)
    if abs(denominator) <= config.eps:
        return []

    samples: list[GeometryPoint] = []
    for index in range(num_samples + 1):
        ratio = index / num_samples
        u_value = segment_math.t_start + (
            segment_math.t_end - segment_math.t_start
        ) * ratio
        x_coord = segment_math.x + u_value
        y_coord = ((1.0 + segment_math.y) / 2.0) - (
            (u_value * u_value) / denominator
        )

        if not math.isfinite(x_coord) or not math.isfinite(y_coord):
            continue
        samples.append(GeometryPoint(x=x_coord, y=y_coord))

    parametric_start = _parametric_point(segment_math.x, segment_math.y, segment_math.t_start, config)
    parametric_end = _parametric_point(segment_math.x, segment_math.y, segment_math.t_end, config)
    _log_segment_debug(
        segment_math=segment_math,
        parametric_start=parametric_start,
        parametric_end=parametric_end,
        reflection_start=start_point,
        reflection_end=end_point,
    )

    if samples:
        samples[0] = start_point
        samples[-1] = end_point
    return samples


def _parametric_point(
    x_value: float,
    y_value: float,
    u_value: float,
    config: SimulationConfig,
) -> GeometryPoint | None:
    denominator = 2.0 * (1.0 - y_value)
    if abs(denominator) <= config.eps:
        return None
    point_x = x_value + u_value
    point_y = ((1.0 + y_value) / 2.0) - ((u_value * u_value) / denominator)
    if not math.isfinite(point_x) or not math.isfinite(point_y):
        return None
    return GeometryPoint(x=point_x, y=point_y)


def _log_segment_debug(
    segment_math: _SegmentMath,
    parametric_start: GeometryPoint | None,
    parametric_end: GeometryPoint | None,
    reflection_start: GeometryPoint,
    reflection_end: GeometryPoint,
) -> None:
    global _debug_segment_logs_emitted

    if _debug_segment_logs_emitted >= _DEBUG_SEGMENT_LOG_LIMIT:
        return

    logger.info(
        (
            "Wedge segment: X1=%.6f Y1=%.6f t1=%.6f "
            "X2=%.6f Y2=%.6f t2=%.6f "
            "dX=%.6e dY=%.6e "
            "parametric_start=(%.6f, %.6f) parametric_end=(%.6f, %.6f) "
            "reflection_start=(%.6f, %.6f) reflection_end=(%.6f, %.6f) "
            "start_delta=%.6e end_delta=%.6e"
        ),
        segment_math.x1,
        segment_math.y1,
        segment_math.t_start,
        segment_math.x2,
        segment_math.y2,
        segment_math.t_end,
        abs(segment_math.x1 - segment_math.x2),
        abs(segment_math.y1 - segment_math.y2),
        parametric_start.x if parametric_start is not None else float("nan"),
        parametric_start.y if parametric_start is not None else float("nan"),
        parametric_end.x if parametric_end is not None else float("nan"),
        parametric_end.y if parametric_end is not None else float("nan"),
        reflection_start.x,
        reflection_start.y,
        reflection_end.x,
        reflection_end.y,
        _point_distance(parametric_start, reflection_start),
        _point_distance(parametric_end, reflection_end),
    )
    _debug_segment_logs_emitted += 1


def _point_distance(
    left: GeometryPoint | None,
    right: GeometryPoint | None,
) -> float:
    if left is None or right is None:
        return float("nan")
    return math.hypot(left.x - right.x, left.y - right.y)


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
