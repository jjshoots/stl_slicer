"""ThreadJobRunner: lifecycle, progress, failure, cancel, supersede. Fakes only; no geometry."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest

from stl_slicer.core.errors import Cancelled
from stl_slicer.core.models import (
    AxisCuts,
    Bounds,
    Cell,
    CellIndex,
    CellLimits,
    CutPlan,
    Job,
    JobStatus,
    MeshAsset,
    PrintVolume,
    SliceResult,
    SliceSpec,
    SliceStats,
)
from stl_slicer.service.jobs import ThreadJobRunner

TIMEOUT = 5.0
SPEC = SliceSpec(print_volume=PrintVolume(x=100, y=100, z=100))
BOUNDS = Bounds(min=(0, 0, 0), max=(10, 10, 10))


@dataclass(frozen=True)
class _Model:
    asset: MeshAsset


@dataclass(frozen=True)
class _Output:
    result: SliceResult
    pieces: list[Any]


class _Models:
    def __init__(self, *model_ids: str) -> None:
        self._items = {
            mid: _Model(
                MeshAsset(
                    model_id=mid,
                    filename=f"{mid}.stl",
                    scale=1.0,
                    triangle_count=12,
                    bounds=BOUNDS,
                    volume=1000.0,
                )
            )
            for mid in model_ids
        }

    def put(self, model: Any) -> None:
        self._items[model.asset.model_id] = model

    def get(self, model_id: str) -> Any:
        return self._items[model_id]

    def delete(self, model_id: str) -> None:
        del self._items[model_id]

    def __contains__(self, model_id: object) -> bool:
        return model_id in self._items

    def ids(self) -> list[str]:
        return list(self._items)


class _Artifacts:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}
        self.put_calls: list[Any] = []

    def put(self, output: Any) -> None:
        self.put_calls.append(output)
        self.items[output.result.job_id] = output

    def get(self, job_id: str) -> Any:
        return self.items[job_id]

    def delete(self, job_id: str) -> None:
        del self.items[job_id]

    def delete_model(self, model_id: str) -> None:
        for k in [k for k, v in self.items.items() if v.result.model_id == model_id]:
            del self.items[k]

    def __contains__(self, job_id: object) -> bool:
        return job_id in self.items

    def job_ids(self, model_id: str) -> list[str]:
        return [k for k, v in self.items.items() if v.result.model_id == model_id]


class _Token:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled("cancelled")


def _result(job_id: str, model_id: str) -> SliceResult:
    plan = CutPlan(
        bounds=BOUNDS,
        limits=CellLimits(max_cell=(100.0, 100.0, 100.0)),
        cuts=AxisCuts(),
        cells=[Cell(index=CellIndex(i=0, j=0, k=0), bounds=BOUNDS)],
        interfaces=[],
    )
    stats = SliceStats(
        piece_count=0,
        input_volume=1000.0,
        output_volume=1000.0,
        max_overlap_volume=0.0,
        duration_s=0.0,
    )
    return SliceResult(
        job_id=job_id, model_id=model_id, spec=SPEC, plan=plan, pieces=[], joints=[], stats=stats
    )


class _Slicer:
    """Records calls; behaviour chosen per call by an optional hook, else returns immediately."""

    def __init__(self, hook: Callable[..., None] | None = None) -> None:
        self.calls: list[str] = []
        self.hook = hook
        self._lock = threading.Lock()

    def __call__(
        self, model: Any, spec: SliceSpec, *, progress: Any, cancel: Any, job_id: str
    ) -> Any:
        with self._lock:
            self.calls.append(job_id)
        if self.hook is not None:
            self.hook(model, progress, cancel, job_id)
        return _Output(result=_result(job_id, model.asset.model_id), pieces=["p0"])


def _until(pred: Callable[[], bool], timeout: float = TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


@pytest.fixture
def make_runner() -> Iterator[Callable[..., tuple[ThreadJobRunner, _Artifacts]]]:
    runners: list[ThreadJobRunner] = []

    def make(slicer: _Slicer, *model_ids: str) -> tuple[ThreadJobRunner, _Artifacts]:
        artifacts = _Artifacts()
        runner = ThreadJobRunner(
            _Models(*(model_ids or ("m1",))), artifacts, slicer=slicer, token_factory=_Token
        )
        runners.append(runner)
        return runner, artifacts

    yield make
    for r in runners:
        r.shutdown()


def _running(runner: ThreadJobRunner, job_id: str) -> Callable[[], bool]:
    return lambda: runner.get(job_id).status is JobStatus.RUNNING


def _poll_until_released(release: threading.Event) -> Callable[..., None]:
    def hook(model: Any, progress: Any, cancel: Any, job_id: str) -> None:
        while True:
            cancel.raise_if_cancelled()
            if release.is_set():
                return
            time.sleep(0.005)

    return hook


def test_submit_wait_done(make_runner: Any) -> None:
    slicer = _Slicer()
    runner, artifacts = make_runner(slicer)
    job = runner.submit("m1", SPEC)
    assert isinstance(job, Job)
    assert job.status in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.DONE)
    assert len(job.job_id) == 12

    done = runner.wait(job.job_id, timeout=TIMEOUT)
    assert done.status is JobStatus.DONE
    assert done.progress == 1.0
    assert done.step == "done"
    assert done.error is None
    assert done.result is not None
    assert done.result.job_id == job.job_id
    assert done.result.model_id == "m1"
    assert len(artifacts.put_calls) == 1
    assert artifacts.put_calls[0].result == done.result
    assert slicer.calls == [job.job_id]

    snap = runner.get(job.job_id)
    snap.status = JobStatus.FAILED
    snap.progress = 0.0
    again = runner.get(job.job_id)
    assert again.status is JobStatus.DONE
    assert again.progress == 1.0


def test_progress_sink_updates_while_running(make_runner: Any) -> None:
    release = threading.Event()
    reported = threading.Event()

    def hook(model: Any, progress: Any, cancel: Any, job_id: str) -> None:
        progress(0.5, "cutting 1/2")
        reported.set()
        assert release.wait(TIMEOUT)

    runner, _ = make_runner(_Slicer(hook))
    job = runner.submit("m1", SPEC)
    assert reported.wait(TIMEOUT)
    mid = runner.get(job.job_id)
    assert mid.status is JobStatus.RUNNING
    assert mid.progress == 0.5
    assert mid.step == "cutting 1/2"
    release.set()
    assert runner.wait(job.job_id, timeout=TIMEOUT).status is JobStatus.DONE


def test_slicer_error_marks_failed(make_runner: Any) -> None:
    def hook(model: Any, progress: Any, cancel: Any, job_id: str) -> None:
        raise ValueError("bad plane")

    runner, artifacts = make_runner(_Slicer(hook))
    job = runner.submit("m1", SPEC)
    failed = runner.wait(job.job_id, timeout=TIMEOUT)
    assert failed.status is JobStatus.FAILED
    assert failed.error == "bad plane"
    assert failed.result is None
    assert artifacts.put_calls == []
    assert artifacts.items == {}


def test_cancel_running_job(make_runner: Any) -> None:
    release = threading.Event()  # never set
    runner, artifacts = make_runner(_Slicer(_poll_until_released(release)))
    job = runner.submit("m1", SPEC)
    _until(_running(runner, job.job_id))
    snap = runner.cancel(job.job_id)
    assert snap.status in (JobStatus.RUNNING, JobStatus.CANCELLED)
    final = runner.wait(job.job_id, timeout=TIMEOUT)
    assert final.status is JobStatus.CANCELLED
    assert final.step == "cancelled"
    assert final.result is None
    assert artifacts.put_calls == []


def test_cancel_queued_job_never_calls_slicer(make_runner: Any) -> None:
    release = threading.Event()
    slicer = _Slicer(_poll_until_released(release))
    runner, _ = make_runner(slicer, "m1", "m2")
    first = runner.submit("m1", SPEC)
    _until(_running(runner, first.job_id))
    second = runner.submit("m2", SPEC)
    assert runner.get(second.job_id).status is JobStatus.QUEUED

    snap = runner.cancel(second.job_id)
    assert snap.status is JobStatus.CANCELLED
    release.set()

    assert runner.wait(first.job_id, timeout=TIMEOUT).status is JobStatus.DONE
    final = runner.wait(second.job_id, timeout=TIMEOUT)
    assert final.status is JobStatus.CANCELLED
    assert final.step == "cancelled"
    assert slicer.calls == [first.job_id]


def test_submit_supersedes_live_job_of_same_model(make_runner: Any) -> None:
    release = threading.Event()
    slicer = _Slicer(_poll_until_released(release))
    runner, artifacts = make_runner(slicer, "m1", "m2")
    first = runner.submit("m1", SPEC)
    _until(_running(runner, first.job_id))
    other = runner.submit("m2", SPEC)
    second = runner.submit("m1", SPEC)
    release.set()

    assert runner.wait(first.job_id, timeout=TIMEOUT).status is JobStatus.CANCELLED
    assert runner.wait(other.job_id, timeout=TIMEOUT).status is JobStatus.DONE
    assert runner.wait(second.job_id, timeout=TIMEOUT).status is JobStatus.DONE
    assert [o.result.job_id for o in artifacts.put_calls] == [other.job_id, second.job_id]


def test_cancel_done_is_noop_and_unknown_ids(make_runner: Any) -> None:
    runner, _ = make_runner(_Slicer())
    job = runner.submit("m1", SPEC)
    assert runner.wait(job.job_id, timeout=TIMEOUT).status is JobStatus.DONE
    snap = runner.cancel(job.job_id)
    assert snap.status is JobStatus.DONE
    assert snap.result is not None
    assert runner.get(job.job_id).status is JobStatus.DONE

    with pytest.raises(KeyError):
        runner.get("nope")
    with pytest.raises(KeyError):
        runner.cancel("nope")
    with pytest.raises(KeyError):
        runner.submit("unknown-model", SPEC)


def test_cancel_is_idempotent(make_runner: Any) -> None:
    release = threading.Event()
    runner, _ = make_runner(_Slicer(_poll_until_released(release)))
    job = runner.submit("m1", SPEC)
    _until(_running(runner, job.job_id))
    runner.cancel(job.job_id)
    runner.cancel(job.job_id)
    assert runner.wait(job.job_id, timeout=TIMEOUT).status is JobStatus.CANCELLED
    assert runner.cancel(job.job_id).status is JobStatus.CANCELLED


def test_shutdown_cancels_live_jobs() -> None:
    release = threading.Event()
    slicer = _Slicer(_poll_until_released(release))
    runner = ThreadJobRunner(_Models("m1", "m2"), _Artifacts(), slicer=slicer, token_factory=_Token)
    first = runner.submit("m1", SPEC)
    _until(_running(runner, first.job_id))
    second = runner.submit("m2", SPEC)
    runner.shutdown()
    assert runner.get(first.job_id).status is JobStatus.CANCELLED
    assert runner.get(second.job_id).status is JobStatus.CANCELLED
    assert slicer.calls == [first.job_id]


def test_default_construction() -> None:
    runner = ThreadJobRunner(_Models("m1"), _Artifacts())
    runner.shutdown()


def test_real_cancel_token_with_fake_slicer() -> None:
    pipeline = pytest.importorskip("stl_slicer.core.pipeline")
    release = threading.Event()
    slicer = _Slicer(_poll_until_released(release))
    runner = ThreadJobRunner(
        _Models("m1"), _Artifacts(), slicer=slicer, token_factory=pipeline.CancelToken
    )
    try:
        running = runner.submit("m1", SPEC)
        _until(_running(runner, running.job_id))
        runner.cancel(running.job_id)
        assert runner.wait(running.job_id, timeout=TIMEOUT).status is JobStatus.CANCELLED
        release.set()
        done = runner.submit("m1", SPEC)
        assert runner.wait(done.job_id, timeout=TIMEOUT).status is JobStatus.DONE
    finally:
        runner.shutdown()
