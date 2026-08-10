from ai_material_preprocessor.errors import ErrorCode, UserFacingError, explain_error


def test_user_facing_error_keeps_technical_detail_out_of_default_message() -> None:
    error = UserFacingError(
        code=ErrorCode.EXTERNAL_TOOL_FAILED,
        user_message="视频处理失败，请检查输入文件是否完整。",
        technical_detail="ffmpeg exited 183: C:/private/source.mp4",
        retryable=True,
    )

    assert str(error) == "视频处理失败，请检查输入文件是否完整。"
    assert error.technical_detail.startswith("ffmpeg exited")
    assert error.retryable is True


def test_unknown_exception_is_normalized_to_safe_actionable_error() -> None:
    result = explain_error(ValueError("secret parser detail"), action="转换文档")

    assert result.code is ErrorCode.UNEXPECTED
    assert result.user_message == "转换文档时遇到意外问题，请重试；若问题持续，请查看历史详情。"
    assert result.technical_detail == "ValueError: secret parser detail"
    assert "secret" not in str(result)
