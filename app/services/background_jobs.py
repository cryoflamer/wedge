from __future__ import annotations

from dataclasses import dataclass
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from app.core.geometry_builder import build_wedge_geometry
from app.core.lyapunov import compute_finite_time_lyapunov
from app.core.orbit_builder import iter_orbit_chunks
from app.models.config import LyapunovConfig, SimulationConfig
from app.models.geometry import WedgeGeometry
from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed
from app.services.scan_sampler import generate_scan_points


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
        for orbit, done in iter_orbit_chunks(
            seed=seed,
            config=self._simulation_config,
            steps=self._phase_steps,
            chunk_size=self._chunk_size,
            cancel_check=self._is_cancel_requested,
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
                orbit=orbit,
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
                )
            )
            self.progress.emit(
                JobProgress(
                    generation_id=self._generation_id,
                    job_kind=self._job_kind,
                    status="done" if done else "partial",
                    current=len(orbit.points),
                    total=self._phase_steps,
                    message=(
                        f"Building trajectory #{seed.id}: "
                        f"{len(orbit.points)} / {self._phase_steps}"
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
        total = max(len(self._seeds), 1)
        for seed_index, seed in enumerate(self._seeds, start=1):
            if self._is_cancel_requested():
                self.finished.emit(
                    JobFinished(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="cancelled",
                        message="rebuild cancelled",
                    )
                )
                return

            latest_orbit: Orbit | None = None
            for orbit, done in iter_orbit_chunks(
                seed=seed,
                config=self._simulation_config,
                steps=self._phase_steps,
                chunk_size=self._chunk_size,
                cancel_check=self._is_cancel_requested,
            ):
                if self._is_cancel_requested():
                    self.finished.emit(
                        JobFinished(
                            generation_id=self._generation_id,
                            job_kind=self._job_kind,
                            status="cancelled",
                            message="rebuild cancelled",
                        )
                    )
                    return

                if self._is_cancel_requested():
                    self.finished.emit(
                        JobFinished(
                            generation_id=self._generation_id,
                            job_kind=self._job_kind,
                            status="cancelled",
                            message="rebuild cancelled",
                        )
                    )
                    return

                latest_orbit = orbit
                geometry = build_wedge_geometry(
                    orbit=orbit,
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
                    )
                )
                self.progress.emit(
                    JobProgress(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="done" if done and seed_index == total else "partial",
                        current=seed_index,
                        total=total,
                        message=(
                            f"Rebuilding {seed_index} / {total}: "
                            f"trajectory #{seed.id} ({len(orbit.points)} / {self._phase_steps})"
                        ),
                    )
                )

            if latest_orbit is None:
                continue

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
                        current=point_index,
                        total=total,
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

            for orbit, done in iter_orbit_chunks(
                seed=seed,
                config=self._simulation_config,
                steps=self._phase_steps,
                chunk_size=self._chunk_size,
                cancel_check=self._is_cancel_requested,
            ):
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

                geometry = build_wedge_geometry(
                    orbit=orbit,
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
                        replace=False,
                    )
                )
                self.progress.emit(
                    JobProgress(
                        generation_id=self._generation_id,
                        job_kind=self._job_kind,
                        status="done" if done and point_index == total else "partial",
                        current=point_index,
                        total=total,
                        message=(
                            f"Scanning {point_index} / {total}: "
                            f"trajectory #{seed.id} ({len(orbit.points)} / {self._phase_steps})"
                        ),
                    )
                )

            added += 1

        self.finished.emit(
            JobFinished(
                generation_id=self._generation_id,
                job_kind=self._job_kind,
                status="done",
                message=f"scan completed: added {added}",
            )
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
