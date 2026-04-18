from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RegionStyle:
    fill: str
    alpha: float
    hatch: str
    border: str
    line_style: str = "solid"


@dataclass
class RegionDescription:
    name: str
    display_text: str
    legend_text: str
    region_type: str
    expression: str
    relation: str | None
    style: RegionStyle
    priority: int = 0
    visible: bool = True
