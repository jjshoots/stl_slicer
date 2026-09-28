"""Tests for the in-memory model and artifact stores (duck-typed stand-ins, no geometry)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from stl_slicer.core.models import (
    AxisCuts,
    Bounds,
    Cell,
    CellIndex,
    CellLimits,
    CutPlan,
    MeshAsset,
    PieceInfo,
    PrintVolume,
    SliceResult,
    SliceSpec,
    SliceStats,
)
from stl_slicer.service.stores import InMemoryArtifactStore, InMemoryModelStore

_BOUNDS = Bounds(min=(0, 0, 0), max=(10, 10, 10))


@dataclass(frozen=True)
class _Model:
    asset: MeshAsset


@dataclass(frozen=True)
class _Info:
    piece_id: str


@dataclass(frozen=True)
class _Piece:
    info: PieceInfo | _Info


@dataclass(frozen=True)
class _Output:
    result: SliceResult
    pieces: list[_Piece] = field(default_factory=list)


def _model(model_id: str) -> _Model:
    asset = MeshAsset(
        model_id=model_id,
        filename=f"{model_id}.stl",
        scale=1.0,
        triangle_count=12,
        bounds=_BOUNDS,
        volume=1000.0,
    )
    return _Model(asset=asset)


def _result(job_id: str, model_id: str) -> SliceResult:
    plan = CutPlan(
        bounds=_BOUNDS,
        limits=CellLimits(max_cell=(10, 10, 10)),
        cuts=AxisCuts(),
        cells=[Cell(index=CellIndex(i=0, j=0, k=0), bounds=_BOUNDS)],
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
        job_id=job_id,
        model_id=model_id,
        spec=SliceSpec(print_volume=PrintVolume(x=100, y=100, z=100)),
        plan=plan,
        pieces=[],
        joints=[],
        stats=stats,
    )


def _output(job_id: str, model_id: str, piece_ids: tuple[str, ...] = ()) -> _Output:
    pieces = [_Piece(info=_Info(piece_id=p)) for p in piece_ids]
    return _Output(result=_result(job_id, model_id), pieces=pieces)


# The stores are typed against core.geometry; stand-ins are structurally sufficient.
def _as_any(obj: object) -> Any:
    return obj


# --- ModelStore -----------------------------------------------------------------------------


def test_model_store_put_get_roundtrip() -> None:
    store = InMemoryModelStore()
    m = _model("a")
    store.put(_as_any(m))
    assert store.get("a") is m
    assert "a" in store
    assert "b" not in store
    assert store.ids() == ["a"]


def test_model_store_evicts_lru_beyond_capacity() -> None:
    store = InMemoryModelStore(capacity=4)
    for mid in "abcd":
        store.put(_as_any(_model(mid)))
    assert store.ids() == ["a", "b", "c", "d"]
    store.put(_as_any(_model("e")))
    assert store.ids() == ["b", "c", "d", "e"]
    assert "a" not in store
    store.put(_as_any(_model("f")))
    assert store.ids() == ["c", "d", "e", "f"]


def test_model_store_put_returns_evicted_ids() -> None:
    store = InMemoryModelStore(capacity=2)
    assert store.put(_as_any(_model("a"))) == []
    assert store.put(_as_any(_model("b"))) == []
    assert store.put(_as_any(_model("a"))) == []  # re-put touches, evicts nothing
    assert store.put(_as_any(_model("c"))) == ["b"]
    assert store.put(_as_any(_model("d"))) == ["a"]
    assert store.ids() == ["c", "d"]


def test_model_store_get_touches_entry() -> None:
    store = InMemoryModelStore(capacity=4)
    for mid in "abcd":
        store.put(_as_any(_model(mid)))
    store.get("a")
    assert store.ids() == ["b", "c", "d", "a"]
    store.put(_as_any(_model("e")))
    assert "a" in store
    assert "b" not in store
    assert store.ids() == ["c", "d", "a", "e"]


def test_model_store_re_put_replaces_and_touches() -> None:
    store = InMemoryModelStore(capacity=4)
    for mid in "abc":
        store.put(_as_any(_model(mid)))
    replacement = _model("a")
    store.put(_as_any(replacement))
    assert store.ids() == ["b", "c", "a"]
    assert store.get("a") is replacement


def test_model_store_unknown_raises_key_error() -> None:
    store = InMemoryModelStore()
    with pytest.raises(KeyError):
        store.get("missing")
    with pytest.raises(KeyError):
        store.delete("missing")


def test_model_store_delete() -> None:
    store = InMemoryModelStore()
    store.put(_as_any(_model("a")))
    store.put(_as_any(_model("b")))
    store.delete("a")
    assert "a" not in store
    assert store.ids() == ["b"]
    with pytest.raises(KeyError):
        store.get("a")


def test_model_store_rejects_bad_capacity() -> None:
    with pytest.raises(ValueError):
        InMemoryModelStore(capacity=0)


# --- ArtifactStore --------------------------------------------------------------------------


def test_artifact_store_put_get() -> None:
    store = InMemoryArtifactStore()
    out = _output("j1", "m1")
    store.put(_as_any(out))
    assert store.get("j1") is out
    assert "j1" in store
    assert store.job_ids("m1") == ["j1"]
    assert store.job_ids("other") == []


def test_artifact_store_keeps_newest_two_per_model() -> None:
    store = InMemoryArtifactStore(jobs_per_model=2)
    store.put(_as_any(_output("j1", "m1")))
    store.put(_as_any(_output("k1", "m2")))
    store.put(_as_any(_output("j2", "m1")))
    store.put(_as_any(_output("j3", "m1")))
    assert store.job_ids("m1") == ["j2", "j3"]
    assert "j1" not in store
    with pytest.raises(KeyError):
        store.get("j1")
    # other models are unaffected
    assert store.job_ids("m2") == ["k1"]
    assert "k1" in store
    store.put(_as_any(_output("j4", "m1")))
    assert store.job_ids("m1") == ["j3", "j4"]
    assert "j2" not in store


def test_artifact_store_delete() -> None:
    store = InMemoryArtifactStore()
    store.put(_as_any(_output("j1", "m1")))
    store.put(_as_any(_output("j2", "m1")))
    store.delete("j1")
    assert "j1" not in store
    assert store.job_ids("m1") == ["j2"]
    with pytest.raises(KeyError):
        store.delete("j1")
    with pytest.raises(KeyError):
        store.get("nope")


def test_artifact_store_delete_model() -> None:
    store = InMemoryArtifactStore()
    store.put(_as_any(_output("j1", "m1")))
    store.put(_as_any(_output("j2", "m1")))
    store.put(_as_any(_output("k1", "m2")))
    store.delete_model("m1")
    assert store.job_ids("m1") == []
    assert "j1" not in store
    assert "j2" not in store
    assert "k1" in store
    store.delete_model("m1")  # no-op
    store.delete_model("never")  # no-op


def test_artifact_store_re_put_same_job_does_not_duplicate() -> None:
    store = InMemoryArtifactStore()
    store.put(_as_any(_output("j1", "m1")))
    store.put(_as_any(_output("j2", "m1")))
    newer = _output("j1", "m1")
    store.put(_as_any(newer))
    assert store.job_ids("m1") == ["j2", "j1"]
    assert store.get("j1") is newer


def test_artifact_store_get_piece() -> None:
    store = InMemoryArtifactStore()
    out = _output("j1", "m1", ("x0_y0_z0", "x1_y0_z0"))
    store.put(_as_any(out))
    assert store.get_piece("j1", "x1_y0_z0") is out.pieces[1]
    with pytest.raises(KeyError):
        store.get_piece("j1", "missing")
    with pytest.raises(KeyError):
        store.get_piece("unknown-job", "x0_y0_z0")


def test_artifact_store_rejects_bad_limit() -> None:
    with pytest.raises(ValueError):
        InMemoryArtifactStore(jobs_per_model=0)
