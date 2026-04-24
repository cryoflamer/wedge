from __future__ import annotations

from copy import deepcopy
import logging
from PySide6.QtCore import QObject, QThread, Signal

from app.models.config import LyapunovConfig, SimulationConfig
from app.models.orbit import Orbit
from app.models.trajectory import TrajectorySeed
from app.services.background_jobs import (
    JobFinished,
    JobProgress,
    LyapunovResultPayload,
    OrbitBuildWorker,
    OrbitPartialResult,
)

logger = logging.getLogger(__name__)


class JobController(QObject):
    progress = Signal(object)
    partial_result = Signal(object)
    lyapunov_result = Signal(object)
    finished = Signal(object)
    state_updated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job_generation = 0
        self._current_job_thread: QThread | None = None
        self._current_job_worker: OrbitBuildWorker | None = None
        self._active_job_payload: dict[str, object] | None = None
        self._paused_job_payloads: list[dict[str, object]] = []
        self._next_job_payload_id = 1
        self._last_progress_percent = 0

    def _next_generation_id(self) -> int:
        self._job_generation += 1
        return self._job_generation

    def is_running(self) -> bool:
        return self._current_job_worker is not None

    def paused_payloads(self) -> list[dict[str, object]]:
        return list(self._paused_job_payloads)

    def latest_paused_job(self) -> dict[str, object] | None:
        if not self._paused_job_payloads:
            return None
        return self._paused_job_payloads[-1]

    def last_progress_percent(self) -> int:
        return self._last_progress_percent

    def progress_percent(self, progress: JobProgress) -> int:
        return self._progress_percent(progress)

    def cancel_current_job(self) -> None:
        worker = self._current_job_worker
        if worker is None:
            return
        worker.cancel()
        if self._active_job_payload is not None:
            paused_payload = dict(self._active_job_payload)
            paused_payload["paused"] = True
            self._store_paused_job(paused_payload)
        self._job_generation += 1
        self._current_job_worker = None
        self._current_job_thread = None
        self._active_job_payload = None
        self.state_updated.emit()

    def start_single_build(
        self,
        seed: TrajectorySeed,
        *,
        simulation_config: SimulationConfig,
        max_reflections: int,
        phase_steps: int,
        chunk_size: int,
        existing_orbits: dict[int, Orbit],
        start_message: str,
    ) -> None:
        self._start_worker(
            job_kind="single_build",
            worker_kwargs={
                "simulation_config": simulation_config,
                "max_reflections": max_reflections,
                "phase_steps": phase_steps,
                "chunk_size": chunk_size,
                "seeds": [seed],
                "existing_orbits": existing_orbits,
            },
            start_message=start_message,
            resumable_payload={
                "job_kind": "single_build",
                "seeds": [seed],
                "start_message": start_message,
                "title": f"Trajectory #{seed.id}",
            },
        )

    def start_rebuild(
        self,
        seeds: list[TrajectorySeed],
        *,
        simulation_config: SimulationConfig,
        max_reflections: int,
        phase_steps: int,
        chunk_size: int,
        start_message: str,
    ) -> None:
        self._start_worker(
            job_kind="rebuild",
            worker_kwargs={
                "simulation_config": simulation_config,
                "max_reflections": max_reflections,
                "phase_steps": phase_steps,
                "chunk_size": chunk_size,
                "seeds": seeds,
            },
            start_message=start_message,
            resumable_payload={
                "job_kind": "rebuild",
                "seeds": list(seeds),
                "start_message": start_message,
                "title": start_message,
            },
        )

    def start_scan(
        self,
        *,
        simulation_config: SimulationConfig,
        max_reflections: int,
        phase_steps: int,
        chunk_size: int,
        mode: str,
        count: int,
        wall: int,
        d_min: float,
        d_max: float,
        tau_min: float,
        tau_max: float,
        next_trajectory_id: int,
        palette: list[str],
        max_trajectory_count: int,
    ) -> None:
        self._start_worker(
            job_kind="scan",
            worker_kwargs={
                "simulation_config": simulation_config,
                "max_reflections": max_reflections,
                "phase_steps": phase_steps,
                "chunk_size": chunk_size,
                "scan_mode": mode,
                "scan_count": count,
                "scan_wall": wall,
                "scan_d_min": d_min,
                "scan_d_max": d_max,
                "scan_tau_min": tau_min,
                "scan_tau_max": tau_max,
                "next_trajectory_id": next_trajectory_id,
                "palette": palette,
                "max_trajectory_count": max_trajectory_count,
            },
        )

    def start_lyapunov(
        self,
        seed: TrajectorySeed,
        *,
        simulation_config: SimulationConfig,
        max_reflections: int,
        phase_steps: int,
        chunk_size: int,
        lyapunov_config: LyapunovConfig,
    ) -> None:
        self._start_worker(
            job_kind="lyapunov",
            worker_kwargs={
                "simulation_config": simulation_config,
                "max_reflections": max_reflections,
                "phase_steps": phase_steps,
                "chunk_size": chunk_size,
                "lyapunov_seed": seed,
                "lyapunov_config": lyapunov_config,
            },
        )

    def resume_job(
        self,
        job_id: int,
        *,
        simulation_config: SimulationConfig,
        max_reflections: int,
        phase_steps: int,
        chunk_size: int,
        existing_orbits: dict[int, Orbit],
    ) -> None:
        if self.is_running():
            return
        payload = next(
            (
                item
                for item in self._paused_job_payloads
                if int(item.get("job_id", -1)) == job_id
            ),
            None,
        )
        if payload is None:
            return
        job_kind = str(payload.get("job_kind", "")).strip()
        start_message = str(payload.get("start_message", "Resuming job..."))
        seeds = payload.get("seeds")
        if not isinstance(seeds, list):
            return
        self.remove_paused_job(job_id)
        if job_kind == "rebuild":
            self._start_worker(
                job_kind="rebuild",
                worker_kwargs={
                    "simulation_config": simulation_config,
                    "max_reflections": max_reflections,
                    "phase_steps": phase_steps,
                    "chunk_size": chunk_size,
                    "seeds": deepcopy(seeds),
                    "existing_orbits": existing_orbits,
                },
                start_message=start_message.replace("Starting", "Resuming"),
                resumable_payload=payload,
            )
            return
        if job_kind == "single_build":
            self._start_worker(
                job_kind="single_build",
                worker_kwargs={
                    "simulation_config": simulation_config,
                    "max_reflections": max_reflections,
                    "phase_steps": phase_steps,
                    "chunk_size": chunk_size,
                    "seeds": deepcopy(seeds),
                    "existing_orbits": existing_orbits,
                },
                start_message=start_message.replace("Building", "Resuming"),
                resumable_payload=payload,
            )

    def _start_worker(
        self,
        *,
        job_kind: str,
        worker_kwargs: dict[str, object],
        start_message: str = "Starting background job...",
        resumable_payload: dict[str, object] | None = None,
    ) -> None:
        self.cancel_current_job()
        generation_id = self._next_generation_id()
        worker = OrbitBuildWorker(
            generation_id=generation_id,
            job_kind=job_kind,
            **worker_kwargs,
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_job_progress)
        worker.partial_result.connect(self._on_job_partial_result)
        worker.lyapunov_result.connect(self._on_lyapunov_result)
        worker.finished.connect(self._on_job_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._current_job_thread = thread
        self._current_job_worker = worker
        if resumable_payload is not None:
            payload = dict(resumable_payload)
            payload.setdefault("job_id", self._next_job_payload_id)
            if payload["job_id"] == self._next_job_payload_id:
                self._next_job_payload_id += 1
            payload["progress_percent"] = 0
            payload["message"] = start_message
            self._active_job_payload = payload
        else:
            self._active_job_payload = None
        self._last_progress_percent = 0
        self.state_updated.emit()
        logger.debug(
            "Starting job generation=%s kind=%s message=%s",
            generation_id,
            job_kind,
            start_message,
        )
        self.progress.emit(
            JobProgress(
                generation_id=generation_id,
                job_kind=job_kind,
                status="running",
                current=0,
                total=0,
                message=start_message,
            )
        )
        thread.start()

    def prune_job_payloads_for_existing_trajectories(self, existing_ids: set[int]) -> None:
        filtered_payloads: list[dict[str, object]] = []
        for payload in self._paused_job_payloads:
            seeds = payload.get("seeds")
            if not isinstance(seeds, list):
                continue
            filtered_seeds = [
                seed for seed in seeds if getattr(seed, "id", None) in existing_ids
            ]
            if not filtered_seeds:
                continue
            next_payload = dict(payload)
            next_payload["seeds"] = filtered_seeds
            filtered_payloads.append(next_payload)
        self._paused_job_payloads = filtered_payloads
        self.state_updated.emit()

    def remove_paused_job(self, job_id: int) -> None:
        self._paused_job_payloads = [
            item
            for item in self._paused_job_payloads
            if int(item.get("job_id", -2)) != job_id
        ]
        self.state_updated.emit()

    def _store_paused_job(self, payload: dict[str, object]) -> None:
        job_id = int(payload.get("job_id", 0))
        self._paused_job_payloads = [
            item for item in self._paused_job_payloads if int(item.get("job_id", -1)) != job_id
        ]
        self._paused_job_payloads.append(payload)

    def _on_job_progress(self, progress: object) -> None:
        if not isinstance(progress, JobProgress):
            return
        if progress.generation_id != self._job_generation:
            logger.debug(
                "Dropping job progress generation=%s expected=%s kind=%s",
                progress.generation_id,
                self._job_generation,
                progress.job_kind,
            )
            return
        percent = self._progress_percent(progress)
        if progress.status in ("running", "partial"):
            self._last_progress_percent = percent
        if self._active_job_payload is not None:
            self._active_job_payload["progress_percent"] = percent
            self._active_job_payload["message"] = progress.message
        self.progress.emit(progress)

    def _on_job_partial_result(self, payload: object) -> None:
        if not isinstance(payload, OrbitPartialResult):
            return
        if payload.generation_id != self._job_generation:
            return
        self.partial_result.emit(payload)

    def _on_lyapunov_result(self, payload: object) -> None:
        if not isinstance(payload, LyapunovResultPayload):
            return
        if payload.generation_id != self._job_generation:
            return
        self.lyapunov_result.emit(payload)

    def _on_job_finished(self, payload: object) -> None:
        if not isinstance(payload, JobFinished):
            return
        if payload.generation_id != self._job_generation:
            return
        self._active_job_payload = None
        self._current_job_worker = None
        self._current_job_thread = None
        self.state_updated.emit()
        self.finished.emit(payload)

    def _progress_percent(self, progress: JobProgress) -> int:
        total = max(progress.total, 0)
        current = min(max(progress.current, 0), total) if total > 0 else 0
        return int((current / total) * 100.0) if total > 0 else 0
