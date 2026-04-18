from __future__ import annotations

import math
import random


def generate_scan_points(
    mode: str,
    count: int,
    d_min: float,
    d_max: float,
    tau_min: float,
    tau_max: float,
) -> list[tuple[float, float]]:
    normalized_mode = mode.strip().lower()
    if count <= 0:
        return []

    if normalized_mode == "random":
        return _random_points(count, d_min, d_max, tau_min, tau_max)
    return _grid_points(count, d_min, d_max, tau_min, tau_max)


def _grid_points(
    count: int,
    d_min: float,
    d_max: float,
    tau_min: float,
    tau_max: float,
) -> list[tuple[float, float]]:
    columns = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / columns))
    d_step = (d_max - d_min) / columns
    tau_step = (tau_max - tau_min) / rows
    points: list[tuple[float, float]] = []

    for row in range(rows):
        tau_value = tau_min + (row + 0.5) * tau_step
        for column in range(columns):
            d_value = d_min + (column + 0.5) * d_step
            points.append((d_value, tau_value))
            if len(points) >= count:
                return points

    return points


def _random_points(
    count: int,
    d_min: float,
    d_max: float,
    tau_min: float,
    tau_max: float,
) -> list[tuple[float, float]]:
    return [
        (
            random.uniform(d_min, d_max),
            random.uniform(tau_min, tau_max),
        )
        for _ in range(count)
    ]

