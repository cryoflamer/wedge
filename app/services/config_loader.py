from __future__ import annotations

from pathlib import Path

import yaml

from app.models.config import Config


def load_config(path: str | Path) -> Config:
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    return Config(
        alpha=float(data["alpha"]),
        beta=float(data["beta"]),
        n_phase=int(data["n_phase"]),
        n_geom=int(data["n_geom"]),
        log_level=str(data.get("log_level", "INFO")),
    )
