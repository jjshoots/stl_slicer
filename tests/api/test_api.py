"""API tests against dict-backed fakes (no geometry kernel)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from stl_slicer.api.app import create_app
from stl_slicer.core.errors import MeshLoadError, PlanError
from stl_slicer.core.models import (
    AxisCuts,
    Bounds,
    CellLimits,
    CutPlan,
    Job,
    JobStatus,
    MeshAsset,
    PrinterPreset,
    SliceSpec,
)
from stl_slicer.service.stores import InMemoryModelStore

BOUNDS = Bounds(min=(0, 0, 0), max=(10, 10, 10))


@dataclass
class _Model:
    asset: MeshAsset


class FakeModels:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def put(self, model: Any) -> list[str]:
        self.data[model.asset.model_id] = model
        return []

    def get(self, model_id: str) -> Any:
        return self.data[model_id]

    def delete(self, model_id: str) -> None:
        del self.data[model_id]

    def __contains__(self, model_id: object) -> bool:
        return model_id in self.data

    def ids(self) -> list[str]:
        return list(self.data)


class FakeArtifacts:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.deleted_models: list[str] = []

    def put(self, output: Any) -> None:
        self.data[output.result.job_id] = output

    def get(self, job_id: str) -> Any:
        return self.data[job_id]

    def delete(self, job_id: str) -> None:
        del self.data[job_id]

    def delete_model(self, model_id: str) -> None:
        self.deleted_models.append(model_id)

    def __contains__(self, job_id: object) -> bool:
        return job_id in self.data

    def job_ids(self, model_id: str) -> list[str]:
        return list(self.data)

    def get_piece(self, job_id: str, piece_id: str) -> Any:
        for piece in self.data[job_id].pieces:
            if piece.info.piece_id == piece_id:
                return piece
        raise KeyError(piece_id)


@dataclass
class FakeRunner:
    models: FakeModels
    jobs: dict[str, Job] = field(default_factory=dict)
    submits: list[tuple[str, SliceSpec]] = field(default_factory=list)
    shut_down: bool = False

    def submit(self, model_id: str, spec: SliceSpec) -> Job:
        if model_id not in self.models:
            raise KeyError(model_id)
        self.submits.append((model_id, spec))
        job = Job(job_id=f"job{len(self.submits)}", model_id=model_id)
        self.jobs[job.job_id] = job
        return job.model_copy(deep=True)

    def get(self, job_id: str) -> Job:
        return self.jobs[job_id].model_copy(deep=True)

    def cancel(self, job_id: str) -> Job:
        job = self.jobs[job_id]
        if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            job.status = JobStatus.CANCELLED
            job.step = "cancelled"
        return job.model_copy(deep=True)

    def cancel_model(self, model_id: str) -> list[Job]:
        return [self.cancel(j.job_id) for j in list(self.jobs.values()) if j.model_id == model_id]

    def shutdown(self) -> None:
        self.shut_down = True


def fake_loader(data: bytes, filename: str, scale: float) -> _Model:
    if data == b"bad":
        raise MeshLoadError("not manifold")
    asset = MeshAsset(
        model_id="m1",
        filename=filename,
        scale=scale,
        triangle_count=12,
        bounds=BOUNDS,
        volume=1000.0,
    )
    return _Model(asset=asset)


def fake_planner(model: _Model, spec: SliceSpec) -> CutPlan:
    if spec.print_volume.x < 5:
        raise PlanError("print volume too small")
    return CutPlan(
        bounds=model.asset.bounds,
        limits=CellLimits(max_cell=(10, 10, 10)),
        cuts=AxisCuts(),
        cells=[],
        interfaces=[],
    )


SPEC = {"print_volume": {"x": 100, "y": 100, "z": 100}}


@dataclass
class Env:
    client: TestClient
    models: FakeModels
    artifacts: FakeArtifacts
    runner: FakeRunner


@pytest.fixture
def env() -> Env:
    models = FakeModels()
    artifacts = FakeArtifacts()
    runner = FakeRunner(models)
    app = create_app(
        models, artifacts, runner, serve_web=False, loader=fake_loader, planner=fake_planner
    )
    return Env(TestClient(app), models, artifacts, runner)


def _upload(client: TestClient, data: bytes = b"solid", scale: str = "2.0") -> Any:
    return client.post(
        "/api/models",
        files={"file": ("part.stl", data, "application/octet-stream")},
        data={"scale": scale},
    )


def test_health(env: Env) -> None:
    r = env.client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_presets(env: Env) -> None:
    r = env.client.get("/api/presets")
    assert r.status_code == 200
    presets = [PrinterPreset.model_validate(p) for p in r.json()]
    assert len(presets) == 5


def test_upload_happy_path(env: Env) -> None:
    r = _upload(env.client)
    assert r.status_code == 200, r.text
    asset = MeshAsset.model_validate(r.json())
    assert asset.model_id == "m1"
    assert asset.filename == "part.stl"
    assert asset.scale == 2.0
    assert "m1" in env.models


def test_upload_default_scale(env: Env) -> None:
    r = env.client.post("/api/models", files={"file": ("part.stl", b"x")})
    assert r.status_code == 200
    assert r.json()["scale"] == 1.0


def test_upload_bad_mesh_is_422(env: Env) -> None:
    r = _upload(env.client, data=b"bad")
    assert r.status_code == 422
    assert r.json() == {"detail": "not manifold"}
    assert env.models.ids() == []


@pytest.mark.parametrize("scale", ["0", "-1"])
def test_upload_nonpositive_scale_is_422(env: Env, scale: str) -> None:
    assert _upload(env.client, scale=scale).status_code == 422
    assert env.models.ids() == []


def test_upload_missing_file_is_422(env: Env) -> None:
    assert env.client.post("/api/models", data={"scale": "1"}).status_code == 422


def test_get_model(env: Env) -> None:
    _upload(env.client)
    r = env.client.get("/api/models/m1")
    assert r.status_code == 200
    assert r.json()["model_id"] == "m1"


@pytest.mark.parametrize("method", ["get", "delete"])
def test_unknown_model_is_404(env: Env, method: str) -> None:
    r = env.client.request(method.upper(), "/api/models/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "not found: nope"}


def test_delete_model(env: Env) -> None:
    _upload(env.client)
    r = env.client.delete("/api/models/m1")
    assert r.status_code == 204
    assert r.content == b""
    assert env.artifacts.deleted_models == ["m1"]
    assert env.client.get("/api/models/m1").status_code == 404


def test_upload_evicting_a_model_drops_its_jobs_and_artifacts() -> None:
    def loader(data: bytes, filename: str, scale: float) -> _Model:
        model = fake_loader(data, filename, scale)
        return _Model(asset=model.asset.model_copy(update={"model_id": filename[:-4]}))

    store = InMemoryModelStore(capacity=4)
    artifacts = FakeArtifacts()
    runner = FakeRunner(store)
    app = create_app(store, artifacts, runner, False, loader=loader, planner=fake_planner)
    client = TestClient(app)
    for name in ("a", "b", "c", "d"):
        assert client.post("/api/models", files={"file": (f"{name}.stl", b"x")}).status_code == 200
    job_id = client.post("/api/models/a/slice", json=SPEC).json()["job_id"]
    assert artifacts.deleted_models == []

    assert client.post("/api/models", files={"file": ("e.stl", b"x")}).status_code == 200
    assert store.ids() == ["b", "c", "d", "e"]
    assert artifacts.deleted_models == ["a"]
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"


def test_delete_model_cancels_its_live_job(env: Env) -> None:
    _upload(env.client)
    job = env.client.post("/api/models/m1/slice", json=SPEC).json()
    assert env.client.delete("/api/models/m1").status_code == 204
    assert env.client.get(f"/api/jobs/{job['job_id']}").json()["status"] == "cancelled"


def test_plan(env: Env) -> None:
    _upload(env.client)
    r = env.client.post("/api/models/m1/plan", json=SPEC)
    assert r.status_code == 200, r.text
    plan = CutPlan.model_validate(r.json())
    assert plan.bounds == BOUNDS


def test_plan_error_is_422(env: Env) -> None:
    _upload(env.client)
    r = env.client.post("/api/models/m1/plan", json={"print_volume": {"x": 1, "y": 100, "z": 100}})
    assert r.status_code == 422
    assert r.json() == {"detail": "print volume too small"}


def test_plan_unknown_model_is_404(env: Env) -> None:
    assert env.client.post("/api/models/nope/plan", json=SPEC).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"print_volume": {"x": 0, "y": 1, "z": 1}},
        {**SPEC, "joint": {"kind": "rivet"}},
        {**SPEC, "joint": {"kind": "dovetail", "neck_width": 12, "head_width": 8}},
    ],
)
def test_invalid_spec_is_422(env: Env, body: dict[str, Any]) -> None:
    _upload(env.client)
    assert env.client.post("/api/models/m1/plan", json=body).status_code == 422
    assert env.client.post("/api/models/m1/slice", json=body).status_code == 422
    assert env.runner.submits == []


def test_planner_validation_error_is_422() -> None:
    models = FakeModels()

    def bad_planner(model: Any, spec: SliceSpec) -> CutPlan:
        return CutPlan.model_validate({"bounds": "nope"})

    app = create_app(
        models, FakeArtifacts(), FakeRunner(models), False, loader=fake_loader, planner=bad_planner
    )
    client = TestClient(app)
    _upload(client)
    r = client.post("/api/models/m1/plan", json=SPEC)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_slice(env: Env) -> None:
    _upload(env.client)
    body = {**SPEC, "joint": {"kind": "dowel"}}
    r = env.client.post("/api/models/m1/slice", json=body)
    assert r.status_code == 200, r.text
    job = Job.model_validate(r.json())
    assert job.model_id == "m1"
    assert job.status == JobStatus.QUEUED
    assert env.runner.submits == [("m1", SliceSpec.model_validate(body))]


def test_slice_unknown_model_is_404(env: Env) -> None:
    assert env.client.post("/api/models/nope/slice", json=SPEC).status_code == 404


def test_get_and_cancel_job(env: Env) -> None:
    _upload(env.client)
    job_id = env.client.post("/api/models/m1/slice", json=SPEC).json()["job_id"]
    r = env.client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    r = env.client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert env.client.get(f"/api/jobs/{job_id}").json()["status"] == "cancelled"


@pytest.mark.parametrize("method", ["get", "delete"])
def test_unknown_job_is_404(env: Env, method: str) -> None:
    assert env.client.request(method.upper(), "/api/jobs/nope").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/api/models/nope/mesh.glb",
        "/api/jobs/nope/pieces.glb",
        "/api/jobs/nope/pieces/x0_y0_z0.stl",
        "/api/jobs/nope/download.zip",
    ],
)
def test_binary_endpoints_404_when_missing(env: Env, path: str) -> None:
    r = env.client.get(path)
    assert r.status_code == 404
    assert r.json()["detail"].startswith("not found")


def test_pieces_404_while_job_not_done(env: Env) -> None:
    _upload(env.client)
    job_id = env.client.post("/api/models/m1/slice", json=SPEC).json()["job_id"]
    assert env.client.get(f"/api/jobs/{job_id}/pieces.glb").status_code == 404
    assert env.client.get(f"/api/jobs/{job_id}/download.zip").status_code == 404


def test_openapi(env: Env) -> None:
    r = env.client.get("/openapi.json")
    assert r.status_code == 200
    doc = r.json()
    schemas = doc["components"]["schemas"]
    for name in ("SliceSpec", "CutPlan", "Job", "MeshAsset", "SliceResult", "PrinterPreset"):
        assert name in schemas
    assert not [s for s in schemas if s.endswith(("-Input", "-Output"))]
    op_ids = {op["operationId"] for item in doc["paths"].values() for op in item.values()}
    assert op_ids == {
        "upload_model",
        "get_model",
        "delete_model",
        "get_model_glb",
        "plan_model",
        "slice_model",
        "get_job",
        "cancel_job",
        "get_pieces_glb",
        "get_piece_stl",
        "download_zip",
        "list_presets",
        "health",
    }
    assert doc["info"]["title"] == "stl-slicer"


def test_lifespan_shuts_down_runner(env: Env) -> None:
    with env.client:
        assert not env.runner.shut_down
    assert env.runner.shut_down


def test_static_mount(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>hello slicer</html>")
    models = FakeModels()
    app = create_app(models, FakeArtifacts(), FakeRunner(models), web_dist=tmp_path)
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "hello slicer" in r.text
    r = client.get("/api/health")
    assert r.json() == {"status": "ok"}
    assert client.get("/api/models/nope").status_code == 404


def test_static_mount_disabled(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html>x</html>")
    models = FakeModels()
    app = create_app(models, FakeArtifacts(), FakeRunner(models), False, web_dist=tmp_path)
    assert TestClient(app).get("/").status_code == 404


def test_static_mount_skipped_when_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    models = FakeModels()
    missing = tmp_path / "missing"
    with caplog.at_level(logging.WARNING, logger="stl_slicer.api.app"):
        app = create_app(models, FakeArtifacts(), FakeRunner(models), web_dist=missing)
    assert TestClient(app).get("/").status_code == 404
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}
    (record,) = [r for r in caplog.records if r.name == "stl_slicer.api.app"]
    assert record.levelno == logging.WARNING
    assert str(missing) in record.getMessage()
    assert "cd web && npm run build" in record.getMessage()


def test_no_missing_dist_warning_when_web_disabled(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    models = FakeModels()
    with caplog.at_level(logging.WARNING, logger="stl_slicer.api.app"):
        create_app(models, FakeArtifacts(), FakeRunner(models), False, web_dist=tmp_path / "x")
    assert not [r for r in caplog.records if r.name == "stl_slicer.api.app"]
