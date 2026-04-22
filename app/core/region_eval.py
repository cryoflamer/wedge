from __future__ import annotations

import math

from app.models.scene_item import SceneItemDescription, scene_item_from_region


def evaluate_region(
    region,
    alpha: float,
    beta: float,
    eps: float = 1.0e-9,
) -> bool:
    scene_item = (
        region
        if isinstance(region, SceneItemDescription)
        else scene_item_from_region(region)
    )
    return evaluate_scene_item(
        scene_item,
        alpha,
        beta,
        eps=eps,
    )


def evaluate_scene_item(
    item: SceneItemDescription,
    alpha: float,
    beta: float,
    *,
    eps: float = 1.0e-9,
) -> bool:
    value = evaluate_scene_item_value(item, alpha, beta)
    if item.compatibility_predicate and item.relation is None:
        return bool(value)
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    relation = item.relation or "<="
    return matches_relation(float(value), relation, eps)


def evaluate_region_boundary(
    region,
    alpha: float,
    beta: float,
    tolerance: float = 0.02,
) -> bool:
    return evaluate_region(region, alpha, beta, eps=tolerance)


def evaluate_boundary_value(
    region,
    alpha: float,
    beta: float,
) -> float | None:
    item = (
        region
        if isinstance(region, SceneItemDescription)
        else scene_item_from_region(region)
    )
    if item.relation != "=" or item.compatibility_predicate:
        return None

    value = evaluate_scene_item_value(item, alpha, beta)
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def evaluate_scene_item_value(
    item: SceneItemDescription,
    alpha: float,
    beta: float,
) -> object:
    return _evaluate_expression(item.expression, alpha, beta)


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


def matches_relation(value: float, relation: str, eps: float = 1.0e-9) -> bool:
    if relation == "=":
        return abs(value) <= eps
    if relation == "<":
        return value < 0.0
    if relation == "<=":
        return value <= 0.0 or abs(value) <= eps
    if relation == ">":
        return value > 0.0
    if relation == ">=":
        return value >= 0.0 or abs(value) <= eps
    return False
