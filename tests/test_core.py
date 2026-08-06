from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_material_preprocessor.converters.video import rename_copy
from ai_material_preprocessor.services.files import safe_component, unique_path


class FileSafetyTests(unittest.TestCase):
    def test_safe_component_removes_windows_invalid_characters(self) -> None:
        self.assertEqual(safe_component('杭州:西湖 / "旅行"'), "杭州_西湖-_-_旅行")

    def test_unique_path_does_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / "sample.md"
            original.write_text("existing", encoding="utf-8")
            self.assertEqual(unique_path(original).name, "sample_2.md")

    def test_rename_copy_preserves_original(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "VID_0001.mp4"
            source.write_bytes(b"sample")
            result = rename_copy(source, root / "output", None, "杭州西湖")
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"sample")
            self.assertTrue(result.exists())
            self.assertIn("杭州西湖", result.name)


if __name__ == "__main__":
    unittest.main()
