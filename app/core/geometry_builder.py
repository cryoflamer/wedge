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
    focus = _focus_from_state(state, config)
    if focus is None or not left.valid or not right.valid:
        return ParabolicSegment(
            step_index=step_index,
            wall_from=left.wall,
            wall_to=right.wall,
            focus=focus,
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
            focus=focus,
            start_point=start_point,
            end_point=end_point,
            samples=[],
            valid=False,
            invalid_reason="segment_boundary_resolution_failed",
        )

    samples = _build_parabola_samples(
        state=state,
        next_state=next_state,
        focus=focus,
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


def _focus_from_state(
    state: PhaseState,
    config: SimulationConfig,
) -> GeometryPoint | None:
    angle = _wall_angle(state.wall, config)
    sin_2_angle = math.sin(2.0 * angle)
    if abs(sin_2_angle) <= config.eps or state.d <= config.eps:
        return None

    y = 1.0 - (
        (state.d * math.sin(angle) - state.tau * math.cos(angle)) ** 2
        / state.d
    )
    x = (1.0 + y * math.cos(2.0 * angle) - state.d) / sin_2_angle
    if not math.isfinite(x) or not math.isfinite(y):
        return None

    return GeometryPoint(x=x, y=y)


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


def _build_parabola_samples(
    state: PhaseState,
    next_state: PhaseState,
    focus: GeometryPoint,
    start_point: GeometryPoint | None,
    end_point: GeometryPoint | None,
    config: SimulationConfig,
    num_samples: int = 48,
) -> list[GeometryPoint]:
    if start_point is None or end_point is None:
        return []

    theta = _wall_angle(state.wall, config)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    tangent = math.tan(theta)
    if abs(tangent) <= config.eps or state.d <= config.eps:
        return []

    coefficient_a = state.d * sin_theta - state.tau * cos_theta
    coefficient_b = state.d * cos_theta + state.tau * sin_theta
    if abs(coefficient_a) <= config.eps:
        return []

    parabola_parameter = (coefficient_a * coefficient_a) / (2.0 * state.d)
    if parabola_parameter <= config.eps:
        return []

    vertex = GeometryPoint(
        x=focus.x,
        y=(1.0 + focus.y) / 2.0,
    )
    t_start = coefficient_b / coefficient_a
    next_theta = _wall_angle(next_state.wall, config)
    next_sin_theta = math.sin(next_theta)
    next_cos_theta = math.cos(next_theta)
    next_coefficient_a = (
        next_state.d * next_sin_theta - next_state.tau * next_cos_theta
    )
    next_coefficient_b = (
        next_state.d * next_cos_theta + next_state.tau * next_sin_theta
    )
    if abs(next_coefficient_a) <= config.eps:
        return []
    t_end = next_coefficient_b / next_coefficient_a

    _log_segment_debug(
        focus=focus,
        vertex=vertex,
        parabola_parameter=parabola_parameter,
        start_point=start_point,
        end_point=end_point,
        t_start_formula=t_start,
        t_end_formula=t_end,
        t_start=t_start,
        t_end=t_end,
    )

    samples: list[GeometryPoint] = []
    for index in range(num_samples + 1):
        ratio = index / num_samples
        t_value = t_start + (t_end - t_start) * ratio
        x_coord = vertex.x + 2.0 * parabola_parameter * t_value
        y_coord = vertex.y - parabola_parameter * t_value * t_value

        if not math.isfinite(x_coord) or not math.isfinite(y_coord):
            continue
        samples.append(GeometryPoint(x=x_coord, y=y_coord))

    if samples:
        samples[0] = start_point
        samples[-1] = end_point
    return samples


def _log_segment_debug(
    focus: GeometryPoint,
    vertex: GeometryPoint,
    parabola_parameter: float,
    start_point: GeometryPoint,
    end_point: GeometryPoint,
    t_start_formula: float,
    t_end_formula: float,
    t_start: float,
    t_end: float,
) -> None:
    global _debug_segment_logs_emitted

    if _debug_segment_logs_emitted >= _DEBUG_SEGMENT_LOG_LIMIT:
        return

    logger.info(
        (
            "Wedge segment: focus=(%.6f, %.6f) vertex=(%.6f, %.6f) p=%.6f "
            "start=(%.6f, %.6f) end=(%.6f, %.6f) "
            "t1=%.6f t2=%.6f chosen_t1=%.6f chosen_t2=%.6f"
        ),
        focus.x,
        focus.y,
        vertex.x,
        vertex.y,
        parabola_parameter,
        start_point.x,
        start_point.y,
        end_point.x,
        end_point.y,
        t_start_formula,
        t_end_formula,
        t_start,
        t_end,
    )
    _debug_segment_logs_emitted += 1


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
