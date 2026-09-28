"""Command-line entry point: `serve`, `slice` and `openapi` (docs/02_build_brief.md §2.8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from fastapi import FastAPI

from stl_slicer.api.app import create_app
from stl_slicer.core.errors import MeshLoadError, PlanError
from stl_slicer.core.models import (
    DovetailJointSpec,
    DowelJointSpec,
    JigsawJointSpec,
    JointSpec,
    NoJointSpec,
    PrintVolume,
    SliceSpec,
)

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Partition STL meshes into print-bed-sized pieces with interlocking joints.",
)

JOINT_KINDS: dict[
    str, type[NoJointSpec] | type[DowelJointSpec] | type[DovetailJointSpec] | type[JigsawJointSpec]
] = {
    "none": NoJointSpec,
    "dowel": DowelJointSpec,
    "dovetail": DovetailJointSpec,
    "jigsaw": JigsawJointSpec,
}


def create_prod_app() -> FastAPI:
    """App factory for `serve`: API plus the built web UI (if present)."""
    return create_app()


def create_dev_app() -> FastAPI:
    """App factory for `serve --dev`: API only (the Vite dev server serves the UI)."""
    return create_app(serve_web=False)


def parse_bed(bed: str) -> PrintVolume:
    """Parse `AxBxC` (millimetres) into a `PrintVolume`.

    Raises:
        typer.BadParameter: malformed or non-positive dimensions.
    """
    parts = bed.lower().split("x")
    if len(parts) != 3:
        raise typer.BadParameter(f"expected AxBxC (e.g. 220x220x250), got {bed!r}")
    try:
        x, y, z = (float(p) for p in parts)
        return PrintVolume(x=x, y=y, z=z)
    except ValueError as exc:  # float() failure or pydantic ValidationError (a ValueError)
        raise typer.BadParameter(f"bed dimensions must be positive numbers, got {bed!r}") from exc


def joint_spec(kind: str) -> JointSpec:
    """Default joint spec for `kind` (none, dowel, dovetail or jigsaw).

    Raises:
        typer.BadParameter: unknown kind.
    """
    try:
        return JOINT_KINDS[kind.lower()]()
    except KeyError:
        choices = "|".join(JOINT_KINDS)
        raise typer.BadParameter(f"joint must be one of {choices}, got {kind!r}") from None


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
    dev: Annotated[
        bool, typer.Option("--dev", help="API only (no static web mount) with auto-reload.")
    ] = False,
) -> None:
    """Run the web app."""
    import uvicorn

    target = "stl_slicer.cli:create_dev_app" if dev else "stl_slicer.cli:create_prod_app"
    uvicorn.run(target, host=host, port=port, factory=True, reload=dev)


@app.command("slice")
def slice_cmd(
    file: Annotated[Path, typer.Argument(help="Mesh file (STL, OBJ, PLY, 3MF, ...).")],
    bed: Annotated[str, typer.Option(help="Print volume in mm, AxBxC.")] = "220x220x250",
    joint: Annotated[str, typer.Option(help="Joint kind: none|dowel|dovetail|jigsaw.")] = "none",
    scale: Annotated[float, typer.Option(help="Uniform scale applied on load.")] = 1.0,
    out: Annotated[Path, typer.Option("-o", "--out", help="Output directory.")] = Path("out"),
) -> None:
    """Slice FILE into bed-sized pieces; write one STL per piece plus manifest.json."""
    volume = parse_bed(bed)
    spec = SliceSpec(print_volume=volume, joint=joint_spec(joint))
    if not file.is_file():
        raise typer.BadParameter(f"no such file: {file}", param_hint="FILE")

    from stl_slicer.core.pipeline import slice_model
    from stl_slicer.io import exporters
    from stl_slicer.io.loaders import load_mesh

    def progress(fraction: float, step: str) -> None:
        typer.echo(f"{step} {fraction:.0%}", err=True)

    try:
        model = load_mesh(file.read_bytes(), file.name, scale)
        output = slice_model(model, spec, progress=progress)
    except (MeshLoadError, PlanError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    out.mkdir(parents=True, exist_ok=True)
    for piece in output.pieces:
        (out / f"{piece.info.piece_id}.stl").write_bytes(exporters.piece_to_stl(piece))
    result = output.result
    (out / "manifest.json").write_text(result.model_dump_json(indent=2))

    for warning in [*model.asset.warnings, *result.warnings]:
        subject = f" [{warning.subject}]" if warning.subject else ""
        typer.echo(f"warning: {warning.code.value}{subject}: {warning.message}", err=True)
    typer.echo(f"{len(output.pieces)} pieces -> {out}")


@app.command()
def openapi() -> None:
    """Print the OpenAPI schema as JSON."""
    print(json.dumps(create_app(serve_web=False).openapi(), indent=2))
