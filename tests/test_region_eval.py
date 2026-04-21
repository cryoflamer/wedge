from __future__ import annotations

import math
import unittest

from app.core.region_eval import evaluate_boundary_value
from app.models.region import RegionDescription, RegionStyle


class RegionEvalAliasesTest(unittest.TestCase):
    def test_greek_letter_aliases_in_expression(self) -> None:
        region = RegionDescription(
            name="boundary",
            display_text="B",
            legend_text="test",
            region_type="boundary",
            expression="3*sin(α-2*β) - sin(3*α-2*β) + 0*π",
            relation=None,
            style=RegionStyle(
                fill="#ffffff",
                alpha=0.0,
                hatch="",
                border="#000000",
            ),
            priority=0,
            visible=True,
        )

        alpha = 0.4
        beta = 0.9
        expected = 3 * math.sin(alpha - 2 * beta) - math.sin(3 * alpha - 2 * beta)
        actual = evaluate_boundary_value(region, alpha, beta)

        self.assertIsNotNone(actual)
        assert actual is not None
        self.assertAlmostEqual(actual, expected, places=12)


if __name__ == "__main__":
    unittest.main()
