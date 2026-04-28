from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.models.config import SimulationConfig
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory import TrajectorySeed
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.services.trajectory_service import TrajectoryService
from app.services.trajectory_update_planner import TrajectoryUpdateDecision


class TrajectoryServiceApplyUpdatesTests(unittest.TestCase):
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

    def test_apply_updates_rebuilds_missing_metadata_orbit(self) -> None:
        config = self._make_config()
        service = self._make_service(config)
        seed = TrajectorySeed(id=1, wall_start=0, d0=0.1, tau0=0.2)
        old_orbit = Orbit(trajectory_id=1)
        rebuilt_orbit = Orbit(trajectory_id=1, completed_steps=64)
        dense_orbit = Orbit(trajectory_id=1, completed_steps=25)
        rebuilt_geometry = WedgeGeometry()
        service.seeds = {1: seed}
        service.orbits = {1: old_orbit}
        service.geometries = {1: WedgeGeometry()}

        with (
            patch.object(service, "build_orbit", return_value=rebuilt_orbit) as build_orbit_mock,
            patch.object(service, "build_geometry_orbit", return_value=dense_orbit) as geometry_orbit_mock,
            patch.object(service, "build_geometry", return_value=rebuilt_geometry) as geometry_mock,
        ):
            plans = service.apply_updates()

        self.assertEqual(plans[1].decision, TrajectoryUpdateDecision.REBUILD)
        self.assertIs(service.orbits[1], rebuilt_orbit)
        self.assertIs(service.geometries[1], rebuilt_geometry)
        build_orbit_mock.assert_called_once_with(seed)
        geometry_orbit_mock.assert_called_once_with(seed)
        geometry_mock.assert_called_once_with(dense_orbit)

    def test_apply_updates_leaves_unchanged_orbit_untouched(self) -> None:
        config = self._make_config()
        service = self._make_service(config)
        seed = TrajectorySeed(id=2, wall_start=1, d0=0.3, tau0=0.4)
        orbit = Orbit(trajectory_id=2, metadata=self._make_metadata(config))
        geometry = WedgeGeometry()
        service.seeds = {2: seed}
        service.orbits = {2: orbit}
        service.geometries = {2: geometry}

        with (
            patch.object(service, "build_orbit") as build_orbit_mock,
            patch.object(service, "build_geometry_orbit") as geometry_orbit_mock,
            patch.object(service, "build_geometry") as geometry_mock,
        ):
            plans = service.apply_updates()

        self.assertEqual(plans[2].decision, TrajectoryUpdateDecision.UNCHANGED)
        self.assertIs(service.orbits[2], orbit)
        self.assertIs(service.geometries[2], geometry)
        build_orbit_mock.assert_not_called()
        geometry_orbit_mock.assert_not_called()
        geometry_mock.assert_not_called()

    def test_apply_updates_does_not_execute_extend_truncate_or_redraw_yet(self) -> None:
        config = self._make_config()
        service = self._make_service(config)
        service.seeds = {
            3: TrajectorySeed(id=3, wall_start=0, d0=0.1, tau0=0.2),
            4: TrajectorySeed(id=4, wall_start=0, d0=0.2, tau0=0.3),
            5: TrajectorySeed(id=5, wall_start=1, d0=0.3, tau0=0.4),
        }
        extend_orbit = Orbit(trajectory_id=3, metadata=self._make_metadata(config, phase_steps=32))
        truncate_orbit = Orbit(trajectory_id=4, metadata=self._make_metadata(config, phase_steps=96))
        redraw_orbit = Orbit(trajectory_id=5, metadata=self._make_metadata(config, geom_steps=12))
        service.orbits = {
            3: extend_orbit,
            4: truncate_orbit,
            5: redraw_orbit,
        }
        service.geometries = {
            3: WedgeGeometry(),
            4: WedgeGeometry(),
            5: WedgeGeometry(),
        }

        with (
            patch.object(service, "build_orbit") as build_orbit_mock,
            patch.object(service, "build_geometry_orbit") as geometry_orbit_mock,
            patch.object(service, "build_geometry") as geometry_mock,
        ):
            plans = service.apply_updates()

        self.assertEqual(plans[3].decision, TrajectoryUpdateDecision.EXTEND)
        self.assertEqual(plans[4].decision, TrajectoryUpdateDecision.TRUNCATE)
        self.assertEqual(plans[5].decision, TrajectoryUpdateDecision.REDRAW)
        self.assertIs(service.orbits[3], extend_orbit)
        self.assertIs(service.orbits[4], truncate_orbit)
        self.assertIs(service.orbits[5], redraw_orbit)
        build_orbit_mock.assert_not_called()
        geometry_orbit_mock.assert_not_called()
        geometry_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
