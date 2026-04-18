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
    label: str
    predicate: str
    style: RegionStyle
    priority: int = 0
