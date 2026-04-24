from __future__ import annotations

from dataclasses import dataclass, field

from app.models.constraint import ConstraintDescription
from app.models.scene_item import SceneItemDescription


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
    performance_trace: bool = False


@dataclass
class ReplayConfig:
    delay_ms: int
    selected_only_by_default: bool = True


@dataclass
class BackgroundConfig:
    build_chunk_size: int = 16
    fast_build: bool = False


@dataclass
class DebugConfig:
    performance_trace: bool = False


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
class PhaseGridConfig:
    major_step_d: float = 0.1
    major_step_tau: float = 0.1
    minor_step_d: float = 0.05
    minor_step_tau: float = 0.05
    show_minor: bool = False
    major_color: str = "#cccccc"
    minor_color: str = "#e6e6e6"
    major_width: float = 1.0
    minor_width: float = 0.6
    major_alpha: float = 0.8
    minor_alpha: float = 0.5
    major_style: str = "solid"
    minor_style: str = "dotted"


@dataclass
class ViewConfig:
    show_phase_grid: bool = True
    show_phase_minor_grid: bool = False
    show_seed_markers: bool = True
    show_stationary_point: bool = True
    phase_grid: PhaseGridConfig = field(default_factory=PhaseGridConfig)
    show_labels: bool = True
    show_directrix: bool = False
    show_reflection_points: bool = True
    show_regions: bool = True
    show_region_labels: bool = True
    show_labels_on_plot: bool = False
    plot_label_mode: str = "legend"
    tooltip_label_mode: str = "legend"
    show_region_legend: bool = True
    show_branch_markers: bool = False
    show_heatmap: bool = False
    heatmap_mode: str = "all"
    heatmap_resolution: int = 32
    heatmap_normalization: str = "linear"
    active_angle_constraint: str | None = None
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
    restore_simulation_parameters: bool = False


@dataclass
class Config:
    app: AppConfig
    simulation: SimulationConfig
    replay: ReplayConfig
    lyapunov: LyapunovConfig
    export: ExportConfig
    view: ViewConfig
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    autosave: AutosaveConfig = field(default_factory=AutosaveConfig)
    regions: list[SceneItemDescription] = field(default_factory=list)
    constraints: list[ConstraintDescription] = field(default_factory=list)
