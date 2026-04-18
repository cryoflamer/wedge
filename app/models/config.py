from __future__ import annotations

from dataclasses import dataclass, field

from app.models.region import RegionDescription


@dataclass
class AppConfig:
    title: str
    theme: str
    log_level: str = "INFO"


@dataclass
class SimulationConfig:
    alpha: float
    beta: float
    n_phase_default: int
    n_geom_default: int
    eps: float = 1.0e-9


@dataclass
class ReplayConfig:
    delay_ms: int
    selected_only_by_default: bool = True


@dataclass
class LyapunovConfig:
    delta0: float = 1.0e-6
    transient_steps: int = 10
    max_steps: int = 200
    renormalization_interval: int = 1
    eps: float = 1.0e-12


@dataclass
class ExportConfig:
    dpi: int
    default_mode: str
    monochrome_line_styles: list[str] = field(default_factory=list)


@dataclass
class ViewConfig:
    show_grid: bool = True
    show_labels: bool = True
    show_directrix: bool = False
    show_reflection_points: bool = True
    show_regions: bool = True
    show_region_labels: bool = True
    show_region_legend: bool = True
    show_branch_markers: bool = False
    phase_point_radius: int = 2
    geometry_point_radius: int = 2
    angle_hover_tooltip: bool = True


@dataclass
class WindowConfig:
    width: int = 1360
    height: int = 980
    x: int | None = None
    y: int | None = None


@dataclass
class AutosaveConfig:
    enabled: bool = True
    path: str = "autosave/session.yaml"


@dataclass
class Config:
    app: AppConfig
    simulation: SimulationConfig
    replay: ReplayConfig
    lyapunov: LyapunovConfig
    export: ExportConfig
    view: ViewConfig
    window: WindowConfig = field(default_factory=WindowConfig)
    autosave: AutosaveConfig = field(default_factory=AutosaveConfig)
    regions: list[RegionDescription] = field(default_factory=list)
