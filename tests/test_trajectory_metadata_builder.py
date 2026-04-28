from __future__ import annotations

import unittest

from app.models.config import SimulationConfig
from app.models.simulation_fingerprint import SimulationFingerprint
from app.services.trajectory_metadata_builder import build_metadata_from_config


class TrajectoryMetadataBuilderTests(unittest.TestCase):
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

    def test_builds_metadata_contract_from_config(self) -> None:
        config = self._make_config()

        metadata = build_metadata_from_config(config)

        self.assertEqual(metadata.fingerprint, SimulationFingerprint.from_config(config))
        self.assertEqual(metadata.phase_steps, 64)
        self.assertEqual(metadata.geom_steps, 24)
        self.assertEqual(metadata.backend_used, "native")
        self.assertEqual(metadata.completed_steps, 64)

    def test_uses_python_backend_when_native_is_disabled(self) -> None:
        metadata = build_metadata_from_config(self._make_config(native_enabled=False))

        self.assertEqual(metadata.backend_used, "python")

    def test_lengths_are_stored_outside_fingerprint(self) -> None:
        config = self._make_config(n_phase_default=128, n_geom_default=48)

        metadata = build_metadata_from_config(config)

        self.assertEqual(metadata.fingerprint, SimulationFingerprint.from_config(config))
        self.assertEqual(metadata.phase_steps, 128)
        self.assertEqual(metadata.geom_steps, 48)


if __name__ == "__main__":
    unittest.main()
