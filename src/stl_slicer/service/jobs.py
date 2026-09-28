"""Background slice jobs: a single-worker runner with cancel and supersede.

Only `service` knows about threads, ids and storage (docs/00_design.md §3, §6 R5). The slicer and
the cancel token are injected; the defaults are imported lazily from `core.pipeline`.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, cast

from stl_slicer.core.errors import Cancelled
from stl_slicer.core.models import Job, JobStatus, SliceSpec
from stl_slicer.service.stores import ArtifactStore, ModelStore

if TYPE_CHECKING:
    from stl_slicer.core.geometry import LoadedModel, SliceOutput

logger = logging.getLogger(__name__)

_LIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


class CancelHandle(Protocol):
    """Structural twin of `core.pipeline.CancelToken`."""

    def cancel(self) -> None: ...

    @property
    def is_cancelled(self) -> bool: ...

    def raise_if_cancelled(self) -> None: ...


Slicer = Callable[..., "SliceOutput"]
"""Called as `slicer(model, spec, progress=sink, cancel=token, job_id=job_id)`."""


class JobRunner(Protocol):
    """Runs slice jobs in the background and reports their state as `Job` snapshots."""

    def submit(self, model_id: str, spec: SliceSpec) -> Job: ...

    def get(self, job_id: str) -> Job: ...

    def cancel(self, job_id: str) -> Job: ...

    def cancel_model(self, model_id: str) -> list[Job]: ...

    def shutdown(self) -> None: ...


@dataclass
class _Entry:
    job: Job
    token: CancelHandle
    future: Future[None] | None = field(default=None)


def _default_slicer() -> Slicer:
    from stl_slicer.core.pipeline import slice_model

    return cast("Slicer", slice_model)


def _default_token_factory() -> Callable[[], CancelHandle]:
    from stl_slicer.core.pipeline import CancelToken

    return cast("Callable[[], CancelHandle]", CancelToken)


class ThreadJobRunner:
    """Single-worker job runner; one live job per model (a new submit supersedes the old one).

    Args:
        models: Where submitted model ids are looked up.
        artifacts: Where successful slice outputs are stored.
        executor: Worker pool; defaults to `ThreadPoolExecutor(max_workers=1)`.
        slicer: Slice function; defaults to `core.pipeline.slice_model` (imported lazily).
        token_factory: Cancel-token constructor; defaults to `core.pipeline.CancelToken`.
    """

    def __init__(
        self,
        models: ModelStore,
        artifacts: ArtifactStore,
        executor: ThreadPoolExecutor | None = None,
        slicer: Slicer | None = None,
        token_factory: Callable[[], CancelHandle] | None = None,
    ) -> None:
        self._models = models
        self._artifacts = artifacts
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="slice")
        self._slicer = slicer
        self._token_factory = token_factory
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def submit(self, model_id: str, spec: SliceSpec) -> Job:
        """Queue a slice of a stored model, cancelling any live job for the same model.

        Raises:
            KeyError: If the model is not in the model store.
        """
        model = self._models.get(model_id)
        slicer = self._slicer or _default_slicer()
        factory = self._token_factory or _default_token_factory()
        job_id = uuid.uuid4().hex[:12]
        entry = _Entry(job=Job(job_id=job_id, model_id=model_id), token=factory())
        with self._lock:
            for other in self._entries.values():
                if other.job.model_id == model_id and other.job.status in _LIVE:
                    self._cancel_locked(other)
            # Submitting under the lock is non-blocking and guarantees `future` is set before any
            # other thread can see the entry; the worker simply waits for the lock.
            entry.future = self._executor.submit(self._run, entry, model, spec, slicer)
            self._entries[job_id] = entry
            return entry.job.model_copy(deep=True)

    def get(self, job_id: str) -> Job:
        """Return a snapshot of a job. Raises KeyError if unknown."""
        with self._lock:
            return self._entries[job_id].job.model_copy(deep=True)

    def cancel(self, job_id: str) -> Job:
        """Cancel a job (idempotent) and return a snapshot. Raises KeyError if unknown.

        A queued job becomes CANCELLED immediately; a running one becomes CANCELLED once the worker
        observes the token; DONE/FAILED jobs are unchanged.
        """
        with self._lock:
            entry = self._entries[job_id]
            self._cancel_locked(entry)
            return entry.job.model_copy(deep=True)

    def cancel_model(self, model_id: str) -> list[Job]:
        """Cancel every live job of a model (used when the model is deleted); returns snapshots."""
        with self._lock:
            cancelled = []
            for entry in self._entries.values():
                if entry.job.model_id == model_id and entry.job.status in _LIVE:
                    self._cancel_locked(entry)
                    cancelled.append(entry.job.model_copy(deep=True))
            return cancelled

    def wait(self, job_id: str, timeout: float | None = None) -> Job:
        """Block until a job's worker has finished, then return its snapshot.

        Raises:
            KeyError: If the job is unknown.
            TimeoutError: If the worker is still running after `timeout` seconds.
        """
        with self._lock:
            future = self._entries[job_id].future
        if future is not None:
            with contextlib.suppress(CancelledError):  # never started; already CANCELLED
                future.result(timeout=timeout)
        return self.get(job_id)

    def shutdown(self) -> None:
        """Cancel every live job and wait for the worker to drain."""
        with self._lock:
            for entry in self._entries.values():
                if entry.job.status in _LIVE:
                    self._cancel_locked(entry)
        self._executor.shutdown(wait=True)

    def _cancel_locked(self, entry: _Entry) -> None:
        job = entry.job
        if job.status not in _LIVE:
            return
        entry.token.cancel()
        if job.status is JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            job.step = "cancelled"
            if entry.future is not None:
                entry.future.cancel()

    def _run(self, entry: _Entry, model: LoadedModel, spec: SliceSpec, slicer: Slicer) -> None:
        job = entry.job
        token = entry.token

        def sink(fraction: float, step: str) -> None:
            with self._lock:
                if job.status is JobStatus.RUNNING:
                    job.progress = min(max(float(fraction), 0.0), 1.0)
                    job.step = step

        try:
            token.raise_if_cancelled()
            with self._lock:
                if job.status is not JobStatus.QUEUED:
                    return
                job.status = JobStatus.RUNNING
                job.step = "starting"
            output = slicer(model, spec, progress=sink, cancel=token, job_id=job.job_id)
            self._artifacts.put(output)
            with self._lock:
                job.result = output.result
                job.status = JobStatus.DONE
                job.progress = 1.0
                job.step = "done"
        except Cancelled:
            with self._lock:
                job.status = JobStatus.CANCELLED
                job.step = "cancelled"
        except Exception as e:
            logger.exception("slice job %s failed", job.job_id)
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.step = "failed"
