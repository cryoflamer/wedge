from __future__ import annotations

import unittest

from app.models.config import SimulationConfig
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.services.trajectory_update_planner import (
    TrajectoryUpdateDecision,
    TrajectoryUpdatePlanner,
)


class TrajectoryUpdatePlannerTests(unittest.TestCase):
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

    def _make_metadata(self, config: SimulationConfig | None = None) -> TrajectoryBuildMetadata:
        source_config = config or self._make_config()
        return TrajectoryBuildMetadata(
            fingerprint=SimulationFingerprint.from_config(source_config),
            phase_steps=source_config.n_phase_default,
            geom_steps=source_config.n_geom_default,
            backend_used="native" if source_config.native_enabled else "python",
            completed_steps=source_config.n_phase_default,
        )

    def _decision(
        self,
        metadata: TrajectoryBuildMetadata | None,
        config: SimulationConfig,
    ) -> TrajectoryUpdateDecision:
        return TrajectoryUpdatePlanner.plan(metadata, config).decision

    def test_no_metadata_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(None, self._make_config()),
            TrajectoryUpdateDecision.REBUILD,
        )

    def test_identical_fingerprint_and_lengths_are_unchanged(self) -> None:
        config = self._make_config()

        self.assertEqual(
            self._decision(self._make_metadata(config), config),
            TrajectoryUpdateDecision.UNCHANGED,
        )

    def test_alpha_change_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(alpha=0.56)),
            TrajectoryUpdateDecision.REBUILD,
        )

    def test_beta_change_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(beta=1.06)),
            TrajectoryUpdateDecision.REBUILD,
        )

    def test_native_enabled_change_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(native_enabled=False)),
            TrajectoryUpdateDecision.REBUILD,
        )

    def test_sample_mode_change_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(native_sample_mode="dense")),
            TrajectoryUpdateDecision.REBUILD,
        )

    def test_sample_step_change_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(native_sample_step=8)),
            TrajectoryUpdateDecision.REBUILD,
        )

    def test_phase_length_increase_extends(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(n_phase_default=128)),
            TrajectoryUpdateDecision.EXTEND,
        )

    def test_phase_length_decrease_truncates(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(n_phase_default=32)),
            TrajectoryUpdateDecision.TRUNCATE,
        )

    def test_geometry_length_change_redraws(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(n_geom_default=48)),
            TrajectoryUpdateDecision.REDRAW,
        )

    def test_alpha_and_phase_length_change_requires_rebuild(self) -> None:
        self.assertEqual(
            self._decision(self._make_metadata(), self._make_config(alpha=0.56, n_phase_default=128)),
            TrajectoryUpdateDecision.REBUILD,
        )


if __name__ == "__main__":
    unittest.main()
