from __future__ import annotations

from copy import deepcopy

from app.models.config import Config
from app.models.region import RegionStyle
from app.models.scene_item import SceneItemDescription


class SceneService:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._dirty = False

    def items(self) -> list[SceneItemDescription]:
        return self._config.regions

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def clear_dirty(self) -> None:
        self._dirty = False

    def selected_item(self, item_name: str | None) -> SceneItemDescription | None:
        if item_name is None:
            return None
        return next((item for item in self._config.regions if item.name == item_name), None)

    def add_item(self, name: str, alias: str) -> SceneItemDescription:
        item = SceneItemDescription(
            name=name,
            alias=alias,
            display_text=alias,
            legend_text=alias,
            expression="0",
            relation="=",
            visible=True,
            priority=0,
            style=RegionStyle(
                fill="#cccccc",
                alpha=0.3,
                hatch="",
                border="#333333",
                line_style="solid",
                line_width=1.0,
            ),
        )
        self._config.regions.append(item)
        self.mark_dirty()
        return item

    def duplicate_item(self, item_name: str) -> SceneItemDescription | None:
        selected = self.selected_item(item_name)
        if selected is None:
            return None
        duplicate = deepcopy(selected)
        duplicate.name = self.unique_copy_name(selected.name)
        self._config.regions.append(duplicate)
        self.mark_dirty()
        return duplicate

    def delete_item(self, item_name: str) -> tuple[SceneItemDescription | None, str | None]:
        selected_index = next(
            (index for index, item in enumerate(self._config.regions) if item.name == item_name),
            -1,
        )
        if selected_index < 0:
            return None, None
        removed = self._config.regions.pop(selected_index)
        remaining_items = sorted(self._config.regions, key=lambda entry: entry.priority)
        next_name: str | None = None
        if remaining_items:
            next_index = min(selected_index, len(remaining_items) - 1)
            next_name = remaining_items[next_index].name
        self.mark_dirty()
        return removed, next_name

    def unique_copy_name(self, base_name: str) -> str:
        existing_names = {item.name for item in self._config.regions}
        candidate = f"{base_name}_copy"
        if candidate not in existing_names:
            return candidate
        index = 2
        while True:
            candidate = f"{base_name}_copy{index}"
            if candidate not in existing_names:
                return candidate
            index += 1

    def apply_editor_payload(
        self,
        item_name: str,
        payload: dict[str, object],
    ) -> SceneItemDescription | None:
        item = self.selected_item(item_name)
        if item is None:
            return None
        item.alias = str(payload.get("alias", item.alias)).strip() or item.alias
        item.display_text = str(payload.get("display_text", item.display_text)).strip() or item.display_text
        item.legend_text = str(payload.get("legend_text", item.legend_text)).strip() or item.legend_text
        item.expression = str(payload.get("expression", item.expression)).strip()
        item.relation = str(payload.get("relation", item.relation or "=")).strip() or "="
        item.visible = bool(payload.get("visible", item.visible))
        try:
            item.priority = int(payload.get("priority", item.priority))
        except (TypeError, ValueError):
            pass
        item.style.fill = str(payload.get("fill", item.style.fill)).strip() or item.style.fill
        item.style.border = str(payload.get("border", item.style.border)).strip() or item.style.border
        try:
            item.style.line_width = float(payload.get("line_width", item.style.line_width))
        except (TypeError, ValueError):
            pass
        item.style.line_style = (
            "dashed"
            if str(payload.get("line_style", item.style.line_style)).strip().lower() == "dashed"
            else "solid"
        )
        item.compatibility_predicate = False
        self.mark_dirty()
        return item
