from __future__ import annotations

import csv
import json
from pathlib import Path

from app.models.orbit import Orbit


def export_orbit_data(
    orbit: Orbit,
    output_path: str | Path,
    export_format: str,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_format = export_format.strip().lower()

    rows = [
        {
            "step_index": point.step_index,
            "d": point.d,
            "tau": point.tau,
            "wall": point.wall,
            "branch": point.branch,
        }
        for point in orbit.points
    ]

    if normalized_format == "csv":
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["step_index", "d", "tau", "wall", "branch"],
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    if normalized_format == "json":
        payload = {
            "trajectory_id": orbit.trajectory_id,
            "valid": orbit.valid,
            "invalid_reason": orbit.invalid_reason,
            "completed_steps": orbit.completed_steps,
            "points": rows,
        }
        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")
        return path

    raise ValueError(f"Unsupported export format: {export_format}")
