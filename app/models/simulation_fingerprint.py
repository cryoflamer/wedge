from __future__ import annotations

from dataclasses import dataclass

from app.models.config import SimulationConfig


@dataclass(frozen=True)
class SimulationFingerprint:
    """Immutable fingerprint for simulation parameters that affect trajectory dynamics."""

    alpha: float
    beta: float
    eps: float
    native_enabled: bool
    native_sample_mode: str
    native_sample_step: int

    @classmethod
    def from_config(cls, config: SimulationConfig) -> "SimulationFingerprint":
        return cls(
            alpha=config.alpha,
            beta=config.beta,
            eps=config.eps,
            native_enabled=config.native_enabled,
            native_sample_mode=config.native_sample_mode,
            native_sample_step=config.native_sample_step,
        )
