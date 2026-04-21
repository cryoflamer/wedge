from __future__ import annotations

import math
import unittest

from app.core.region_eval import evaluate_boundary_value
from app.models.region import RegionDescription, RegionStyle


class RegionEvalTests(unittest.TestCase):
    def test_returns_numeric_boundary_value_for_boundary_curve(self) -> None:
        region = RegionDescription(
            name="n3_boundary",
            display_text="B",
            legend_text="3*sin(alpha-2*beta) - sin(3*alpha-2*beta) = 0",
            region_type="boundary",
            expression="3*sin(alpha-2*beta) - sin(3*alpha-2*beta)",
            relation=None,
            style=RegionStyle(
                fill="#ffffff",
                alpha=0.0,
                hatch="",
                border="#d62828",
                line_style="dashdot",
            ),
            priority=30,
            visible=True,
        )

        value = evaluate_boundary_value(
            region,
            alpha=math.pi / 6.0,
            beta=math.pi / 3.0,
        )

        self.assertIsNotNone(value)
        self.assertAlmostEqual(value or 0.0, -2.5, places=9)


if __name__ == "__main__":
    unittest.main()
