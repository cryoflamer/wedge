from __future__ import annotations

import copy

from app.core.math_engine import PhaseState, next_state, validate_state
from app.models.config import SimulationConfig
from app.models.orbit import Orbit, OrbitPoint, ReplayFrame
from app.models.trajectory import TrajectorySeed


def build_orbit(
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
) -> Orbit:
    initial_state = PhaseState(
        d=seed.d0,
        tau=seed.tau0,
        wall=seed.wall_start,
    )
    initial_validation = validate_state(initial_state, config)

    orbit = Orbit(
        trajectory_id=seed.id,
        valid=initial_validation.valid,
        invalid_reason=initial_validation.reason,
    )
    orbit.points.append(
        OrbitPoint(
            step_index=0,
            d=initial_state.d,
            tau=initial_state.tau,
            wall=initial_state.wall,
            valid=initial_validation.valid,
            invalid_reason=initial_validation.reason,
            branch="seed",
        )
    )
    orbit.replay_frames.append(ReplayFrame(frame_index=0, orbit_point_index=0))

    if not initial_validation.valid or steps <= 1:
        orbit.completed_steps = len(orbit.points)
        return orbit

    current_state = initial_state
    for step_index in range(1, steps):
        step_result = next_state(current_state, config)
        if step_result.state is None:
            orbit.valid = False
            orbit.invalid_reason = step_result.reason
            orbit.completed_steps = len(orbit.points)
            return orbit

        orbit.points.append(
            OrbitPoint(
                step_index=step_index,
                d=step_result.state.d,
                tau=step_result.state.tau,
                wall=step_result.state.wall,
                valid=step_result.valid,
                invalid_reason=step_result.reason,
                branch=step_result.branch,
            )
        )
        orbit.replay_frames.append(
            ReplayFrame(
                frame_index=step_index,
                orbit_point_index=step_index,
            )
        )

        if not step_result.valid:
            orbit.valid = False
            orbit.invalid_reason = step_result.reason
            orbit.completed_steps = len(orbit.points)
            return orbit

        current_state = step_result.state

    orbit.completed_steps = len(orbit.points)
    return orbit


def iter_orbit_chunks(
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
    chunk_size: int,
):
    initial_state = PhaseState(
        d=seed.d0,
        tau=seed.tau0,
        wall=seed.wall_start,
    )
    initial_validation = validate_state(initial_state, config)

    orbit = Orbit(
        trajectory_id=seed.id,
        valid=initial_validation.valid,
        invalid_reason=initial_validation.reason,
    )
    orbit.points.append(
        OrbitPoint(
            step_index=0,
            d=initial_state.d,
            tau=initial_state.tau,
            wall=initial_state.wall,
            valid=initial_validation.valid,
            invalid_reason=initial_validation.reason,
            branch="seed",
        )
    )
    orbit.replay_frames.append(ReplayFrame(frame_index=0, orbit_point_index=0))
    orbit.completed_steps = len(orbit.points)

    if not initial_validation.valid or steps <= 1:
        yield copy.deepcopy(orbit), True
        return

    current_state = initial_state
    step_index = 1
    chunk_limit = max(chunk_size, 1)
    while step_index < steps:
        chunk_end = min(step_index + chunk_limit, steps)
        for current_step in range(step_index, chunk_end):
            step_result = next_state(current_state, config)
            if step_result.state is None:
                orbit.valid = False
                orbit.invalid_reason = step_result.reason
                orbit.completed_steps = len(orbit.points)
                yield copy.deepcopy(orbit), True
                return

            orbit.points.append(
                OrbitPoint(
                    step_index=current_step,
                    d=step_result.state.d,
                    tau=step_result.state.tau,
                    wall=step_result.state.wall,
                    valid=step_result.valid,
                    invalid_reason=step_result.reason,
                    branch=step_result.branch,
                )
            )
            orbit.replay_frames.append(
                ReplayFrame(
                    frame_index=current_step,
                    orbit_point_index=current_step,
                )
            )

            if not step_result.valid:
                orbit.valid = False
                orbit.invalid_reason = step_result.reason
                orbit.completed_steps = len(orbit.points)
                yield copy.deepcopy(orbit), True
                return

            current_state = step_result.state

        orbit.completed_steps = len(orbit.points)
        step_index = chunk_end
        yield copy.deepcopy(orbit), step_index >= steps
