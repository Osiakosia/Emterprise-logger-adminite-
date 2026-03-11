from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class Job:
    id: str
    kind: str
    status: str  # queued|running|done|error|canceled
    created_ts: float
    started_ts: float = 0.0
    finished_ts: float = 0.0
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str = ""
    cancel_requested: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}

    def create(self, *, kind: str, meta: Optional[Dict[str, Any]] = None) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(
            id=job_id,
            kind=kind,
            status="queued",
            created_ts=time.time(),
            meta=meta or {},
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            job.cancel_requested = True
            if job.status in ("queued",):
                job.status = "canceled"
                job.finished_ts = time.time()
            return True

    def _set(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for k, v in fields.items():
                setattr(job, k, v)

    def run_background(self, job: Job, fn: Callable[[Callable[[], bool], Callable[[float, str], None]], Any]) -> None:
        """
        fn(cancelled, update) -> result

        cancelled(): bool    # check if cancel requested
        update(p, msg): None # update progress/message
        """
        def worker():
            # if canceled while queued
            j = self.get(job.id)
            if not j or j.status == "canceled":
                return

            self._set(job.id, status="running", started_ts=time.time(), progress=0.0, message="started")
            try:
                def cancelled() -> bool:
                    jj = self.get(job.id)
                    return bool(jj and jj.cancel_requested)

                def update(p: float, msg: str = "") -> None:
                    self._set(job.id, progress=float(p), message=str(msg))

                result = fn(cancelled, update)

                # if cancel requested, mark canceled even if fn returned
                if cancelled():
                    self._set(job.id, status="canceled", finished_ts=time.time(), message="canceled")
                else:
                    self._set(job.id, status="done", finished_ts=time.time(), progress=1.0, message="done", result=result)

            except Exception as e:
                self._set(job.id, status="error", finished_ts=time.time(), message="error", error=str(e))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def to_dict(self, job: Job) -> Dict[str, Any]:
        return {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "created_ts": job.created_ts,
            "started_ts": job.started_ts,
            "finished_ts": job.finished_ts,
            "progress": job.progress,
            "message": job.message,
            "result": job.result,
            "error": job.error,
            "cancel_requested": job.cancel_requested,
            "meta": job.meta,
        }