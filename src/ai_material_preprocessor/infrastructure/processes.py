from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
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
    success_codes: tuple[int, ...] = (0,)
    environment: Mapping[str, str] | None = None

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
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        if cancellation and cancellation.is_cancelled:
            raise UserFacingError(
                ErrorCode.CANCELLED,
                "任务已取消，原文件没有改动。",
                retryable=True,
            )
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        started = time.monotonic()
        environment = None
        if request.environment is not None:
            environment = {**os.environ, **request.environment}
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
                env=environment,
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

        def cancellation_error() -> UserFacingError:
            return UserFacingError(
                ErrorCode.CANCELLED,
                "任务已取消，原文件没有改动。",
                retryable=True,
            )

        def timeout_error() -> UserFacingError:
            return UserFacingError(
                ErrorCode.EXTERNAL_TOOL_TIMEOUT,
                f"{request.tool_name}处理超时，已安全停止；可以调整设置后重试。",
                technical_detail=(
                    f"timeout after {request.timeout_seconds:.3f}s: {request.command!r}"
                ),
                retryable=True,
            )

        if on_stdout_line is None:
            while True:
                if cancellation and cancellation.is_cancelled:
                    self._stop_process(process)
                    raise cancellation_error()
                elapsed = time.monotonic() - started
                if request.timeout_seconds is not None and elapsed >= request.timeout_seconds:
                    self._stop_process(process)
                    raise timeout_error()
                wait_for = self.poll_interval_seconds
                if request.timeout_seconds is not None:
                    wait_for = min(
                        wait_for,
                        max(0.001, request.timeout_seconds - elapsed),
                    )
                try:
                    stdout, stderr = process.communicate(timeout=wait_for)
                    break
                except subprocess.TimeoutExpired:
                    continue
        else:
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []

            def drain_stdout() -> None:
                if process.stdout is None:
                    return
                for line in process.stdout:
                    stdout_lines.append(line)
                    try:
                        on_stdout_line(line.rstrip("\r\n"))
                    except Exception:
                        continue

            def drain_stderr() -> None:
                if process.stderr is None:
                    return
                stderr_lines.extend(process.stderr)

            readers = [
                threading.Thread(target=drain_stdout, daemon=True),
                threading.Thread(target=drain_stderr, daemon=True),
            ]
            for reader in readers:
                reader.start()
            pending_error: UserFacingError | None = None
            while process.poll() is None:
                if cancellation and cancellation.is_cancelled:
                    self._stop_process(process)
                    pending_error = cancellation_error()
                    break
                elapsed = time.monotonic() - started
                if request.timeout_seconds is not None and elapsed >= request.timeout_seconds:
                    self._stop_process(process)
                    pending_error = timeout_error()
                    break
                time.sleep(self.poll_interval_seconds)
            for reader in readers:
                reader.join(timeout=1)
            stdout = "".join(stdout_lines)
            stderr = "".join(stderr_lines)
            if pending_error is not None:
                raise pending_error

        elapsed = time.monotonic() - started
        result = CommandResult(request.command, process.returncode, stdout, stderr, elapsed)
        if result.returncode not in request.success_codes:
            detail = (result.stderr or result.stdout or "no process output").strip()
            raise UserFacingError(
                ErrorCode.EXTERNAL_TOOL_FAILED,
                f"{request.tool_name}处理失败，请查看任务详情。",
                technical_detail=f"exit {result.returncode}: {detail}",
                retryable=True,
            )
        return result
