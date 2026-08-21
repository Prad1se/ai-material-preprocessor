from pathlib import Path

import pytest

from ai_material_preprocessor.application.preview_registry import (
    PreviewProviderRegistry,
    PreviewRequest,
    UnregisteredPreviewProviderError,
)
from ai_material_preprocessor.models import Operation


class FakePreviewProvider:
    def __init__(self, label: str) -> None:
        self.label = label
        self.requests: list[PreviewRequest] = []

    def build(self, request: PreviewRequest):
        self.requests.append(request)
        return self.label


def test_preview_registry_routes_document_and_video_requests(tmp_path: Path) -> None:
    documents = FakePreviewProvider("documents")
    video = FakePreviewProvider("video")
    registry = PreviewProviderRegistry()
    registry.register((Operation.TO_MARKDOWN, Operation.TO_PDF), documents)
    registry.register((Operation.COMPRESS_VIDEO,), video)

    document_request = PreviewRequest(
        (tmp_path / "lesson.docx",), Operation.TO_MARKDOWN, tmp_path / "out"
    )
    video_request = PreviewRequest(
        (tmp_path / "clip.mp4",), Operation.COMPRESS_VIDEO, tmp_path / "out"
    )

    assert registry.build(document_request) == "documents"
    assert registry.build(video_request) == "video"
    assert documents.requests == [document_request]
    assert video.requests == [video_request]


def test_preview_registry_reports_unregistered_operation(tmp_path: Path) -> None:
    request = PreviewRequest((tmp_path / "clip.mp4",), Operation.ORGANIZE_VIDEO, tmp_path / "out")

    with pytest.raises(UnregisteredPreviewProviderError, match="ORGANIZE_VIDEO"):
        PreviewProviderRegistry().build(request)
