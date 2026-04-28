from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.models.config import SimulationConfig
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory import TrajectorySeed
from app.services.trajectory_service import TrajectoryService


class TrajectoryServiceMetadataTests(unittest.TestCase):
    def _make_simulation_config(self, **overrides: object) -> SimulationConfig:
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

    def test_build_orbit_attaches_metadata_from_current_config(self) -> None:
        simulation_config = self._make_simulation_config()
        service = self._make_service(simulation_config)
        seed = TrajectorySeed(id=7, wall_start=0, d0=0.1, tau0=0.2)
        built_orbit = Orbit(trajectory_id=seed.id, completed_steps=17)

        with patch("app.services.trajectory_service.build_orbit", return_value=built_orbit) as build_mock:
            orbit = service.build_orbit(seed)

        self.assertIs(orbit, built_orbit)
        self.assertIsNotNone(orbit.metadata)
        self.assertEqual(orbit.metadata.fingerprint, SimulationFingerprint.from_config(simulation_config))
        self.assertEqual(orbit.metadata.phase_steps, 64)
        self.assertEqual(orbit.metadata.geom_steps, 24)
        self.assertEqual(orbit.metadata.backend_used, "native")
        self.assertEqual(orbit.metadata.completed_steps, 17)
        build_mock.assert_called_once_with(
            seed=seed,
            config=simulation_config,
            steps=64,
        )

    def test_build_orbit_respects_geometry_step_requirement_when_larger(self) -> None:
        simulation_config = self._make_simulation_config(n_phase_default=16, n_geom_default=24)
        service = self._make_service(simulation_config)
        seed = TrajectorySeed(id=8, wall_start=1, d0=0.3, tau0=0.4)

        with patch(
            "app.services.trajectory_service.build_orbit",
            return_value=Orbit(trajectory_id=seed.id, completed_steps=25),
        ) as build_mock:
            orbit = service.build_orbit(seed)

        self.assertIsNotNone(orbit.metadata)
        self.assertEqual(orbit.metadata.phase_steps, 16)
        self.assertEqual(orbit.metadata.geom_steps, 24)
        self.assertEqual(orbit.metadata.completed_steps, 25)
        build_mock.assert_called_once_with(
            seed=seed,
            config=simulation_config,
            steps=25,
        )

    def test_pending_orbit_metadata_stays_empty(self) -> None:
        service = self._make_service(self._make_simulation_config())
        seed = TrajectorySeed(id=9, wall_start=0, d0=0.1, tau0=0.2)

        service.add_pending_seed(seed)

        self.assertIsNone(service.orbits[seed.id].metadata)

    def test_reset_pending_result_clears_metadata(self) -> None:
        service = self._make_service(self._make_simulation_config())
        trajectory_id = 10
        service.orbits[trajectory_id] = Orbit(trajectory_id=trajectory_id)
        service.orbits[trajectory_id].metadata = object()

        service.reset_pending_result(trajectory_id)

        self.assertIsNone(service.orbits[trajectory_id].metadata)

    def test_apply_partial_result_attaches_metadata_when_missing(self) -> None:
        simulation_config = self._make_simulation_config()
        service = self._make_service(simulation_config)
        seed = TrajectorySeed(id=11, wall_start=1, d0=0.4, tau0=0.5)
        orbit = Orbit(trajectory_id=seed.id, completed_steps=31)

        service.apply_partial_result(
            trajectory_id=seed.id,
            seed=seed,
            orbit=orbit,
            geometry=WedgeGeometry(),
        )

        self.assertIsNotNone(orbit.metadata)
        self.assertEqual(orbit.metadata.fingerprint, SimulationFingerprint.from_config(simulation_config))
        self.assertEqual(orbit.metadata.completed_steps, 31)
        self.assertIs(service.orbits[seed.id], orbit)

    def test_apply_partial_result_preserves_existing_metadata(self) -> None:
        service = self._make_service(self._make_simulation_config())
        seed = TrajectorySeed(id=12, wall_start=0, d0=0.6, tau0=0.7)
        orbit = Orbit(trajectory_id=seed.id, completed_steps=8)
        orbit.metadata = object()

        service.apply_partial_result(
            trajectory_id=seed.id,
            seed=seed,
            orbit=orbit,
            geometry=WedgeGeometry(),
        )

        self.assertIs(orbit.metadata, service.orbits[seed.id].metadata)


if __name__ == "__main__":
    unittest.main()
