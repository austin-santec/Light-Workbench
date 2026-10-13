import tempfile
import unittest
from pathlib import Path

from app_config import AppPaths, default_database_config_path, default_support_log_root


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
                root / "Templates" / "OSX-150 Single Mode COC Template 2 (45max).xlsx",
            )
            self.assertEqual(
                paths.coc_template_path_for_capacity(48),
                root / "Templates" / "OSX-150 Single Mode COC Template 1 (48max).xlsx",
            )
            self.assertEqual(
                paths.coc_template_path_for_profile("OSX-100", "SM", 45),
                root / "Templates" / "OSX-100 Single Mode COC Template 2 (45max).xlsx",
            )
            self.assertEqual(
                paths.coc_template_path_for_profile("OSX-100", "MM", 48),
                root / "Templates" / "OSX-100 Multi Mode COC Template 1 (48max).xlsx",
            )
            with self.assertRaises(ValueError):
                paths.coc_template_path_for_profile("OSX-150", "MM", 45)
            self.assertEqual(paths.assets_root, root / "assets")
            self.assertEqual(paths.instructions_path, root / "ILM_READING_GUIDE.html")

    def test_default_support_logs_use_local_app_data_not_project_or_run_root(self):
        path = default_support_log_root()
        self.assertEqual(path.name, "logs")
        self.assertEqual(path.parent.name, "LightWorkbench")
        self.assertNotIn("ILM-Reads", str(path))

    def test_default_database_settings_use_per_user_config_folder(self):
        path = default_database_config_path()
        self.assertEqual(path.name, "database.ini")
        self.assertEqual(path.parent.name, "config")
        self.assertEqual(path.parent.parent.name, "LightWorkbench")


if __name__ == "__main__":
    unittest.main()
