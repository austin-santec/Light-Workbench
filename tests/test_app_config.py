import tempfile
import unittest
from pathlib import Path

from app_config import AppPaths


class AppConfigTests(unittest.TestCase):
    def test_paths_are_injectable_for_tests_and_future_installations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = AppPaths(
                project_root=root,
                run_root=root / "runs",
                part_lookup_root=root / "lookup",
            )

            self.assertEqual(
                paths.coc_template_path,
                root / "Templates" / "OSX-100 Single Mode COC Template 1.xlsx",
            )
            self.assertEqual(paths.assets_root, root / "assets")
            self.assertEqual(paths.instructions_path, root / "ILM_READING_GUIDE.html")


if __name__ == "__main__":
    unittest.main()
