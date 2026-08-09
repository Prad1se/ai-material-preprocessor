from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..errors import ErrorCode, UserFacingError


@dataclass(frozen=True)
class CommandRequest:
    executable: str
    arguments: tuple[str, ...] = ()
    tool_name: str = "外部工具"
    cwd: Path | None = None
    timeout_seconds: float | None = 300.0

    @property
    def command(self) -> tuple[str, ...]:
        return (self.executable, *self.arguments)


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()


class ProcessRunner:
    def __init__(self, *, poll_interval_seconds: float = 0.1) -> None:
        self.poll_interval_seconds = max(0.01, poll_interval_seconds)

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)

    def run(
        self,
        request: CommandRequest,
        *,
        cancellation: CancellationToken | None = None,
    ) -> CommandResult:
        if cancellation and cancellation.is_cancelled:
            raise UserFacingError(
                ErrorCode.CANCELLED,
                "任务已取消，原文件没有改动。",
                retryable=True,
            )
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                list(request.command),
                cwd=request.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
                shell=False,
            )
        except OSError as exc:
            raise UserFacingError(
                ErrorCode.TOOL_MISSING,
                f"无法启动{request.tool_name}，请在设置中重新检测或选择工具路径。",
                technical_detail=f"{type(exc).__name__}: {exc}",
                retryable=True,
            ) from exc

        stdout = ""
        stderr = ""
        while True:
            if cancellation and cancellation.is_cancelled:
                self._stop_process(process)
                raise UserFacingError(
                    ErrorCode.CANCELLED,
                    "任务已取消，原文件没有改动。",
                    retryable=True,
                )
            elapsed = time.monotonic() - started
            if request.timeout_seconds is not None and elapsed >= request.timeout_seconds:
                self._stop_process(process)
                raise UserFacingError(
                    ErrorCode.EXTERNAL_TOOL_TIMEOUT,
                    f"{request.tool_name}处理超时，已安全停止；可以调整设置后重试。",
                    technical_detail=(
                        f"timeout after {request.timeout_seconds:.3f}s: {request.command!r}"
                    ),
                    retryable=True,
                )
            wait_for = self.poll_interval_seconds
            if request.timeout_seconds is not None:
                wait_for = min(wait_for, max(0.001, request.timeout_seconds - elapsed))
            try:
                stdout, stderr = process.communicate(timeout=wait_for)
                break
            except subprocess.TimeoutExpired:
                continue

        elapsed = time.monotonic() - started
        result = CommandResult(request.command, process.returncode, stdout, stderr, elapsed)
        if result.returncode:
            detail = (result.stderr or result.stdout or "no process output").strip()
            raise UserFacingError(
                ErrorCode.EXTERNAL_TOOL_FAILED,
                f"{request.tool_name}处理失败，请查看任务详情。",
                technical_detail=f"exit {result.returncode}: {detail}",
                retryable=True,
            )
        return result
