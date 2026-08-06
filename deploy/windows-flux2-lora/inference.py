"""Public fixed-graph surface; implementation lives in the package contract."""

from contract import (
    build_control_workflow,
    build_inference_workflow,
    validate_control_workflow,
    validate_inference_workflow,
)

__all__ = [
    "build_control_workflow",
    "build_inference_workflow",
    "validate_control_workflow",
    "validate_inference_workflow",
]
