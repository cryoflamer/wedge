from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.services.config_loader import load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="wedge billiard phase-space explorer"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to YAML config file.",
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    setup_logging(config.app.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Application initialized")
    logger.info("Config loaded from %s", args.config.resolve())
    logger.info(
        "Simulation parameters: alpha=%s beta=%s",
        config.simulation.alpha,
        config.simulation.beta,
    )
    try:
        from app.ui.main_window import run_app
    except ImportError as exc:
        logger.error("GUI dependency is missing: %s", exc)
        logger.error("Install project requirements before running the GUI.")
        return

    run_app(config, str(args.config))


if __name__ == "__main__":
    main()
