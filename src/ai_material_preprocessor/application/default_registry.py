from __future__ import annotations

from ..apps.documents.executor import DocumentOperationExecutor, DocumentService
from ..apps.documents.policy import DOCUMENT_OPERATIONS
from ..apps.video.executor import (
    VideoAIPackOperationExecutor,
    VideoAIPackService,
    VideoOperationExecutor,
    VideoService,
)
from ..apps.video.policy import LEGACY_VIDEO_OPERATIONS
from ..models import Operation
from .executor_registry import OperationExecutorRegistry


def build_default_executor_registry(
    document_service: DocumentService,
    video_service: VideoService,
    video_ai_pack_service: VideoAIPackService | None = None,
) -> OperationExecutorRegistry:
    registry = OperationExecutorRegistry()
    registry.register(DOCUMENT_OPERATIONS, DocumentOperationExecutor(document_service))
    registry.register(LEGACY_VIDEO_OPERATIONS, VideoOperationExecutor(video_service))
    if video_ai_pack_service is not None:
        registry.register(
            (Operation.VIDEO_AI_PACK,),
            VideoAIPackOperationExecutor(video_ai_pack_service),
        )
    return registry
