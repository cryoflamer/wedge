from __future__ import annotations

from dataclasses import dataclass, field

from app.models.config import SimulationConfig
from app.models.orbit import Orbit
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.services.trajectory_update_planner import (
    TrajectoryUpdatePlan,
    TrajectoryUpdatePlanner,
)


@dataclass
class TrajectoryRegistry:
    """Minimal in-memory registry for active trajectories.

    This class intentionally does not know anything about Qt, rendering,
    background workers, rebuild execution, or caches. It only centralizes
    storage and delegates update decisions to TrajectoryUpdatePlanner.
    """

    _trajectories: dict[int, Orbit] = field(default_factory=dict)

    def add(self, trajectory: Orbit) -> None:
        self._trajectories[trajectory.trajectory_id] = trajectory

    def get(self, trajectory_id: int) -> Orbit | None:
        return self._trajectories.get(trajectory_id)

    def remove(self, trajectory_id: int) -> Orbit | None:
        return self._trajectories.pop(trajectory_id, None)

    def get_all(self) -> list[Orbit]:
        return list(self._trajectories.values())

    def clear(self) -> None:
        self._trajectories.clear()

    def update_metadata(
        self,
        trajectory_id: int,
        metadata: TrajectoryBuildMetadata | None,
    ) -> bool:
        trajectory = self.get(trajectory_id)
        if trajectory is None:
            return False

        trajectory.metadata = metadata
        return True

    def plan_updates(self, new_config: SimulationConfig) -> dict[int, TrajectoryUpdatePlan]:
        return {
            trajectory_id: TrajectoryUpdatePlanner.plan(trajectory.metadata, new_config)
            for trajectory_id, trajectory in self._trajectories.items()
        }
