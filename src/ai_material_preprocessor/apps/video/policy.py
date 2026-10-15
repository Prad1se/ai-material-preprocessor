from __future__ import annotations

from ...converters.video import VIDEO_EXTENSIONS
from ...models import Operation

VIDEO_OPERATIONS = frozenset(
    {
        Operation.COMPRESS_VIDEO,
        Operation.EXTRACT_AUDIO,
        Operation.STANDARDIZE_MP4,
        Operation.KEYFRAMES_CONTACT_SHEET,
        Operation.RENAME_VIDEO,
        Operation.ORGANIZE_VIDEO,
        Operation.VIDEO_AI_PACK,
    }
)
LEGACY_VIDEO_OPERATIONS = VIDEO_OPERATIONS - {Operation.VIDEO_AI_PACK}
VIDEO_INPUT_EXTENSIONS = frozenset(VIDEO_EXTENSIONS)
VIDEO_TOOL_NAMES = frozenset({"ffmpeg", "ffprobe", "exiftool"})
