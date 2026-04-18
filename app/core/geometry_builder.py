from __future__ import annotations

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

    _sync_reflection_points_with_segments(geometry)
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

    start_point = _resolve_segment_boundary_point(
        focus=focus,
        wall=left.wall,
        other_point=right.point,
        fallback=left.point,
        config=config,
    )
    end_point = _resolve_segment_boundary_point(
        focus=focus,
        wall=right.wall,
        other_point=start_point,
        fallback=right.point,
        config=config,
    )
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
    config: SimulationConfig,
    num_samples: int = 48,
) -> list[GeometryPoint]:
    if start_point is None or end_point is None:
        return []

    denominator = 2.0 * (focus.y - 1.0)
    if abs(denominator) <= config.eps:
        return []

    x_start = start_point.x
    x_end = end_point.x
    samples: list[GeometryPoint] = []
    for index in range(num_samples + 1):
        ratio = index / num_samples
        x_coord = x_start + (x_end - x_start) * ratio
        y_coord = (
            (x_coord - focus.x) * (x_coord - focus.x) + focus.y * focus.y - 1.0
        ) / denominator

        if not math.isfinite(y_coord):
            continue
        samples.append(GeometryPoint(x=x_coord, y=y_coord))

    if samples:
        samples[0] = start_point
        samples[-1] = end_point
    return samples


def _resolve_segment_boundary_point(
    focus: GeometryPoint,
    wall: int,
    other_point: GeometryPoint | None,
    fallback: GeometryPoint | None,
    config: SimulationConfig,
) -> GeometryPoint | None:
    candidates = _wall_intersections_from_focus(focus, wall, config)
    if not candidates:
        return fallback
    if len(candidates) == 1 or other_point is None:
        return _closest_point(candidates, fallback)

    other_side = other_point.x - focus.x
    if abs(other_side) > config.eps:
        same_side = [
            candidate
            for candidate in candidates
            if (candidate.x - focus.x) * other_side >= -config.eps
        ]
        if same_side:
            return _closest_point(same_side, fallback)

    return _closest_point(candidates, fallback)


def _wall_intersections_from_focus(
    focus: GeometryPoint,
    wall: int,
    config: SimulationConfig,
) -> list[GeometryPoint]:
    angle = _wall_angle(wall, config)
    tangent = math.tan(angle)
    if abs(tangent) <= config.eps:
        return []

    slope = 1.0 / tangent
    a_coef = slope * slope
    b_coef = -2.0 * (slope * focus.x + focus.y - 1.0)
    c_coef = focus.x * focus.x + focus.y * focus.y - 1.0
    discriminant = b_coef * b_coef - 4.0 * a_coef * c_coef
    if discriminant < -config.eps:
        return []
    discriminant = max(discriminant, 0.0)

    points: list[GeometryPoint] = []
    sqrt_discriminant = math.sqrt(discriminant)
    for sign in (-1.0, 1.0):
        y_coord = (-b_coef + sign * sqrt_discriminant) / (2.0 * a_coef)
        x_coord = slope * y_coord
        if not math.isfinite(x_coord) or not math.isfinite(y_coord):
            continue
        if y_coord < -config.eps:
            continue
        point = GeometryPoint(x=x_coord, y=y_coord)
        if not any(
            abs(existing.x - point.x) <= config.eps
            and abs(existing.y - point.y) <= config.eps
            for existing in points
        ):
            points.append(point)

    points.sort(key=lambda point: point.y)
    return points


def _closest_point(
    candidates: list[GeometryPoint],
    fallback: GeometryPoint | None,
) -> GeometryPoint:
    if fallback is None:
        return candidates[-1]

    return min(
        candidates,
        key=lambda point: math.hypot(point.x - fallback.x, point.y - fallback.y),
    )


def _sync_reflection_points_with_segments(geometry: WedgeGeometry) -> None:
    if not geometry.segments:
        return

    first_segment = geometry.segments[0]
    if first_segment.valid and first_segment.start_point is not None:
        first_reflection = geometry.reflections[0]
        first_reflection.point = first_segment.start_point
        first_reflection.valid = True
        first_reflection.invalid_reason = None

    for index, segment in enumerate(geometry.segments):
        if (
            not segment.valid
            or segment.end_point is None
            or index + 1 >= len(geometry.reflections)
        ):
            continue

        reflection = geometry.reflections[index + 1]
        reflection.point = segment.end_point
        reflection.valid = True
        reflection.invalid_reason = None


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
