from ai_material_preprocessor.services.markdown_cleaning import clean_markdown
from ai_material_preprocessor.services.markdown_quality import check_quality
from ai_material_preprocessor.services.markdown_splitting import split_markdown
from ai_material_preprocessor.ui.theme import APP_STYLESHEET


def test_document_pipeline_has_separate_clean_quality_and_split_modules(tmp_path) -> None:
    cleaned = clean_markdown("# 标题\n\n\n内容\n", source_suffix=".docx")
    report = check_quality(cleaned, base_dir=tmp_path, max_tokens=100)
    chunks = split_markdown(cleaned, target_tokens=20, max_tokens=40)

    assert "\n\n\n" not in cleaned
    assert report.score == 90
    assert report.issues[0].code == "very_short"
    assert len(chunks) == 1
    assert clean_markdown.__module__.endswith("markdown_cleaning")
    assert check_quality.__module__.endswith("markdown_quality")
    assert split_markdown.__module__.endswith("markdown_splitting")


def test_ui_theme_is_separate_and_keeps_combo_items_readable() -> None:
    assert "QComboBox QAbstractItemView" in APP_STYLESHEET
    assert "selection-color: #171717" in APP_STYLESHEET


def test_preview_controls_have_explicit_light_and_dark_system_safe_colors() -> None:
    assert "QPlainTextEdit, QTreeWidget" in APP_STYLESHEET
    assert "QTabWidget::pane" in APP_STYLESHEET
    assert "QTabBar::tab" in APP_STYLESHEET
    assert "background: #ffffff" in APP_STYLESHEET
    assert "color: #171717" in APP_STYLESHEET
