from __future__ import annotations

import math
import unittest

from app.services.parameter_parser import parse_real_expression


class ParameterParserTests(unittest.TestCase):
    def test_parses_pi_expression(self) -> None:
        self.assertAlmostEqual(parse_real_expression("pi/6"), math.pi / 6.0)
        self.assertAlmostEqual(
            parse_real_expression("pi/2 - pi/6"),
            math.pi / 3.0,
        )
        self.assertAlmostEqual(parse_real_expression("2*pi/5"), 2.0 * math.pi / 5.0)

    def test_parses_decimal_expression(self) -> None:
        self.assertAlmostEqual(parse_real_expression("0.5"), 0.5)
        self.assertAlmostEqual(parse_real_expression("-0.25"), -0.25)

    def test_rejects_unsupported_expression(self) -> None:
        with self.assertRaises(ValueError):
            parse_real_expression("sin(pi/6)")

        with self.assertRaises(ValueError):
            parse_real_expression("__import__('os').system('pwd')")

    def test_rejects_empty_expression(self) -> None:
        with self.assertRaises(ValueError):
            parse_real_expression("  ")


if __name__ == "__main__":
    unittest.main()
