from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.config_loader import load_config, save_runtime_config


class ConfigLoaderUnicodeTest(unittest.TestCase):
    def test_save_runtime_config_preserves_unicode_expressions(self) -> None:
        source = Path("config.yaml")
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "config.yaml"
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            config = load_config(target)
            save_runtime_config(config, target)

            saved = target.read_text(encoding="utf-8")
            self.assertIn("3*sin(α-2*β) - sin(3*α-2*β)", saved)
            self.assertIn("β - (π - α)", saved)
            self.assertNotIn("\\u03B1", saved)
            self.assertNotIn("\\u03B2", saved)
            self.assertNotIn("\\u03C0", saved)


if __name__ == "__main__":
    unittest.main()
