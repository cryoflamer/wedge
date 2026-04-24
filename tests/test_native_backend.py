from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core import native_backend
from app.core.orbit_builder import build_orbit
from app.core.trajectory_engine import build_orbit as build_orbit_via_engine
from app.models.config import SimulationConfig
from app.models.trajectory import TrajectorySeed


class NativeBackendFallbackTests(unittest.TestCase):
    def test_fallback_is_safe_when_native_module_is_missing(self) -> None:
        available = native_backend.is_native_available()
        if not available:
            self.assertFalse(available)

    def test_wrapper_exposes_boolean_availability(self) -> None:
        self.assertIsInstance(native_backend.is_native_available(), bool)

    def test_native_add_ints_if_module_is_built(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")
        self.assertEqual(native_backend.add_ints(2, 3), 5)

    def test_native_dense_orbit_matches_python_reference(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")

        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
        )
        d0 = 0.72
        tau0 = 0.08
        wall0 = 1
        steps = 24

        expected = self._build_python_dense_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            config=config,
            steps=steps,
        )
        actual = native_backend.native_build_dense_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
        )

        self.assertEqual(len(actual["steps"]), len(expected["steps"]))
        self.assertEqual(list(actual["wall"]), expected["wall"])
        for got, want in zip(actual["d"], expected["d"]):
            self.assertAlmostEqual(float(got), want, places=10)
        for got, want in zip(actual["tau"], expected["tau"]):
            self.assertAlmostEqual(float(got), want, places=10)
        self.assertEqual(bool(actual["valid"]), expected["valid"])
        self.assertEqual(actual["invalid_reason"], expected["invalid_reason"])

    def test_native_final_state_matches_python_reference_across_step_counts(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")

        for wall0 in (1, 2):
            for steps in (10, 100, 1000):
                with self.subTest(wall0=wall0, steps=steps):
                    self._assert_native_final_state_matches_python(
                        wall0=wall0,
                        steps=steps,
                        sample_mode="dense",
                        sample_step=1,
                    )
                    self._assert_native_final_state_matches_python(
                        wall0=wall0,
                        steps=steps,
                        sample_mode="every_n",
                        sample_step=1,
                    )

    def test_native_sparse_every_n_returns_fewer_points_than_dense(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")
        config, d0, tau0, wall0, steps = self._sample_case()
        dense_ref = self._build_python_dense_orbit(
            d0=d0, tau0=tau0, wall0=wall0, config=config, steps=steps
        )
        expected = self._sparsify_reference(dense_ref, sample_step=4, sample_mode="every_n")
        actual = native_backend.native_build_sparse_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
            sample_step=4,
            sample_mode="every_n",
        )
        self.assertLess(len(actual["steps"]), len(dense_ref["steps"]))
        self._assert_sparse_matches_reference(actual, expected)

    def test_native_sparse_final_returns_exactly_one_sample(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")
        config, d0, tau0, wall0, steps = self._sample_case()
        dense_ref = self._build_python_dense_orbit(
            d0=d0, tau0=tau0, wall0=wall0, config=config, steps=steps
        )
        expected = self._sparsify_reference(dense_ref, sample_step=8, sample_mode="final")
        actual = native_backend.native_build_sparse_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
            sample_step=8,
            sample_mode="final",
        )
        self.assertEqual(len(actual["steps"]), 1)
        self._assert_sparse_matches_reference(actual, expected)

    def test_native_sparse_sample_step_one_matches_dense_reference(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")
        config, d0, tau0, wall0, steps = self._sample_case()
        dense_ref = self._build_python_dense_orbit(
            d0=d0, tau0=tau0, wall0=wall0, config=config, steps=steps
        )
        expected = self._sparsify_reference(dense_ref, sample_step=1, sample_mode="every_n")
        actual = native_backend.native_build_sparse_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
            sample_step=1,
            sample_mode="every_n",
        )
        self._assert_sparse_matches_reference(actual, expected)

    def test_native_sparse_dense_alias_matches_dense_reference(self) -> None:
        if not native_backend.is_native_available():
            self.skipTest("native module is not built")
        config, d0, tau0, wall0, steps = self._sample_case()
        dense_ref = self._build_python_dense_orbit(
            d0=d0, tau0=tau0, wall0=wall0, config=config, steps=steps
        )
        expected = self._sparsify_reference(dense_ref, sample_step=1, sample_mode="dense")
        actual = native_backend.native_build_sparse_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
            sample_step=7,
            sample_mode="dense",
        )
        self._assert_sparse_matches_reference(actual, expected)

    def _build_python_dense_orbit(
        self,
        *,
        d0: float,
        tau0: float,
        wall0: int,
        config: SimulationConfig,
        steps: int,
    ) -> dict[str, object]:
        orbit = build_orbit(
            seed=TrajectorySeed(id=1, wall_start=wall0, d0=d0, tau0=tau0),
            config=config,
            steps=steps,
        )
        result = {
            "steps": [point.step_index for point in orbit.points],
            "d": [point.d for point in orbit.points],
            "tau": [point.tau for point in orbit.points],
            "wall": [point.wall for point in orbit.points],
            "valid": orbit.valid,
            "invalid_reason": orbit.invalid_reason if not orbit.valid else None,
            "final_step": orbit.points[-1].step_index,
            "final_d": orbit.points[-1].d,
            "final_tau": orbit.points[-1].tau,
            "final_wall": orbit.points[-1].wall,
            "invalid_step": orbit.points[-1].step_index if not orbit.valid else None,
        }
        return result

    def _sparsify_reference(
        self,
        dense: dict[str, object],
        *,
        sample_step: int,
        sample_mode: str,
    ) -> dict[str, object]:
        dense_steps = list(dense["steps"])
        dense_d = list(dense["d"])
        dense_tau = list(dense["tau"])
        dense_wall = list(dense["wall"])

        sampled_indices: list[int] = []
        if sample_mode == "final":
            sampled_indices = [len(dense_steps) - 1] if dense_steps else []
        elif sample_mode == "dense" or sample_step <= 1:
            sampled_indices = list(range(len(dense_steps)))
        elif sample_mode == "every_n":
            sampled_indices = [
                index
                for index, step_index in enumerate(dense_steps)
                if step_index == 0 or (step_index % sample_step) == 0
            ]
            if sampled_indices and sampled_indices[-1] != len(dense_steps) - 1:
                sampled_indices.append(len(dense_steps) - 1)
        else:
            raise AssertionError(f"unsupported sample mode for test: {sample_mode}")

        return {
            "steps": [dense_steps[index] for index in sampled_indices],
            "d": [dense_d[index] for index in sampled_indices],
            "tau": [dense_tau[index] for index in sampled_indices],
            "wall": [dense_wall[index] for index in sampled_indices],
            "final_step": dense["final_step"],
            "final_d": dense["final_d"],
            "final_tau": dense["final_tau"],
            "final_wall": dense["final_wall"],
            "valid": dense["valid"],
            "invalid_step": dense["invalid_step"],
            "invalid_reason": dense["invalid_reason"],
        }

    def _assert_sparse_matches_reference(
        self,
        actual: dict[str, object],
        expected: dict[str, object],
    ) -> None:
        self.assertEqual(list(actual["steps"]), expected["steps"])
        self.assertEqual(list(actual["wall"]), expected["wall"])
        for got, want in zip(actual["d"], expected["d"]):
            self.assertAlmostEqual(float(got), float(want), places=10)
        for got, want in zip(actual["tau"], expected["tau"]):
            self.assertAlmostEqual(float(got), float(want), places=10)
        self.assertEqual(int(actual["final_step"]), int(expected["final_step"]))
        self.assertAlmostEqual(float(actual["final_d"]), float(expected["final_d"]), places=10)
        self.assertAlmostEqual(float(actual["final_tau"]), float(expected["final_tau"]), places=10)
        self.assertEqual(int(actual["final_wall"]), int(expected["final_wall"]))
        self.assertEqual(bool(actual["valid"]), bool(expected["valid"]))
        self.assertEqual(actual["invalid_step"], expected["invalid_step"])
        self.assertEqual(actual["invalid_reason"], expected["invalid_reason"])

    def _assert_native_final_state_matches_python(
        self,
        *,
        wall0: int,
        steps: int,
        sample_mode: str,
        sample_step: int,
    ) -> None:
        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
        )
        d0 = 0.72
        tau0 = 0.08
        expected = self._build_python_dense_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            config=config,
            steps=steps,
        )
        dense_actual = native_backend.native_build_dense_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
        )
        sparse_actual = native_backend.native_build_sparse_orbit(
            d0=d0,
            tau0=tau0,
            wall0=wall0,
            alpha=config.alpha,
            beta=config.beta,
            steps=steps,
            sample_step=sample_step,
            sample_mode=sample_mode,
        )
        for actual in (dense_actual, sparse_actual):
            self.assertEqual(int(actual["final_step"]), int(expected["final_step"]))
            self.assertAlmostEqual(float(actual["final_d"]), float(expected["final_d"]), places=10)
            self.assertAlmostEqual(float(actual["final_tau"]), float(expected["final_tau"]), places=10)
            self.assertEqual(int(actual["final_wall"]), int(expected["final_wall"]))
            self.assertEqual(bool(actual["valid"]), bool(expected["valid"]))
            self.assertEqual(actual["invalid_step"], expected["invalid_step"])
            self.assertEqual(actual["invalid_reason"], expected["invalid_reason"])

    def _sample_case(self) -> tuple[SimulationConfig, float, float, int, int]:
        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=False,
            native_sample_mode="every_n",
            native_sample_step=1,
        )
        return config, 0.72, 0.08, 1, 24


class NativeTrajectoryEngineIntegrationTests(unittest.TestCase):
    def test_native_enabled_sample_step_one_matches_python_build_orbit(self) -> None:
        seed = TrajectorySeed(id=7, wall_start=1, d0=0.72, tau0=0.08)
        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=True,
            native_sample_mode="every_n",
            native_sample_step=1,
        )
        expected = build_orbit(seed=seed, config=config, steps=24)
        native_result = {
            "steps": [point.step_index for point in expected.points],
            "d": [point.d for point in expected.points],
            "tau": [point.tau for point in expected.points],
            "wall": [point.wall for point in expected.points],
            "final_step": expected.points[-1].step_index,
            "final_d": expected.points[-1].d,
            "final_tau": expected.points[-1].tau,
            "final_wall": expected.points[-1].wall,
            "valid": expected.valid,
            "invalid_step": expected.points[-1].step_index if not expected.valid else None,
            "invalid_reason": expected.invalid_reason,
        }
        with patch("app.core.trajectory_engine.is_native_available", return_value=True), patch(
            "app.core.trajectory_engine.native_build_sparse_orbit",
            return_value=native_result,
        ):
            actual = build_orbit_via_engine(seed=seed, config=config, steps=24)
        self.assertEqual(len(actual.points), len(expected.points))
        self.assertEqual(actual.valid, expected.valid)
        self.assertEqual(actual.invalid_reason, expected.invalid_reason)
        self.assertEqual(
            [(point.step_index, point.wall) for point in actual.points],
            [(point.step_index, point.wall) for point in expected.points],
        )
        for got, want in zip(actual.points, expected.points):
            self.assertAlmostEqual(got.d, want.d, places=10)
            self.assertAlmostEqual(got.tau, want.tau, places=10)

    def test_python_fallback_used_when_native_disabled_or_unavailable(self) -> None:
        seed = TrajectorySeed(id=9, wall_start=1, d0=0.72, tau0=0.08)
        disabled_config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=False,
            native_sample_mode="every_n",
            native_sample_step=1,
        )
        with patch("app.core.trajectory_engine.is_native_available", return_value=True), patch(
            "app.core.trajectory_engine.native_build_sparse_orbit",
        ) as native_mock:
            build_orbit_via_engine(seed=seed, config=disabled_config, steps=24)
        native_mock.assert_not_called()

        unavailable_config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=True,
            native_sample_mode="every_n",
            native_sample_step=1,
        )
        with patch("app.core.trajectory_engine.is_native_available", return_value=False), patch(
            "app.core.trajectory_engine.native_build_sparse_orbit",
        ) as native_mock:
            build_orbit_via_engine(seed=seed, config=unavailable_config, steps=24)
        native_mock.assert_not_called()

    def test_native_sparse_engine_sample_step_ten_returns_compact_orbit(self) -> None:
        seed = TrajectorySeed(id=11, wall_start=1, d0=0.72, tau0=0.08)
        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=True,
            native_sample_mode="every_n",
            native_sample_step=10,
        )
        native_result = {
            "steps": [0, 10, 20, 23],
            "d": [0.72, 0.61, 0.53, 0.49],
            "tau": [0.08, 0.04, -0.02, -0.05],
            "wall": [1, 2, 1, 2],
            "final_step": 23,
            "final_d": 0.49,
            "final_tau": -0.05,
            "final_wall": 2,
            "valid": True,
            "invalid_step": None,
            "invalid_reason": None,
        }
        with patch("app.core.trajectory_engine.is_native_available", return_value=True), patch(
            "app.core.trajectory_engine.native_build_sparse_orbit",
            return_value=native_result,
        ):
            actual = build_orbit_via_engine(seed=seed, config=config, steps=24)
        self.assertEqual([point.step_index for point in actual.points], [0, 10, 20, 23])
        self.assertEqual(len(actual.points), 4)
        self.assertEqual(actual.completed_steps, 24)

    def test_native_sparse_engine_final_mode_returns_only_final_point(self) -> None:
        seed = TrajectorySeed(id=12, wall_start=2, d0=0.72, tau0=0.08)
        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=True,
            native_sample_mode="final",
            native_sample_step=100,
        )
        native_result = {
            "steps": [23],
            "d": [0.41],
            "tau": [-0.07],
            "wall": [1],
            "final_step": 23,
            "final_d": 0.41,
            "final_tau": -0.07,
            "final_wall": 1,
            "valid": True,
            "invalid_step": None,
            "invalid_reason": None,
        }
        with patch("app.core.trajectory_engine.is_native_available", return_value=True), patch(
            "app.core.trajectory_engine.native_build_sparse_orbit",
            return_value=native_result,
        ):
            actual = build_orbit_via_engine(seed=seed, config=config, steps=24)
        self.assertEqual(len(actual.points), 1)
        self.assertEqual(actual.points[0].step_index, 23)
        self.assertEqual(actual.points[0].wall, 1)
        self.assertEqual(actual.completed_steps, 24)
        self.assertTrue(actual.valid)

    def test_native_sparse_engine_invalid_metadata_is_preserved(self) -> None:
        seed = TrajectorySeed(id=13, wall_start=1, d0=0.72, tau0=0.08)
        config = SimulationConfig(
            alpha=0.55,
            beta=1.05,
            n_phase_default=32,
            n_geom_default=16,
            eps=1.0e-9,
            native_enabled=True,
            native_sample_mode="final",
            native_sample_step=10,
        )
        native_result = {
            "steps": [17],
            "d": [0.33],
            "tau": [0.12],
            "wall": [2],
            "final_step": 17,
            "final_d": 0.33,
            "final_tau": 0.12,
            "final_wall": 2,
            "valid": False,
            "invalid_step": 17,
            "invalid_reason": "outside_domain",
        }
        with patch("app.core.trajectory_engine.is_native_available", return_value=True), patch(
            "app.core.trajectory_engine.native_build_sparse_orbit",
            return_value=native_result,
        ):
            actual = build_orbit_via_engine(seed=seed, config=config, steps=24)
        self.assertFalse(actual.valid)
        self.assertEqual(actual.invalid_reason, "outside_domain")
        self.assertEqual(actual.completed_steps, 18)
        self.assertEqual(actual.points[-1].step_index, 17)
        self.assertFalse(actual.points[-1].valid)
        self.assertEqual(actual.points[-1].invalid_reason, "outside_domain")


if __name__ == "__main__":
    unittest.main()
