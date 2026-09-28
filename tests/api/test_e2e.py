"""End-to-end API tests against the real loader, planner, pipeline and exporters."""

from __future__ import annotations

import io
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("stl_slicer.core.pipeline")

import trimesh
from fastapi.testclient import TestClient

from stl_slicer.api.app import create_app
from stl_slicer.core.models import CutPlan, Job, MeshAsset, SliceResult

SPHERE = Path(__file__).resolve().parents[1] / "fixtures" / "sphere.stl"
SPEC = {"print_volume": {"x": 40, "y": 40, "z": 40}}
TERMINAL = {"done", "failed", "cancelled"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(serve_web=False)) as c:
        yield c


def _upload(client: TestClient, data: bytes, name: str = "sphere.stl") -> Any:
    return client.post(
        "/api/models",
        files={"file": (name, data, "application/octet-stream")},
        data={"scale": "1"},
    )


def _wait(client: TestClient, job_id: str, timeout: float = 60.0) -> Job:
    deadline = time.monotonic() + timeout
    while True:
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200, res.text
        job = Job.model_validate(res.json())
        if job.status in TERMINAL or time.monotonic() > deadline:
            return job
        time.sleep(0.05)


def test_upload_plan_slice_download_delete(client: TestClient) -> None:
    res = _upload(client, SPHERE.read_bytes())
    assert res.status_code == 200, res.text
    asset = MeshAsset.model_validate(res.json())
    assert asset.triangle_count == 1280
    mid = asset.model_id

    res = client.post(f"/api/models/{mid}/plan", json=SPEC)
    assert res.status_code == 200, res.text
    assert CutPlan.model_validate(res.json()).cell_count >= 8

    res = client.post(f"/api/models/{mid}/slice", json=SPEC)
    assert res.status_code == 200, res.text
    job = Job.model_validate(res.json())
    assert job.status in {"queued", "running"}

    job = _wait(client, job.job_id)
    assert job.status == "done", job.error
    assert job.result is not None
    result = job.result
    piece_ids = {p.piece_id for p in result.pieces}
    assert piece_ids

    res = client.get(f"/api/jobs/{job.job_id}/pieces.glb")
    assert res.status_code == 200
    assert res.content[:4] == b"glTF"
    scene = trimesh.load(io.BytesIO(res.content), file_type="glb", force="scene")
    node_names = set(scene.graph.nodes_geometry)
    assert node_names == piece_ids

    pid = sorted(piece_ids)[0]
    res = client.get(f"/api/jobs/{job.job_id}/pieces/{pid}.stl")
    assert res.status_code == 200
    piece = trimesh.load(io.BytesIO(res.content), file_type="stl", force="mesh")
    assert piece.bounds[0][2] == pytest.approx(0.0, abs=1e-6)

    res = client.get(f"/api/jobs/{job.job_id}/download.zip")
    assert res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        names = set(zf.namelist())
        assert names == {"manifest.json"} | {f"{p}.stl" for p in piece_ids}
        manifest = SliceResult.model_validate_json(zf.read("manifest.json"))
    assert manifest.job_id == job.job_id
    assert {p.piece_id for p in manifest.pieces} == piece_ids

    assert client.delete(f"/api/models/{mid}").status_code == 204
    assert client.get(f"/api/models/{mid}").status_code == 404
    assert client.get(f"/api/jobs/{job.job_id}/pieces.glb").status_code == 404


def test_upload_non_manifold_is_422(client: TestClient) -> None:
    box = trimesh.creation.box(extents=(10, 10, 10))
    open_box = trimesh.Trimesh(vertices=box.vertices, faces=box.faces[1:], process=False)
    data = open_box.export(file_type="stl")
    assert isinstance(data, bytes)
    res = _upload(client, data, "open_box.stl")
    assert res.status_code == 422, res.text


def test_second_slice_supersedes_first(client: TestClient) -> None:
    res = _upload(client, SPHERE.read_bytes())
    assert res.status_code == 200, res.text
    mid = res.json()["model_id"]

    first = client.post(f"/api/models/{mid}/slice", json=SPEC)
    second = client.post(f"/api/models/{mid}/slice", json=SPEC)
    assert first.status_code == 200 and second.status_code == 200

    job1 = _wait(client, first.json()["job_id"])
    job2 = _wait(client, second.json()["job_id"])
    assert job1.status in {"cancelled", "done"}
    assert job2.status == "done", job2.error
