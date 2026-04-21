from __future__ import annotations

import math

from app.models.region import RegionDescription


def evaluate_region(
    region: RegionDescription,
    alpha: float,
    beta: float,
) -> bool:
    if region.region_type == "predicate":
        return bool(_evaluate_expression(region.expression, alpha, beta))

    if region.region_type == "implicit":
        value = _evaluate_expression(region.expression, alpha, beta)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
        return _matches_relation(float(value), region.relation or "<=")

    return False


def evaluate_region_boundary(
    region: RegionDescription,
    alpha: float,
    beta: float,
    tolerance: float = 0.02,
) -> bool:
    value = evaluate_boundary_value(region, alpha, beta)
    if value is None:
        return False
    return abs(value) <= tolerance


def evaluate_boundary_value(
    region: RegionDescription,
    alpha: float,
    beta: float,
) -> float | None:
    if region.region_type != "boundary":
        return None

    value = _evaluate_expression(region.expression, alpha, beta)
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _evaluate_expression(
    expression: str,
    alpha: float,
    beta: float,
) -> object:
    safe_globals = {"__builtins__": {}}
    safe_locals = {
        "alpha": alpha,
        "α": alpha,
        "beta": beta,
        "β": beta,
        "pi": math.pi,
        "π": math.pi,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "sqrt": math.sqrt,
        "abs": abs,
    }

    try:
        return eval(expression, safe_globals, safe_locals)
    except Exception:
        return False


def _matches_relation(value: float, relation: str) -> bool:
    if relation == "<":
        return value < 0.0
    if relation == "<=":
        return value <= 0.0
    if relation == ">":
        return value > 0.0
    if relation == ">=":
        return value >= 0.0
    return False
