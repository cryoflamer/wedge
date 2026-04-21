from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from app.services.config_loader import load_config


class ConfigLoaderConstraintTests(unittest.TestCase):
    def test_loads_constraints_separately_from_regions(self) -> None:
        payload = textwrap.dedent(
            """
            app:
              title: Test
              theme: light
            simulation:
              alpha: 0.3
              beta: 1.0
              n_phase_default: 100
              n_geom_default: 20
            replay:
              delay_ms: 120
            export:
              dpi: 200
              default_mode: color
            view:
              active_angle_constraint: symmetric_angle
            regions:
            - name: n3_boundary
              type: boundary
              display_text: B
              legend_text: boundary
              expression: beta - alpha
              visible: true
              style:
                fill: '#ffffff'
                alpha: 0.0
                hatch: ''
                border: '#d62828'
                line_style: dashdot
            - name: symmetric_angle
              type: constraint
              constraint_type: symmetry
              display_text: S
              legend_text: beta = pi - alpha
              expression: beta - (pi - alpha)
              visible: true
            - name: boundary_constraint
              type: constraint
              constraint_type: boundary
              target: n3_boundary
              display_text: B3
              legend_text: along boundary
              visible: true
            """
        ).strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            path.write_text(payload, encoding="utf-8")
            config = load_config(path)

        self.assertEqual(config.view.active_angle_constraint, "symmetric_angle")
        self.assertEqual(len(config.regions), 1)
        self.assertEqual(config.regions[0].name, "n3_boundary")
        self.assertEqual(len(config.constraints), 2)
        self.assertEqual(config.constraints[0].name, "symmetric_angle")
        self.assertEqual(config.constraints[0].constraint_type, "symmetry")
        self.assertEqual(config.constraints[1].target, "n3_boundary")


if __name__ == "__main__":
    unittest.main()
