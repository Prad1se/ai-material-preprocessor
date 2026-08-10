from __future__ import annotations

from pathlib import Path

from ..errors import ErrorCode, UserFacingError
from ..infrastructure.processes import (
    CancellationToken,
    CommandRequest,
    CommandResult,
    ProcessRunner,
)


class ConversionError(UserFacingError):
    def __init__(
        self,
        user_message: str,
        *,
        code: ErrorCode = ErrorCode.CONVERSION_FAILED,
        technical_detail: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(code, user_message, technical_detail, retryable)


def run_command(
    command: list[str],
    cwd: Path | None = None,
    *,
    tool_name: str = "",
    timeout_seconds: float | None = 300.0,
    cancellation: CancellationToken | None = None,
    runner: ProcessRunner | None = None,
) -> CommandResult:
    if not command:
        raise ConversionError("外部工具命令为空，无法开始处理。")
    request = CommandRequest(
        executable=str(command[0]),
        arguments=tuple(str(value) for value in command[1:]),
        tool_name=tool_name or Path(command[0]).stem or "外部工具",
        cwd=cwd,
        timeout_seconds=timeout_seconds,
    )
    try:
        return (runner or ProcessRunner()).run(request, cancellation=cancellation)
    except UserFacingError as exc:
        raise ConversionError(
            exc.user_message,
            code=exc.code,
            technical_detail=exc.technical_detail,
            retryable=exc.retryable,
        ) from exc
