from __future__ import annotations

import unittest

from app.models import Orbit, TrajectoryBuildMetadata
from app.models.config import SimulationConfig
from app.models.simulation_fingerprint import SimulationFingerprint


class TrajectoryBuildMetadataTests(unittest.TestCase):
    def _make_fingerprint(self) -> SimulationFingerprint:
        return SimulationFingerprint.from_config(
            SimulationConfig(
                alpha=0.55,
                beta=1.05,
                n_phase_default=64,
                n_geom_default=24,
                eps=1.0e-9,
                native_enabled=True,
                native_sample_mode="every_n",
                native_sample_step=4,
            )
        )

    def test_metadata_stores_build_contract(self) -> None:
        metadata = TrajectoryBuildMetadata(
            fingerprint=self._make_fingerprint(),
            phase_steps=64,
            geom_steps=24,
            backend_used="native",
            completed_steps=63,
        )

        self.assertEqual(metadata.phase_steps, 64)
        self.assertEqual(metadata.geom_steps, 24)
        self.assertEqual(metadata.backend_used, "native")
        self.assertEqual(metadata.completed_steps, 63)

    def test_orbit_metadata_is_optional(self) -> None:
        orbit = Orbit(trajectory_id=1)

        self.assertIsNone(orbit.metadata)

    def test_orbit_can_store_metadata_without_changing_completed_steps(self) -> None:
        metadata = TrajectoryBuildMetadata(
            fingerprint=self._make_fingerprint(),
            phase_steps=64,
            geom_steps=24,
            backend_used="python",
            completed_steps=10,
        )
        orbit = Orbit(trajectory_id=1, completed_steps=10, metadata=metadata)

        self.assertIs(orbit.metadata, metadata)
        self.assertEqual(orbit.completed_steps, 10)


if __name__ == "__main__":
    unittest.main()
