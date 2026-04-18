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

    trimmed_points = orbit.points[:max_reflections]
    states = [
        PhaseState(d=point.d, tau=point.tau, wall=point.wall)
        for point in trimmed_points
    ]

    for orbit_point, state in zip(trimmed_points, states):
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
        trimmed_points,
        states,
        geometry.reflections,
        geometry.reflections[1:],
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

    focus = _focus_from_state(state, config)
    if focus is None:
        return ReflectionPoint(
            step_index=step_index,
            wall=state.wall,
            point=None,
            valid=False,
            invalid_reason="focus_reconstruction_failed",
        )

    point = _intersection_with_wall(focus, _wall_angle(state.wall, config), config.eps)
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
            valid=False,
            invalid_reason=left.invalid_reason or right.invalid_reason or "segment_reconstruction_failed",
        )

    return ParabolicSegment(
        step_index=step_index,
        wall_from=left.wall,
        wall_to=right.wall,
        focus=focus,
        start_point=left.point,
        end_point=right.point,
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

    y = 1.0 - ((state.tau * math.cos(angle) + state.d * math.sin(angle)) ** 2) / state.d
    x = (1.0 + y * math.cos(2.0 * angle) - state.d) / sin_2_angle
    if not math.isfinite(x) or not math.isfinite(y):
        return None

    return GeometryPoint(x=x, y=y)


def _intersection_with_wall(
    focus: GeometryPoint,
    angle: float,
    eps: float,
) -> GeometryPoint | None:
    tangent = math.tan(angle)
    linear = 2.0 * (tangent * (1.0 - focus.y) - focus.x)
    constant = focus.x * focus.x + focus.y * focus.y - 1.0
    discriminant = linear * linear - 4.0 * constant

    if discriminant < -eps:
        return None
    discriminant = max(discriminant, 0.0)
    root = math.sqrt(discriminant)

    candidates = []
    for sign in (-1.0, 1.0):
        x = (-linear + sign * root) / 2.0
        y = tangent * x
        if x >= -eps and y >= -eps and y <= 1.0 + eps:
            candidates.append(GeometryPoint(x=x, y=y))

    if not candidates:
        return None

    return min(candidates, key=lambda point: point.y)


def _wall_angle(wall: int, config: SimulationConfig) -> float:
    return config.alpha if wall == 1 else config.beta
