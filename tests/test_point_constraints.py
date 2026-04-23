from __future__ import annotations

import math
import unittest

from app.core.point_constraints import (
    ActivePointConstraint,
    BoundarySegment,
    project_point_to_constraint,
    project_point_to_nearest_constraint,
)


class PointConstraintTests(unittest.TestCase):
    def test_projects_to_symmetry_constraint_analytically(self) -> None:
        alpha, beta = project_point_to_constraint(
            0.4,
            1.2,
            ActivePointConstraint(kind="symmetry"),
        )

        self.assertAlmostEqual(alpha, 0.4, places=12)
        self.assertAlmostEqual(beta, math.pi - 0.4, places=12)
        self.assertLess(beta, math.pi - alpha)

    def test_projects_to_nearest_boundary_segment(self) -> None:
        alpha, beta = project_point_to_constraint(
            0.4,
            1.1,
            ActivePointConstraint(
                kind="boundary",
                boundary_segments=(
                    BoundarySegment(0.0, 1.0, 1.0, 1.0),
                    BoundarySegment(0.0, 2.0, 1.0, 2.0),
                ),
            ),
        )

        self.assertAlmostEqual(alpha, 0.4, places=12)
        self.assertAlmostEqual(beta, 1.0, places=12)

    def test_projects_to_nearest_constraint_curve(self) -> None:
        alpha, beta = project_point_to_nearest_constraint(
            0.4,
            1.08,
            (
                ActivePointConstraint(kind="symmetry"),
                ActivePointConstraint(
                    kind="boundary",
                    boundary_segments=(
                        BoundarySegment(0.0, 1.0, 1.0, 1.0),
                    ),
                ),
            ),
        )

        self.assertAlmostEqual(alpha, 0.4, places=12)
        self.assertAlmostEqual(beta, 1.0, places=12)

    def test_nearest_constraint_keeps_symmetry_available(self) -> None:
        alpha, beta = project_point_to_nearest_constraint(
            0.4,
            math.pi - 0.38,
            (
                ActivePointConstraint(kind="symmetry"),
                ActivePointConstraint(
                    kind="boundary",
                    boundary_segments=(
                        BoundarySegment(0.0, 1.0, 1.0, 1.0),
                    ),
                ),
            ),
        )

        self.assertAlmostEqual(alpha, 0.4, places=12)
        self.assertAlmostEqual(beta, math.pi - 0.4, places=12)


if __name__ == "__main__":
    unittest.main()
