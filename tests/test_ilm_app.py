import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QEventLoop, QTimer, Qt
from PyQt5.QtTest import QTest

from app_info import APP_NAME, APP_TAGLINE, APP_VERSION
from ilm_app import (
    AboutDialog,
    DEFAULT_RUN_ROOT,
    MainWindow,
    STANDARD_PART_NUMBERS,
    format_channel_summary,
)
from run_data import MeasurementRecord, RunData


class ReferenceMeter:
    instances = []
    reference_measurements = 0

    def __init__(self):
        self.description = "Fake OP815"
        self.connected = False
        self.closed = False
        self.__class__.instances.append(self)

    def connect(self):
        self.connected = True

    def measure_both_wavelengths(self):
        return {1310: 0.724, 1550: 0.276}

    def measure_reference_wavelengths(self):
        self.__class__.reference_measurements += 1
        return self.measure_both_wavelengths()

    def close(self):
        self.connected = False
        self.closed = True


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_loads_saved_limit_and_retest_count_from_companion_json(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "output.csv"
            csv_path.write_text(
                "channel,1310 IL,1550 IL,,Metadata,Value\n"
                "1,2.1000,1.9000,,Mode,Simulation\n",
                encoding="utf-8",
            )
            (Path(directory) / "run.json").write_text(
                json.dumps(
                    {
                        "warning_limit_db": 2.5,
                        "attempts": [
                            {"channel": 1, "retest": False},
                            {"channel": 1, "retest": True},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            window = MainWindow(str(csv_path))

            self.assertEqual(window.limit_spin.value(), 2.5)
            self.assertEqual(window.metadata_labels["Retest attempts"].text(), "1")
            self.assertEqual(window.metric_labels["over_limit"].text(), "0")
            window.close()

    def test_open_csv_starts_in_default_run_folder(self):
        window = MainWindow()
        with patch(
            "ilm_app.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as file_dialog:
            window.open_csv()

        self.assertEqual(file_dialog.call_args.args[2], str(DEFAULT_RUN_ROOT))
        window.close()

    def test_about_dialog_displays_branding_version_and_tagline(self):
        dialog = AboutDialog()

        self.assertEqual(dialog.windowTitle(), "About %s" % APP_NAME)
        self.assertIn("Version: %s" % APP_VERSION, dialog.about_view.toPlainText())
        self.assertEqual(dialog.tagline_label.text(), APP_TAGLINE)
        dialog.close()

    def test_help_menu_contains_about_action(self):
        window = MainWindow()
        menus = {
            action.text(): action.menu() for action in window.menuBar().actions()
        }
        self.assertEqual(
            [action.text() for action in menus["File"].actions()],
            [
                "Open CSV Run...",
                "Data Output Folder",
                "Part Number Lookup Folder...",
                "COC Template...",
                "Write COC...",
                "Exit",
            ],
        )
        self.assertEqual(
            [action.text() for action in menus["Edit"].actions()], ["Keybinds..."]
        )
        self.assertEqual(
            [action.text() for action in menus["Tools"].actions()],
            [
                "Check Dependencies...",
                "Red Light Test...",
                "Live IL Reading...",
                "Dark Mode",
            ],
        )
        self.assertEqual(
            [action.text() for action in menus["Help"].actions()],
            ["IL Instructions", "About"],
        )
        window.close()

    def test_il_instructions_opens_the_bundled_guide(self):
        window = MainWindow()
        with patch(
            "ilm_app.QDesktopServices.openUrl", return_value=True
        ) as open_url:
            window.show_il_instructions()

        opened_path = Path(open_url.call_args.args[0].toLocalFile())
        self.assertEqual(opened_path.name, "ILM_READING_GUIDE.html")
        self.assertTrue(opened_path.is_file())
        window.close()

    def test_dark_mode_is_checkable_and_preserves_red_accent(self):
        window = MainWindow()
        original = window.settings.value("dark_mode", None)
        try:
            window.toggle_dark_mode(True)
            self.assertTrue(window.dark_mode_enabled)
            self.assertTrue(window.dark_mode_action.isChecked())
            self.assertIn("#202124", window.styleSheet())
            self.assertIn("QPushButton { background: #e60013", window.styleSheet())
            self.assertIn(
                "QPushButton:disabled { background: #8b000b",
                window.styleSheet(),
            )

        finally:
            if original is None:
                window.settings.remove("dark_mode")
            else:
                window.settings.setValue("dark_mode", original)
            window.close()

    def test_data_output_folder_opens_default_run_folder(self):
        window = MainWindow()
        with tempfile.TemporaryDirectory() as directory:
            output_root = Path(directory) / "ILM-Reads"
            with patch("ilm_app.DEFAULT_RUN_ROOT", output_root), patch(
                "ilm_app.QDesktopServices.openUrl", return_value=True
            ) as open_url:
                window.open_data_output_folder()

            self.assertTrue(output_root.is_dir())
            opened_url = open_url.call_args.args[0]
            self.assertEqual(Path(opened_url.toLocalFile()), output_root)
        window.close()

    def test_analysis_displays_over_limit_channel_lists(self):
        window = MainWindow()
        window.run_data = RunData(
            Path("test-run"),
            [
                # Channel 1 is over at 1310; channel 2 at 1550; channel 3 at both.
                MeasurementRecord(1, 2.1, 1.0),
                MeasurementRecord(2, 1.0, 2.1),
                MeasurementRecord(3, 2.1, 2.1),
            ],
            {},
        )
        window.refresh_analysis()

        self.assertEqual(window.metric_labels["total"].text(), "3")
        self.assertEqual(window.metric_labels["over_limit"].text(), "3")
        self.assertEqual(window.metric_labels["over_1310"].text(), "2 (1, 3)")
        self.assertEqual(window.metric_labels["over_1550"].text(), "2 (2, 3)")
        self.assertEqual(window.metric_labels["over_both"].text(), "1 (3)")
        window.close()

    def test_table_filter_shows_expected_channels(self):
        window = MainWindow()
        window.run_data = RunData(
            Path("test-run"),
            [
                MeasurementRecord(1, 1.0, 1.0),
                MeasurementRecord(2, 2.1, 1.0),
                MeasurementRecord(3, 1.0, 2.1),
                MeasurementRecord(4, 2.1, 2.1),
            ],
            {},
        )

        def visible_channels():
            return [
                int(window.table.item(row, 0).text())
                for row in range(window.table.rowCount())
            ]

        window.refresh_table()
        self.assertEqual(visible_channels(), [1, 2, 3, 4])

        expected_by_filter = {
            1: [1],
            2: [2, 3, 4],
            3: [2, 4],
            4: [3, 4],
            5: [4],
        }
        for filter_index, expected in expected_by_filter.items():
            window.reading_filter.setCurrentIndex(filter_index)
            self.assertEqual(visible_channels(), expected)

        # A channel being measured remains visible in every filtered view.
        window.hardware_operator_required(6, 54)
        self.assertEqual(visible_channels(), [4, 6])
        window.close()

    def test_select_over_limit_switches_to_any_over_limit_filter(self):
        window = MainWindow()
        window.run_data = RunData(
            Path("test-run"),
            [
                MeasurementRecord(1, 1.0, 1.0),
                MeasurementRecord(2, 2.1, 1.0),
                MeasurementRecord(3, 1.0, 2.1),
            ],
            {},
        )
        window.reading_filter.setCurrentIndex(1)
        window.refresh_table()

        window.select_over_limit()

        self.assertEqual(window.reading_filter.currentIndex(), 2)
        selected_rows = [
            index.row() for index in window.table.selectionModel().selectedRows()
        ]
        self.assertEqual(selected_rows, [0, 1])
        self.assertEqual(
            [window.displayed_records[row].channel for row in selected_rows],
            [2, 3],
        )
        window.close()

    def test_current_readings_identify_their_channel(self):
        window = MainWindow()
        window.run_data = RunData(Path("test-run"), [], {})

        window.hardware_operator_required(7, 49)
        self.assertEqual(window.current_channel_label.text(), "Channel: 7")
        self.assertEqual(window.demo_1310_label.text(), "1310 nm: -")

        window.hardware_reading_ready(7, 49, 1.2, 1.3)
        self.assertEqual(window.current_channel_label.text(), "Channel: 7")
        self.assertEqual(window.demo_1310_label.text(), "1310 nm: 1.2000 dB")
        window.close()

    def test_channel_controls_follow_selected_hardware_mode(self):
        window = MainWindow()

        self.assertTrue(window.hardware_single_channel.isHidden())
        self.assertTrue(window.hardware_channel_ranges.isHidden())
        self.assertFalse(window.manual_channel_order_checkbox.isHidden())

        window.hardware_channel_mode.setCurrentIndex(1)
        self.assertFalse(window.hardware_single_channel.isHidden())
        self.assertTrue(window.hardware_channel_ranges.isHidden())
        self.assertTrue(window.manual_channel_order_checkbox.isHidden())

        window.hardware_channel_mode.setCurrentIndex(2)
        self.assertTrue(window.hardware_single_channel.isHidden())
        self.assertFalse(window.hardware_channel_ranges.isHidden())

        window.hardware_channel_mode.setCurrentIndex(0)
        self.assertTrue(window.hardware_single_channel.isHidden())
        self.assertTrue(window.hardware_channel_ranges.isHidden())
        self.assertFalse(window.manual_channel_order_checkbox.isHidden())
        window.close()

    def test_setup_reference_calculation_does_not_open_live_window_and_disconnects(self):
        ReferenceMeter.instances.clear()
        ReferenceMeter.reference_measurements = 0
        with patch("ilm_app.SantecPowerMeter", ReferenceMeter):
            window = MainWindow()
            try:
                QTest.mouseClick(window.calculate_reference_button, Qt.LeftButton)
                QTest.qWait(150)

                self.assertEqual(window.reference_1310_spin.value(), 0.72)
                self.assertEqual(window.reference_1550_spin.value(), 0.28)
                self.assertIsNone(window.reference_progress)
                self.assertEqual(len(ReferenceMeter.instances), 1)
                self.assertEqual(ReferenceMeter.reference_measurements, 1)
                self.assertTrue(ReferenceMeter.instances[0].closed)
            finally:
                window.close()

    def test_switch_serial_accepts_unrestricted_text(self):
        window = MainWindow()
        serial = "SW-12345678901234567890"
        window.hardware_switch_serial.setText(serial)

        self.assertEqual(window.hardware_switch_serial.text(), serial)
        self.assertEqual(window.metadata_labels["Switch serial"].text(), "-")
        window.close()

    def test_part_number_and_operating_band_controls_support_selection_and_typing(self):
        window = MainWindow()
        try:
            self.assertEqual(
                [
                    window.hardware_part_number.itemText(index)
                    for index in range(window.hardware_part_number.count())
                ],
                STANDARD_PART_NUMBERS,
            )
            self.assertTrue(window.hardware_part_number.isEditable())
            window.hardware_part_number.setEditText("CUSTOM-PART-NUMBER")
            self.assertEqual(
                window.hardware_part_number.currentText(),
                "CUSTOM-PART-NUMBER",
            )
            window.hardware_part_number.setCurrentText(STANDARD_PART_NUMBERS[2])
            self.assertEqual(
                window.hardware_part_number.currentText(),
                STANDARD_PART_NUMBERS[2],
            )
            self.assertFalse(window.hardware_operating_band.isEditable())
            self.assertEqual(
                [
                    window.hardware_operating_band.itemText(index)
                    for index in range(window.hardware_operating_band.count())
                ],
                ["O band", "C band"],
            )
            window.hardware_operating_band.setCurrentText("C band")
            self.assertEqual(window.hardware_operating_band.currentText(), "C band")
        finally:
            window.close()

    def test_current_readings_share_the_top_row_with_hardware_controls(self):
        window = MainWindow()
        group_boxes = {
            box.title(): box for box in window.findChildren(type(window.current_readings_box))
        }

        self.assertEqual(
            group_boxes["Current readings"].geometry().y(),
            group_boxes["Hardware controls"].geometry().y(),
        )
        self.assertEqual(window.start_hardware_button.text(), "Start Run")
        for button in (
            window.start_hardware_button,
            window.stop_hardware_button,
            window.continue_hardware_button,
            window.write_hardware_button,
        ):
            self.assertEqual(button.minimumWidth(), 125)
            self.assertEqual(button.minimumHeight(), 48)
        self.assertEqual(window.continue_hardware_button.title_label.text(), "Read IL")
        self.assertEqual(window.write_hardware_button.title_label.text(), "Write IL")
        self.assertEqual(
            window.continue_hardware_button.shortcut_label.text(),
            "[%s]" % window.continue_shortcut.key().toString(),
        )
        self.assertEqual(
            window.write_hardware_button.shortcut_label.text(),
            "[%s]" % window.write_shortcut.key().toString(),
        )
        self.assertTrue(window.demo_channel_label.isHidden())
        window.close()

    def test_all_buttons_have_a_dark_red_disabled_style(self):
        window = MainWindow()

        self.assertIn("QPushButton { background: #e60013", window.styleSheet())
        self.assertIn(
            "QPushButton:disabled { background: #8b000b",
            window.styleSheet(),
        )
        self.assertFalse(window.stop_hardware_button.isEnabled())
        self.assertFalse(window.continue_hardware_button.isEnabled())
        window.close()

    def test_open_csv_controls_disable_during_a_hardware_run(self):
        window = MainWindow()

        self.assertTrue(window.open_csv_button.isEnabled())
        self.assertTrue(window.open_csv_action.isEnabled())

        window.set_open_csv_available(False)
        self.assertFalse(window.open_csv_button.isEnabled())
        self.assertFalse(window.open_csv_action.isEnabled())

        window.set_open_csv_available(True)
        self.assertTrue(window.open_csv_button.isEnabled())
        self.assertTrue(window.open_csv_action.isEnabled())
        window.close()

    def test_coc_controls_require_at_least_one_written_measurement(self):
        window = MainWindow()
        window.run_data = RunData(Path("test-run"), [], {})
        window.refresh_coc_controls()
        self.assertFalse(window.write_coc_button.isEnabled())
        self.assertFalse(window.write_coc_action.isEnabled())

        window.run_data.measurements.append(MeasurementRecord(1, 1.0, 1.1))
        window.refresh_coc_controls()
        self.assertTrue(window.write_coc_button.isEnabled())
        self.assertTrue(window.write_coc_action.isEnabled())
        window.close()

    def test_measurement_button_shortcuts_update_after_keybind_change(self):
        window = MainWindow()
        class MemorySettings:
            def __init__(self):
                self.values = {"continue_key": "Ctrl+R", "write_key": "Ctrl+W"}

            def value(self, key, default=None):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

        window.settings = MemorySettings()
        window.update_shortcuts()

        self.assertEqual(window.continue_hardware_button.shortcut_label.text(), "[Ctrl+R]")
        self.assertEqual(window.write_hardware_button.shortcut_label.text(), "[Ctrl+W]")
        window.close()

    def test_reference_controls_use_two_decimals_and_point_zero_one_steps(self):
        window = MainWindow()

        for spin, value in (
            (window.reference_1310_spin, 0.00),
            (window.reference_1550_spin, 0.00),
        ):
            self.assertEqual(spin.decimals(), 2)
            self.assertAlmostEqual(spin.singleStep(), 0.01)
            self.assertAlmostEqual(spin.value(), 0.00)
            spin.setValue(value)
            spin.stepUp()
            self.assertAlmostEqual(spin.value(), value + 0.01)
            spin.stepDown()
            self.assertAlmostEqual(spin.value(), value)
        window.close()

    def test_enter_minus_enter_keybind_cycle_does_not_leave_stale_shortcut(self):
        window = MainWindow()

        class MemorySettings:
            def __init__(self):
                self.values = {"continue_key": "Return", "write_key": "+"}

            def value(self, key, default=None):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

        window.settings = MemorySettings()
        window.update_shortcuts()
        window.settings.setValue("continue_key", "-")
        window.update_shortcuts()

        # Let Qt process the deferred deletion before restoring Enter. This
        # is the sequence that previously left a deleted keypad shortcut
        # wrapper behind and crashed on the next update.
        event_loop = QEventLoop()
        QTimer.singleShot(0, event_loop.quit)
        event_loop.exec_()

        window.settings.setValue("continue_key", "Enter")
        window.update_shortcuts()
        self.assertEqual(window.continue_shortcut.key().toString(), "Return")
        self.assertIsNotNone(window.keypad_enter_shortcut)
        window.close()

    def test_header_displays_bundled_company_logo(self):
        window = MainWindow()

        self.assertFalse(window.logo_label.isHidden())
        self.assertFalse(window.logo_label.pixmap().isNull())
        self.assertLessEqual(window.logo_label.pixmap().height(), 52)
        window.close()

    def test_enter_can_read_repeatedly_before_writing(self):
        window = MainWindow()
        window.run_data = RunData(Path("test-run"), [], {})
        calls = []

        worker = type("FakeWorker", (), {})()
        worker.continue_current = lambda: calls.append("continue")
        worker.read_current = lambda: calls.append("read")
        window.hardware_worker = worker

        window.hardware_operator_required(1, 49)
        window.show()
        window.activateWindow()
        self.application.processEvents()

        QTest.keyClick(window, Qt.Key_Return)
        self.application.processEvents()
        self.assertEqual(calls, ["continue"])

        window.hardware_reading_ready(1, 49, 1.0, 1.1)
        self.application.processEvents()
        self.assertTrue(window.continue_hardware_button.isEnabled())

        QTest.keyClick(window, Qt.Key_Return)
        self.application.processEvents()
        window.hardware_reading_ready(1, 49, 1.2, 1.3)
        self.application.processEvents()
        QTest.keyClick(window, Qt.Key_Return)
        self.application.processEvents()

        self.assertEqual(calls, ["continue", "read", "read"])
        window.close()


if __name__ == "__main__":
    unittest.main()
