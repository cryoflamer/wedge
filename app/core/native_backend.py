from __future__ import annotations

from typing import Any

try:
    from app.core.native_engine import _native_engine as _native_module
except Exception:
    _native_module = None


def is_native_available() -> bool:
    if _native_module is None:
        return False
    try:
        return bool(_native_module.native_backend_available())
    except Exception:
        return False


def add_ints(a: int, b: int) -> int:
    if _native_module is None:
        raise RuntimeError("native backend is not available")
    return int(_native_module.add_ints(a, b))


def native_build_dense_orbit(
    d0: float,
    tau0: float,
    wall0: int,
    alpha: float,
    beta: float,
    steps: int,
) -> dict[str, Any]:
    if _native_module is None:
        raise RuntimeError("native backend is not available")
    result = _native_module.native_build_dense_orbit(
        float(d0),
        float(tau0),
        int(wall0),
        float(alpha),
        float(beta),
        int(steps),
    )
    return dict(result)


def native_build_sparse_orbit(
    d0: float,
    tau0: float,
    wall0: int,
    alpha: float,
    beta: float,
    steps: int,
    sample_step: int,
    sample_mode: str,
) -> dict[str, Any]:
    if _native_module is None:
        raise RuntimeError("native backend is not available")
    result = _native_module.native_build_sparse_orbit(
        float(d0),
        float(tau0),
        int(wall0),
        float(alpha),
        float(beta),
        int(steps),
        int(sample_step),
        str(sample_mode),
    )
    return dict(result)
