"""FastAPI dependencies: typed accessors for the collaborators stored on `app.state`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Protocol, cast

from fastapi import Depends, Request

from stl_slicer.core.models import CutPlan, SliceSpec
from stl_slicer.service.jobs import JobRunner
from stl_slicer.service.stores import ArtifactStore, ModelStore

if TYPE_CHECKING:
    from stl_slicer.core.geometry import LoadedModel


class Loader(Protocol):
    """Turns uploaded bytes into a loaded model (raises MeshLoadError)."""

    def __call__(self, data: bytes, filename: str, scale: float, /) -> LoadedModel: ...


class Planner(Protocol):
    """Computes the cut plan for a model and spec (raises PlanError)."""

    def __call__(self, model: LoadedModel, spec: SliceSpec, /) -> CutPlan: ...


def get_models(request: Request) -> ModelStore:
    """Return the app's model store."""
    return cast("ModelStore", request.app.state.models)


def get_artifacts(request: Request) -> ArtifactStore:
    """Return the app's artifact store."""
    return cast("ArtifactStore", request.app.state.artifacts)


def get_runner(request: Request) -> JobRunner:
    """Return the app's job runner."""
    return cast("JobRunner", request.app.state.runner)


def get_loader(request: Request) -> Loader:
    """Return the app's mesh loader."""
    return cast("Loader", request.app.state.loader)


def get_planner(request: Request) -> Planner:
    """Return the app's cut planner."""
    return cast("Planner", request.app.state.planner)


ModelsDep = Annotated[ModelStore, Depends(get_models)]
ArtifactsDep = Annotated[ArtifactStore, Depends(get_artifacts)]
RunnerDep = Annotated[JobRunner, Depends(get_runner)]
LoaderDep = Annotated[Loader, Depends(get_loader)]
PlannerDep = Annotated[Planner, Depends(get_planner)]
