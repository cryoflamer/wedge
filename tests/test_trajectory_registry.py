import unittest

from app.models.config import SimulationConfig
from app.models.orbit import Orbit
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.services.trajectory_registry import TrajectoryRegistry
from app.services.trajectory_update_planner import TrajectoryUpdateDecision


def make_config(**overrides):
    values = {
        "alpha": 0.5,
        "beta": 1.0,
        "n_phase_default": 100,
        "n_geom_default": 10,
        "eps": 1.0e-9,
        "native_enabled": True,
        "native_sample_mode": "every_n",
        "native_sample_step": 1,
    }
    values.update(overrides)
    return SimulationConfig(**values)


def make_metadata(config=None, **overrides):
    config = config or make_config()
    values = {
        "fingerprint": SimulationFingerprint.from_config(config),
        "phase_steps": config.n_phase_default,
        "geom_steps": config.n_geom_default,
        "backend_used": "native",
        "completed_steps": config.n_phase_default,
    }
    values.update(overrides)
    return TrajectoryBuildMetadata(**values)


class TrajectoryRegistryTests(unittest.TestCase):
    def test_registry_stores_and_returns_trajectories(self):
        registry = TrajectoryRegistry()
        orbit = Orbit(trajectory_id=1)

        registry.add(orbit)

        self.assertIs(registry.get(1), orbit)
        self.assertEqual(registry.get_all(), [orbit])

    def test_remove_returns_removed_trajectory(self):
        registry = TrajectoryRegistry()
        orbit = Orbit(trajectory_id=1)
        registry.add(orbit)

        removed = registry.remove(1)

        self.assertIs(removed, orbit)
        self.assertIsNone(registry.get(1))

    def test_clear_removes_all_trajectories(self):
        registry = TrajectoryRegistry()
        registry.add(Orbit(trajectory_id=1))
        registry.add(Orbit(trajectory_id=2))

        registry.clear()

        self.assertEqual(registry.get_all(), [])

    def test_update_metadata_updates_existing_trajectory(self):
        registry = TrajectoryRegistry()
        orbit = Orbit(trajectory_id=1)
        metadata = make_metadata()
        registry.add(orbit)

        updated = registry.update_metadata(1, metadata)

        self.assertTrue(updated)
        self.assertIs(orbit.metadata, metadata)

    def test_update_metadata_returns_false_for_missing_trajectory(self):
        registry = TrajectoryRegistry()

        updated = registry.update_metadata(99, make_metadata())

        self.assertFalse(updated)

    def test_plan_updates_uses_planner_for_all_trajectories(self):
        config = make_config()
        registry = TrajectoryRegistry()
        registry.add(Orbit(trajectory_id=1, metadata=make_metadata(config)))
        registry.add(Orbit(trajectory_id=2, metadata=make_metadata(config, phase_steps=50)))
        registry.add(Orbit(trajectory_id=3))

        plans = registry.plan_updates(config)

        self.assertEqual(plans[1].decision, TrajectoryUpdateDecision.UNCHANGED)
        self.assertEqual(plans[2].decision, TrajectoryUpdateDecision.EXTEND)
        self.assertEqual(plans[3].decision, TrajectoryUpdateDecision.REBUILD)


if __name__ == "__main__":
    unittest.main()
