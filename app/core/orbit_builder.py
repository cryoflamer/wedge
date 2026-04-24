from __future__ import annotations

import copy
import time
from typing import Optional, Tuple

from app.core.math_engine import PhaseState, next_state, validate_state
from app.models.config import SimulationConfig
from app.models.orbit import Orbit, OrbitPoint, ReplayFrame
from app.models.trajectory import TrajectorySeed

PhaseSample = Tuple[int, float, float, int, bool, Optional[str], Optional[str]]


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
    perf_enabled = config.performance_trace
    t0 = time.perf_counter()
    ns_time = 0.0
    phase_samples: list[PhaseSample] = []
    for step_index in range(1, steps):
        t_ns0 = time.perf_counter()
        step_result = next_state(current_state, config)
        ns_time += time.perf_counter() - t_ns0
        if step_result.state is None:
            orbit.valid = False
            orbit.invalid_reason = step_result.reason
            _append_phase_samples(orbit, phase_samples)
            orbit.completed_steps = len(orbit.points)
            _print_loop_profile(perf_enabled, t0, ns_time)
            return orbit

        phase_samples.append(
            (
                step_index,
                step_result.state.d,
                step_result.state.tau,
                step_result.state.wall,
                step_result.valid,
                step_result.reason,
                step_result.branch,
            )
        )

        if not step_result.valid:
            orbit.valid = False
            orbit.invalid_reason = step_result.reason
            _append_phase_samples(orbit, phase_samples)
            orbit.completed_steps = len(orbit.points)
            _print_loop_profile(perf_enabled, t0, ns_time)
            return orbit

        current_state = step_result.state

    _append_phase_samples(orbit, phase_samples)
    orbit.completed_steps = len(orbit.points)
    _print_loop_profile(perf_enabled, t0, ns_time)
    return orbit


def iter_orbit_chunks(
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
    chunk_size: int,
    cancel_check=None,
    existing_orbit: Orbit | None = None,
):
    if existing_orbit is not None and existing_orbit.points:
        orbit = copy.deepcopy(existing_orbit)
        orbit.trajectory_id = seed.id
        orbit.completed_steps = len(orbit.points)
        if not orbit.valid or len(orbit.points) >= steps:
            yield copy.deepcopy(orbit), True
            return
        last_point = orbit.points[-1]
        current_state = PhaseState(
            d=last_point.d,
            tau=last_point.tau,
            wall=last_point.wall,
        )
        step_index = len(orbit.points)
    else:
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
    perf_enabled = config.performance_trace
    t0 = time.perf_counter()
    ns_time = 0.0
    while step_index < steps:
        if cancel_check is not None and cancel_check():
            orbit.completed_steps = len(orbit.points)
            _print_loop_profile(perf_enabled, t0, ns_time)
            return
        chunk_end = min(step_index + chunk_limit, steps)
        chunk_samples: list[PhaseSample] = []
        for current_step in range(step_index, chunk_end):
            if cancel_check is not None and cancel_check():
                orbit.completed_steps = len(orbit.points)
                _print_loop_profile(perf_enabled, t0, ns_time)
                return
            t_ns0 = time.perf_counter()
            step_result = next_state(current_state, config)
            ns_time += time.perf_counter() - t_ns0
            if step_result.state is None:
                orbit.valid = False
                orbit.invalid_reason = step_result.reason
                _append_phase_samples(orbit, chunk_samples)
                orbit.completed_steps = len(orbit.points)
                _print_loop_profile(perf_enabled, t0, ns_time)
                yield copy.deepcopy(orbit), True
                return

            chunk_samples.append(
                (
                    current_step,
                    step_result.state.d,
                    step_result.state.tau,
                    step_result.state.wall,
                    step_result.valid,
                    step_result.reason,
                    step_result.branch,
                )
            )

            if not step_result.valid:
                orbit.valid = False
                orbit.invalid_reason = step_result.reason
                _append_phase_samples(orbit, chunk_samples)
                orbit.completed_steps = len(orbit.points)
                _print_loop_profile(perf_enabled, t0, ns_time)
                yield copy.deepcopy(orbit), True
                return

            current_state = step_result.state

        _append_phase_samples(orbit, chunk_samples)
        orbit.completed_steps = len(orbit.points)
        step_index = chunk_end
        yield copy.deepcopy(orbit), step_index >= steps
    _print_loop_profile(perf_enabled, t0, ns_time)


def _print_loop_profile(perf_enabled: bool, t0: float, ns_time: float) -> None:
    if not perf_enabled:
        return
    total = time.perf_counter() - t0
    print(f"[loop] total: {total:.3f}s")
    print(f"[loop] next_state: {ns_time:.3f}s")
    print(f"[loop] overhead: {total - ns_time:.3f}s")


def _append_phase_samples(orbit: Orbit, samples: list[PhaseSample]) -> None:
    for step_index, d_value, tau_value, wall, valid, reason, branch in samples:
        orbit.points.append(
            OrbitPoint(
                step_index=step_index,
                d=d_value,
                tau=tau_value,
                wall=wall,
                valid=valid,
                invalid_reason=reason,
                branch=branch,
            )
        )
        orbit.replay_frames.append(
            ReplayFrame(
                frame_index=step_index,
                orbit_point_index=step_index,
            )
        )
