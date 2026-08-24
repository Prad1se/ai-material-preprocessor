from __future__ import annotations

from ..apps.documents.policy import DOCUMENT_OPERATIONS
from ..apps.documents.preview import DocumentPreviewProvider
from ..apps.video.policy import LEGACY_VIDEO_OPERATIONS
from ..apps.video.preview import VideoAIPackPreviewProvider, VideoPreviewProvider
from ..models import Operation
from .preview_registry import PreviewProviderRegistry


def build_default_preview_registry() -> PreviewProviderRegistry:
    registry = PreviewProviderRegistry()
    registry.register(DOCUMENT_OPERATIONS, DocumentPreviewProvider())
    registry.register(LEGACY_VIDEO_OPERATIONS, VideoPreviewProvider())
    registry.register((Operation.VIDEO_AI_PACK,), VideoAIPackPreviewProvider())
    return registry
