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


@dataclass
class Config:
    app: AppConfig
    simulation: SimulationConfig
    replay: ReplayConfig
    export: ExportConfig
    view: ViewConfig
    regions: list[RegionDescription] = field(default_factory=list)
