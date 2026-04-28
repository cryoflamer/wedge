from __future__ import annotations

from app.models.config import SimulationConfig
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory_metadata import TrajectoryBuildMetadata


def build_metadata_from_config(config: SimulationConfig) -> TrajectoryBuildMetadata:
    """Build the desired trajectory metadata contract for a simulation config.

    This function is intentionally pure: it does not inspect existing orbits,
    execute rebuilds, mutate UI state, or update caches. It only translates the
    desired simulation config into the metadata shape consumed by the planner.
    """
    phase_steps = config.n_phase_default
    return TrajectoryBuildMetadata(
        fingerprint=SimulationFingerprint.from_config(config),
        phase_steps=phase_steps,
        geom_steps=config.n_geom_default,
        backend_used="native" if config.native_enabled else "python",
        completed_steps=phase_steps,
    )
