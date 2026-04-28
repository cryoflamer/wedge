from __future__ import annotations

from dataclasses import dataclass

from app.models.simulation_fingerprint import SimulationFingerprint


@dataclass
class TrajectoryBuildMetadata:
    """Metadata describing how a trajectory orbit was built."""

    fingerprint: SimulationFingerprint
    phase_steps: int
    geom_steps: int
    backend_used: str = "python"
    completed_steps: int = 0
