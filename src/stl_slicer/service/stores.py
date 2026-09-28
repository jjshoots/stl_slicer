"""In-process stores for uploaded models and slice artifacts.

Stores only touch `.asset.model_id`, `.result.job_id` and `.result.model_id` (and
`.pieces[*].info.piece_id` for `get_piece`), so they are duck-typed at runtime; the geometry
types are referenced for type checking only. See docs/00_design.md §6.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from stl_slicer.core.geometry import LoadedModel, Piece, SliceOutput


class ModelStore(Protocol):
    """Loaded models keyed by `asset.model_id`, with bounded capacity."""

    def put(self, model: LoadedModel) -> None: ...

    def get(self, model_id: str) -> LoadedModel: ...

    def delete(self, model_id: str) -> None: ...

    def __contains__(self, model_id: object) -> bool: ...

    def ids(self) -> list[str]: ...


class InMemoryModelStore:
    """Thread-safe LRU store of loaded models.

    Args:
        capacity: Maximum number of models kept; the least recently used is evicted beyond it.
    """

    def __init__(self, capacity: int = 4) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        self._items: OrderedDict[str, LoadedModel] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def put(self, model: LoadedModel) -> None:
        """Insert (or replace) a model as most recently used, evicting the LRU beyond capacity."""
        key = model.asset.model_id
        with self._lock:
            self._items[key] = model
            self._items.move_to_end(key)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)

    def get(self, model_id: str) -> LoadedModel:
        """Return a model and mark it most recently used. Raises KeyError if unknown."""
        with self._lock:
            model = self._items[model_id]
            self._items.move_to_end(model_id)
            return model

    def delete(self, model_id: str) -> None:
        """Remove a model. Raises KeyError if unknown."""
        with self._lock:
            del self._items[model_id]

    def __contains__(self, model_id: object) -> bool:
        with self._lock:
            return model_id in self._items

    def ids(self) -> list[str]:
        """Model ids, most recently used last."""
        with self._lock:
            return list(self._items)


class ArtifactStore(Protocol):
    """Slice outputs keyed by job id, grouped by model, newest few kept per model."""

    def put(self, output: SliceOutput) -> None: ...

    def get(self, job_id: str) -> SliceOutput: ...

    def delete(self, job_id: str) -> None: ...

    def delete_model(self, model_id: str) -> None: ...

    def __contains__(self, job_id: object) -> bool: ...

    def job_ids(self, model_id: str) -> list[str]: ...

    def get_piece(self, job_id: str, piece_id: str) -> Piece: ...


class InMemoryArtifactStore:
    """Thread-safe store of slice outputs keeping the newest `jobs_per_model` per model.

    Args:
        jobs_per_model: How many outputs to retain per model; older ones are dropped on `put`.
    """

    def __init__(self, jobs_per_model: int = 2) -> None:
        if jobs_per_model < 1:
            raise ValueError("jobs_per_model must be >= 1")
        self._jobs_per_model = jobs_per_model
        self._outputs: dict[str, SliceOutput] = {}
        self._by_model: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    @property
    def jobs_per_model(self) -> int:
        return self._jobs_per_model

    def put(self, output: SliceOutput) -> None:
        """Store an output as its model's newest job, dropping the oldest beyond the limit."""
        job_id = output.result.job_id
        model_id = output.result.model_id
        with self._lock:
            if job_id in self._outputs:
                self._remove_locked(job_id)
            self._outputs[job_id] = output
            jobs = self._by_model.setdefault(model_id, [])
            jobs.append(job_id)
            while len(jobs) > self._jobs_per_model:
                oldest = jobs.pop(0)
                del self._outputs[oldest]

    def get(self, job_id: str) -> SliceOutput:
        """Return the output for a job. Raises KeyError if unknown."""
        with self._lock:
            return self._outputs[job_id]

    def get_piece(self, job_id: str, piece_id: str) -> Piece:
        """Return one piece of a job's output. Raises KeyError if the job or piece is unknown."""
        output = self.get(job_id)
        for piece in output.pieces:
            if piece.info.piece_id == piece_id:
                return piece
        raise KeyError(piece_id)

    def delete(self, job_id: str) -> None:
        """Remove a job's output. Raises KeyError if unknown."""
        with self._lock:
            if job_id not in self._outputs:
                raise KeyError(job_id)
            self._remove_locked(job_id)

    def delete_model(self, model_id: str) -> None:
        """Drop every output for a model; no-op if there are none."""
        with self._lock:
            for job_id in self._by_model.pop(model_id, []):
                self._outputs.pop(job_id, None)

    def __contains__(self, job_id: object) -> bool:
        with self._lock:
            return job_id in self._outputs

    def job_ids(self, model_id: str) -> list[str]:
        """Job ids stored for a model, oldest first (empty if none)."""
        with self._lock:
            return list(self._by_model.get(model_id, []))

    def _remove_locked(self, job_id: str) -> None:
        output = self._outputs.pop(job_id)
        model_id = output.result.model_id
        jobs = self._by_model.get(model_id)
        if jobs is not None:
            jobs.remove(job_id)
            if not jobs:
                del self._by_model[model_id]
