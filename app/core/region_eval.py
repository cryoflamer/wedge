from __future__ import annotations

import math

from app.models.region import RegionDescription


def evaluate_region_predicate(
    region: RegionDescription,
    alpha: float,
    beta: float,
) -> bool:
    safe_globals = {"__builtins__": {}}
    safe_locals = {
        "alpha": alpha,
        "beta": beta,
        "pi": math.pi,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "sqrt": math.sqrt,
        "abs": abs,
    }

    try:
        return bool(eval(region.predicate, safe_globals, safe_locals))
    except Exception:
        return False
