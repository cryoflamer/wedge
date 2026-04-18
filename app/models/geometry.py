from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GeometryPoint:
    x: float
    y: float


@dataclass
class WedgeWall:
    wall: int
    angle: float
    start: GeometryPoint
    end: GeometryPoint


@dataclass
class ReflectionPoint:
    step_index: int
    wall: int
    point: GeometryPoint | None
    valid: bool = True
    invalid_reason: str | None = None


@dataclass
class ParabolicSegment:
    step_index: int
    wall_from: int
    wall_to: int
    focus: GeometryPoint | None
    start_point: GeometryPoint | None
    end_point: GeometryPoint | None
    valid: bool = True
    invalid_reason: str | None = None


@dataclass
class WedgeGeometry:
    walls: list[WedgeWall] = field(default_factory=list)
    reflections: list[ReflectionPoint] = field(default_factory=list)
    segments: list[ParabolicSegment] = field(default_factory=list)
