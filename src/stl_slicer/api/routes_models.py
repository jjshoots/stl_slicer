"""Model routes: upload, inspect, delete, preview mesh, plan and slice."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile

from stl_slicer.api.deps import ArtifactsDep, LoaderDep, ModelsDep, PlannerDep, RunnerDep
from stl_slicer.core.models import CutPlan, Job, MeshAsset, SliceSpec

GLB_MEDIA_TYPE = "model/gltf-binary"

router = APIRouter(prefix="/api/models", tags=["models"])


@router.post("", response_model=MeshAsset, operation_id="upload_model")
async def upload_model(
    models: ModelsDep,
    loader: LoaderDep,
    file: Annotated[UploadFile, File()],
    scale: Annotated[float, Form(gt=0)] = 1.0,
) -> MeshAsset:
    """Upload a mesh file; 422 if it cannot be made manifold."""
    data = await file.read()
    model = loader(data, file.filename or "model.stl", scale)
    models.put(model)
    return model.asset


@router.get("/{model_id}", response_model=MeshAsset, operation_id="get_model")
def get_model(model_id: str, models: ModelsDep) -> MeshAsset:
    """Return an uploaded model's metadata."""
    return models.get(model_id).asset


@router.delete(
    "/{model_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
    operation_id="delete_model",
)
def delete_model(
    model_id: str, models: ModelsDep, artifacts: ArtifactsDep, runner: RunnerDep
) -> Response:
    """Delete a model, cancel its live jobs, and drop every slice artifact derived from it."""
    models.delete(model_id)
    runner.cancel_model(model_id)
    artifacts.delete_model(model_id)
    return Response(status_code=204)


@router.get(
    "/{model_id}/mesh.glb",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {GLB_MEDIA_TYPE: {}}, "description": "Model mesh as GLB."}},
    operation_id="get_model_glb",
)
def get_model_glb(model_id: str, models: ModelsDep) -> Response:
    """Return the model mesh in the model frame as binary glTF."""
    from stl_slicer.io import exporters

    model = models.get(model_id)
    return Response(content=exporters.mesh_to_glb(model.mesh), media_type=GLB_MEDIA_TYPE)


@router.post("/{model_id}/plan", response_model=CutPlan, operation_id="plan_model")
def plan_model(model_id: str, spec: SliceSpec, models: ModelsDep, planner: PlannerDep) -> CutPlan:
    """Compute the cut plan synchronously (live preview)."""
    return planner(models.get(model_id), spec)


@router.post("/{model_id}/slice", response_model=Job, operation_id="slice_model")
def slice_model(model_id: str, spec: SliceSpec, runner: RunnerDep) -> Job:
    """Submit a slice job; supersedes any live job for the same model."""
    return runner.submit(model_id, spec)
