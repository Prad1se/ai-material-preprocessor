from pathlib import Path

from PIL import Image

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
