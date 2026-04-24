from __future__ import annotations

from dataclasses import dataclass
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from app.core.native_backend import is_native_available, native_build_sparse_orbits_batch
from app.core.trajectory_engine import (
    build_dense_orbit_for_geometry,
    build_orbit,
    build_wedge_geometry,
    compute_finite_time_lyapunov,
    iter_orbit_chunks,
)
from app.models.config import LyapunovConfig, SimulationConfig
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit, OrbitPoint, ReplayFrame
from app.models.trajectory import TrajectorySeed
from app.services.scan_sampler import generate_scan_points

NATIVE_SCAN_BATCH_CHUNK_SIZE = 128


@dataclass(frozen=True)
class JobProgress:
    generation_id: int
    job_kind: str
    status: str
    current: int
    total: int
    message: str


@dataclass(frozen=True)
class OrbitPartialResult:
    generation_id: int
    trajectory_id: int
    seed: TrajectorySeed
    orbit: Orbit
    geometry: WedgeGeometry
    replace: bool
    current: int
    total: int
    message: str


@dataclass(frozen=True)
class JobFinished:
    generation_id: int
    job_kind: str
    status: str
    message: str


@dataclass(frozen=True)
class LyapunovResultPayload:
    generation_id: int
    trajectory_id: int
    estimate: float | None
    running_estimate: list[float]
    status: str
    reason: str | None
    steps_used: int
    wall_divergence_count: int


class OrbitBuildWorker(QObject):
    progress = Signal(object)
    partial_result = Signal(object)
    lyapunov_result = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        generation_id: int,
        job_kind: str,
        simulation_config: SimulationConfig,
        max_reflections: int,
        phase_steps: int,
        chunk_size: int,
        seeds: list[TrajectorySeed] | None = None,
        scan_mode: str | None = None,
        scan_count: int = 0,
        scan_wall: int = 1,
        scan_d_min: float = 0.0,
        scan_d_max: float = 0.0,
        scan_tau_min: float = 0.0,
        scan_tau_max: float = 0.0,
        next_trajectory_id: int = 1,
        palette: list[str] | None = None,
        max_trajectory_count: int = 0,
        lyapunov_seed: TrajectorySeed | None = None,
        lyapunov_config: LyapunovConfig | None = None,
        existing_orbits: dict[int, Orbit] | None = None,
        fast_build: bool = False,
    ) -> None:
        super().__init__()
        self._generation_id = generation_id
        self._job_kind = job_kind
        self._simulation_config = simulation_config
        self._max_reflections = max_reflections
        self._phase_steps = phase_steps
        self._chunk_size = max(chunk_size, 1)
        self._seeds = list(seeds or [])
        self._scan_mode = scan_mode or "grid"
        self._scan_count = scan_count
        self._scan_wall = scan_wall
        self._scan_d_min = scan_d_min
        self._scan_d_max = scan_d_max
        self._scan_tau_min = scan_tau_min
        self._scan_tau_max = scan_tau_max
        self._next_trajectory_id = next_trajectory_id
        self._palette = list(palette or [])
        self._max_trajectory_count = max_trajectory_count
        self._lyapunov_seed = lyapunov_seed
        self._lyapunov_config = lyapunov_config
        self._existing_orbits = dict(existing_orbits or {})
        self._fast_build = fast_build
        self._cancel_event = Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def _is_cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    @Slot()
    def run(self) -> None:
        if self._job_kind == "single_build":
            self._run_single_build()
            return
        if self._job_kind == "rebuild":
            self._run_rebuild()
            return
        if self._job_kind == "scan":
            self._run_scan()
            return
        if self._job_kind == "lyapunov":
            self._run_lyapunov()
            return

        self.finished.emit(
            JobFinished(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="failed",
                message=f"unsupported job kind: {self._job_kind}",
            )
        )

    def _run_single_build(self) -> None:
        if not self._seeds:
            self.finished.emit(
                JobFinished(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="failed",
                    message="missing seed",
                )
            )
            return

        seed = self._seeds[0]
        total_steps = max(self._phase_steps - 1, 1)
        self.progress.emit(
            JobProgress(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="running",
                current=0,
                total=total_steps,
                message=f"Building trajectory #{seed.id}",
            )
        )
        if self._fast_build:
            orbit = build_orbit(
                seed=seed,
                config=self._simulation_config,
                steps=self._phase_steps,
            )
            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message="build cancelled",
                    )
                )
                return
            geometry = build_wedge_geometry(
                orbit=self._build_geometry_orbit(seed, orbit),
                config=self._simulation_config,
                max_reflections=self._max_reflections,
            )
            current = max(len(orbit.points) - 1, 0)
            self.partial_result.emit(
                OrbitPartialResult(
                    generation_id=self._generation_id,
                    trajectory_id=seed.id,
                    seed=seed,
                    orbit=orbit,
                    geometry=geometry,
                    replace=True,
                    current=current,
                    total=total_steps,
                    message=f"Building trajectory #{seed.id}: {current} / {total_steps}",
                )
            )
            self.progress.emit(
                JobProgress(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="done",
                    current=current,
                    total=total_steps,
                    message=f"Building trajectory #{seed.id}: {current} / {total_steps}",
                )
            )
            self.finished.emit(
                JobFinished(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="done",
                    message=f"trajectory #{seed.id} built",
                )
            )
            return
        for orbit, done in iter_orbit_chunks(
            seed=seed,
            config=self._simulation_config,
            steps=self._phase_steps,
            chunk_size=self._chunk_size,
            cancel_check=self._is_cancel_requested,
            existing_orbit=self._existing_orbits.get(seed.id),
        ):
            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message="build cancelled",
                    )
                )
                return

            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message="build cancelled",
                    )
                )
                return

            geometry = build_wedge_geometry(
                orbit=self._build_geometry_orbit(seed, orbit),
                config=self._simulation_config,
                max_reflections=self._max_reflections,
            )
            self.partial_result.emit(
                OrbitPartialResult(
                    generation_id=self._generation_id,
                    trajectory_id=seed.id,
                    seed=seed,
                    orbit=orbit,
                    geometry=geometry,
                    replace=True,
                    current=max(len(orbit.points) - 1, 0),
                    total=total_steps,
                    message=(
                        f"Building trajectory #{seed.id}: "
                        f"{max(len(orbit.points) - 1, 0)} / {total_steps}"
                    ),
                )
            )
            self.progress.emit(
                JobProgress(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="done" if done else "partial",
                    current=max(len(orbit.points) - 1, 0),
                    total=total_steps,
                    message=(
                        f"Building trajectory #{seed.id}: "
                        f"{max(len(orbit.points) - 1, 0)} / {total_steps}"
                    ),
                )
            )

        if self._is_cancel_requested():
            self.finished.emit(
                JobFinished(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="cancelled",
                    message="build cancelled",
                )
            )
            return

        self.finished.emit(
            JobFinished(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="done",
                message=f"trajectory #{seed.id} built",
            )
        )

    def _run_rebuild(self) -> None:
        self._run_seed_batch(
            self._seeds,
            replace_existing=True,
            progress_label="Rebuilding",
        )
        if self._is_cancel_requested():
            return
        self.finished.emit(
            JobFinished(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="done",
                message="rebuild completed",
            )
        )

    def _run_scan(self) -> None:
        if self._max_trajectory_count <= 0:
            self.finished.emit(
                JobFinished(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="failed",
                    message="invalid trajectory capacity",
                )
            )
            return

        generated_points = generate_scan_points(
            mode=self._scan_mode,
            count=self._scan_count,
            d_min=self._scan_d_min,
            d_max=self._scan_d_max,
            tau_min=self._scan_tau_min,
            tau_max=self._scan_tau_max,
        )

        total = max(len(generated_points), 1)
        steps_per_seed = max(self._phase_steps - 1, 1)
        total_work = max(total * steps_per_seed, 1)
        self.progress.emit(
            JobProgress(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="running",
                current=0,
                total=total_work,
                message=f"Scanning 0 / {total}",
            )
        )
        seeds: list[TrajectorySeed] = []
        seed_progress_index: dict[int, int] = {}
        added = 0
        for point_index, (d_value, tau_value) in enumerate(generated_points, start=1):
            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message="scan cancelled",
                    )
                )
                return

            if (1.0 - d_value) ** 2 + tau_value * tau_value >= 1.0:
                self.progress.emit(
                    JobProgress(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="partial",
                        current=(point_index - 1) * steps_per_seed,
                        total=total_work,
                        message=f"Scanning {point_index} / {total}: skipped outside domain",
                    )
                )
                continue

            if added >= self._max_trajectory_count:
                break

            trajectory_id = self._next_trajectory_id + added
            color = (
                self._palette[(trajectory_id - 1) % len(self._palette)]
                if self._palette
                else "#1f77b4"
            )
            seed = TrajectorySeed(
                id=trajectory_id,
                wall_start=self._scan_wall,
                d0=d_value,
                tau0=tau_value,
                color=color,
            )
            seeds.append(seed)
            seed_progress_index[seed.id] = point_index
            added += 1

        self._scan_seed_progress_index = seed_progress_index
        self._scan_seed_total = total
        self._run_seed_batch(
            seeds,
            replace_existing=False,
            progress_label="Scanning",
        )
        self._scan_seed_progress_index = {}
        self._scan_seed_total = 0
        if self._is_cancel_requested():
            return

        self.finished.emit(
            JobFinished(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="done",
                message=f"scan completed: added {added}",
            )
        )

    def _run_seed_batch(
        self,
        seeds: list[TrajectorySeed],
        *,
        replace_existing: bool,
        progress_label: str,
    ) -> None:
        total = max(
            getattr(self, "_scan_seed_total", 0) if progress_label == "Scanning" else len(seeds),
            1,
        )
        steps_per_seed = max(self._phase_steps - 1, 1)
        total_work = max(total * steps_per_seed, 1)
        if progress_label == "Rebuilding":
            self.progress.emit(
                JobProgress(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="running",
                    current=0,
                    total=total_work,
                    message=f"{progress_label} 0 / {total}",
                )
            )

        use_native_batch = (
            progress_label == "Scanning"
            and not replace_existing
            and len(seeds) > 1
            and getattr(self._simulation_config, "native_enabled", False)
            and is_native_available()
            and str(getattr(self._simulation_config, "native_sample_mode", "every_n")) != "dense"
            and int(getattr(self._simulation_config, "native_sample_step", 1)) >= 1
        )
        if use_native_batch:
            self._run_native_seed_batch(
                seeds,
                replace_existing=replace_existing,
                progress_label=progress_label,
                total=total,
                steps_per_seed=steps_per_seed,
                total_work=total_work,
            )
            return

        for seed_index, seed in enumerate(seeds, start=1):
            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message=f"{progress_label.lower()} cancelled",
                    )
                )
                return

            display_index = (
                getattr(self, "_scan_seed_progress_index", {}).get(seed.id, seed_index)
                if progress_label == "Scanning"
                else seed_index
            )
            try:
                if self._fast_build:
                    orbit = build_orbit(
                        seed=seed,
                        config=self._simulation_config,
                        steps=self._phase_steps,
                    )
                    if self._is_cancel_requested():
                        self.finished.emit(
                            JobFinished(
                                generation_id=self._generation_id,
                                job_kind=self._job_kind,
                                status="cancelled",
                                message=f"{progress_label.lower()} cancelled",
                            )
                        )
                        return
                    geometry = build_wedge_geometry(
                        orbit=self._build_geometry_orbit(seed, orbit),
                        config=self._simulation_config,
                        max_reflections=self._max_reflections,
                    )
                    current = ((display_index - 1) * steps_per_seed) + max(len(orbit.points) - 1, 0)
                    message = (
                        f"{progress_label} {display_index} / {total}: "
                        f"trajectory #{seed.id} "
                        f"({max(len(orbit.points) - 1, 0)} / {steps_per_seed})"
                    )
                    self.partial_result.emit(
                        OrbitPartialResult(
                            generation_id=self._generation_id,
                            trajectory_id=seed.id,
                            seed=seed,
                            orbit=orbit,
                            geometry=geometry,
                            replace=replace_existing,
                            current=current,
                            total=total_work,
                            message=message,
                        )
                    )
                    self.progress.emit(
                        JobProgress(
                            generation_id=self._generation_id,
                            job_kind=self._job_kind,
                            status="done" if display_index == total else "partial",
                            current=current,
                            total=total_work,
                            message=message,
                        )
                    )
                    continue

                for orbit, done in iter_orbit_chunks(
                    seed=seed,
                    config=self._simulation_config,
                    steps=self._phase_steps,
                    chunk_size=self._chunk_size,
                    cancel_check=self._is_cancel_requested,
                    existing_orbit=self._existing_orbits.get(seed.id) if replace_existing else None,
                ):
                    if self._is_cancel_requested():
                        self.finished.emit(
                            JobFinished(
                                generation_id=self._generation_id,
                                job_kind=self._job_kind,
                                status="cancelled",
                                message=f"{progress_label.lower()} cancelled",
                            )
                        )
                        return

                    geometry = build_wedge_geometry(
                        orbit=self._build_geometry_orbit(seed, orbit),
                        config=self._simulation_config,
                        max_reflections=self._max_reflections,
                    )
                    current = ((display_index - 1) * steps_per_seed) + max(len(orbit.points) - 1, 0)
                    message = (
                        f"{progress_label} {display_index} / {total}: "
                        f"trajectory #{seed.id} "
                        f"({max(len(orbit.points) - 1, 0)} / {steps_per_seed})"
                    )
                    self.partial_result.emit(
                        OrbitPartialResult(
                            generation_id=self._generation_id,
                            trajectory_id=seed.id,
                            seed=seed,
                            orbit=orbit,
                            geometry=geometry,
                            replace=replace_existing,
                            current=current,
                            total=total_work,
                            message=message,
                        )
                    )
                    self.progress.emit(
                        JobProgress(
                            generation_id=self._generation_id,
                            job_kind=self._job_kind,
                            status="done" if done and display_index == total else "partial",
                            current=current,
                            total=total_work,
                            message=message,
                        )
                    )
            except Exception as exc:
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="failed",
                        message=f"{progress_label.lower()} failed: {exc}",
                    )
                )
                return

    def _run_native_seed_batch(
        self,
        seeds: list[TrajectorySeed],
        *,
        replace_existing: bool,
        progress_label: str,
        total: int,
        steps_per_seed: int,
        total_work: int,
    ) -> None:
        sample_step = int(getattr(self._simulation_config, "native_sample_step", 1))
        sample_mode = str(getattr(self._simulation_config, "native_sample_mode", "every_n"))
        self.progress.emit(
            JobProgress(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="running",
                current=0,
                total=total,
                message=f"{progress_label} 0 / {total} trajectories",
            )
        )
        completed_trajectories = 0
        for chunk_start in range(0, len(seeds), NATIVE_SCAN_BATCH_CHUNK_SIZE):
            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message=f"{progress_label.lower()} cancelled",
                    )
                )
                return

            chunk = seeds[chunk_start : chunk_start + NATIVE_SCAN_BATCH_CHUNK_SIZE]
            try:
                batch_results = native_build_sparse_orbits_batch(
                    d0_list=[seed.d0 for seed in chunk],
                    tau0_list=[seed.tau0 for seed in chunk],
                    wall0_list=[seed.wall_start for seed in chunk],
                    alpha=self._simulation_config.alpha,
                    beta=self._simulation_config.beta,
                    steps=self._phase_steps,
                    sample_step=sample_step,
                    sample_mode=sample_mode,
                )
            except Exception as exc:
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="failed",
                        message=f"{progress_label.lower()} failed: {exc}",
                    )
                )
                return
            for chunk_index, (seed, native_result) in enumerate(zip(chunk, batch_results), start=1):
                if self._is_cancel_requested():
                    self.finished.emit(
                        JobFinished(
                            generation_id=self._generation_id,
                            job_kind=self._job_kind,
                            status="cancelled",
                            message=f"{progress_label.lower()} cancelled",
                        )
                    )
                    return

                display_index = getattr(self, "_scan_seed_progress_index", {}).get(
                    seed.id,
                    chunk_start + chunk_index,
                )
                orbit = self._native_result_to_orbit(seed.id, native_result)
                geometry = build_wedge_geometry(
                    orbit=self._build_geometry_orbit(seed, orbit),
                    config=self._simulation_config,
                    max_reflections=self._max_reflections,
                )
                current = ((display_index - 1) * steps_per_seed) + max(orbit.completed_steps - 1, 0)
                message = (
                    f"{progress_label} {display_index} / {total}: "
                    f"trajectory #{seed.id} "
                    f"({max(orbit.completed_steps - 1, 0)} / {steps_per_seed})"
                )
                self.partial_result.emit(
                    OrbitPartialResult(
                        generation_id=self._generation_id,
                        trajectory_id=seed.id,
                        seed=seed,
                        orbit=orbit,
                        geometry=geometry,
                        replace=replace_existing,
                        current=current,
                        total=total_work,
                        message=message,
                    )
                )
                self.progress.emit(
                    JobProgress(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="done" if display_index == total else "partial",
                        current=current,
                        total=total_work,
                        message=message,
                    )
                )
                completed_trajectories = display_index
            self.progress.emit(
                JobProgress(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="done" if completed_trajectories == total else "partial",
                    current=completed_trajectories,
                    total=total,
                    message=f"{progress_label} {completed_trajectories} / {total} trajectories",
                )
            )

    def _native_result_to_orbit(self, trajectory_id: int, native_result: dict) -> Orbit:
        steps = [int(value) for value in native_result["steps"]]
        d_values = [float(value) for value in native_result["d"]]
        tau_values = [float(value) for value in native_result["tau"]]
        walls = [int(value) for value in native_result["wall"]]
        orbit = Orbit(
            trajectory_id=trajectory_id,
            valid=bool(native_result["valid"]),
            invalid_reason=native_result["invalid_reason"],
        )
        for index, (step_index, d_value, tau_value, wall) in enumerate(
            zip(steps, d_values, tau_values, walls)
        ):
            is_last = index == len(steps) - 1
            point_valid = orbit.valid or not is_last
            point_reason = orbit.invalid_reason if (is_last and not orbit.valid) else None
            orbit.points.append(
                OrbitPoint(
                    step_index=step_index,
                    d=d_value,
                    tau=tau_value,
                    wall=wall,
                    valid=point_valid,
                    invalid_reason=point_reason,
                    branch=None,
                )
            )
            orbit.replay_frames.append(
                ReplayFrame(
                    frame_index=step_index,
                    orbit_point_index=index,
                )
            )
        final_step = native_result.get("final_step")
        orbit.completed_steps = int(final_step) + 1 if final_step is not None else len(orbit.points)
        return orbit

    def _build_geometry_orbit(self, seed: TrajectorySeed, orbit: Orbit) -> Orbit:
        use_dense_geometry = (
            getattr(self._simulation_config, "native_enabled", False)
            and is_native_available()
            and (
                int(getattr(self._simulation_config, "native_sample_step", 1)) > 1
                or str(getattr(self._simulation_config, "native_sample_mode", "every_n")) != "dense"
            )
        )
        if not use_dense_geometry:
            return orbit
        return build_dense_orbit_for_geometry(
            seed=seed,
            config=self._simulation_config,
            steps=self._phase_steps,
        )

    def _run_lyapunov(self) -> None:
        if self._lyapunov_seed is None or self._lyapunov_config is None:
            self.finished.emit(
                JobFinished(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="failed",
                    message="missing lyapunov input",
                )
            )
            return

        self.progress.emit(
            JobProgress(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="running",
                current=0,
                total=self._lyapunov_config.max_steps,
                message=f"Computing Lyapunov for #{self._lyapunov_seed.id}",
            )
        )
        result = compute_finite_time_lyapunov(
            seed=self._lyapunov_seed,
            simulation_config=self._simulation_config,
            lyapunov_config=self._lyapunov_config,
        )
        if self._is_cancel_requested():
            self.finished.emit(
                JobFinished(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="cancelled",
                    message="lyapunov cancelled",
                )
            )
            return

        self.lyapunov_result.emit(
            LyapunovResultPayload(
                generation_id=self._generation_id,
                trajectory_id=self._lyapunov_seed.id,
                estimate=result.estimate,
                running_estimate=result.running_estimate,
                status=result.status,
                reason=result.reason,
                steps_used=result.steps_used,
                wall_divergence_count=result.wall_divergence_count,
            )
        )
        self.finished.emit(
            JobFinished(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="done" if result.status in ("done", "partial") else "failed",
                message=f"Lyapunov {result.status}",
            )
        )
