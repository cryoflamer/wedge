from __future__ import annotations

from pathlib import Path

import yaml

from app.models.config import (
    AppConfig,
    AutosaveConfig,
    BackgroundConfig,
    Config,
    ExportConfig,
    LyapunovConfig,
    PhaseGridConfig,
    ReplayConfig,
    SimulationConfig,
    ViewConfig,
    WindowConfig,
)
from app.models.constraint import ConstraintDescription
from app.models.region import RegionDescription, RegionStyle


def load_config(path: str | Path) -> Config:
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    app_data = data.get("app", {})
    simulation_data = data.get("simulation", {})
    replay_data = data.get("replay", {})
    background_data = data.get("background", {})
    lyapunov_data = data.get("lyapunov", {})
    export_data = data.get("export", {})
    view_data = data.get("view", {})
    phase_grid_data = view_data.get("phase_grid", {})
    window_data = data.get("window", {})
    autosave_data = data.get("autosave", {})
    scene_items = data.get("regions", [])
    constraints: list[ConstraintDescription] = []
    regions: list[RegionDescription] = []

    for item in scene_items:
        item_type = str(item.get("type", "predicate"))
        if item_type == "constraint":
            constraints.append(
                ConstraintDescription(
                    name=str(item["name"]),
                    constraint_type=str(item.get("constraint_type", "symmetry")),
                    display_text=str(
                        item.get("display_text", item.get("label", item["name"]))
                    ),
                    legend_text=str(
                        item.get("legend_text", item.get("display_text", item["name"]))
                    ),
                    expression=(
                        str(item["expression"])
                        if item.get("expression") is not None
                        else None
                    ),
                    target=(
                        str(item["target"])
                        if item.get("target") is not None
                        else None
                    ),
                    priority=int(item.get("priority", 0)),
                    visible=bool(item.get("visible", True)),
                )
            )
            continue

        regions.append(
            RegionDescription(
                name=str(item["name"]),
                display_text=str(
                    item.get("display_text", item.get("label", item["name"]))
                ),
                legend_text=str(
                    item.get("legend_text", item.get("display_text", item["name"]))
                ),
                region_type=item_type,
                expression=str(
                    item.get("expression", item.get("predicate", "False"))
                ),
                relation=(
                    str(item["relation"])
                    if item.get("relation") is not None
                    else None
                ),
                style=RegionStyle(
                    fill=str(item.get("style", {}).get("fill", "#cccccc")),
                    alpha=float(item.get("style", {}).get("alpha", 0.3)),
                    hatch=str(item.get("style", {}).get("hatch", "/")),
                    border=str(item.get("style", {}).get("border", "#333333")),
                    line_style=str(
                        item.get("style", {}).get("line_style", "solid")
                    ),
                    line_width=float(item.get("style", {}).get("line_width", 1.0)),
                ),
                priority=int(item.get("priority", 0)),
                visible=bool(item.get("visible", True)),
            )
        )

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
        background=BackgroundConfig(
            build_chunk_size=int(background_data.get("build_chunk_size", 16)),
            fast_build=bool(background_data.get("fast_build", False)),
        ),
        lyapunov=LyapunovConfig(
            delta0=float(lyapunov_data.get("delta0", 1.0e-6)),
            transient_steps=int(lyapunov_data.get("transient_steps", 10)),
            max_steps=int(lyapunov_data.get("max_steps", 200)),
            renormalization_interval=int(
                lyapunov_data.get("renormalization_interval", 1)
            ),
            eps=float(lyapunov_data.get("eps", 1.0e-12)),
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
            show_phase_grid=bool(
                view_data.get(
                    "show_phase_grid",
                    view_data.get("show_grid", True),
                )
            ),
            show_phase_minor_grid=bool(
                view_data.get(
                    "show_phase_minor_grid",
                    phase_grid_data.get("show_minor", False),
                )
            ),
            show_seed_markers=bool(
                view_data.get("show_seed_markers", True)
            ),
            show_stationary_point=bool(
                view_data.get("show_stationary_point", True)
            ),
            phase_grid=PhaseGridConfig(
                major_step_d=float(phase_grid_data.get("major_step_d", 0.1)),
                major_step_tau=float(phase_grid_data.get("major_step_tau", 0.1)),
                minor_step_d=float(phase_grid_data.get("minor_step_d", 0.05)),
                minor_step_tau=float(phase_grid_data.get("minor_step_tau", 0.05)),
                show_minor=bool(phase_grid_data.get("show_minor", False)),
                major_color=str(phase_grid_data.get("major_color", "#cccccc")),
                minor_color=str(phase_grid_data.get("minor_color", "#e6e6e6")),
                major_width=float(phase_grid_data.get("major_width", 1.0)),
                minor_width=float(phase_grid_data.get("minor_width", 0.6)),
                major_alpha=float(phase_grid_data.get("major_alpha", 0.8)),
                minor_alpha=float(phase_grid_data.get("minor_alpha", 0.5)),
                major_style=str(phase_grid_data.get("major_style", "solid")),
                minor_style=str(phase_grid_data.get("minor_style", "dotted")),
            ),
            show_labels=bool(view_data.get("show_labels", True)),
            show_directrix=bool(view_data.get("show_directrix", False)),
            show_reflection_points=bool(
                view_data.get("show_reflection_points", True)
            ),
            show_regions=bool(view_data.get("show_regions", True)),
            show_region_labels=bool(view_data.get("show_region_labels", True)),
            show_labels_on_plot=bool(
                view_data.get("show_labels_on_plot", False)
            ),
            plot_label_mode=str(view_data.get("plot_label_mode", "legend")),
            tooltip_label_mode=str(
                view_data.get("tooltip_label_mode", "legend")
            ),
            show_region_legend=bool(view_data.get("show_region_legend", True)),
            show_branch_markers=bool(
                view_data.get("show_branch_markers", False)
            ),
            show_heatmap=bool(view_data.get("show_heatmap", False)),
            heatmap_mode=str(view_data.get("heatmap_mode", "all")),
            heatmap_resolution=int(view_data.get("heatmap_resolution", 32)),
            heatmap_normalization=str(
                view_data.get("heatmap_normalization", "linear")
            ),
            active_angle_constraint=(
                str(view_data["active_angle_constraint"])
                if view_data.get("active_angle_constraint") is not None
                else None
            ),
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
            restore_simulation_parameters=bool(
                autosave_data.get("restore_simulation_parameters", True)
            ),
        ),
        regions=regions,
        constraints=constraints,
    )


def save_runtime_config(
    config: Config,
    path: str | Path,
    *,
    persist_boundary_styles: bool = False,
    persist_scene_items: bool = False,
) -> Path:
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
    background_payload = payload.get("background", {})
    if not isinstance(background_payload, dict):
        background_payload = {}
    background_payload["build_chunk_size"] = config.background.build_chunk_size
    background_payload["fast_build"] = config.background.fast_build
    payload["background"] = background_payload

    if persist_scene_items:
        regions_payload: list[dict] = []
        for region in config.regions:
            item: dict[str, object] = {
                "name": region.name,
                "type": region.region_type,
                "display_text": region.display_text,
                "legend_text": region.legend_text,
                "expression": region.expression,
                "priority": region.priority,
                "visible": region.visible,
                "style": {
                    "fill": region.style.fill,
                    "alpha": region.style.alpha,
                    "hatch": region.style.hatch,
                    "border": region.style.border,
                    "line_style": region.style.line_style,
                    "line_width": region.style.line_width,
                },
            }
            if region.relation is not None:
                item["relation"] = region.relation
            regions_payload.append(item)
        payload["regions"] = regions_payload
    elif persist_boundary_styles:
        regions_payload = payload.get("regions", [])
        if not isinstance(regions_payload, list):
            regions_payload = []
        region_items_by_name = {
            str(item.get("name")): item
            for item in regions_payload
            if isinstance(item, dict) and item.get("name") is not None
        }
        for region in config.regions:
            item = region_items_by_name.get(region.name)
            if item is None:
                continue
            style_payload = item.get("style", {})
            if not isinstance(style_payload, dict):
                style_payload = {}
            style_payload["border"] = region.style.border
            style_payload["line_style"] = region.style.line_style
            style_payload["line_width"] = region.style.line_width
            item["style"] = style_payload
        payload["regions"] = regions_payload

    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(
            payload,
            file,
            sort_keys=False,
            allow_unicode=True,
        )

    return config_path
