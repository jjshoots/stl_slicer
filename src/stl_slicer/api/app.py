"""FastAPI application factory. See docs/00_design.md §6 and docs/02_build_brief.md §2.8."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from stl_slicer.api import routes_jobs, routes_misc, routes_models
from stl_slicer.api.deps import Loader, Planner
from stl_slicer.core.errors import MeshLoadError, PlanError
from stl_slicer.core.models import CutPlan, SliceSpec
from stl_slicer.service.jobs import JobRunner, ThreadJobRunner
from stl_slicer.service.stores import (
    ArtifactStore,
    InMemoryArtifactStore,
    InMemoryModelStore,
    ModelStore,
)

if TYPE_CHECKING:
    from stl_slicer.core.geometry import LoadedModel

logger = logging.getLogger(__name__)

DEFAULT_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def _app_version() -> str:
    try:
        return version("stl-slicer")
    except PackageNotFoundError:
        return "0.1.0"


def _default_loader(data: bytes, filename: str, scale: float, /) -> LoadedModel:
    from stl_slicer.io.loaders import load_mesh

    return load_mesh(data, filename, scale)


def _default_planner(model: LoadedModel, spec: SliceSpec, /) -> CutPlan:
    from stl_slicer.core.pipeline import cell_limits
    from stl_slicer.core.planning import plan_grid

    return plan_grid(
        model.asset.bounds, cell_limits(spec), spec.partition.cuts, axes=spec.partition.axes
    )


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ValidationError)
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    return JSONResponse(status_code=422, content={"detail": errors})


async def _not_found(_request: Request, exc: Exception) -> JSONResponse:
    key = exc.args[0] if exc.args else ""
    return JSONResponse(status_code=404, content={"detail": f"not found: {key}"})


def create_app(
    models: ModelStore | None = None,
    artifacts: ArtifactStore | None = None,
    runner: JobRunner | None = None,
    serve_web: bool = True,
    *,
    loader: Loader | None = None,
    planner: Planner | None = None,
    web_dist: Path | None = None,
) -> FastAPI:
    """Build the API app; collaborators default to in-memory stores and a threaded runner."""
    model_store: ModelStore = models if models is not None else InMemoryModelStore()
    artifact_store: ArtifactStore = artifacts if artifacts is not None else InMemoryArtifactStore()
    job_runner: JobRunner = (
        runner if runner is not None else ThreadJobRunner(model_store, artifact_store)
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            job_runner.shutdown()

    app = FastAPI(
        title="stl-slicer",
        version=_app_version(),
        separate_input_output_schemas=False,
        lifespan=lifespan,
    )
    app.state.models = model_store
    app.state.artifacts = artifact_store
    app.state.runner = job_runner
    app.state.loader = loader if loader is not None else _default_loader
    app.state.planner = planner if planner is not None else _default_planner

    app.add_exception_handler(MeshLoadError, _domain_error)
    app.add_exception_handler(PlanError, _domain_error)
    app.add_exception_handler(ValidationError, _validation_error)
    app.add_exception_handler(KeyError, _not_found)

    app.include_router(routes_models.router)
    app.include_router(routes_jobs.router)
    app.include_router(routes_misc.router)

    dist = web_dist if web_dist is not None else DEFAULT_WEB_DIST
    if serve_web:
        if dist.is_dir():
            app.mount("/", StaticFiles(directory=dist, html=True), name="web")
        else:
            logger.warning(
                "web UI not served: %s does not exist (build it with `cd web && npm run build`); "
                "serving the API only",
                dist,
            )
    return app
