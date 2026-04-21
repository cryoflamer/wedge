from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConstraintDescription:
    name: str
    constraint_type: str
    display_text: str
    legend_text: str
    expression: str | None = None
    target: str | None = None
    priority: int = 0
    visible: bool = True
