from app.models.region import RegionDescription, RegionStyle
from app.models.scene_item import scene_item_from_region, scene_items_from_regions


def test_scene_item_from_region_maps_existing_fields() -> None:
    region = RegionDescription(
        name="test_boundary",
        display_text="Test Boundary",
        legend_text="Boundary Legend",
        region_type="boundary",
        expression="alpha - beta",
        relation="=",
        style=RegionStyle(
            fill="#cccccc",
            alpha=0.0,
            hatch="",
            border="#333333",
            line_style="solid",
            line_width=1.5,
        ),
        priority=7,
        visible=False,
    )

    item = scene_item_from_region(region)

    assert item.name == "test_boundary"
    assert item.alias == "test_boundary"
    assert item.display_text == "Test Boundary"
    assert item.legend_text == "Boundary Legend"
    assert item.expression == "alpha - beta"
    assert item.relation == "="
    assert item.visible is False
    assert item.priority == 7
    assert item.alias == "test_boundary"
    assert item.style == region.style
    assert item.style is not region.style


def test_scene_items_from_regions_maps_every_region() -> None:
    regions = [
        RegionDescription(
            name="r1",
            display_text="R1",
            legend_text="Region 1",
            region_type="predicate",
            expression="False",
            relation=None,
            style=RegionStyle(
                fill="#aaaaaa",
                alpha=0.3,
                hatch="",
                border="#111111",
            ),
        ),
        RegionDescription(
            name="r2",
            display_text="R2",
            legend_text="Region 2",
            region_type="boundary",
            expression="alpha - beta",
            relation="=",
            style=RegionStyle(
                fill="#bbbbbb",
                alpha=0.0,
                hatch="",
                border="#222222",
            ),
        ),
    ]

    items = scene_items_from_regions(regions)

    assert [item.name for item in items] == ["r1", "r2"]
    assert items[0].relation is None
    assert items[1].relation == "="
