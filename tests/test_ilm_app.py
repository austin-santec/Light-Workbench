import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt5.QtCore import QEventLoop, QObject, QTimer, Qt, pyqtSignal
from PyQt5.QtTest import QTest

from application.coc_workflow import CocRunOption
from app_info import APP_NAME, APP_TAGLINE, APP_VERSION
from domain.coc_preparation import CocSourceRun, prepare_coc
from domain.models import ConnectionState, DeviceCategory, DeviceInfo
from ilm_app import (
    AboutDialog,
    CompletedReplacementDialog,
    DEFAULT_PART_LOOKUP_ROOT,
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

    def find_devices(self):
        return [(0, "OP815", "FAKE-123")]

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


class DarkReferenceMeter(ReferenceMeter):
    instances = []

    def measure_reference_wavelengths(self):
        self.__class__.reference_measurements += 1
        return {1310: -45.23, 1550: -41.0}


class ReferenceSwitch:
    instances = []

    def __init__(self, **_kwargs):
        self.connected = False
        self.closed = False
        self.__class__.instances.append(self)

    def connect(self):
        self.connected = True

    def configured_channel_count(self):
        return 48

    def set_channel(self, channel):
        return channel

    def close(self):
        self.connected = False
        self.closed = True


class FakePartNumberLookupController(QObject):
    succeeded = pyqtSignal(int, str, str)
    failed = pyqtSignal(int, str, str, str)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.was_closed = False

    def start(self, serial, lookup_root):
        request_id = len(self.requests) + 1
        self.requests.append((request_id, serial, Path(lookup_root)))
        return request_id

    def close(self):
        self.was_closed = True


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_loads_saved_limit_and_run_number_from_companion_json(self):
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
            self.assertEqual(window.metadata_labels["Run number"].text(), "1")
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

    def test_main_window_close_is_rejected_when_hardware_shutdown_times_out(self):
        window = MainWindow()
        hardware_controller = MagicMock()
        hardware_controller.is_active = True
        hardware_controller.stop_and_wait.return_value = False
        window.hardware_controller = hardware_controller

        close_event = QCloseEvent()
        with patch("ilm_app.QMessageBox.warning"):
            window.closeEvent(close_event)

        self.assertFalse(close_event.isAccepted())
        hardware_controller.stop_and_wait.assert_called_once_with()
        window.deleteLater()

    def test_about_dialog_displays_branding_version_and_tagline(self):
        dialog = AboutDialog()

        self.assertEqual(dialog.windowTitle(), "About %s" % APP_NAME)
        self.assertIn("Version: %s" % APP_VERSION, dialog.about_view.toPlainText())
        self.assertEqual(dialog.tagline_label.text(), APP_TAGLINE)
        dialog.close()

    def test_connected_hardware_panel_displays_transient_identity(self):
        window = MainWindow()
        window.show()
        QApplication.processEvents()

        self.assertIsNot(
            window.hardware_status_panel.parentWidget(),
            window.start_hardware_button.parentWidget(),
        )
        self.assertLessEqual(
            window.hardware_status_panel.geometry().right(),
            window.open_csv_button.geometry().left(),
        )
        self.assertTrue(window.hardware_status_panel.laser_source_status.isHidden())
        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.POWER_METER,
                manufacturer="Santec",
                model="OP815",
                serial_number="METER-123",
                state=ConnectionState.CONNECTED,
            )
        )
        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.OPTICAL_SWITCH,
                manufacturer="Santec",
                model="OSX-150",
                serial_number="SWITCH-456",
                raw_identity="SANTEC,OSX-150,SWITCH-456,03.01.02",
                resource_address="USB0::SWITCH::INSTR",
                transport_details="SCPI write ending: CRLF",
                state=ConnectionState.CONNECTED,
            )
        )

        self.assertIn("Connected", window.hardware_status_panel.power_meter_status.text())
        self.assertIn("OP815", window.hardware_status_panel.power_meter_status.text())
        self.assertIn("SWITCH-456", window.hardware_status_panel.optical_switch_status.text())
        self.assertIn("#22c55e", window.hardware_status_panel.optical_switch_status.styleSheet())
        self.assertIn(
            "SCPI write ending: CRLF",
            window.hardware_status_panel.optical_switch_status.toolTip(),
        )
        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.POWER_METER,
                manufacturer="Santec",
                model="OP815",
                serial_number="METER-123",
                state=ConnectionState.IN_USE,
            )
        )
        self.assertIn("In use", window.hardware_status_panel.power_meter_status.text())
        self.assertIn(
            "#60a5fa",
            window.hardware_status_panel.power_meter_status.styleSheet(),
        )
        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.OPTICAL_SWITCH,
                manufacturer="Santec",
                model="OSX-150",
                serial_number="SWITCH-456",
                firmware_version="03.00.85",
                configured_channel_count=0,
                failure_stage="configuration",
                failed_command="CFG:SWT:END?",
                raw_response="0",
                error="The switch has no usable channel configuration.",
                state=ConnectionState.ERROR,
            )
        )
        switch_status = window.hardware_status_panel.optical_switch_status
        self.assertIn("Configuration error", switch_status.text())
        self.assertIn("0 channels", switch_status.text())
        self.assertIn("CFG:SWT:END?", switch_status.toolTip())
        self.assertIn("Response: 0", switch_status.toolTip())
        window.close()

    def test_connected_supported_switch_autofills_main_board_and_part_number(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)
        window.hardware_switch_serial.setText("OPERATOR-SWITCH-SERIAL")

        for index, model in enumerate(("OSX-100", "OSX-150"), start=1):
            serial = "SN%d" % index
            window._hardware_device_status_changed(
                DeviceInfo(
                    category=DeviceCategory.OPTICAL_SWITCH,
                    model=model,
                    serial_number=serial,
                    state=ConnectionState.CONNECTED,
                )
            )
            request_id, requested_serial, _root = lookup.requests[-1]
            expected_serial = str(index)
            self.assertEqual(requested_serial, expected_serial)
            self.assertEqual(window.hardware_main_board_serial.text(), expected_serial)
            self.assertEqual(
                window.hardware_switch_serial.text(),
                "OPERATOR-SWITCH-SERIAL",
            )

            part_number = "%s-PART" % model
            lookup.succeeded.emit(request_id, expected_serial, part_number)
            self.assertEqual(window.hardware_part_number.currentText(), part_number)

        window.close()

    def test_real_automatic_lookup_reads_folder_without_creating_run_files(self):
        with tempfile.TemporaryDirectory() as directory:
            lookup_root = Path(directory)
            (lookup_root / "SN31415_OSX-150-PART").mkdir()
            original_entries = sorted(path.name for path in lookup_root.iterdir())
            with patch("ilm_app.DEFAULT_PART_LOOKUP_ROOT", lookup_root):
                window = MainWindow()
                lookup_finished = QEventLoop()
                window.part_lookup_controller.succeeded.connect(
                    lambda *_values: lookup_finished.quit()
                )
                QTimer.singleShot(3000, lookup_finished.quit)

                window._hardware_device_status_changed(
                    DeviceInfo(
                        category=DeviceCategory.OPTICAL_SWITCH,
                        model="OSX-150",
                        serial_number="31415",
                        state=ConnectionState.CONNECTED,
                    )
                )
                lookup_finished.exec_()
                self.application.processEvents()

                self.assertEqual(
                    window.hardware_part_number.currentText(),
                    "OSX-150-PART",
                )
                self.assertIsNone(window.run_data)
                self.assertIsNone(window.run_recorder)
                self.assertEqual(
                    sorted(path.name for path in lookup_root.iterdir()),
                    original_entries,
                )
                window.close()

    def test_switch_autofill_ignores_nonconnected_and_empty_identity_events(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)

        for state in (
            ConnectionState.CONNECTING,
            ConnectionState.IN_USE,
            ConnectionState.DISCONNECTED,
            ConnectionState.ERROR,
        ):
            window._hardware_device_status_changed(
                DeviceInfo(
                    category=DeviceCategory.OPTICAL_SWITCH,
                    model="OSX-150",
                    serial_number="12345",
                    state=state,
                )
            )
        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.OPTICAL_SWITCH,
                model="OSX-150",
                serial_number="",
                state=ConnectionState.CONNECTED,
            )
        )

        self.assertEqual(lookup.requests, [])
        self.assertEqual(window.hardware_main_board_serial.text(), "")
        window.close()

    def test_switch_autofill_avoids_duplicate_and_lease_release_lookups(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)
        connected = DeviceInfo(
            category=DeviceCategory.OPTICAL_SWITCH,
            model="OSX-150",
            serial_number="12345",
            state=ConnectionState.CONNECTED,
        )

        window._hardware_device_status_changed(connected)
        window._hardware_device_status_changed(connected)
        window._hardware_device_status_changed(
            connected.with_state(ConnectionState.IN_USE)
        )
        window._hardware_device_status_changed(connected)
        self.assertEqual(len(lookup.requests), 1)

        window._hardware_device_status_changed(
            connected.with_state(ConnectionState.DISCONNECTED)
        )
        window._hardware_device_status_changed(connected)
        self.assertEqual(len(lookup.requests), 2)
        window.close()

    def test_switch_autofill_preserves_existing_part_for_same_serial(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)
        window.hardware_main_board_serial.setText("SN12345")
        window.hardware_part_number.setCurrentText("MANUAL-PART")

        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.OPTICAL_SWITCH,
                model="OSX-150",
                serial_number="12345",
                state=ConnectionState.CONNECTED,
            )
        )

        self.assertEqual(lookup.requests, [])
        self.assertEqual(window.hardware_part_number.currentText(), "MANUAL-PART")
        window.close()

    def test_changed_switch_serial_clears_stale_part_and_ignores_old_result(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)
        window.hardware_main_board_serial.setText("OLD")
        window.hardware_part_number.setCurrentText("OLD-PART")

        for serial in ("10001", "10002"):
            window._hardware_device_status_changed(
                DeviceInfo(
                    category=DeviceCategory.OPTICAL_SWITCH,
                    model="OSX-100",
                    serial_number=serial,
                    state=ConnectionState.CONNECTED,
                )
            )

        self.assertEqual(window.hardware_main_board_serial.text(), "10002")
        self.assertEqual(window.hardware_part_number.currentText(), "")
        lookup.succeeded.emit(1, "10001", "STALE-PART")
        self.assertEqual(window.hardware_part_number.currentText(), "")
        lookup.succeeded.emit(2, "10002", "CURRENT-PART")
        self.assertEqual(window.hardware_part_number.currentText(), "CURRENT-PART")
        window.close()

    def test_automatic_lookup_failure_keeps_serial_and_manual_entry_available(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)
        window._hardware_device_status_changed(
            DeviceInfo(
                category=DeviceCategory.OPTICAL_SWITCH,
                model="OSX-150",
                serial_number="24680",
                state=ConnectionState.CONNECTED,
            )
        )

        lookup.failed.emit(
            1,
            "24680",
            "no_matching_serial",
            "No matching folder was found.",
        )

        self.assertEqual(window.hardware_main_board_serial.text(), "24680")
        self.assertEqual(window.hardware_part_number.currentText(), "")
        self.assertTrue(window.hardware_part_number.isEditable())
        self.assertIn(
            "Connected",
            window.hardware_status_panel.optical_switch_status.text(),
        )
        self.assertIn("lookup failed", window.statusBar().currentMessage())
        window.close()

    def test_switch_autofill_does_not_replace_loaded_or_active_run_metadata(self):
        for run_is_active in (False, True):
            with self.subTest(run_is_active=run_is_active):
                lookup = FakePartNumberLookupController()
                window = MainWindow(part_lookup_controller=lookup)
                window.hardware_main_board_serial.setText("SAVED")
                window.hardware_part_number.setCurrentText("SAVED-PART")
                if run_is_active:
                    window.hardware_controller.worker = object()
                else:
                    window.run_data = RunData(
                        Path("saved.csv"),
                        [],
                        {
                            "Main board serial": "SAVED",
                            "Part number": "SAVED-PART",
                        },
                    )

                window._hardware_device_status_changed(
                    DeviceInfo(
                        category=DeviceCategory.OPTICAL_SWITCH,
                        model="OSX-150",
                        serial_number="NEW-SERIAL",
                        state=ConnectionState.CONNECTED,
                    )
                )

                self.assertEqual(window.hardware_main_board_serial.text(), "SAVED")
                self.assertEqual(window.hardware_part_number.currentText(), "SAVED-PART")
                self.assertEqual(lookup.requests, [])
                window.hardware_controller.worker = None
                window.close()

    def test_manual_part_lookup_uses_exporter_and_updates_loaded_metadata(self):
        lookup = FakePartNumberLookupController()
        window = MainWindow(part_lookup_controller=lookup)
        window.run_data = RunData(Path("saved.csv"), [], {})
        window.hardware_main_board_serial.setText("SN13579")
        window.coc_exporter.find_part_number = MagicMock(return_value="MANUAL-PART")

        window.lookup_part_number()

        window.coc_exporter.find_part_number.assert_called_once_with(
            "SN13579",
            str(DEFAULT_PART_LOOKUP_ROOT),
        )
        self.assertEqual(window.hardware_part_number.currentText(), "MANUAL-PART")
        self.assertEqual(window.run_data.metadata["Part number"], "MANUAL-PART")
        window.close()

    def test_completed_replacement_dialog_prefills_recommendations(self):
        dialog = CompletedReplacementDialog(
            recommendations=[
                {
                    "current_physical_port": 10,
                    "candidate_physical_port": 49,
                }
            ]
        )

        self.assertEqual(dialog.table.columnCount(), 2)
        self.assertEqual(
            [dialog.table.horizontalHeaderItem(i).text() for i in range(2)],
            ["Current Port", "Replacement Port"],
        )
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(dialog.table.cellWidget(0, 0).value(), 10)
        self.assertEqual(dialog.table.cellWidget(0, 1).value(), 49)
        dialog.close()

    def test_completed_replacement_dialog_records_reason_operator_and_history(self):
        dialog = CompletedReplacementDialog(operator="DA")
        dialog.table.cellWidget(0, 0).setValue(14)
        dialog.table.cellWidget(0, 1).setValue(41)
        dialog.reason_edit.setText("High insertion loss")
        dialog.operator_edit.setText("DA")

        dialog.accept_records()

        self.assertEqual(len(dialog.history), 1)
        self.assertEqual(dialog.history[0]["current_port"], 14)
        self.assertEqual(dialog.history[0]["replacement_port"], 41)
        self.assertEqual(dialog.history[0]["reason"], "High insertion loss")
        self.assertEqual(dialog.history[0]["operator"], "DA")
        self.assertEqual(dialog.records[0]["replacement_port"], 41)
        dialog.close()

    def test_completed_replacement_dialog_preserves_replacement_chain(self):
        dialog = CompletedReplacementDialog(
            history=[
                {
                    "event_id": "first",
                    "event_type": "replacement_recorded",
                    "current_port": 14,
                    "replacement_port": 41,
                    "reason": "High loss",
                    "operator": "DA",
                    "recorded_at_utc": "2026-10-06T21:32:18Z",
                }
            ],
            operator="JS",
        )
        dialog.table.selectRow(0)
        dialog.replace_again()
        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertEqual(dialog.table.cellWidget(1, 0).value(), 41)
        dialog.table.selectRow(1)
        dialog.table.cellWidget(1, 1).setValue(43)
        dialog.reason_edit.setText("Replacement port failed")
        dialog.operator_edit.setText("JS")

        dialog.accept_records()

        self.assertEqual(len(dialog.history), 2)
        self.assertEqual(dialog.records[0]["current_port"], 14)
        self.assertEqual(dialog.records[0]["replacement_port"], 43)
        dialog.close()

    def test_copy_replacement_notes_formats_recorded_ports_for_unit_editor(self):
        window = MainWindow()
        window.completed_replacements = [
            {"current_port": 4, "replacement_port": 43},
            {"current_port": 3, "replacement_port": 37},
            {"current_port": 17, "replacement_port": 39},
            {"current_port": 23, "replacement_port": 40},
        ]
        window.refresh_replacement_summary()
        window.copy_replacement_notes()

        self.assertTrue(window.copy_replacement_notes_button.isEnabled())
        self.assertEqual(
            QApplication.clipboard().text(),
            "Port replacements completed:\n"
            "4 \u2192 43\n"
            "3 \u2192 37\n"
            "17 \u2192 39\n"
            "23 \u2192 40",
        )
        window.close()

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
                "Part Number Lookup Folder",
                "COC Template...",
                "Write COC...",
                "Exit",
            ],
        )
        self.assertEqual(
            [action.text() for action in menus["Edit"].actions()],
            ["Keybinds...", "Admin Mode...", "Admin Config..."],
        )
        self.assertEqual(
            [action.text() for action in menus["Tools"].actions()],
            [
                "Switch VISA Address...",
                "Check Dependencies...",
                "Red Light Test...",
                "Live IL Reading...",
                "Power Measurement Diagnostics...",
                "Live Write Mode",
                "Dark Mode",
            ],
        )
        self.assertEqual(
            [action.text() for action in menus["Help"].actions()],
            ["IL Instructions", "Support Logs", "About"],
        )
        self.assertEqual(
            [action.text() for action in window.support_logs_menu.actions()],
            [
                "Open Logs Folder",
                "Export Support Bundle...",
                "Copy Logs Folder Path",
                "Logging Status...",
            ],
        )
        window.close()

    def test_admin_config_is_locked_until_admin_mode(self):
        window = MainWindow()
        self.assertFalse(window.admin_config_action.isEnabled())
        self.assertFalse(window.admin_session.is_active)
        window.close()

    def test_admin_mode_switches_lulu_icon_and_restores_it_on_exit(self):
        class AcceptedAdminDialog:
            password = "lwb"

            def __init__(self, _parent=None):
                pass

            def exec_(self):
                return QDialog.Accepted

        window = MainWindow()
        normal_window_icon = window.windowIcon().pixmap(32, 32).toImage()
        normal_header_icon = window.logo_label.pixmap().toImage()

        with patch("ilm_app.AdminPasswordDialog", AcceptedAdminDialog):
            window.toggle_admin_mode()

        self.assertTrue(window.admin_session.is_active)
        self.assertNotEqual(
            window.windowIcon().pixmap(32, 32).toImage(), normal_window_icon
        )
        self.assertNotEqual(window.logo_label.pixmap().toImage(), normal_header_icon)

        window.toggle_admin_mode()
        self.assertFalse(window.admin_session.is_active)
        self.assertEqual(
            window.windowIcon().pixmap(32, 32).toImage(), normal_window_icon
        )
        self.assertEqual(window.logo_label.pixmap().toImage(), normal_header_icon)
        window.close()

    def test_model_criteria_only_make_formal_failures_red(self):
        window = MainWindow()
        window.run_data = RunData(
            Path("test-run"),
            [
                MeasurementRecord(1, 2.3, 2.3),
                MeasurementRecord(2, 2.6, 2.0),
            ],
            {},
            criteria_snapshot=window.limit_profiles["OSX-150"].as_dict(),
        )
        window.refresh_analysis()
        self.assertEqual(window.metric_labels["optimization"].text(), "1")
        self.assertEqual(window.metric_labels["over_limit"].text(), "1")
        self.assertFalse(window.table.item(0, 0).background().style() != Qt.NoBrush)
        expected_fail = "#5b1f25" if window.dark_mode_enabled else "#ffe1dc"
        self.assertEqual(window.table.item(1, 0).background().color().name(), expected_fail)
        window.close()

    def test_switch_visa_address_setting_is_used_by_new_switches(self):
        window = MainWindow()

        class MemorySettings:
            values = {}

            def setValue(self, key, value):
                self.values[key] = value

            def value(self, key, default=None):
                return self.values.get(key, default)

        window.settings = MemorySettings()
        address = "USB0::0x2428::0xD00D::SWITCH::INSTR"
        with patch("ilm_app.QInputDialog.getText", return_value=(address, True)):
            window.choose_switch_visa_address()
        self.assertEqual(window.settings.values["switch_visa_address"], address)
        with patch("ilm_app.OSX150") as switch_type:
            window.hardware_factory.create_switch()
        switch_type.assert_called_once_with(
            resource_address=address,
            last_known_address="",
            address_observer=window._remember_automatically_detected_switch,
        )
        with patch("ilm_app.QInputDialog.getText", return_value=("", True)):
            window.choose_switch_visa_address()
        self.assertEqual(window.settings.values["switch_visa_address"], "")
        window.close()

    def test_part_number_lookup_folder_opens_fixed_designated_folder(self):
        window = MainWindow()
        with patch(
            "ilm_app.DEFAULT_PART_LOOKUP_ROOT", Path(tempfile.gettempdir())
        ), patch(
            "ilm_app.QDesktopServices.openUrl", return_value=True
        ) as open_url:
            window.open_part_lookup_folder()

        self.assertEqual(
            Path(open_url.call_args.args[0].toLocalFile()),
            Path(tempfile.gettempdir()),
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
            self.assertEqual(
                window.hardware_status_panel.objectName(),
                "connected_hardware_status",
            )
            self.assertIn(
                "QDialog, QMessageBox, QInputDialog, QProgressDialog",
                window.styleSheet(),
            )
            self.assertIn(
                "QDialog, QMessageBox, QInputDialog, QProgressDialog { background: #202124; color: #e8eaed; font-size: 13px; }",
                window.styleSheet(),
            )
            self.assertIn(
                "QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel, QProgressDialog QLabel { color: #e8eaed; font-size: 13px; }",
                window.styleSheet(),
            )
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

    def test_previous_run_comparison_can_be_shown_and_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            unit_directory = Path(directory) / "Unit-17688"
            previous_directory = unit_directory / "Run-1-SW1"
            previous_directory.mkdir(parents=True)
            previous_csv = previous_directory / "Run-1-SW1.csv"
            previous_csv.write_text(
                "channel,1310 IL,1550 IL,,Metadata,Value\n"
                "1,1.5000,1.6000,,Run number,1\n",
                encoding="utf-8",
            )

            window = MainWindow()
            window.unit_directory = unit_directory
            window.unit_record = {
                "runs": [
                    {
                        "run_number": 1,
                        "directory": "Run-1-SW1",
                        "csv_file": "Run-1-SW1.csv",
                    },
                    {
                        "run_number": 2,
                        "directory": "Run-2-SW2",
                        "csv_file": "Run-2-SW2.csv",
                    },
                ]
            }
            window.run_data = RunData(
                unit_directory / "Run-2-SW2",
                [
                    MeasurementRecord(1, 1.7, 1.8),
                    MeasurementRecord(2, 1.9, 2.0),
                ],
                {"Run number": "2"},
            )
            window.refresh_comparison_runs()

            self.assertTrue(window.comparison_run_combo.isEnabled())
            self.assertEqual(window.comparison_run_combo.count(), 2)
            window.comparison_run_combo.setCurrentIndex(1)

            self.assertEqual(window.table.columnCount(), 6)
            self.assertEqual(
                window.table.horizontalHeaderItem(4).text(),
                "Run 1 1310 nm IL (dB)",
            )
            self.assertEqual(window.table.item(0, 4).text(), "1.5000")
            self.assertEqual(window.table.item(1, 4).text(), "-")

            window.comparison_run_combo.setCurrentIndex(0)
            self.assertEqual(window.table.columnCount(), 4)
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

    def test_hardware_setup_fields_use_requested_positions(self):
        window = MainWindow()
        layout = window.hardware_setup_box.layout()

        def position(widget):
            row, column, _row_span, _column_span = layout.getItemPosition(
                layout.indexOf(widget)
            )
            return row, column

        self.assertEqual(position(window.channel_mode_context), (0, 2))
        self.assertEqual(position(window.hardware_main_board_serial), (2, 1))
        self.assertEqual(position(window.hardware_switch_serial), (3, 1))
        self.assertEqual(position(window.hardware_part_number), (3, 3))
        self.assertEqual(position(window.reference_1310_spin), (4, 1))
        self.assertEqual(position(window.hardware_operating_band), (4, 3))
        window.close()

    def test_only_hardware_setup_fonts_are_doubled(self):
        window = MainWindow()
        try:
            expected_size = QApplication.font().pointSizeF() * 1.2
            self.assertAlmostEqual(
                window.hardware_setup_box.font().pointSizeF(),
                expected_size,
            )
            self.assertAlmostEqual(
                window.hardware_main_board_serial.font().pointSizeF(),
                expected_size,
            )
            self.assertAlmostEqual(
                window.lookup_part_number_button.font().pointSizeF(),
                expected_size,
            )
            self.assertEqual(
                window.start_hardware_button.font().pointSizeF(),
                QApplication.font().pointSizeF(),
            )
        finally:
            window.close()

    def test_setup_reference_calculation_does_not_open_live_window_and_disconnects(self):
        ReferenceMeter.instances.clear()
        ReferenceMeter.reference_measurements = 0
        with patch("ilm_app.SantecPowerMeter", ReferenceMeter):
            window = MainWindow()
            try:
                window.hardware_connection_manager.connect_measurement_hardware().result(
                    timeout=2
                )
                QTest.qWait(25)
                QTest.mouseClick(window.calculate_reference_button, Qt.LeftButton)
                QTest.qWait(150)

                self.assertEqual(window.reference_1310_spin.value(), 0.72)
                self.assertEqual(window.reference_1550_spin.value(), 0.28)
                self.assertIsNone(window.reference_progress)
                self.assertEqual(len(ReferenceMeter.instances), 1)
                self.assertEqual(ReferenceMeter.reference_measurements, 1)
                self.assertFalse(ReferenceMeter.instances[0].closed)
                self.assertTrue(window.hardware_connection_manager.measurement_ready)
            finally:
                window.close()

    def test_dark_reference_does_not_authorize_a_production_run(self):
        DarkReferenceMeter.instances.clear()
        DarkReferenceMeter.reference_measurements = 0
        with patch("ilm_app.SantecPowerMeter", DarkReferenceMeter), patch(
            "ilm_app.QMessageBox.critical"
        ) as critical:
            window = MainWindow()
            try:
                window.hardware_connection_manager.connect_measurement_hardware().result(
                    timeout=2
                )
                QTest.qWait(25)
                QTest.mouseClick(window.calculate_reference_button, Qt.LeftButton)
                QTest.qWait(150)

                critical.assert_called_once()
                message = critical.call_args.args[2]
                self.assertIn("1310 nm measured -45.2300 dBm", message)
                self.assertIn("1550 nm measured -41.0000 dBm", message)
                self.assertFalse(window.reference_session.is_valid)
                self.assertFalse(window.start_hardware_button.isEnabled())
                self.assertIsNone(window.reference_progress)
            finally:
                window.close()

    def test_setup_reference_calculation_requires_preconnected_hardware(self):
        class MissingMeter(ReferenceMeter):
            instances = []

            def find_devices(self):
                return []

        with patch("ilm_app.SantecPowerMeter", MissingMeter), patch(
            "ilm_app.QMessageBox.warning"
        ) as warning:
            window = MainWindow()
            try:
                window.calculate_reference()

                warning.assert_called_once()
                self.assertIn("Connect the measurement hardware", warning.call_args.args[2])
                self.assertFalse(window.calculate_reference_button.isEnabled())
                self.assertIsNone(window.reference_progress)
                self.assertIsNone(window.reference_thread)
                self.assertFalse(MissingMeter.instances)
            finally:
                window.close()

    def test_measurement_connection_failure_cleans_up_without_crashing(self):
        class DisconnectedMeter(ReferenceMeter):
            def connect(self):
                raise RuntimeError("No OP815/ILM was detected over USB.")

        DisconnectedMeter.instances.clear()
        with patch("ilm_app.SantecPowerMeter", DisconnectedMeter), patch(
            "ilm_app.QMessageBox.warning"
        ) as warning:
            window = MainWindow()
            try:
                window.hardware_connection_manager.connect_measurement_hardware().result(
                    timeout=2
                )
                QTest.qWait(100)

                warning.assert_called_once()
                self.assertIn("No OP815/ILM", warning.call_args.args[2])
                self.assertIsNone(window.reference_progress)
                self.assertIsNone(window.reference_thread)
                self.assertFalse(window.calculate_reference_button.isEnabled())
                self.assertTrue(DisconnectedMeter.instances[-1].closed)
            finally:
                window.close()

    def test_hardware_connection_menu_and_readiness_gating(self):
        ReferenceMeter.instances.clear()
        ReferenceSwitch.instances.clear()
        with patch("ilm_app.SantecPowerMeter", ReferenceMeter), patch(
            "ilm_app.OSX150", ReferenceSwitch
        ):
            window = MainWindow()
            try:
                self.assertEqual(window.connect_hardware_button.text(), "Connect Hardware...")
                action_texts = [
                    action.text()
                    for action in window.connect_hardware_button.menu().actions()
                    if not action.isSeparator()
                ]
                self.assertEqual(
                    action_texts,
                    [
                        "Connect All Required Hardware",
                        "Connect Measurement Hardware",
                        "Connect Optical Switch",
                        "Disconnect Measurement Hardware",
                        "Disconnect Optical Switch",
                        "Disconnect All Hardware",
                    ],
                )
                self.assertFalse(window.start_hardware_button.isEnabled())
                self.assertFalse(window.calculate_reference_button.isEnabled())

                window.hardware_connection_manager.connect_measurement_hardware().result(
                    timeout=2
                )
                QTest.qWait(25)
                self.assertTrue(window.calculate_reference_button.isEnabled())
                self.assertFalse(window.start_hardware_button.isEnabled())

                window.hardware_connection_manager.connect_switch().result(timeout=2)
                QTest.qWait(25)
                # Start is clickable once hardware is connected so the
                # centralized preflight can explain missing setup/reference
                # requirements instead of silently disabling the action.
                self.assertTrue(window.start_hardware_button.isEnabled())
                window.apply_calculated_reference(-0.04, 0.14)
                self.assertTrue(window.start_hardware_button.isEnabled())
                window.run_data = RunData(
                    Path("test-run"),
                    [MeasurementRecord(1, 1.0, 1.1)],
                    {},
                )
                window._update_hardware_readiness_controls()
                self.assertTrue(window.retest_button.isEnabled())

                window.hardware_connection_manager.disconnect_switch().result(
                    timeout=2
                )
                QTest.qWait(25)
                self.assertFalse(window.start_hardware_button.isEnabled())
                self.assertFalse(window.retest_button.isEnabled())
                self.assertTrue(window.calculate_reference_button.isEnabled())
            finally:
                window.close()

    def test_main_window_close_disconnects_persistent_hardware(self):
        ReferenceMeter.instances.clear()
        ReferenceSwitch.instances.clear()
        with patch("ilm_app.SantecPowerMeter", ReferenceMeter), patch(
            "ilm_app.OSX150", ReferenceSwitch
        ):
            window = MainWindow()
            window.hardware_connection_manager.connect_all().result(timeout=2)
            QTest.qWait(25)

            self.assertTrue(window.hardware_connection_manager.run_ready)
            self.assertTrue(window.close())

            self.assertTrue(ReferenceMeter.instances[-1].closed)
            self.assertTrue(ReferenceSwitch.instances[-1].closed)

    def test_switch_serial_accepts_unrestricted_text(self):
        window = MainWindow()
        serial = "SW-12345678901234567890"
        window.hardware_switch_serial.setText(serial)

        self.assertEqual(window.hardware_switch_serial.text(), serial)
        self.assertEqual(window.metadata_labels["Switch serial"].text(), "-")
        window.close()

    def test_tested_by_field_is_saved_as_hardware_identity_metadata(self):
        window = MainWindow()
        window.hardware_tested_by.setText("AJ")

        self.assertEqual(window.hardware_tested_by.text(), "AJ")
        self.assertEqual(window._current_hardware_identity()["Tested by"], "AJ")
        self.assertIn("Tested by", window.metadata_labels)
        window.close()

    def test_production_reference_fields_are_locked_until_admin_mode(self):
        window = MainWindow()
        try:
            self.assertTrue(window.reference_1310_spin.isReadOnly())
            self.assertTrue(window.reference_1550_spin.isReadOnly())
            self.assertFalse(window.apply_manual_reference_button.isEnabled())
            window.admin_session.authenticate("lwb")
            window._refresh_reference_controls()
            self.assertFalse(window.reference_1310_spin.isReadOnly())
            self.assertFalse(window.reference_1550_spin.isReadOnly())
            self.assertTrue(window.apply_manual_reference_button.isEnabled())
        finally:
            window.close()

    def test_manual_reference_requires_explicit_admin_apply(self):
        window = MainWindow()
        try:
            window.admin_session.authenticate("lwb")
            window._refresh_reference_controls()
            window.reference_1310_spin.setValue(-0.04)
            window.reference_1550_spin.setValue(0.14)
            self.assertFalse(window.reference_session.is_valid)
            window.apply_manual_reference()
            self.assertTrue(window.reference_session.is_valid)
            self.assertEqual(window.reference_session.snapshot.method, "manual_admin")
        finally:
            window.close()

    def test_reference_status_hides_snapshot_id_from_operator(self):
        window = MainWindow()
        try:
            snapshot = window.apply_calculated_reference(-0.04, 0.14)

            self.assertEqual(
                window.reference_status_label.text(),
                "Reference status: Calculated",
            )
            self.assertTrue(snapshot.snapshot_id)
            self.assertNotIn(snapshot.snapshot_id[:8], window.reference_status_label.text())
        finally:
            window.close()

    def test_start_run_uses_separate_metadata_and_reference_warnings(self):
        window = MainWindow()
        window.admin_session.authenticate("lwb")
        metadata_dialog = MagicMock()
        metadata_return = object()
        metadata_continue = object()
        metadata_dialog.addButton.side_effect = [
            metadata_return,
            metadata_continue,
        ]
        metadata_dialog.clickedButton.return_value = metadata_continue

        with patch(
            "ilm_app.QMessageBox",
            return_value=metadata_dialog,
        ):
            self.assertTrue(window.confirm_hardware_setup_complete())

        self.assertEqual(
            metadata_dialog.addButton.call_args_list[1].args[0],
            "Continue Without Metadata",
        )
        window.close()

    def test_normal_operator_cannot_bypass_missing_metadata(self):
        window = MainWindow()
        try:
            with patch("ilm_app.QMessageBox.warning") as warning:
                self.assertFalse(window.confirm_hardware_setup_complete())
            warning.assert_not_called()
        finally:
            window.close()

    def test_start_preflight_blocks_before_controller_or_persistence_side_effects(self):
        window = MainWindow()
        try:
            window.hardware_controller.start = MagicMock()
            with patch("ilm_app.QMessageBox.warning") as warning:
                self.assertFalse(window._authorize_hardware_start())

            warning.assert_called_once()
            message = warning.call_args.args[2]
            self.assertIn("Main board serial", message)
            self.assertIn("Connect the measurement hardware", message)
            window.hardware_controller.start.assert_not_called()
            self.assertIsNone(window.run_data)
            self.assertIsNone(window.run_recorder)
        finally:
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
            self.assertEqual(button.objectName(), "hardware_primary_control")
        for button in (window.write_coc_button, window.copy_raw_data_button):
            self.assertEqual(button.minimumWidth(), 125)
            self.assertEqual(button.maximumWidth(), 125)
            self.assertEqual(button.minimumHeight(), 48)
            self.assertEqual(button.maximumHeight(), 48)
        self.assertIn(
            "QPushButton#hardware_primary_control { padding: 11px 20px; font-size: 16px",
            window.styleSheet(),
        )
        self.assertIn(
            "QPushButton#hardware_primary_control QLabel#button_title { font-size: 16px; }",
            window.styleSheet(),
        )
        self.assertEqual(
            window.continue_hardware_button.title_label.text(), "Live Reading"
        )
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

    def test_information_panels_are_inside_a_vertical_scroll_area(self):
        window = MainWindow()
        try:
            self.assertIs(window.info_scroll_area.widget(), window.info_panel)
            self.assertEqual(
                window.info_scroll_area.verticalScrollBarPolicy(),
                Qt.ScrollBarAsNeeded,
            )
            self.assertEqual(
                window.info_scroll_area.horizontalScrollBarPolicy(),
                Qt.ScrollBarAlwaysOff,
            )
        finally:
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
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Run-1.csv"
            window = MainWindow()
            window.run_data = RunData(path, [], {})
            window.refresh_coc_controls()
            self.assertEqual(window.copy_raw_data_button.text(), "Copy Raw Data...")
            self.assertFalse(window.write_coc_button.isEnabled())
            self.assertFalse(window.copy_raw_data_button.isEnabled())
            self.assertFalse(window.write_coc_action.isEnabled())

            window.run_data.measurements.append(MeasurementRecord(1, 1.0, 1.1))
            window.refresh_coc_controls()
            self.assertFalse(window.write_coc_button.isEnabled())
            self.assertTrue(window.copy_raw_data_button.isEnabled())

            path.write_text("channel,1310 IL,1550 IL\n1,1.0000,1.1000\n", encoding="utf-8")
            window.refresh_coc_controls()
            self.assertTrue(window.write_coc_button.isEnabled())
            self.assertTrue(window.write_coc_action.isEnabled())
            window.close()

    def test_write_coc_uses_persisted_preparation_without_hardware(self):
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "Run-1.csv"
            metadata = {
                "Run number": "1",
                "Main board serial": "MB1",
                "Part number": "OSX-150-1A-001-09-FA-00B-1H",
                "Switch serial": "SW1",
                "Operating band": "O band",
                "Tested by": "AJ",
            }
            criteria = {
                "model": "OSX-150",
                "warning_enabled": True,
                "warning_above_db": 2.25,
                "fail_above_db": 2.5,
            }
            source = CocSourceRun(
                1,
                run_path,
                (
                    MeasurementRecord(1, 2.3, 2.2, 1),
                    MeasurementRecord(2, 0.8, 0.9, 2),
                ),
                metadata,
                criteria,
            )
            result = prepare_coc(source, 1)
            self.assertTrue(result.optimization_recommendations)

            class AcceptedDialog:
                def __init__(self, *_args, **_kwargs):
                    self.preparation_result = result
                    self.base_run = source

                def exec_(self):
                    return QDialog.Accepted

            window = MainWindow()
            window.run_data = RunData(
                run_path,
                list(source.measurements),
                dict(metadata),
                criteria_snapshot=dict(criteria),
            )
            output_path = Path(directory) / "COC OSX-150 MB1.xlsx"
            window.coc_exporter.export = MagicMock(return_value=output_path)

            with patch.object(
                window,
                "_coc_run_options",
                return_value=[CocRunOption(source)],
            ), patch("ilm_app.CocExportDialog", AcceptedDialog), patch.object(
                window,
                "_select_coc_template",
                return_value=Path(directory) / "template.xlsx",
            ), patch.object(
                window,
                "_confirm_coc_optimization",
                return_value=True,
            ) as confirm, patch.object(
                window,
                "_persist_coc_export_metadata",
            ) as persist, patch("ilm_app.QMessageBox.information"):
                window.write_coc()

            window.coc_exporter.export.assert_called_once()
            self.assertEqual(
                window.coc_exporter.export.call_args.kwargs["front_panel_channel_count"],
                1,
            )
            confirm.assert_called_once_with(result)
            persist.assert_called_once()
            self.assertFalse(window.hardware_controller.is_active)
            window.close()

    def test_return_from_optimization_warning_creates_no_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            run_path = Path(directory) / "Run-1.csv"
            metadata = {
                "Run number": "1",
                "Main board serial": "MB1",
                "Part number": "OSX-150-1A-001-09-FA-00B-1H",
                "Switch serial": "SW1",
                "Operating band": "O band",
            }
            criteria = {
                "model": "OSX-150",
                "warning_enabled": True,
                "warning_above_db": 2.25,
                "fail_above_db": 2.5,
            }
            source = CocSourceRun(
                1,
                run_path,
                (
                    MeasurementRecord(1, 2.3, 2.2, 1),
                    MeasurementRecord(2, 0.8, 0.9, 2),
                ),
                metadata,
                criteria,
            )
            result = prepare_coc(source, 1)
            self.assertTrue(result.optimization_recommendations)

            class AcceptedDialog:
                def __init__(self, *_args, **_kwargs):
                    self.preparation_result = result
                    self.base_run = source

                def exec_(self):
                    return QDialog.Accepted

            window = MainWindow()
            window.run_data = RunData(run_path, list(source.measurements), dict(metadata))
            window.coc_exporter.export = MagicMock()

            with patch.object(
                window,
                "_coc_run_options",
                return_value=[CocRunOption(source)],
            ), patch("ilm_app.CocExportDialog", AcceptedDialog), patch.object(
                window,
                "_confirm_coc_optimization",
                return_value=False,
            ):
                window.write_coc()

            window.coc_exporter.export.assert_not_called()
            window.close()

    def test_copy_raw_data_uses_all_written_rows_not_visible_filter(self):
        window = MainWindow()
        window.run_data = RunData(
            Path("test-run"),
            [
                MeasurementRecord(1, 1.23456, 0.5),
                MeasurementRecord(2, 2.5, 2.6),
            ],
            {},
        )
        window.refresh_table()
        window.reading_filter.setCurrentIndex(1)
        self.assertEqual(window.table.rowCount(), 1)

        window.copy_raw_data()

        self.assertEqual(
            QApplication.clipboard().text(),
            "1\t1.2346\t0.5000\n"
            "2\t2.5000\t2.6000",
        )
        window.close()

    def test_copy_raw_data_does_not_replace_clipboard_without_written_rows(self):
        window = MainWindow()
        window.run_data = RunData(Path("test-run"), [], {})
        QApplication.clipboard().setText("keep this")

        with patch("ilm_app.QMessageBox.information") as information:
            window.copy_raw_data()

        self.assertEqual(QApplication.clipboard().text(), "keep this")
        information.assert_called_once()
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

    def test_live_write_mode_is_confirmed_and_updates_the_reading_controls(self):
        window = MainWindow()
        try:
            self.assertTrue(window.live_write_mode_enabled)
            self.assertTrue(window.live_write_mode_action.isChecked())
            self.assertEqual(
                window.continue_hardware_button.title_label.text(), "Live Reading"
            )
            window.live_write_mode_action.trigger()
            self.assertFalse(window.live_write_mode_enabled)
            self.assertEqual(
                window.continue_hardware_button.title_label.text(), "Read IL"
            )
            with patch(
                "ilm_app.QMessageBox.question",
                return_value=QMessageBox.Yes,
            ) as confirm:
                window.live_write_mode_action.trigger()

            confirm.assert_called_once()
            self.assertTrue(window.live_write_mode_enabled)
            self.assertTrue(window.live_write_mode_action.isChecked())
            self.assertEqual(
                window.continue_hardware_button.title_label.text(),
                "Live Reading",
            )
            self.assertTrue(window.write_shortcut.isEnabled())
        finally:
            window.close()

    def test_live_write_mode_keeps_reading_pending_until_write(self):
        window = MainWindow()
        try:
            window.run_data = RunData(Path("test-run"), [], {})
            recorder = MagicMock()
            recorder.attempts = []
            window.run_recorder = recorder
            worker_calls = []
            worker = type("FakeWorker", (), {})()
            worker.write_current = lambda: worker_calls.append("write")
            window.hardware_worker = worker

            with patch(
                "ilm_app.QMessageBox.question",
                return_value=QMessageBox.Yes,
            ):
                window.toggle_live_write_mode(True)

            window.scroll_to_channel = MagicMock()
            window.hardware_operator_required(7, 49)
            self.assertFalse(window.hardware_live_indicator.isHidden())
            self.assertFalse(window.continue_hardware_button.isEnabled())
            window.hardware_reading_ready(7, 49, 1.2, 1.3)

            self.assertFalse(window.hardware_live_indicator.isHidden())
            self.assertEqual(window.run_data.measurements, [])
            self.assertIsNotNone(window.hardware_pending_reading)
            window.scroll_to_channel.assert_not_called()

            window.write_hardware()

            self.assertEqual(
                [(record.channel, record.loss_1310, record.loss_1550)
                 for record in window.run_data.measurements],
                [(7, 1.2, 1.3)],
            )
            recorder.save.assert_called()
            self.assertEqual(worker_calls, ["write"])
            window.scroll_to_channel.assert_called_once_with(7)
        finally:
            window.close()

    def test_negative_reading_stays_visible_but_cannot_be_written(self):
        window = MainWindow()
        try:
            window.run_data = RunData(Path("test-run"), [], {})
            recorder = MagicMock()
            recorder.attempts = []
            window.run_recorder = recorder
            worker_calls = []
            worker = type("FakeWorker", (), {})()
            worker.write_current = lambda: worker_calls.append("write")
            window.hardware_worker = worker

            window.hardware_operator_required(7, 49)
            window.hardware_reading_ready(7, 49, -0.0001, 1.3)

            self.assertIn("Invalid negative loss", window.reading_status_label.text())
            self.assertFalse(window.write_hardware_button.isEnabled())
            with patch("ilm_app.QMessageBox.warning") as warning:
                self.assertFalse(window.write_hardware())

            warning.assert_called_once()
            self.assertEqual(window.run_data.measurements, [])
            self.assertEqual(worker_calls, [])
        finally:
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
        window.toggle_live_write_mode(False)
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
