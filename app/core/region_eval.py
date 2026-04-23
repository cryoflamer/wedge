from __future__ import annotations

import ast
import math

from app.models.scene_item import SceneItemDescription, scene_item_from_region


def evaluate_region(
    region,
    alpha: float,
    beta: float,
    eps: float = 1.0e-9,
) -> bool:
    # Compatibility entrypoint only. New runtime paths should pass
    # SceneItemDescription to evaluate_scene_item(); legacy RegionDescription
    # objects are adapted at this boundary and must not become runtime state.
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
    # Unified evaluator entrypoint. Keep semantics expression + relation based:
    # do not reintroduce region_type dispatch here or in render/UI paths.
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
    # Compatibility helper for boundary rendering. It still consumes the unified
    # SceneItem model after adaptation; relation "=" is the only boundary test.
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


def validate_scene_item_expression(expression: str) -> tuple[bool, str | None]:
    if not expression.strip():
        return False, "empty expression"
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return False, exc.msg

    try:
        value = eval(
            compile(tree, "<scene-item-expression>", "eval"),
            {"__builtins__": {}},
            _expression_locals(math.pi / 4.0, math.pi / 2.0),
        )
    except Exception as exc:
        return False, str(exc) or type(exc).__name__
    if not isinstance(value, (bool, int, float)):
        return False, "expression must evaluate to a number or boolean"
    if isinstance(value, (int, float)) and not math.isfinite(float(value)):
        return False, "expression must evaluate to a finite value"
    return True, None


def _expression_locals(alpha: float, beta: float) -> dict[str, object]:
    return {
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


def _evaluate_expression(
    expression: str,
    alpha: float,
    beta: float,
) -> object:
    safe_globals = {"__builtins__": {}}
    safe_locals = _expression_locals(alpha, beta)

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
