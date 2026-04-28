from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.models.config import SimulationConfig
from app.models.orbit import Orbit
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.services.trajectory_service import TrajectoryService
from app.services.trajectory_update_planner import TrajectoryUpdateDecision


class TrajectoryServicePlanningTests(unittest.TestCase):
    def _make_config(self, **overrides: object) -> SimulationConfig:
        values = {
            "alpha": 0.55,
            "beta": 1.05,
            "n_phase_default": 64,
            "n_geom_default": 24,
            "eps": 1.0e-9,
            "native_enabled": True,
            "native_sample_mode": "every_n",
            "native_sample_step": 4,
        }
        values.update(overrides)
        return SimulationConfig(**values)

    def _make_service(self, simulation_config: SimulationConfig) -> TrajectoryService:
        return TrajectoryService(lambda: SimpleNamespace(simulation=simulation_config))

    def _make_metadata(
        self,
        config: SimulationConfig | None = None,
        **overrides: object,
    ) -> TrajectoryBuildMetadata:
        source_config = config or self._make_config()
        values = {
            "fingerprint": SimulationFingerprint.from_config(source_config),
            "phase_steps": source_config.n_phase_default,
            "geom_steps": source_config.n_geom_default,
            "backend_used": "native" if source_config.native_enabled else "python",
            "completed_steps": source_config.n_phase_default,
        }
        values.update(overrides)
        return TrajectoryBuildMetadata(**values)

    def test_plan_updates_uses_current_config_for_all_orbits(self) -> None:
        config = self._make_config()
        service = self._make_service(config)
        service.orbits = {
            1: Orbit(trajectory_id=1, metadata=self._make_metadata(config)),
            2: Orbit(trajectory_id=2, metadata=self._make_metadata(config, phase_steps=32)),
            3: Orbit(trajectory_id=3),
        }

        plans = service.plan_updates()

        self.assertEqual(plans[1].decision, TrajectoryUpdateDecision.UNCHANGED)
        self.assertEqual(plans[2].decision, TrajectoryUpdateDecision.EXTEND)
        self.assertEqual(plans[3].decision, TrajectoryUpdateDecision.REBUILD)

    def test_plan_updates_accepts_explicit_simulation_config(self) -> None:
        current_config = self._make_config()
        changed_config = self._make_config(alpha=0.65)
        service = self._make_service(current_config)
        service.orbits = {
            1: Orbit(trajectory_id=1, metadata=self._make_metadata(current_config)),
        }

        plans = service.plan_updates(changed_config)

        self.assertEqual(plans[1].decision, TrajectoryUpdateDecision.REBUILD)

    def test_plan_updates_does_not_mutate_existing_orbits(self) -> None:
        config = self._make_config()
        metadata = self._make_metadata(config, phase_steps=32)
        orbit = Orbit(trajectory_id=1, metadata=metadata)
        service = self._make_service(config)
        service.orbits = {1: orbit}

        service.plan_updates()

        self.assertIs(service.orbits[1], orbit)
        self.assertIs(service.orbits[1].metadata, metadata)


if __name__ == "__main__":
    unittest.main()
