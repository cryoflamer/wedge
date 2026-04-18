from __future__ import annotations

import math
import unittest

from app.core.math_engine import PhaseState, next_state, validate_state
from app.models.config import SimulationConfig


class BoundaryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SimulationConfig(
            alpha=math.pi / 6.0,
            beta=math.pi / 3.0,
            n_phase_default=100,
            n_geom_default=25,
            eps=1.0e-9,
        )

    def test_rejects_non_positive_d(self) -> None:
        result = validate_state(PhaseState(d=0.0, tau=0.0, wall=1), self.config)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "non_positive_d")

    def test_rejects_state_outside_domain(self) -> None:
        result = validate_state(PhaseState(d=1.0, tau=1.0, wall=1), self.config)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "outside_domain")

    def test_rejects_invalid_alpha(self) -> None:
        config = SimulationConfig(
            alpha=0.0,
            beta=math.pi / 3.0,
            n_phase_default=100,
            n_geom_default=25,
            eps=1.0e-9,
        )
        result = validate_state(PhaseState(d=0.5, tau=0.0, wall=1), config)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "invalid_alpha")

    def test_rejects_invalid_beta(self) -> None:
        config = SimulationConfig(
            alpha=math.pi / 6.0,
            beta=math.pi / 6.0,
            n_phase_default=100,
            n_geom_default=25,
            eps=1.0e-9,
        )
        result = validate_state(PhaseState(d=0.5, tau=0.0, wall=1), config)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "invalid_beta")

    def test_falls_back_to_same_wall_when_cross_wall_leaves_domain(self) -> None:
        state = PhaseState(d=0.763713, tau=0.268421, wall=1)
        result = next_state(state, self.config)
        self.assertTrue(result.valid)
        self.assertEqual(result.branch, "same_wall")
        self.assertIsNotNone(result.state)
        self.assertEqual(result.state.wall, 1)


if __name__ == "__main__":
    unittest.main()
