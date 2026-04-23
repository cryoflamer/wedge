from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.region_eval import evaluate_scene_item_value
from app.models.scene_item import SceneItemDescription


@dataclass(frozen=True)
class BoundarySegment:
    start_alpha: float
    start_beta: float
    end_alpha: float
    end_beta: float


@dataclass(frozen=True)
class ActivePointConstraint:
    kind: str
    region_name: str | None = None
    boundary_segments: tuple[BoundarySegment, ...] = ()


def project_point_to_constraint(
    alpha: float,
    beta: float,
    constraint: ActivePointConstraint | None,
) -> tuple[float, float]:
    if constraint is None:
        return alpha, beta

    if constraint.kind == "symmetry":
        projected_alpha = min(
            max(alpha, _nextafter(0.0, 1.0)),
            _nextafter(math.pi / 2.0, 0.0),
        )
        projected_beta = _nextafter(math.pi - projected_alpha, projected_alpha)
        return projected_alpha, projected_beta

    if constraint.kind == "boundary" and constraint.boundary_segments:
        return project_point_to_boundary(alpha, beta, constraint.boundary_segments)

    return alpha, beta


def project_point_to_nearest_constraint(
    alpha: float,
    beta: float,
    constraints: tuple[ActivePointConstraint, ...] | list[ActivePointConstraint],
) -> tuple[float, float]:
    best_point = (alpha, beta)
    best_distance = math.inf
    for constraint in constraints:
        point = project_point_to_constraint(alpha, beta, constraint)
        distance = math.hypot(point[0] - alpha, point[1] - beta)
        if distance < best_distance:
            best_distance = distance
            best_point = point
    return best_point


def project_point_to_boundary(
    alpha: float,
    beta: float,
    boundary_segments: tuple[BoundarySegment, ...] | list[BoundarySegment],
) -> tuple[float, float]:
    best_point = (alpha, beta)
    best_distance = math.inf
    for segment in boundary_segments:
        point = _project_point_to_segment(alpha, beta, segment)
        distance = math.hypot(point[0] - alpha, point[1] - beta)
        if distance < best_distance:
            best_distance = distance
            best_point = point
    return best_point


def build_boundary_segments(
    item: SceneItemDescription,
    is_inside_domain,
    alpha_steps: int = 160,
    beta_steps: int = 320,
) -> list[BoundarySegment]:
    alpha_values = [
        (math.pi / 2.0) * index / alpha_steps
        for index in range(alpha_steps + 1)
    ]
    beta_values = [
        math.pi * index / beta_steps
        for index in range(beta_steps + 1)
    ]

    value_grid: list[list[float | None]] = []
    for alpha in alpha_values:
        row: list[float | None] = []
        for beta in beta_values:
            if not is_inside_domain(alpha, beta):
                row.append(None)
                continue
            value = evaluate_scene_item_value(item, alpha, beta)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                row.append(None)
                continue
            row.append(float(value))
        value_grid.append(row)

    segments: list[BoundarySegment] = []
    for alpha_index in range(alpha_steps):
        alpha0 = alpha_values[alpha_index]
        alpha1 = alpha_values[alpha_index + 1]
        for beta_index in range(beta_steps):
            beta0 = beta_values[beta_index]
            beta1 = beta_values[beta_index + 1]

            corners = [
                (alpha0, beta0, value_grid[alpha_index][beta_index]),
                (alpha1, beta0, value_grid[alpha_index + 1][beta_index]),
                (alpha1, beta1, value_grid[alpha_index + 1][beta_index + 1]),
                (alpha0, beta1, value_grid[alpha_index][beta_index + 1]),
            ]
            if any(value is None for _, _, value in corners):
                continue

            crossings: list[tuple[float, float]] = []
            for start_index, end_index in ((0, 1), (1, 2), (2, 3), (3, 0)):
                crossing = _edge_crossing(
                    corners[start_index],
                    corners[end_index],
                    is_inside_domain,
                )
                if crossing is not None:
                    crossings.append(crossing)

            if len(crossings) == 2:
                segments.append(
                    BoundarySegment(
                        start_alpha=crossings[0][0],
                        start_beta=crossings[0][1],
                        end_alpha=crossings[1][0],
                        end_beta=crossings[1][1],
                    )
                )
            elif len(crossings) == 4:
                center_alpha = 0.5 * (alpha0 + alpha1)
                center_beta = 0.5 * (beta0 + beta1)
                center_value = evaluate_boundary_value(
                    item,
                    center_alpha,
                    center_beta,
                )
                if center_value is None:
                    continue
                pairings = ((0, 1), (2, 3)) if center_value >= 0.0 else ((0, 3), (1, 2))
                for start_index, end_index in pairings:
                    segments.append(
                        BoundarySegment(
                            start_alpha=crossings[start_index][0],
                            start_beta=crossings[start_index][1],
                            end_alpha=crossings[end_index][0],
                            end_beta=crossings[end_index][1],
                        )
                    )

    return segments


def evaluate_boundary_value(
    item: SceneItemDescription,
    alpha: float,
    beta: float,
) -> float | None:
    value = evaluate_scene_item_value(item, alpha, beta)
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _project_point_to_segment(
    alpha: float,
    beta: float,
    segment: BoundarySegment,
) -> tuple[float, float]:
    dx = segment.end_alpha - segment.start_alpha
    dy = segment.end_beta - segment.start_beta
    length_sq = dx * dx + dy * dy
    if length_sq <= 1.0e-18:
        return segment.start_alpha, segment.start_beta

    ratio = (
        ((alpha - segment.start_alpha) * dx) + ((beta - segment.start_beta) * dy)
    ) / length_sq
    ratio = min(max(ratio, 0.0), 1.0)
    return (
        segment.start_alpha + ratio * dx,
        segment.start_beta + ratio * dy,
    )


def _edge_crossing(
    start: tuple[float, float, float | None],
    end: tuple[float, float, float | None],
    is_inside_domain,
    epsilon: float = 1.0e-12,
) -> tuple[float, float] | None:
    alpha0, beta0, value0 = start
    alpha1, beta1, value1 = end
    if value0 is None or value1 is None:
        return None

    if abs(value0) <= epsilon and abs(value1) <= epsilon:
        return None
    if abs(value0) <= epsilon:
        return alpha0, beta0
    if abs(value1) <= epsilon:
        return alpha1, beta1
    if value0 * value1 > 0.0:
        return None

    ratio = value0 / (value0 - value1)
    alpha = alpha0 + ratio * (alpha1 - alpha0)
    beta = beta0 + ratio * (beta1 - beta0)
    if not is_inside_domain(alpha, beta):
        return None
    return alpha, beta


def _nextafter(value: float, target: float) -> float:
    if hasattr(math, "nextafter"):
        return math.nextafter(value, target)

    epsilon = 1.0e-15
    if target > value:
        return value + epsilon
    if target < value:
        return value - epsilon
    return value
