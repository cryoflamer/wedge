from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from app.services.background_jobs import (
    JobFinished,
    JobProgress,
    LyapunovResultPayload,
    OrbitBuildWorker,
    OrbitPartialResult,
)


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

    def next_generation_id(self) -> int:
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

    def start_worker(
        self,
        worker: OrbitBuildWorker,
        start_message: str = "Starting background job...",
        resumable_payload: dict[str, object] | None = None,
    ) -> None:
        self.cancel_current_job()
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
        self.state_updated.emit()
        self.progress.emit(
            JobProgress(
                generation_id=worker._generation_id,
                job_kind="start",
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
            return
        if self._active_job_payload is not None:
            total = max(progress.total, 0)
            current = min(max(progress.current, 0), total) if total > 0 else 0
            percent = int((current / total) * 100.0) if total > 0 else 0
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
