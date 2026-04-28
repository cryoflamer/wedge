from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from app.core.trajectory_engine import (
    build_dense_orbit_for_geometry,
    build_orbit,
    build_wedge_geometry,
)
from app.models.config import Config, SimulationConfig
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.models.trajectory import TrajectorySeed
from app.services.trajectory_metadata_builder import build_metadata_from_config
from app.services.trajectory_update_planner import (
    TrajectoryUpdateDecision,
    TrajectoryUpdatePlan,
    TrajectoryUpdatePlanner,
)


class TrajectoryService:
    def __init__(self, config_provider: Callable[[], Config]) -> None:
        self._config_provider = config_provider
        self.seeds: dict[int, TrajectorySeed] = {}
        self.orbits: dict[int, Orbit] = {}
        self.geometries: dict[int, WedgeGeometry] = {}

    def get_seeds(self) -> dict[int, TrajectorySeed]:
        return self.seeds

    def get_orbits(self) -> dict[int, Orbit]:
        return self.orbits

    def build_orbit(self, seed: TrajectorySeed) -> Orbit:
        config = self._config_provider()
        orbit = build_orbit(
            seed=seed,
            config=config.simulation,
            steps=max(
                config.simulation.n_phase_default,
                config.simulation.n_geom_default + 1,
            ),
        )
        orbit.metadata = self._build_metadata_for_orbit(orbit)
        return orbit

    def _build_metadata_for_orbit(self, orbit: Orbit) -> TrajectoryBuildMetadata:
        config = self._config_provider()
        metadata = build_metadata_from_config(config.simulation)
        return replace(metadata, completed_steps=orbit.completed_steps)

    def build_geometry(self, orbit: Orbit) -> WedgeGeometry:
        config = self._config_provider()
        return build_wedge_geometry(
            orbit=orbit,
            config=config.simulation,
            max_reflections=config.simulation.n_geom_default,
        )

    def build_geometry_orbit(self, seed: TrajectorySeed) -> Orbit:
        config = self._config_provider()
        return build_dense_orbit_for_geometry(
            seed=seed,
            config=config.simulation,
            steps=max(1, config.simulation.n_geom_default + 1),
        )

    def rebuild_orbits(self) -> None:
        self.orbits = {
            trajectory_id: self.build_orbit(seed)
            for trajectory_id, seed in self.seeds.items()
        }
        self.geometries = {
            trajectory_id: self.build_geometry_orbit(seed)
            for trajectory_id, seed in self.seeds.items()
        }
        self.geometries = {
            trajectory_id: self.build_geometry(orbit)
            for trajectory_id, orbit in self.geometries.items()
        }

    def add_built_seed(self, seed: TrajectorySeed) -> None:
        self.seeds[seed.id] = seed
        self.orbits[seed.id] = self.build_orbit(seed)
        self.geometries[seed.id] = self.build_geometry(self.build_geometry_orbit(seed))

    def add_pending_seed(self, seed: TrajectorySeed) -> None:
        self.seeds[seed.id] = seed
        self.orbits[seed.id] = Orbit(trajectory_id=seed.id)
        self.geometries[seed.id] = WedgeGeometry()

    def add_trajectory(self, seed: TrajectorySeed, *, pending: bool = False) -> None:
        if pending:
            self.add_pending_seed(seed)
            return
        self.add_built_seed(seed)

    def update_seed_values(
        self,
        trajectory_id: int,
        d_value: float,
        tau_value: float,
    ) -> TrajectorySeed | None:
        seed = self.seeds.get(trajectory_id)
        if seed is None:
            return None
        seed.d0 = d_value
        seed.tau0 = tau_value
        return seed

    def reset_pending_result(self, trajectory_id: int) -> None:
        self.orbits[trajectory_id] = Orbit(trajectory_id=trajectory_id)
        self.geometries[trajectory_id] = WedgeGeometry()

    def plan_updates(
        self,
        new_config: SimulationConfig | None = None,
    ) -> dict[int, TrajectoryUpdatePlan]:
        """Return read-only update plans for all currently stored orbits."""
        simulation_config = new_config or self._config_provider().simulation
        desired_metadata = build_metadata_from_config(simulation_config)
        return {
            trajectory_id: TrajectoryUpdatePlanner.plan_metadata(orbit.metadata, desired_metadata)
            for trajectory_id, orbit in self.orbits.items()
        }

    def apply_updates(
        self,
        new_config: SimulationConfig | None = None,
    ) -> dict[int, TrajectoryUpdatePlan]:
        """Apply the minimal supported update decisions and return all plans.

        This execution layer supports REBUILD, REDRAW, and UNCHANGED. Extend
        and truncate decisions are still planned but left untouched for later
        focused patches.
        """
        simulation_config = new_config or self._config_provider().simulation
        desired_metadata = build_metadata_from_config(simulation_config)
        plans = self.plan_updates(simulation_config)
        for trajectory_id, plan in plans.items():
            if plan.decision == TrajectoryUpdateDecision.UNCHANGED:
                continue

            seed = self.seeds.get(trajectory_id)
            if seed is None:
                continue

            if plan.decision == TrajectoryUpdateDecision.REBUILD:
                self.orbits[trajectory_id] = self.build_orbit(seed)
                self.geometries[trajectory_id] = self.build_geometry(self.build_geometry_orbit(seed))
                continue

            if plan.decision == TrajectoryUpdateDecision.REDRAW:
                orbit = self.orbits.get(trajectory_id)
                if orbit is None or orbit.metadata is None:
                    continue

                self.geometries[trajectory_id] = self.build_geometry(self.build_geometry_orbit(seed))
                orbit.metadata = replace(
                    desired_metadata,
                    completed_steps=orbit.metadata.completed_steps,
                )

        return plans

    def remove_trajectory(self, trajectory_id: int) -> None:
        self.seeds.pop(trajectory_id, None)
        self.orbits.pop(trajectory_id, None)
        self.geometries.pop(trajectory_id, None)

    def clear_trajectories(self) -> None:
        self.seeds.clear()
        self.orbits.clear()
        self.geometries.clear()

    def load_trajectories(self, seeds: dict[int, TrajectorySeed]) -> None:
        self.seeds = seeds

    def initialize_pending_for_all(self) -> None:
        self.orbits = {
            trajectory_id: Orbit(trajectory_id=trajectory_id)
            for trajectory_id in self.seeds
        }
        self.geometries = {
            trajectory_id: WedgeGeometry()
            for trajectory_id in self.seeds
        }

    def clear_results(self) -> None:
        self.orbits = {}
        self.geometries = {}

    def apply_partial_result(
        self,
        trajectory_id: int,
        seed: TrajectorySeed,
        orbit: Orbit,
        geometry: WedgeGeometry,
    ) -> None:
        if orbit.metadata is None:
            orbit.metadata = self._build_metadata_for_orbit(orbit)
        self.seeds[trajectory_id] = seed
        self.orbits[trajectory_id] = orbit
        self.geometries[trajectory_id] = geometry
