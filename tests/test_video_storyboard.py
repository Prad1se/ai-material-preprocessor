from pathlib import Path

from PIL import Image, ImageDraw

from ai_material_preprocessor.converters.video import create_contact_sheet


def test_contact_sheet_combines_frames_and_writes_manifest_friendly_image(tmp_path: Path) -> None:
    frames = []
    for index, color in enumerate(("red", "green", "blue", "yellow", "purple"), start=1):
        path = tmp_path / f"frame_{index:03d}.jpg"
        Image.new("RGB", (640, 360), color).save(path)
        frames.append(path)
    output = tmp_path / "contact-sheet.jpg"

    result = create_contact_sheet(frames, output, columns=3, cell_width=240)

    assert result == output
    with Image.open(output) as image:
        assert image.width == 720
        assert image.height == 334


def test_contact_sheet_captions_include_source_name_and_timestamps(
    monkeypatch, tmp_path: Path
) -> None:
    frames = []
    for index in range(2):
        frame = tmp_path / f"frame_{index + 1:03d}.jpg"
        Image.new("RGB", (80, 40), "white").save(frame)
        frames.append(frame)
    labels: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def capture_text(self, xy, text, *args, **kwargs):
        labels.append(str(text))
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", capture_text)

    create_contact_sheet(
        frames,
        tmp_path / "sheet.jpg",
        source_name="旅行.mp4",
        timestamps=(1.25, 65.5),
    )

    assert labels == ["旅行.mp4 · 00:00:01.250", "旅行.mp4 · 00:01:05.500"]
