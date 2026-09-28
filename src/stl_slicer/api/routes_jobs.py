"""Job routes: status, cancel, and binary results."""

from __future__ import annotations

from fastapi import APIRouter, Response

from stl_slicer.api.deps import ArtifactsDep, RunnerDep
from stl_slicer.core.models import Job

GLB_MEDIA_TYPE = "model/gltf-binary"
STL_MEDIA_TYPE = "model/stl"
ZIP_MEDIA_TYPE = "application/zip"

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get("/{job_id}", response_model=Job, operation_id="get_job")
def get_job(job_id: str, runner: RunnerDep) -> Job:
    """Return a snapshot of a job."""
    return runner.get(job_id)


@router.delete("/{job_id}", response_model=Job, operation_id="cancel_job")
def cancel_job(job_id: str, runner: RunnerDep) -> Job:
    """Cancel a job (idempotent) and return its snapshot."""
    return runner.cancel(job_id)


@router.get(
    "/{job_id}/pieces.glb",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {GLB_MEDIA_TYPE: {}}, "description": "All pieces as one scene."}},
    operation_id="get_pieces_glb",
)
def get_pieces_glb(job_id: str, artifacts: ArtifactsDep) -> Response:
    """Return every piece in the model frame; node name = piece_id."""
    from stl_slicer.io import exporters

    output = artifacts.get(job_id)
    return Response(content=exporters.pieces_to_glb(output.pieces), media_type=GLB_MEDIA_TYPE)


@router.get(
    "/{job_id}/pieces/{piece_id}.stl",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {STL_MEDIA_TYPE: {}}, "description": "One piece, print frame."}},
    operation_id="get_piece_stl",
)
def get_piece_stl(job_id: str, piece_id: str, artifacts: ArtifactsDep) -> Response:
    """Return one piece as STL in the print frame (min z = 0, xy-centred)."""
    from stl_slicer.io import exporters

    output = artifacts.get(job_id)
    for piece in output.pieces:
        if piece.info.piece_id == piece_id:
            data = exporters.mesh_to_stl(piece.mesh.translate(piece.info.print_offset))
            return Response(
                content=data, media_type=STL_MEDIA_TYPE, headers=_attachment(f"{piece_id}.stl")
            )
    raise KeyError(piece_id)


@router.get(
    "/{job_id}/download.zip",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {ZIP_MEDIA_TYPE: {}}, "description": "STLs + manifest.json."}},
    operation_id="download_zip",
)
def download_zip(job_id: str, artifacts: ArtifactsDep) -> Response:
    """Return every piece STL (print frame) plus manifest.json (= SliceResult)."""
    from stl_slicer.io import exporters

    output = artifacts.get(job_id)
    return Response(
        content=exporters.pieces_to_zip(output.pieces, output.result),
        media_type=ZIP_MEDIA_TYPE,
        headers=_attachment(f"slice-{job_id}.zip"),
    )
