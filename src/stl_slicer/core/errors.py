"""Domain errors. Leaf module: imports nothing from the package."""


class SlicerError(Exception):
    """Base class for every error raised by stl_slicer."""


class PlanError(SlicerError):
    """The partition request cannot produce a valid plan (bad limits or cut positions)."""


class MeshLoadError(SlicerError):
    """The input could not be turned into a manifold mesh."""


class SliceInvariantError(SlicerError):
    """A geometric invariant the pipeline guarantees was violated. This is a bug, not user error."""


class Cancelled(SlicerError):  # noqa: N818 - a signal, not an error condition
    """The job was cancelled between steps."""
