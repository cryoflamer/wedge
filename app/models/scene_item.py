from __future__ import annotations

from dataclasses import dataclass

from app.models.region import RegionDescription, RegionStyle


@dataclass
class SceneItemDescription:
    name: str
    # Transitional fallback only: the old RegionDescription model does not
    # store a separate alias yet, so the adapter currently mirrors `name`.
    alias: str
    display_text: str
    legend_text: str
    expression: str
    relation: str | None
    visible: bool
    priority: int
    style: RegionStyle


def scene_item_from_region(region: RegionDescription) -> SceneItemDescription:
    """Adapt the old region/boundary runtime model into a transitional scene item.

    Compatibility notes:
    - boundary items keep `expression` and use relation "="
    - implicit region items keep their old `relation`
    - predicate items remain a temporary compatibility case until evaluator
      unification moves everything onto the final expression + relation model
    """
    return SceneItemDescription(
        name=region.name,
        alias=region.name,
        display_text=region.display_text,
        legend_text=region.legend_text,
        expression=region.expression,
        relation="=" if region.region_type == "boundary" else region.relation,
        visible=region.visible,
        priority=region.priority,
        style=RegionStyle(
            fill=region.style.fill,
            alpha=region.style.alpha,
            hatch=region.style.hatch,
            border=region.style.border,
            line_style=region.style.line_style,
            line_width=region.style.line_width,
        ),
    )


def scene_items_from_regions(
    regions: list[RegionDescription],
) -> list[SceneItemDescription]:
    return [scene_item_from_region(region) for region in regions]
