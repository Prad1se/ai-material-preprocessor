from __future__ import annotations

from ..apps.documents.executor import DocumentOperationExecutor, DocumentService
from ..apps.documents.policy import DOCUMENT_OPERATIONS
from ..apps.video.executor import VideoOperationExecutor, VideoService
from ..apps.video.policy import VIDEO_OPERATIONS
from .executor_registry import OperationExecutorRegistry


def build_default_executor_registry(
    document_service: DocumentService,
    video_service: VideoService,
) -> OperationExecutorRegistry:
    registry = OperationExecutorRegistry()
    registry.register(DOCUMENT_OPERATIONS, DocumentOperationExecutor(document_service))
    registry.register(VIDEO_OPERATIONS, VideoOperationExecutor(video_service))
    return registry
