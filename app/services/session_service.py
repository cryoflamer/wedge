from __future__ import annotations

from pathlib import Path

import yaml

from app.models.session import Session
from app.models.trajectory import TrajectorySeed


def save_session(session: Session, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "alpha": session.alpha,
        "beta": session.beta,
        "n_phase": session.n_phase,
        "n_geom": session.n_geom,
        "replay_delay_ms": session.replay_delay_ms,
        "replay_selected_only": session.replay_selected_only,
        "selected_trajectory_id": session.selected_trajectory_id,
        "angle_units": session.angle_units,
        "symmetric_mode": session.symmetric_mode,
        "export_mode": session.export_mode,
        "phase_fixed_domain": session.phase_fixed_domain,
        "show_phase_grid": session.show_phase_grid,
        "show_phase_minor_grid": session.show_phase_minor_grid,
        "show_seed_markers": session.show_seed_markers,
        "show_stationary_point": session.show_stationary_point,
        "show_directrix": session.show_directrix,
        "show_regions": session.show_regions,
        "show_region_labels": session.show_region_labels,
        "show_region_legend": session.show_region_legend,
        "show_branch_markers": session.show_branch_markers,
        "show_heatmap": session.show_heatmap,
        "heatmap_mode": session.heatmap_mode,
        "heatmap_resolution": session.heatmap_resolution,
        "heatmap_normalization": session.heatmap_normalization,
        "active_angle_constraint": session.active_angle_constraint,
        "fast_build": session.fast_build,
        "trajectories": [
            {
                "id": trajectory.id,
                "wall_start": trajectory.wall_start,
                "d0": trajectory.d0,
                "tau0": trajectory.tau0,
                "visible": trajectory.visible,
                "color": trajectory.color,
            }
            for trajectory in session.trajectories
        ],
        "phase_viewport_wall_1": session.phase_viewport_wall_1,
        "phase_viewport_wall_2": session.phase_viewport_wall_2,
    }

    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(payload, file, sort_keys=False)

    return path


def load_session(input_path: str | Path) -> Session:
    path = Path(input_path)
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    trajectories = [
        TrajectorySeed(
            id=int(item["id"]),
            wall_start=int(item["wall_start"]),
            d0=float(item["d0"]),
            tau0=float(item["tau0"]),
            visible=bool(item.get("visible", True)),
            color=str(item.get("color", "#1f77b4")),
        )
        for item in data.get("trajectories", [])
    ]

    return Session(
        alpha=float(data["alpha"]),
        beta=float(data["beta"]),
        n_phase=int(data["n_phase"]),
        n_geom=int(data["n_geom"]),
        replay_delay_ms=int(data.get("replay_delay_ms", 120)),
        replay_selected_only=bool(data.get("replay_selected_only", True)),
        selected_trajectory_id=(
            int(data["selected_trajectory_id"])
            if data.get("selected_trajectory_id") is not None
            else None
        ),
        angle_units=str(data.get("angle_units", "rad")),
        symmetric_mode=bool(data.get("symmetric_mode", False)),
        export_mode=str(data.get("export_mode", "color")),
        phase_fixed_domain=bool(data.get("phase_fixed_domain", True)),
        show_phase_grid=bool(data.get("show_phase_grid", True)),
        show_phase_minor_grid=bool(data.get("show_phase_minor_grid", False)),
        show_seed_markers=bool(data.get("show_seed_markers", True)),
        show_stationary_point=bool(data.get("show_stationary_point", True)),
        show_directrix=bool(data.get("show_directrix", False)),
        show_regions=bool(data.get("show_regions", True)),
        show_region_labels=bool(data.get("show_region_labels", True)),
        show_region_legend=bool(data.get("show_region_legend", True)),
        show_branch_markers=bool(data.get("show_branch_markers", False)),
        show_heatmap=bool(data.get("show_heatmap", False)),
        heatmap_mode=str(data.get("heatmap_mode", "all")),
        heatmap_resolution=int(data.get("heatmap_resolution", 32)),
        heatmap_normalization=str(data.get("heatmap_normalization", "linear")),
        active_angle_constraint=(
            str(data["active_angle_constraint"])
            if data.get("active_angle_constraint") is not None
            else None
        ),
        fast_build=bool(data.get("fast_build", False)),
        trajectories=trajectories,
        phase_viewport_wall_1=_as_viewport(data.get("phase_viewport_wall_1")),
        phase_viewport_wall_2=_as_viewport(data.get("phase_viewport_wall_2")),
    )


def _as_viewport(value: object) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return tuple(float(item) for item in value)
