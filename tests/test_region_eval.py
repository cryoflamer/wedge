from __future__ import annotations

import math
import unittest

from app.core.region_eval import (
    evaluate_boundary_value,
    evaluate_region,
    evaluate_scene_item,
    matches_relation,
)
from app.models.region import RegionDescription, RegionStyle
from app.models.scene_item import SceneItemDescription


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

    def test_unified_relations_match_zero_comparison(self) -> None:
        cases = [
            ("<", "alpha - beta", True),
            ("<=", "alpha - beta", True),
            (">", "beta - alpha", True),
            (">=", "beta - alpha", True),
            ("=", "alpha - alpha", True),
            ("=", "alpha - beta", False),
        ]
        alpha = 0.4
        beta = 0.9

        for relation, expression, expected in cases:
            with self.subTest(relation=relation, expression=expression):
                item = SceneItemDescription(
                    name=f"region_{relation}",
                    alias=f"region_{relation}",
                    display_text="R",
                    legend_text="test",
                    expression=expression,
                    relation=relation,
                    visible=True,
                    priority=0,
                    style=RegionStyle(
                        fill="#ffffff",
                        alpha=0.0,
                        hatch="",
                        border="#000000",
                    ),
                )

                self.assertEqual(evaluate_scene_item(item, alpha, beta), expected)

    def test_equality_and_weak_relations_use_eps_tolerance(self) -> None:
        self.assertTrue(matches_relation(1.0e-10, "=", 1.0e-9))
        self.assertTrue(matches_relation(1.0e-10, "<=", 1.0e-9))
        self.assertTrue(matches_relation(-1.0e-10, ">=", 1.0e-9))
        self.assertFalse(matches_relation(1.0e-4, "=", 1.0e-9))

    def test_boundary_uses_unified_equality_relation(self) -> None:
        region = RegionDescription(
            name="boundary",
            display_text="B",
            legend_text="boundary",
            region_type="boundary",
            expression="alpha - beta",
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

        self.assertFalse(evaluate_region(region, 0.4, 0.9))
        self.assertTrue(evaluate_region(region, 0.4, 0.4))

    def test_region_adapter_keeps_predicate_compatibility_semantics(self) -> None:
        region = RegionDescription(
            name="predicate",
            display_text="P",
            legend_text="predicate",
            region_type="predicate",
            expression="alpha < beta",
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

        self.assertTrue(evaluate_region(region, 0.4, 0.9))
        self.assertFalse(evaluate_region(region, 0.9, 0.4))


if __name__ == "__main__":
    unittest.main()
