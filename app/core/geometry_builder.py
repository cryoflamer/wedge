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

    for orbit_point, state, left, right in zip(
        segment_points,
        states[:segment_count],
        geometry.reflections,
        geometry.reflections[1 : segment_count + 1],
    ):
        geometry.segments.append(
            _build_segment(
                step_index=orbit_point.step_index,
                state=state,
                left=left,
                right=right,
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


def _build_segment(
    step_index: int,
    state: PhaseState,
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
        focus=focus,
        start_point=start_point,
        end_point=end_point,
        wall_to=right.wall,
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
    focus: GeometryPoint,
    start_point: GeometryPoint | None,
    end_point: GeometryPoint | None,
    wall_to: int,
    config: SimulationConfig,
    num_samples: int = 48,
) -> list[GeometryPoint]:
    if start_point is None or end_point is None:
        return []

    parabola_parameter = (1.0 - focus.y) / 2.0
    if parabola_parameter <= config.eps:
        return []

    vertex = GeometryPoint(
        x=focus.x,
        y=(1.0 + focus.y) / 2.0,
    )
    start_candidates = _parabola_t_candidates_from_point(
        start_point,
        vertex,
        parabola_parameter,
        config,
    )
    end_candidates = _parabola_t_candidates_from_point(
        end_point,
        vertex,
        parabola_parameter,
        config,
    )
    if not start_candidates or not end_candidates:
        return []

    start_candidates = _filter_t_candidates_by_x(
        point=start_point,
        candidates=start_candidates,
        vertex=vertex,
        parabola_parameter=parabola_parameter,
        config=config,
    )
    end_candidates = _filter_t_candidates_by_x(
        point=end_point,
        candidates=end_candidates,
        vertex=vertex,
        parabola_parameter=parabola_parameter,
        config=config,
    )
    t_start, t_end = _select_segment_parameters(
        start_point=start_point,
        end_point=end_point,
        start_candidates=start_candidates,
        end_candidates=end_candidates,
        wall_to=wall_to,
        vertex=vertex,
        parabola_parameter=parabola_parameter,
        config=config,
    )
    _log_segment_debug(
        focus=focus,
        vertex=vertex,
        parabola_parameter=parabola_parameter,
        start_point=start_point,
        end_point=end_point,
        start_candidates=start_candidates,
        end_candidates=end_candidates,
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


def _parabola_t_candidates_from_point(
    point: GeometryPoint,
    vertex: GeometryPoint,
    parabola_parameter: float,
    config: SimulationConfig,
) -> tuple[float, float] | tuple[float]:
    normalized = (vertex.y - point.y) / parabola_parameter
    if normalized < -config.eps:
        return tuple()

    abs_t = math.sqrt(max(normalized, 0.0))
    if abs_t <= config.eps:
        return (0.0,)
    return (-abs_t, abs_t)


def _select_segment_parameters(
    start_point: GeometryPoint,
    end_point: GeometryPoint,
    start_candidates: tuple[float, ...],
    end_candidates: tuple[float, ...],
    wall_to: int,
    vertex: GeometryPoint,
    parabola_parameter: float,
    config: SimulationConfig,
) -> tuple[float, float]:
    best_pair: tuple[float, float] | None = None
    best_score: tuple[float, float, float] | None = None

    for t_start in start_candidates:
        start_error = abs(_x_from_t(vertex, parabola_parameter, t_start) - start_point.x)
        for t_end in end_candidates:
            end_error = abs(_x_from_t(vertex, parabola_parameter, t_end) - end_point.x)
            mismatch_penalty = 0.0
            if (
                wall_to == 2
                and len(end_candidates) > 1
                and abs(t_end) <= abs(t_start) + config.eps
            ):
                mismatch_penalty = 1.0

            score = (
                mismatch_penalty,
                start_error + end_error,
                abs(t_end - t_start),
            )
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (t_start, t_end)

    if best_pair is None:
        return 0.0, 0.0
    return best_pair


def _filter_t_candidates_by_x(
    point: GeometryPoint,
    candidates: tuple[float, ...],
    vertex: GeometryPoint,
    parabola_parameter: float,
    config: SimulationConfig,
) -> tuple[float, ...]:
    if len(candidates) <= 1:
        return candidates

    errors = [
        abs(_x_from_t(vertex, parabola_parameter, candidate) - point.x)
        for candidate in candidates
    ]
    best_error = min(errors)
    filtered = tuple(
        candidate
        for candidate, error in zip(candidates, errors)
        if abs(error - best_error) <= config.eps
    )
    return filtered or candidates


def _x_from_t(
    vertex: GeometryPoint,
    parabola_parameter: float,
    t_value: float,
) -> float:
    return vertex.x + 2.0 * parabola_parameter * t_value


def _log_segment_debug(
    focus: GeometryPoint,
    vertex: GeometryPoint,
    parabola_parameter: float,
    start_point: GeometryPoint,
    end_point: GeometryPoint,
    start_candidates: tuple[float, ...],
    end_candidates: tuple[float, ...],
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
            "t1_candidates=%s t2_candidates=%s chosen_t1=%.6f chosen_t2=%.6f"
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
        start_candidates,
        end_candidates,
        t_start,
        t_end,
    )
    _debug_segment_logs_emitted += 1


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
