from __future__ import annotations

from enum import StrEnum

from ..apps.documents.policy import DOCUMENT_OPERATIONS
from ..apps.video.policy import VIDEO_OPERATIONS
from ..models import Operation


class WorkspaceId(StrEnum):
    DOCUMENTS = "documents"
    VIDEO = "video"


def workspace_for_operation(operation: Operation) -> WorkspaceId:
    if operation in DOCUMENT_OPERATIONS:
        return WorkspaceId.DOCUMENTS
    if operation in VIDEO_OPERATIONS:
        return WorkspaceId.VIDEO
    raise ValueError(f"Operation {operation.name} does not belong to a workspace.")


def operations_for_workspace(workspace: WorkspaceId) -> frozenset[Operation]:
    return DOCUMENT_OPERATIONS if workspace is WorkspaceId.DOCUMENTS else VIDEO_OPERATIONS
