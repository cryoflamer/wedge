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
            show_regions=bool(view_data.get("show_regions", True)),
            show_region_labels=bool(view_data.get("show_region_labels", True)),
            show_region_legend=bool(view_data.get("show_region_legend", True)),
            phase_point_radius=int(view_data.get("phase_point_radius", 2)),
            geometry_point_radius=int(view_data.get("geometry_point_radius", 2)),
            angle_hover_tooltip=bool(
                view_data.get("angle_hover_tooltip", True)
            ),
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
                display_text=str(
                    region.get("display_text", region.get("label", region["name"]))
                ),
                legend_text=str(
                    region.get("legend_text", region.get("display_text", region["name"]))
                ),
                region_type=str(region.get("type", "predicate")),
                expression=str(
                    region.get("expression", region.get("predicate", "False"))
                ),
                relation=(
                    str(region["relation"])
                    if region.get("relation") is not None
                    else None
                ),
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
                visible=bool(region.get("visible", True)),
            )
            for region in regions_data
        ],
    )


def save_runtime_config(config: Config, path: str | Path) -> Path:
    config_path = Path(path)
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as file:
            payload = yaml.safe_load(file) or {}
    else:
        payload = {}

    payload["window"] = {
        "width": config.window.width,
        "height": config.window.height,
        "x": config.window.x,
        "y": config.window.y,
    }

    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(payload, file, sort_keys=False)

    return config_path
