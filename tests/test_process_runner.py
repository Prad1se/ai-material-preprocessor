from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import cast

import pytest

from ai_material_preprocessor.converters.common import ConversionError, run_command
from ai_material_preprocessor.errors import ErrorCode, UserFacingError
from ai_material_preprocessor.infrastructure.processes import (
    CancellationToken,
    CommandRequest,
    ProcessRunner,
)


def test_process_runner_preserves_space_and_chinese_arguments(tmp_path: Path) -> None:
    source = tmp_path / "带 空格的素材.txt"
    source.write_text("ok", encoding="utf-8")
    request = CommandRequest(
        executable=sys.executable,
        arguments=(
            "-c",
            "import sys; sys.stdout.buffer.write(sys.argv[1].encode('utf-8'))",
            str(source),
        ),
        tool_name="Python",
        timeout_seconds=5,
    )

    result = ProcessRunner().run(request)

    assert result.returncode == 0
    assert result.stdout.strip() == str(source)
    assert result.command[0] == sys.executable


def test_process_runner_timeout_has_typed_user_error() -> None:
    request = CommandRequest(
        executable=sys.executable,
        arguments=("-c", "import time; time.sleep(5)"),
        tool_name="测试工具",
        timeout_seconds=0.05,
    )

    with pytest.raises(UserFacingError) as captured:
        ProcessRunner(poll_interval_seconds=0.01).run(request)

    assert captured.value.code is ErrorCode.EXTERNAL_TOOL_TIMEOUT
    assert "测试工具" in captured.value.user_message
    assert captured.value.retryable is True


def test_process_runner_honors_pre_cancelled_token() -> None:
    token = CancellationToken()
    token.cancel()
    request = CommandRequest(
        executable=sys.executable,
        arguments=("-c", "print('must not run')"),
        tool_name="测试工具",
    )

    with pytest.raises(UserFacingError) as captured:
        ProcessRunner().run(request, cancellation=token)

    assert captured.value.code is ErrorCode.CANCELLED
    assert captured.value.retryable is True


def test_process_runner_stops_an_already_running_process_on_cancellation() -> None:
    token = CancellationToken()
    request = CommandRequest(
        executable=sys.executable,
        arguments=("-c", "import time; time.sleep(30)"),
        tool_name="测试工具",
        timeout_seconds=60,
    )
    timer = threading.Timer(0.05, token.cancel)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(UserFacingError) as captured:
            ProcessRunner(poll_interval_seconds=0.01).run(
                request,
                cancellation=token,
            )
    finally:
        timer.cancel()

    assert captured.value.code is ErrorCode.CANCELLED
    assert time.monotonic() - started < 2


def test_process_runner_failure_reports_tool_without_exposing_command_in_message() -> None:
    request = CommandRequest(
        executable=sys.executable,
        arguments=("-c", "import sys; print('private detail', file=sys.stderr); sys.exit(7)"),
        tool_name="测试工具",
    )

    with pytest.raises(UserFacingError) as captured:
        ProcessRunner().run(request)

    assert captured.value.code is ErrorCode.EXTERNAL_TOOL_FAILED
    assert captured.value.user_message == "测试工具处理失败，请查看任务详情。"
    assert "private detail" in captured.value.technical_detail
    assert "private detail" not in str(captured.value)


def test_process_runner_streams_stdout_lines_without_losing_captured_output() -> None:
    request = CommandRequest(
        executable=sys.executable,
        arguments=(
            "-u",
            "-c",
            "import time; print('out_time_us=1000000'); time.sleep(.03); print('progress=end')",
        ),
        tool_name="测试工具",
        timeout_seconds=5,
    )
    lines: list[str] = []

    result = ProcessRunner(poll_interval_seconds=0.005).run(
        request,
        on_stdout_line=lines.append,
    )

    assert lines == ["out_time_us=1000000", "progress=end"]
    assert "out_time_us=1000000" in result.stdout
    assert "progress=end" in result.stdout


def test_legacy_converter_boundary_uses_typed_process_errors() -> None:
    with pytest.raises(ConversionError) as captured:
        run_command(
            [sys.executable, "-c", "import sys; sys.exit(9)"],
            tool_name="转换测试工具",
        )

    assert captured.value.code is ErrorCode.EXTERNAL_TOOL_FAILED
    assert str(captured.value) == "转换测试工具处理失败，请查看任务详情。"


def test_legacy_converter_boundary_accepts_timeout() -> None:
    with pytest.raises(ConversionError) as captured:
        run_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            tool_name="转换测试工具",
            timeout_seconds=0.05,
        )

    assert captured.value.code is ErrorCode.EXTERNAL_TOOL_TIMEOUT


def test_process_runner_accepts_declared_reboot_required_success_code() -> None:
    request = CommandRequest(
        executable=sys.executable,
        arguments=("-c", "import sys; sys.exit(194)"),
        tool_name="安装器",
        success_codes=(0, 194),
    )

    result = ProcessRunner().run(request)

    assert result.returncode == 194


def test_process_runner_merges_explicit_environment_without_shell() -> None:
    request = CommandRequest(
        executable=sys.executable,
        arguments=(
            "-c",
            "import os; print(os.environ['TOOL_DOWNLOAD_ROOT'].encode('unicode_escape').decode())",
        ),
        tool_name="环境测试",
        environment={"TOOL_DOWNLOAD_ROOT": "D:/带 空格/缓存"},
    )

    result = ProcessRunner().run(request)

    assert result.stdout.strip() == "D:/\\u5e26 \\u7a7a\\u683c/\\u7f13\\u5b58"


def test_stop_process_survives_wait_timeout_after_kill() -> None:
    class StubProcess:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def poll(self) -> int | None:
            return None

        def terminate(self) -> None:
            self.actions.append("terminate")

        def kill(self) -> None:
            self.actions.append("kill")

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired(cmd="stub", timeout=timeout)

    stub = cast("subprocess.Popen[str]", StubProcess())

    ProcessRunner._stop_process(stub)

    assert stub.actions == ["terminate", "kill"]
