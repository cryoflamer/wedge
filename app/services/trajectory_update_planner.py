from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.config import SimulationConfig
from app.models.simulation_fingerprint import SimulationFingerprint
from app.models.trajectory_metadata import TrajectoryBuildMetadata


class TrajectoryUpdateDecision(str, Enum):
    """Actions required to make an existing trajectory match a new simulation config."""

    UNCHANGED = "unchanged"
    REDRAW = "redraw"
    EXTEND = "extend"
    TRUNCATE = "truncate"
    REBUILD = "rebuild"


@dataclass(frozen=True)
class TrajectoryUpdatePlan:
    """Planner result for a single trajectory."""

    decision: TrajectoryUpdateDecision
    reason: str


class TrajectoryUpdatePlanner:
    """Pure planner for deciding how a trajectory should react to config changes."""

    @staticmethod
    def plan(
        metadata: TrajectoryBuildMetadata | None,
        new_config: SimulationConfig,
    ) -> TrajectoryUpdatePlan:
        if metadata is None:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.REBUILD,
                reason="trajectory metadata is missing",
            )

        new_fingerprint = SimulationFingerprint.from_config(new_config)
        if metadata.fingerprint != new_fingerprint:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.REBUILD,
                reason="simulation fingerprint changed",
            )

        if metadata.phase_steps < new_config.n_phase_default:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.EXTEND,
                reason="phase length increased",
            )

        if metadata.phase_steps > new_config.n_phase_default:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.TRUNCATE,
                reason="phase length decreased",
            )

        if metadata.geom_steps != new_config.n_geom_default:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.REDRAW,
                reason="geometry length changed",
            )

        return TrajectoryUpdatePlan(
            decision=TrajectoryUpdateDecision.UNCHANGED,
            reason="trajectory is up to date",
        )
