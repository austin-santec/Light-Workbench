import tempfile
import unittest
from pathlib import Path

from infrastructure.coc_exporter import FileCocExporter


class FileCocExporterTests(unittest.TestCase):
    def test_part_lookup_stays_behind_exporter_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "SN00123_OSX-150-TEST"
            folder.mkdir()

            exporter = FileCocExporter()
            self.assertEqual(
                exporter.find_part_number("SN00123", directory),
                "OSX-150-TEST",
            )
            self.assertEqual(exporter.normalise_serial("SN00123"), "00123")


if __name__ == "__main__":
    unittest.main()
