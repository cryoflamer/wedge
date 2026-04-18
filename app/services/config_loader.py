from __future__ import annotations

from pathlib import Path

import yaml

from app.models.config import (
    AppConfig,
    AutosaveConfig,
    Config,
    ExportConfig,
    ReplayConfig,
    SimulationConfig,
    ViewConfig,
    WindowConfig,
)
from app.models.region import RegionDescription, RegionStyle


def load_config(path: str | Path) -> Config:
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    app_data = data.get("app", {})
    simulation_data = data.get("simulation", {})
    replay_data = data.get("replay", {})
    export_data = data.get("export", {})
    view_data = data.get("view", {})
    window_data = data.get("window", {})
    autosave_data = data.get("autosave", {})
    regions_data = data.get("regions", [])

    return Config(
        app=AppConfig(
            title=str(app_data.get("title", "Wedge Field Billiard Explorer")),
            theme=str(app_data.get("theme", "light")),
            log_level=str(app_data.get("log_level", "INFO")),
        ),
        simulation=SimulationConfig(
            alpha=float(simulation_data["alpha"]),
            beta=float(simulation_data["beta"]),
            n_phase_default=int(simulation_data["n_phase_default"]),
            n_geom_default=int(simulation_data["n_geom_default"]),
            eps=float(simulation_data.get("eps", 1.0e-9)),
        ),
        replay=ReplayConfig(
            delay_ms=int(replay_data.get("delay_ms", 120)),
            selected_only_by_default=bool(
                replay_data.get("selected_only_by_default", True)
            ),
        ),
        export=ExportConfig(
            dpi=int(export_data.get("dpi", 200)),
            default_mode=str(export_data.get("default_mode", "color")),
            monochrome_line_styles=[
                str(style)
                for style in export_data.get("monochrome_line_styles", [])
            ],
        ),
        view=ViewConfig(
            show_grid=bool(view_data.get("show_grid", True)),
            show_labels=bool(view_data.get("show_labels", True)),
            show_directrix=bool(view_data.get("show_directrix", False)),
            show_reflection_points=bool(
                view_data.get("show_reflection_points", True)
            ),
            phase_point_radius=int(view_data.get("phase_point_radius", 2)),
            geometry_point_radius=int(view_data.get("geometry_point_radius", 2)),
        ),
        window=WindowConfig(
            width=int(window_data.get("width", 1360)),
            height=int(window_data.get("height", 980)),
            x=(
                int(window_data["x"])
                if window_data.get("x") is not None
                else None
            ),
            y=(
                int(window_data["y"])
                if window_data.get("y") is not None
                else None
            ),
        ),
        autosave=AutosaveConfig(
            enabled=bool(autosave_data.get("enabled", True)),
            path=str(autosave_data.get("path", "autosave/session.yaml")),
        ),
        regions=[
            RegionDescription(
                name=str(region["name"]),
                label=str(region["label"]),
                predicate=str(region["predicate"]),
                style=RegionStyle(
                    fill=str(region.get("style", {}).get("fill", "#cccccc")),
                    alpha=float(region.get("style", {}).get("alpha", 0.3)),
                    hatch=str(region.get("style", {}).get("hatch", "/")),
                    border=str(region.get("style", {}).get("border", "#333333")),
                    line_style=str(
                        region.get("style", {}).get("line_style", "solid")
                    ),
                ),
                priority=int(region.get("priority", 0)),
            )
            for region in regions_data
        ],
    )


def save_config(config: Config, path: str | Path) -> Path:
    config_path = Path(path)
    payload = {
        "app": {
            "title": config.app.title,
            "theme": config.app.theme,
            "log_level": config.app.log_level,
        },
        "simulation": {
            "alpha": config.simulation.alpha,
            "beta": config.simulation.beta,
            "n_phase_default": config.simulation.n_phase_default,
            "n_geom_default": config.simulation.n_geom_default,
            "eps": config.simulation.eps,
        },
        "replay": {
            "delay_ms": config.replay.delay_ms,
            "selected_only_by_default": config.replay.selected_only_by_default,
        },
        "export": {
            "dpi": config.export.dpi,
            "default_mode": config.export.default_mode,
            "monochrome_line_styles": list(config.export.monochrome_line_styles),
        },
        "view": {
            "show_grid": config.view.show_grid,
            "show_labels": config.view.show_labels,
            "show_directrix": config.view.show_directrix,
            "show_reflection_points": config.view.show_reflection_points,
            "phase_point_radius": config.view.phase_point_radius,
            "geometry_point_radius": config.view.geometry_point_radius,
        },
        "window": {
            "width": config.window.width,
            "height": config.window.height,
            "x": config.window.x,
            "y": config.window.y,
        },
        "autosave": {
            "enabled": config.autosave.enabled,
            "path": config.autosave.path,
        },
        "regions": [
            {
                "name": region.name,
                "label": region.label,
                "predicate": region.predicate,
                "style": {
                    "fill": region.style.fill,
                    "alpha": region.style.alpha,
                    "hatch": region.style.hatch,
                    "border": region.style.border,
                    "line_style": region.style.line_style,
                },
                "priority": region.priority,
            }
            for region in config.regions
        ],
    }

    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(payload, file, sort_keys=False)

    return config_path
