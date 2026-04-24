from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

try:
    from app.models.config import SimulationConfig
    from app.models.trajectory import TrajectorySeed
    from app.services.background_jobs import OrbitBuildWorker
except ImportError:  # pragma: no cover
    OrbitBuildWorker = None


@unittest.skipIf(OrbitBuildWorker is None, "PySide6 is not available")
class BackgroundJobsNativeBatchTests(unittest.TestCase):
    def _make_worker(self) -> OrbitBuildWorker:
        return OrbitBuildWorker(
            generation_id=1,
            job_kind="scan",
            simulation_config=SimulationConfig(
                alpha=0.55,
                beta=1.05,
                n_phase_default=32,
                n_geom_default=16,
                eps=1.0e-9,
                native_enabled=True,
                native_sample_mode="every_n",
                native_sample_step=10,
            ),
            max_reflections=8,
            phase_steps=24,
            chunk_size=8,
        )

    def test_run_seed_batch_uses_native_batch_for_scan(self) -> None:
        worker = self._make_worker()
        worker.partial_result = MagicMock()
        worker.progress = MagicMock()
        seeds = [
            TrajectorySeed(id=1, wall_start=1, d0=0.7, tau0=0.1),
            TrajectorySeed(id=2, wall_start=2, d0=0.6, tau0=0.0),
        ]
        native_result = {
            "steps": [0, 10, 20, 23],
            "d": [0.7, 0.65, 0.6, 0.58],
            "tau": [0.1, 0.04, -0.02, -0.03],
            "wall": [1, 2, 1, 2],
            "final_step": 23,
            "final_d": 0.58,
            "final_tau": -0.03,
            "final_wall": 2,
            "valid": True,
            "invalid_step": None,
            "invalid_reason": None,
        }
        with patch("app.services.background_jobs.is_native_available", return_value=True), patch(
            "app.services.background_jobs.native_build_sparse_orbits_batch",
            return_value=[native_result, native_result],
        ) as batch_mock, patch(
            "app.services.background_jobs.build_dense_orbit_for_geometry"
        ) as dense_mock, patch("app.services.background_jobs.build_wedge_geometry") as geometry_mock:
            dense_mock.side_effect = lambda seed, config, steps: worker._native_result_to_orbit(seed.id, native_result)
            geometry_mock.return_value = None
            worker._run_seed_batch(seeds, replace_existing=False, progress_label="Scanning")
        batch_mock.assert_called_once()
        self.assertEqual(dense_mock.call_count, 2)
        worker.partial_result.emit.assert_called()
        worker.progress.emit.assert_called()

    def test_run_seed_batch_falls_back_when_native_unavailable(self) -> None:
        worker = self._make_worker()
        worker.progress = MagicMock()
        seeds = [TrajectorySeed(id=1, wall_start=1, d0=0.7, tau0=0.1)]
        with patch("app.services.background_jobs.is_native_available", return_value=False), patch(
            "app.services.background_jobs.native_build_sparse_orbits_batch",
        ) as batch_mock, patch("app.services.background_jobs.iter_orbit_chunks", return_value=[]):
            worker._run_seed_batch(seeds, replace_existing=False, progress_label="Scanning")
        batch_mock.assert_not_called()
        worker.progress.emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
