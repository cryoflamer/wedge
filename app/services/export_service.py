from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget


def export_widget_png(
    widget: QWidget,
    output_path: str | Path,
    dpi: int,
    monochrome: bool = False,
) -> Path:
    path = Path(output_path)
    image = widget.grab().toImage()

    if monochrome:
        image = image.convertToFormat(QImage.Format_Grayscale8)

    dots_per_meter = int(dpi / 0.0254)
    image.setDotsPerMeterX(dots_per_meter)
    image.setDotsPerMeterY(dots_per_meter)
    image.save(str(path), "PNG")
    return path


def export_widget_bundle_png(
    widgets: dict[str, QWidget],
    base_path: str | Path,
    dpi: int,
    monochrome: bool = False,
) -> list[Path]:
    path = Path(base_path)
    stem = path.stem
    suffix = path.suffix or ".png"
    parent = path.parent

    exported_paths: list[Path] = []
    for name, widget in widgets.items():
        output_path = parent / f"{stem}_{name}{suffix}"
        exported_paths.append(
            export_widget_png(
                widget=widget,
                output_path=output_path,
                dpi=dpi,
                monochrome=monochrome,
            )
        )

    return exported_paths
