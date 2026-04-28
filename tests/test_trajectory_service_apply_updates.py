from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.models.config import SimulationConfig
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit, OrbitPoint, ReplayFrame
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

    def test_apply_updates_does_not_execute_extend_yet(self) -> None:
        config = self._make_config()
        service = self._make_service(config)
        seed = TrajectorySeed(id=3, wall_start=0, d0=0.1, tau0=0.2)
        extend_orbit = Orbit(trajectory_id=3, metadata=self._make_metadata(config, phase_steps=32))
        service.seeds = {3: seed}
        service.orbits = {3: extend_orbit}
        service.geometries = {3: WedgeGeometry()}

        with (
            patch.object(service, "build_orbit") as build_orbit_mock,
            patch.object(service, "build_geometry_orbit") as geometry_orbit_mock,
            patch.object(service, "build_geometry") as geometry_mock,
        ):
            plans = service.apply_updates()

        self.assertEqual(plans[3].decision, TrajectoryUpdateDecision.EXTEND)
        self.assertIs(service.orbits[3], extend_orbit)
        build_orbit_mock.assert_not_called()
        geometry_orbit_mock.assert_not_called()
        geometry_mock.assert_not_called()

    def test_apply_updates_truncates_phase_orbit_without_rebuilding_it(self) -> None:
        config = self._make_config(n_phase_default=32)
        service = self._make_service(config)
        seed = TrajectorySeed(id=4, wall_start=0, d0=0.2, tau0=0.3)
        orbit = Orbit(
            trajectory_id=4,
            points=[
                OrbitPoint(step_index=0, d=0.1, tau=0.2, wall=0),
                OrbitPoint(step_index=16, d=0.2, tau=0.3, wall=1),
                OrbitPoint(step_index=32, d=0.3, tau=0.4, wall=0),
                OrbitPoint(step_index=48, d=0.4, tau=0.5, wall=1),
            ],
            replay_frames=[
                ReplayFrame(frame_index=0, orbit_point_index=0),
                ReplayFrame(frame_index=16, orbit_point_index=1),
                ReplayFrame(frame_index=32, orbit_point_index=2),
                ReplayFrame(frame_index=48, orbit_point_index=3),
            ],
            completed_steps=64,
            metadata=self._make_metadata(config, phase_steps=64, completed_steps=64),
        )
        old_geometry = WedgeGeometry()
        dense_orbit = Orbit(trajectory_id=4, completed_steps=25)
        rebuilt_geometry = WedgeGeometry()
        service.seeds = {4: seed}
        service.orbits = {4: orbit}
        service.geometries = {4: old_geometry}

        with (
            patch.object(service, "build_orbit") as build_orbit_mock,
            patch.object(service, "build_geometry_orbit", return_value=dense_orbit) as geometry_orbit_mock,
            patch.object(service, "build_geometry", return_value=rebuilt_geometry) as geometry_mock,
        ):
            plans = service.apply_updates()

        truncated_orbit = service.orbits[4]
        self.assertEqual(plans[4].decision, TrajectoryUpdateDecision.TRUNCATE)
        self.assertIsNot(truncated_orbit, orbit)
        self.assertEqual([point.step_index for point in truncated_orbit.points], [0, 16])
        self.assertEqual([frame.orbit_point_index for frame in truncated_orbit.replay_frames], [0, 1])
        self.assertEqual(truncated_orbit.completed_steps, config.n_phase_default)
        self.assertIsNotNone(truncated_orbit.metadata)
        self.assertEqual(truncated_orbit.metadata.phase_steps, config.n_phase_default)
        self.assertEqual(truncated_orbit.metadata.geom_steps, config.n_geom_default)
        self.assertEqual(truncated_orbit.metadata.completed_steps, config.n_phase_default)
        self.assertIs(service.geometries[4], rebuilt_geometry)
        build_orbit_mock.assert_not_called()
        geometry_orbit_mock.assert_called_once_with(seed)
        geometry_mock.assert_called_once_with(dense_orbit)

    def test_apply_updates_redraws_geometry_without_rebuilding_phase_orbit(self) -> None:
        config = self._make_config()
        service = self._make_service(config)
        seed = TrajectorySeed(id=5, wall_start=1, d0=0.3, tau0=0.4)
        orbit = Orbit(
            trajectory_id=5,
            completed_steps=64,
            metadata=self._make_metadata(config, geom_steps=12, completed_steps=64),
        )
        old_geometry = WedgeGeometry()
        dense_orbit = Orbit(trajectory_id=5, completed_steps=25)
        redrawn_geometry = WedgeGeometry()
        service.seeds = {5: seed}
        service.orbits = {5: orbit}
        service.geometries = {5: old_geometry}

        with (
            patch.object(service, "build_orbit") as build_orbit_mock,
            patch.object(service, "build_geometry_orbit", return_value=dense_orbit) as geometry_orbit_mock,
            patch.object(service, "build_geometry", return_value=redrawn_geometry) as geometry_mock,
        ):
            plans = service.apply_updates()

        self.assertEqual(plans[5].decision, TrajectoryUpdateDecision.REDRAW)
        self.assertIs(service.orbits[5], orbit)
        self.assertIs(service.geometries[5], redrawn_geometry)
        self.assertIsNotNone(orbit.metadata)
        self.assertEqual(orbit.metadata.geom_steps, config.n_geom_default)
        self.assertEqual(orbit.metadata.phase_steps, config.n_phase_default)
        self.assertEqual(orbit.metadata.completed_steps, 64)
        build_orbit_mock.assert_not_called()
        geometry_orbit_mock.assert_called_once_with(seed)
        geometry_mock.assert_called_once_with(dense_orbit)


if __name__ == "__main__":
    unittest.main()
