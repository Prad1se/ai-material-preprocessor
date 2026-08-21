from __future__ import annotations

from ...converters.markdown import SUPPORTED_EXTENSIONS as MARKDOWN_EXTENSIONS
from ...converters.office_pdf import POWERPOINT_EXTENSIONS, WORD_EXTENSIONS
from ...models import Operation

DOCUMENT_OPERATIONS = frozenset({Operation.TO_MARKDOWN, Operation.TO_PDF})
DOCUMENT_INPUT_EXTENSIONS = frozenset(MARKDOWN_EXTENSIONS | WORD_EXTENSIONS | POWERPOINT_EXTENSIONS)
DOCUMENT_TOOL_NAMES = frozenset({"markitdown", "rapidocr", "libreoffice", "winword", "powerpoint"})
