"""Read-only, local-folder coverage for model-aware product-log lookup."""

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from infrastructure.coc_export import find_part_number, part_lookup_roots
from infrastructure.coc_exporter import FileCocExporter


class ModelPartNumberLookupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.parent = Path(self.directory.name)
        for model in ("OSX-100", "OSX-150"):
            (self.parent / model).mkdir()

    def add_part(self, model, serial="00123", part_model=None):
        part = "%s-1A-048-09-FA-00B-1H" % (part_model or model)
        folder = self.parent / model / ("SN%s_%s" % (serial, part))
        folder.mkdir()
        return part

    def test_shared_resolution_selects_model_or_both_without_filesystem_io(self):
        with patch.object(Path, "stat", side_effect=AssertionError("Unexpected I/O")):
            self.assertEqual(
                part_lookup_roots("osx_100", self.parent),
                (self.parent / "OSX-100",),
            )
            self.assertEqual(
                part_lookup_roots(None, self.parent),
                (self.parent / "OSX-100", self.parent / "OSX-150"),
            )
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                part_lookup_roots("UNKNOWN", self.parent)

    def test_known_model_uses_only_its_own_folder_and_preserves_serial_zeros(self):
        for model in ("OSX-100", "OSX-150"):
            self.add_part(model)
        exporter = FileCocExporter()
        for model in ("OSX-100", "OSX-150"):
            with self.subTest(model=model):
                self.assertTrue(exporter.find_part_number(
                    "SN00123", switch_model=model, lookup_parent=self.parent
                ).startswith(model + "-"))
                self.assertEqual(
                    exporter.part_lookup_roots(model, self.parent),
                    (self.parent / model,),
                )

    def test_unknown_model_accepts_one_match_across_both_folders(self):
        part = self.add_part("OSX-100")
        self.assertEqual(find_part_number("00123", lookup_parent=self.parent), part)

    def test_known_model_does_not_fall_back_to_other_model(self):
        self.add_part("OSX-100")
        with self.assertRaisesRegex(LookupError, "No matching folder"):
            find_part_number("00123", switch_model="OSX-150", lookup_parent=self.parent)

    def test_unknown_model_rejects_same_serial_across_models(self):
        self.add_part("OSX-100")
        self.add_part("OSX-150")
        with self.assertRaisesRegex(LookupError, "More than one"):
            find_part_number("00123", lookup_parent=self.parent)

    def test_multiple_matches_in_same_model_are_rejected(self):
        self.add_part("OSX-100")
        (self.parent / "OSX-100" / "sn00123_OSX-100-1A-012-OTHER").mkdir()
        with self.assertRaisesRegex(LookupError, "More than one"):
            find_part_number("00123", switch_model="OSX-100", lookup_parent=self.parent)

    def test_unknown_search_cannot_accept_match_when_other_folder_unavailable(self):
        self.add_part("OSX-100")
        (self.parent / "OSX-150").rmdir()
        with self.assertRaisesRegex(FileNotFoundError, "Lookup is incomplete"):
            find_part_number("00123", lookup_parent=self.parent)
        self.assertTrue(find_part_number(
            "00123", switch_model="OSX-100", lookup_parent=self.parent
        ).startswith("OSX-100-"))

    def test_permission_failure_is_not_reported_as_no_match(self):
        with patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")):
            with self.assertRaises(PermissionError):
                find_part_number("00123", lookup_parent=self.parent)

    def test_folder_model_and_part_number_must_agree(self):
        self.add_part("OSX-100", part_model="OSX-150")
        for model in (None, "OSX-100"):
            with self.subTest(model=model):
                with self.assertRaisesRegex(LookupError, "Part-number model mismatch"):
                    find_part_number(
                        "00123", switch_model=model, lookup_parent=self.parent
                    )

    def test_explicit_legacy_root_still_works_and_checks_requested_model(self):
        part = self.add_part("OSX-150")
        root = self.parent / "OSX-150"
        self.assertEqual(find_part_number("00123", root), part)
        with self.assertRaisesRegex(LookupError, "model mismatch"):
            find_part_number("00123", root, switch_model="OSX-100")

    def test_missing_serial_part_number_and_exact_serial_boundary(self):
        with self.assertRaisesRegex(ValueError, "serial number first"):
            find_part_number("", lookup_parent=self.parent)
        (self.parent / "OSX-100" / "SN00123_").mkdir()
        with self.assertRaisesRegex(LookupError, "does not contain a part number"):
            find_part_number("00123", lookup_parent=self.parent)
        self.add_part("OSX-150", serial="001234")
        with self.assertRaisesRegex(LookupError, "No matching folder"):
            find_part_number("00123", switch_model="OSX-150", lookup_parent=self.parent)

    def test_lookup_never_opens_files_or_uses_filesystem_mutators(self):
        part = self.add_part("OSX-100")
        evidence = self.parent / "OSX-100" / ("SN00123_" + part) / "keep.txt"
        evidence.write_text("unchanged", encoding="utf-8")
        before = sorted(str(item.relative_to(self.parent)) for item in self.parent.rglob("*"))
        with ExitStack() as stack:
            for method in (
                "open", "mkdir", "touch", "write_text", "write_bytes", "rename",
                "replace", "unlink", "rmdir", "chmod", "symlink_to", "hardlink_to",
            ):
                stack.enter_context(patch.object(
                    Path, method, side_effect=AssertionError("Lookup must be read-only")
                ))
            stack.enter_context(patch(
                "builtins.open", side_effect=AssertionError("Lookup must not open files")
            ))
            self.assertEqual(find_part_number("00123", lookup_parent=self.parent), part)
            with self.assertRaises(LookupError):
                find_part_number("missing", lookup_parent=self.parent)
        self.assertEqual(evidence.read_text(encoding="utf-8"), "unchanged")
        self.assertEqual(
            sorted(str(item.relative_to(self.parent)) for item in self.parent.rglob("*")),
            before,
        )


if __name__ == "__main__":
    unittest.main()
