from __future__ import annotations

from ..apps.documents.policy import DOCUMENT_OPERATIONS
from ..apps.documents.preview import DocumentPreviewProvider
from ..apps.video.policy import VIDEO_OPERATIONS
from ..apps.video.preview import VideoPreviewProvider
from .preview_registry import PreviewProviderRegistry


def build_default_preview_registry() -> PreviewProviderRegistry:
    registry = PreviewProviderRegistry()
    registry.register(DOCUMENT_OPERATIONS, DocumentPreviewProvider())
    registry.register(VIDEO_OPERATIONS, VideoPreviewProvider())
    return registry
