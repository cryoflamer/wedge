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

    if segment_count <= 0:
        return geometry

    candidate_pairs = [
        _parabola_candidates_from_state(state, config)
        for state in states[: reflection_count]
    ]
    first_match = _match_candidate_pair(
        candidate_pairs[0],
        candidate_pairs[1],
        config,
    )
    if first_match is None:
        for orbit_point, left, right in zip(
            segment_points,
            geometry.reflections,
            geometry.reflections[1 : segment_count + 1],
        ):
            geometry.segments.append(
                _invalid_segment(
                    step_index=orbit_point.step_index,
                    left=left,
                    right=right,
                    reason="parabola_match_failed",
                )
            )
        return geometry

    first_index, next_index, first_distance = first_match
    if first_distance > _PARABOLA_MATCH_TOLERANCE:
        logger.warning(
            "Initial parabola match exceeds tolerance: %.6e",
            first_distance,
        )

    active_index = 1 - next_index
    left = geometry.reflections[0]
    right = geometry.reflections[1]
    geometry.segments.append(
        _build_segment(
            step_index=segment_points[0].step_index,
            left=left,
            right=right,
            current_candidate=candidate_pairs[0][first_index],
            next_candidate=candidate_pairs[1][next_index],
            config=config,
        )
    )

    for segment_offset in range(1, segment_count):
        orbit_point = segment_points[segment_offset]
        left = geometry.reflections[segment_offset]
        right = geometry.reflections[segment_offset + 1]
        current_pair = candidate_pairs[segment_offset]
        next_pair = candidate_pairs[segment_offset + 1]
        current_candidate = current_pair[active_index]
        next_match = _match_active_candidate(
            current_candidate,
            next_pair,
            config,
        )
        if next_match is None:
            geometry.segments.append(
                _invalid_segment(
                    step_index=orbit_point.step_index,
                    left=left,
                    right=right,
                    reason="parabola_chain_failed",
                )
            )
            break

        next_index, distance = next_match
        if distance > _PARABOLA_MATCH_TOLERANCE:
            logger.warning(
                "Parabola chain match exceeds tolerance at step %s: %.6e",
                orbit_point.step_index,
                distance,
            )

        geometry.segments.append(
            _build_segment(
                step_index=orbit_point.step_index,
                left=left,
                right=right,
                current_candidate=current_candidate,
                next_candidate=next_pair[next_index],
                config=config,
            )
        )
        active_index = 1 - next_index

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


class _ParabolaCandidate:
    def __init__(
        self,
        x: float,
        y: float,
        u: float,
        sign: int,
    ) -> None:
        self.x = x
        self.y = y
        self.u = u
        self.sign = sign


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
    current_candidate: _ParabolaCandidate,
    next_candidate: _ParabolaCandidate,
    config: SimulationConfig,
) -> ParabolicSegment:
    focus = GeometryPoint(x=current_candidate.x, y=current_candidate.y)
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

    samples = _build_parabola_samples(
        current_candidate=current_candidate,
        next_candidate=next_candidate,
        start_point=start_point,
        end_point=end_point,
        config=config,
    )
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


def _parabola_candidates_from_state(
    state: PhaseState,
    config: SimulationConfig,
) -> tuple[_ParabolaCandidate, _ParabolaCandidate] | None:
    theta = _wall_angle(state.wall, config)
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    sin_2_theta = math.sin(2.0 * theta)
    if abs(sin_2_theta) <= config.eps or state.d <= config.eps:
        return None

    candidates: list[_ParabolaCandidate] = []
    for sign in (-1, 1):
        a_term = state.d * sin_theta + sign * state.tau * cos_theta
        y_coord = 1.0 - (a_term * a_term) / state.d
        x_coord = (
            1.0
            + y_coord * math.cos(2.0 * theta)
            - state.d
        ) / sin_2_theta
        b_term = state.d * cos_theta - sign * state.tau * sin_theta
        u_value = (a_term * b_term) / state.d
        if (
            not math.isfinite(x_coord)
            or not math.isfinite(y_coord)
            or not math.isfinite(u_value)
        ):
            return None
        candidates.append(
            _ParabolaCandidate(
                x=x_coord,
                y=y_coord,
                u=u_value,
                sign=sign,
            )
        )

    return candidates[0], candidates[1]


def _candidate_distance(
    left: _ParabolaCandidate,
    right: _ParabolaCandidate,
) -> float:
    return math.hypot(left.x - right.x, left.y - right.y)


def _match_candidate_pair(
    current_pair: tuple[_ParabolaCandidate, _ParabolaCandidate] | None,
    next_pair: tuple[_ParabolaCandidate, _ParabolaCandidate] | None,
    config: SimulationConfig,
) -> tuple[int, int, float] | None:
    if current_pair is None or next_pair is None:
        return None

    best_match: tuple[int, int, float] | None = None
    for current_index, current_candidate in enumerate(current_pair):
        for next_index, next_candidate in enumerate(next_pair):
            distance = _candidate_distance(current_candidate, next_candidate)
            if best_match is None or distance < best_match[2]:
                best_match = (current_index, next_index, distance)
    return best_match


def _match_active_candidate(
    active_candidate: _ParabolaCandidate,
    next_pair: tuple[_ParabolaCandidate, _ParabolaCandidate] | None,
    config: SimulationConfig,
) -> tuple[int, float] | None:
    if next_pair is None:
        return None

    distances = [
        _candidate_distance(active_candidate, candidate)
        for candidate in next_pair
    ]
    best_index = 0 if distances[0] <= distances[1] else 1
    return best_index, distances[best_index]


def _build_parabola_samples(
    current_candidate: _ParabolaCandidate,
    next_candidate: _ParabolaCandidate,
    start_point: GeometryPoint | None,
    end_point: GeometryPoint | None,
    config: SimulationConfig,
    num_samples: int = 48,
) -> list[GeometryPoint]:
    if start_point is None or end_point is None:
        return []

    denominator = 2.0 * (1.0 - current_candidate.y)
    if abs(denominator) <= config.eps:
        return []

    _log_segment_debug(
        current_candidate=current_candidate,
        next_candidate=next_candidate,
        start_point=start_point,
        end_point=end_point,
    )

    samples: list[GeometryPoint] = []
    for index in range(num_samples + 1):
        ratio = index / num_samples
        u_value = current_candidate.u + (
            next_candidate.u - current_candidate.u
        ) * ratio
        x_coord = current_candidate.x + u_value
        y_coord = ((1.0 + current_candidate.y) / 2.0) - (
            (u_value * u_value) / denominator
        )

        if not math.isfinite(x_coord) or not math.isfinite(y_coord):
            continue
        samples.append(GeometryPoint(x=x_coord, y=y_coord))

    if samples:
        samples[0] = start_point
        samples[-1] = end_point
    return samples


def _log_segment_debug(
    current_candidate: _ParabolaCandidate,
    next_candidate: _ParabolaCandidate,
    start_point: GeometryPoint,
    end_point: GeometryPoint,
) -> None:
    global _debug_segment_logs_emitted

    if _debug_segment_logs_emitted >= _DEBUG_SEGMENT_LOG_LIMIT:
        return

    logger.info(
        (
            "Wedge segment: current=(X=%.6f, Y=%.6f, u=%.6f, sign=%d) "
            "next=(X=%.6f, Y=%.6f, u=%.6f, sign=%d) "
            "match=%.6e "
            "start=(%.6f, %.6f) end=(%.6f, %.6f) "
            "start_delta=%.6e end_delta=%.6e"
        ),
        current_candidate.x,
        current_candidate.y,
        current_candidate.u,
        current_candidate.sign,
        next_candidate.x,
        next_candidate.y,
        next_candidate.u,
        next_candidate.sign,
        _candidate_distance(current_candidate, next_candidate),
        start_point.x,
        start_point.y,
        end_point.x,
        end_point.y,
        _point_delta(current_candidate, start_point),
        _point_delta(next_candidate, end_point),
    )
    _debug_segment_logs_emitted += 1


def _point_delta(
    candidate: _ParabolaCandidate,
    point: GeometryPoint,
) -> float:
    denominator = 2.0 * (1.0 - candidate.y)
    if abs(denominator) <= 1.0e-12:
        return float("nan")
    x_coord = candidate.x + candidate.u
    y_coord = ((1.0 + candidate.y) / 2.0) - (
        (candidate.u * candidate.u) / denominator
    )
    return math.hypot(x_coord - point.x, y_coord - point.y)


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
