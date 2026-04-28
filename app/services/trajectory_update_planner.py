from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.models.config import SimulationConfig
from app.models.trajectory_metadata import TrajectoryBuildMetadata
from app.services.trajectory_metadata_builder import build_metadata_from_config


class TrajectoryUpdateDecision(str, Enum):
    """Actions required to make an existing trajectory match desired metadata."""

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
    """Pure planner for deciding how a trajectory should react to metadata changes."""

    @staticmethod
    def plan_metadata(
        metadata: TrajectoryBuildMetadata | None,
        desired_metadata: TrajectoryBuildMetadata,
    ) -> TrajectoryUpdatePlan:
        """Plan an update from existing build metadata to desired build metadata."""
        if metadata is None:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.REBUILD,
                reason="trajectory metadata is missing",
            )

        if metadata.fingerprint != desired_metadata.fingerprint:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.REBUILD,
                reason="simulation fingerprint changed",
            )

        if metadata.phase_steps < desired_metadata.phase_steps:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.EXTEND,
                reason="phase length increased",
            )

        if metadata.phase_steps > desired_metadata.phase_steps:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.TRUNCATE,
                reason="phase length decreased",
            )

        if metadata.geom_steps != desired_metadata.geom_steps:
            return TrajectoryUpdatePlan(
                decision=TrajectoryUpdateDecision.REDRAW,
                reason="geometry length changed",
            )

        return TrajectoryUpdatePlan(
            decision=TrajectoryUpdateDecision.UNCHANGED,
            reason="trajectory is up to date",
        )

    @staticmethod
    def plan(
        metadata: TrajectoryBuildMetadata | None,
        new_config: SimulationConfig,
    ) -> TrajectoryUpdatePlan:
        """Compatibility wrapper for planning against a simulation config."""
        desired_metadata = build_metadata_from_config(new_config)
        return TrajectoryUpdatePlanner.plan_metadata(metadata, desired_metadata)
