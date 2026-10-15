import tempfile
import unittest
from pathlib import Path

from infrastructure.database import migrations as migration_module
from tools.release_resources import (
    ReleaseResourceError,
    discover_sql_migrations,
    verify_packaged_sql_migrations,
)


class SqlMigrationReleaseResourceTests(unittest.TestCase):
    def test_project_source_migrations_are_discoverable(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "infrastructure"
            / "database"
            / "sql_migrations"
        )

        discovered = discover_sql_migrations(source)

        self.assertGreater(len(discovered), 0)
        self.assertEqual(
            [path.name for path in discovered],
            sorted(path.name for path in source.glob("*.sql")),
        )

    def test_runtime_migration_path_is_module_relative(self):
        self.assertEqual(
            migration_module.DEFAULT_MIGRATIONS_PATH,
            Path(migration_module.__file__).with_name("sql_migrations"),
        )

    def test_discovery_includes_all_sql_files_in_filename_order(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")
            (source / "notes.txt").write_text("ignored", encoding="utf-8")
            (source / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")

            discovered = discover_sql_migrations(source)

        self.assertEqual(
            [path.name for path in discovered],
            ["0001_first.sql", "0002_second.sql"],
        )

    def test_discovery_rejects_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"

            with self.assertRaisesRegex(ReleaseResourceError, "does not exist"):
                discover_sql_migrations(missing)

    def test_discovery_rejects_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ReleaseResourceError, "No SQL migration"):
                discover_sql_migrations(Path(directory))

    def test_verification_accepts_matching_packaged_migrations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            packaged = root / "packaged"
            source.mkdir()
            packaged.mkdir()
            for name, script in (
                ("0002_second.sql", "SELECT 2;"),
                ("0001_first.sql", "SELECT 1;"),
            ):
                (source / name).write_text(script, encoding="utf-8")
                (packaged / name).write_text(script, encoding="utf-8")

            verified = verify_packaged_sql_migrations(source, packaged)

        self.assertEqual(
            [path.name for path in verified],
            ["0001_first.sql", "0002_second.sql"],
        )

    def test_verification_rejects_missing_packaged_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")

            with self.assertRaisesRegex(
                ReleaseResourceError, "Packaged SQL migration directory"
            ):
                verify_packaged_sql_migrations(source, root / "missing")

    def test_verification_rejects_missing_packaged_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            packaged = root / "packaged"
            source.mkdir()
            packaged.mkdir()
            (source / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")

            with self.assertRaisesRegex(ReleaseResourceError, "0001_first.sql"):
                verify_packaged_sql_migrations(source, packaged)

    def test_verification_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            packaged = root / "packaged"
            source.mkdir()
            packaged.mkdir()
            (source / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
            (packaged / "0001_first.sql").write_text(
                "SELECT 2;", encoding="utf-8"
            )

            with self.assertRaisesRegex(ReleaseResourceError, "hash"):
                verify_packaged_sql_migrations(source, packaged)

    def test_verification_rejects_unexpected_packaged_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            packaged = root / "packaged"
            source.mkdir()
            packaged.mkdir()
            (source / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
            (packaged / "0001_first.sql").write_text(
                "SELECT 1;", encoding="utf-8"
            )
            (packaged / "9999_stale.sql").write_text(
                "SELECT 9999;", encoding="utf-8"
            )

            with self.assertRaisesRegex(ReleaseResourceError, "9999_stale.sql"):
                verify_packaged_sql_migrations(source, packaged)


if __name__ == "__main__":
    unittest.main()
