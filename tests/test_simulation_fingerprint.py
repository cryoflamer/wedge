from __future__ import annotations

import unittest

from app.models.config import SimulationConfig
from app.models.simulation_fingerprint import SimulationFingerprint


class SimulationFingerprintTests(unittest.TestCase):
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

    def test_identical_configs_have_identical_fingerprints(self) -> None:
        first = SimulationFingerprint.from_config(self._make_config())
        second = SimulationFingerprint.from_config(self._make_config())

        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))

    def test_dynamic_config_changes_change_fingerprint(self) -> None:
        base = SimulationFingerprint.from_config(self._make_config())

        for field_name, value in (
            ("alpha", 0.56),
            ("beta", 1.06),
            ("eps", 1.0e-8),
            ("native_enabled", False),
            ("native_sample_mode", "dense"),
            ("native_sample_step", 8),
        ):
            with self.subTest(field_name=field_name):
                changed = SimulationFingerprint.from_config(self._make_config(**{field_name: value}))
                self.assertNotEqual(base, changed)

    def test_phase_and_geometry_lengths_are_not_part_of_fingerprint(self) -> None:
        base = SimulationFingerprint.from_config(self._make_config())
        changed_lengths = SimulationFingerprint.from_config(
            self._make_config(n_phase_default=128, n_geom_default=48)
        )

        self.assertEqual(base, changed_lengths)


if __name__ == "__main__":
    unittest.main()
