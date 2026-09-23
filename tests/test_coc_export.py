import tempfile
import unittest
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from coc_export import export_coc, find_part_number
from run_data import MeasurementRecord


class CocExportTests(unittest.TestCase):
    def make_template(self, directory):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        template = workbook.create_sheet("OSX Template")
        template["B1"] = "Template title"
        template.merge_cells("B4:C4")
        template.merge_cells("D4:E4")
        template["B4"] = "old part"
        template["D4"] = "old serial"
        template["F4"] = date(2020, 1, 1)
        for row in list(range(11, 56)) + list(range(67, 70)):
            template["D%d" % row] = "old 1310"
            template["E%d" % row] = "old 1550"
        path = Path(directory) / "template.xlsx"
        workbook.save(path)
        return path

    def test_exports_partial_readings_to_expected_cells_and_preserves_template(self):
        with tempfile.TemporaryDirectory() as directory:
            template = self.make_template(directory)
            output = export_coc(
                template,
                directory,
                [
                    MeasurementRecord(1, 1.2345, 2.3456),
                    MeasurementRecord(48, 4.5678, 5.6789),
                    MeasurementRecord(49, 9.0, 9.0),
                ],
                "OSX-150-TEST",
                "00123",
                export_date=date(2026, 9, 16),
                tested_by="AJ",
            )
            workbook = load_workbook(output)
            sheet = workbook["OSX Template"]

            self.assertEqual(output.name, "COC OSX-150 00123.xlsx")
            self.assertEqual(sheet["B4"].value, "OSX-150-TEST")
            self.assertEqual(sheet["D4"].value, "00123")
            self.assertEqual(sheet["F4"].value.date(), date(2026, 9, 16))
            self.assertEqual(sheet["G4"].value, "AJ")
            self.assertEqual(sheet["D11"].value, 1.2345)
            self.assertEqual(sheet["E11"].value, 2.3456)
            self.assertIsNone(sheet["D12"].value)
            self.assertEqual(sheet["D69"].value, 4.5678)
            self.assertEqual(sheet["E69"].value, 5.6789)
            self.assertEqual(sheet["B1"].value, "Template title")

    def test_filename_collision_gets_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            template = self.make_template(directory)
            first = export_coc(template, directory, [], "PART", "12345")
            second = export_coc(template, directory, [], "PART", "12345")
            self.assertEqual(first.name, "COC OSX-150 12345.xlsx")
            self.assertEqual(second.name, "COC OSX-150 12345 (2).xlsx")

    def test_bundled_template_graphics_are_preserved(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "Templates"
            / "OSX-100 Single Mode COC Template 1.xlsx"
        )
        with tempfile.TemporaryDirectory() as directory:
            output = export_coc(template, directory, [], "PART", "12345")
            with ZipFile(template) as template_zip, ZipFile(output) as output_zip:
                for name in (
                    "xl/media/image1.png",
                    "xl/media/image2.png",
                    "xl/drawings/drawing1.xml",
                    "xl/drawings/_rels/drawing1.xml.rels",
                ):
                    self.assertIn(name, output_zip.namelist())
                    self.assertEqual(template_zip.read(name), output_zip.read(name))
                sheet_relationships = output_zip.read(
                    "xl/worksheets/_rels/sheet2.xml.rels"
                )
                self.assertIn(b"relationships/drawing", sheet_relationships)
                self.assertIn(b"../drawings/drawing1.xml", sheet_relationships)
                sheet_xml = output_zip.read("xl/worksheets/sheet2.xml")
                self.assertIn(b"<drawing ", sheet_xml)
                self.assertIn(
                    b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"',
                    sheet_xml,
                )
            workbook = load_workbook(output)
            self.assertIn("OSX Template", workbook.sheetnames)
            workbook.close()

    def test_finds_part_number_from_serial_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "SN00123_OSX-150-1A-008-09-FA-00B-1H"
            folder.mkdir()
            self.assertEqual(find_part_number("00123", directory), "OSX-150-1A-008-09-FA-00B-1H")
            self.assertEqual(find_part_number("SN00123", directory), "OSX-150-1A-008-09-FA-00B-1H")


if __name__ == "__main__":
    unittest.main()
