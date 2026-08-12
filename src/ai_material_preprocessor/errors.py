from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    CANCELLED = "cancelled"
    UNSUPPORTED_INPUT = "unsupported_input"
    TOOL_MISSING = "tool_missing"
    EXTERNAL_TOOL_FAILED = "external_tool_failed"
    EXTERNAL_TOOL_TIMEOUT = "external_tool_timeout"
    DOWNLOAD_FAILED = "download_failed"
    INTEGRITY_FAILED = "integrity_failed"
    INSTALL_FAILED = "install_failed"
    CONVERSION_FAILED = "conversion_failed"
    FILE_SYSTEM = "file_system"
    UNEXPECTED = "unexpected"


@dataclass(eq=False)
class UserFacingError(RuntimeError):
    """An actionable public message paired with private diagnostic detail."""

    code: ErrorCode
    user_message: str
    technical_detail: str = ""
    retryable: bool = False

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.user_message)

    def __str__(self) -> str:
        return self.user_message


def explain_error(error: Exception, *, action: str = "处理文件") -> UserFacingError:
    if isinstance(error, UserFacingError):
        return error
    if isinstance(error, OSError):
        return UserFacingError(
            ErrorCode.FILE_SYSTEM,
            f"{action}时无法访问文件，请检查路径、权限和可用空间。",
            technical_detail=f"{type(error).__name__}: {error}",
            retryable=True,
        )
    return UserFacingError(
        ErrorCode.UNEXPECTED,
        f"{action}时遇到意外问题，请重试；若问题持续，请查看历史详情。",
        technical_detail=f"{type(error).__name__}: {error}",
        retryable=False,
    )
