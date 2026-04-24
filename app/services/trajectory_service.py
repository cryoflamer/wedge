from __future__ import annotations

from collections.abc import Callable

from app.core.trajectory_engine import build_orbit, build_wedge_geometry
from app.models.config import Config
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed


class TrajectoryService:
    def __init__(self, config_provider: Callable[[], Config]) -> None:
        self._config_provider = config_provider
        self.seeds: dict[int, TrajectorySeed] = {}
        self.orbits: dict[int, Orbit] = {}
        self.geometries: dict[int, WedgeGeometry] = {}

    def build_orbit(self, seed: TrajectorySeed) -> Orbit:
        config = self._config_provider()
        return build_orbit(
            seed=seed,
            config=config.simulation,
            steps=max(
                config.simulation.n_phase_default,
                config.simulation.n_geom_default + 1,
            ),
        )

    def build_geometry(self, orbit: Orbit) -> WedgeGeometry:
        config = self._config_provider()
        return build_wedge_geometry(
            orbit=orbit,
            config=config.simulation,
            max_reflections=config.simulation.n_geom_default,
        )

    def rebuild_orbits(self) -> None:
        self.orbits = {
            trajectory_id: self.build_orbit(seed)
            for trajectory_id, seed in self.seeds.items()
        }
        self.geometries = {
            trajectory_id: self.build_geometry(orbit)
            for trajectory_id, orbit in self.orbits.items()
        }
