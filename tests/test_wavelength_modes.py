import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PyQt5.QtWidgets import QApplication

from domain.coc_preparation import CocSourceRun, prepare_coc
from domain.diagnostic_analysis import (
    DiagnosticReading,
    MONITORING_METHOD,
    analyze_diagnostic_readings,
)
from domain.models import ConnectionState, DeviceCategory, DeviceInfo, MeasurementRecord
from domain.reference import ReferenceMethod, new_reference_snapshot
from domain.limit_profiles import default_limit_profiles
from domain.reporting import summarize_run
from domain.run_data import RunData
from domain.wavelengths import (
    MM_SOURCE_PROFILE,
    MM_WAVELENGTH_PROFILE,
    SM_SOURCE_PROFILE,
    SM_WAVELENGTH_PROFILE,
    MeasurementClassification,
    measurement_configuration,
)
from infrastructure.csv_run_loader import load_run_csv
from infrastructure.diagnostic_export import export_diagnostic_history
from infrastructure.run_persistence import RunRecorder, load_run_json
from op815_driver import OP815
from application.power_diagnostics_controller import PowerDiagnosticsWorker


class WavelengthConfigurationTests(unittest.TestCase):
    def test_profiles_preserve_order_and_production_eligibility(self):
        self.assertEqual(SM_WAVELENGTH_PROFILE.opm_wavelengths_nm, (1310, 1550))
        self.assertEqual(MM_WAVELENGTH_PROFILE.opm_wavelengths_nm, (850, 1300))
        self.assertTrue(SM_WAVELENGTH_PROFILE.has_approved_limits)
        self.assertTrue(SM_WAVELENGTH_PROFILE.coc_eligible)
        self.assertTrue(MM_WAVELENGTH_PROFILE.has_approved_limits)
        self.assertFalse(MM_WAVELENGTH_PROFILE.coc_eligible)

    def test_selected_mode_is_authoritative_for_new_configurations(self):
        self.assertEqual(
            measurement_configuration("SM", SM_SOURCE_PROFILE).classification,
            MeasurementClassification.NATIVE,
        )
        mm_configuration = measurement_configuration("MM", SM_SOURCE_PROFILE)
        self.assertEqual(mm_configuration.classification, MeasurementClassification.NATIVE)
        self.assertEqual(mm_configuration.source_wavelengths_nm, (850, 1300))
        self.assertEqual(
            measurement_configuration("MM", MM_SOURCE_PROFILE).classification,
            MeasurementClassification.NATIVE,
        )
        self.assertEqual(
            measurement_configuration("SM", MM_SOURCE_PROFILE).classification,
            MeasurementClassification.NATIVE,
        )

    def test_mm_selection_sets_opm_and_assumed_source_wavelengths(self):
        driver = OP815.__new__(OP815)
        configuration = measurement_configuration("MM", SM_SOURCE_PROFILE)
        events = []
        source_calls = []
        state = {"wavelength": 1310}
        driver._trace_callback = events.append
        driver._trace_context = {}
        driver._trace_metadata = {}
        driver.configure_measurement(configuration)
        driver._diagnostic_verification_enabled = False

        def get_wavelength(wavelength, index, count):
            wavelength._obj.value = state["wavelength"]
            index._obj.value = 0
            count._obj.value = 2
            return 1

        driver.get_wavelength = get_wavelength
        driver.set_wavelength = (
            lambda wavelength: state.update(wavelength=wavelength) or 1
        )
        driver.source_on = (
            lambda source_id, enabled: source_calls.append(
                (int(source_id), bool(enabled))
            )
            or 1
        )
        driver.read_power = (
            lambda power: setattr(
                power._obj,
                "value",
                -0.7 if state["wavelength"] == 850 else -0.5,
            )
            or 1
        )

        with patch("op815_driver.time.sleep"):
            readings = driver.measure_both_wavelengths()

        self.assertEqual(readings, {850: -0.7, 1300: -0.5})
        started = [
            event
            for event in events
            if event["event"] == "wavelength_measurement_started"
        ]
        self.assertEqual(
            [event["requested_wavelength_nm"] for event in started],
            [850, 1300],
        )
        completed = [
            event
            for event in events
            if event["event"] == "wavelength_measurement_completed"
        ]
        self.assertEqual(
            [event["nominal_source_wavelength_nm"] for event in completed],
            [850, 1300],
        )
        self.assertIn((0, True), source_calls)
        self.assertIn((1, True), source_calls)

    def test_native_mm_uses_mm_opm_and_source_wavelengths(self):
        driver = OP815.__new__(OP815)
        driver.measurement_configuration = measurement_configuration(
            "MM", MM_SOURCE_PROFILE
        )
        driver._diagnostic_verification_enabled = False
        driver.clear_trace_context = Mock()
        driver.current_wavelength = Mock(return_value=1310)
        driver.turn_all_sources_off = Mock()
        driver._trace = Mock()
        driver._set_wavelength = Mock()
        driver.measure_wavelength = Mock(side_effect=(-0.7, -0.5))

        with patch("op815_driver.time.sleep"):
            readings = driver.measure_both_wavelengths()

        self.assertEqual(readings, {850: -0.7, 1300: -0.5})
        calls = driver.measure_wavelength.call_args_list
        self.assertEqual([call.args[0] for call in calls], [850, 1300])
        self.assertEqual([call.kwargs["source_id"] for call in calls], [0, 1])
        self.assertEqual(
            [call.kwargs["nominal_source_wavelength_nm"] for call in calls],
            [850, 1300],
        )
        self.assertGreaterEqual(driver.turn_all_sources_off.call_count, 2)


class WavelengthPersistenceTests(unittest.TestCase):
    def test_mm_run_round_trips_without_sm_field_names(self):
        configuration = measurement_configuration("MM", SM_SOURCE_PROFILE)
        snapshot = new_reference_snapshot(
            -0.20,
            -0.10,
            method=ReferenceMethod.CALCULATED,
            measurement_configuration=configuration,
        )
        record = MeasurementRecord.from_wavelengths(
            3,
            {850: 0.65, 1300: 0.50},
            physical_port=3,
            reference_snapshot=snapshot.as_dict(),
            wavelength_mode="MM",
            measurement_classification="native",
            source_wavelengths_nm=(850, 1300),
            source_ids=(0, 1),
        )
        metadata = {
            "Wavelength mode": "MM",
            "OPM wavelengths nm": "850,1300",
            "Source wavelengths nm": "850,1300",
            "Source IDs": "0,1",
            "Source profile": "op815-mm",
            "Measurement classification": "native",
        }
        with tempfile.TemporaryDirectory() as directory:
            recorder = RunRecorder(root=directory, metadata=metadata)
            recorder.save([record])
            payload = load_run_json(recorder.json_path)
            loaded = load_run_csv(recorder.csv_path)
            with recorder.csv_path.open(
                newline="", encoding="utf-8"
            ) as stream:
                header = next(csv.reader(stream))

        saved = payload["measurements"][0]
        self.assertEqual(payload["schema_version"], 5)
        self.assertNotIn("loss_1310_db", saved)
        self.assertEqual(saved["losses_by_wavelength"], {"850": 0.65, "1300": 0.5})
        self.assertEqual(header[:3], ["channel", "850 IL", "1300 IL"])
        self.assertEqual(loaded.wavelength_mode, "MM")
        self.assertEqual(loaded.measurements[0].ordered_losses, (0.65, 0.50))
        self.assertEqual(
            loaded.measurements[0].measurement_classification,
            "native",
        )

    def test_legacy_csv_still_defaults_to_native_sm(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.csv"
            path.write_text(
                "channel,1310 IL,1550 IL\n1,0.6000,0.5000\n",
                encoding="utf-8",
            )
            loaded = load_run_csv(path)

        self.assertEqual(loaded.wavelength_mode, "SM")
        self.assertEqual(loaded.opm_wavelengths_nm, (1310, 1550))

    def test_coc_preparation_rejects_mm_source_data(self):
        record = MeasurementRecord.from_wavelengths(
            1,
            {850: 0.6, 1300: 0.5},
            wavelength_mode="MM",
            measurement_classification="native",
            source_wavelengths_nm=(850, 1300),
        )
        source = CocSourceRun(
            1,
            Path("mm.csv"),
            (record,),
            metadata={"Wavelength mode": "MM"},
            criteria={"model": "OSX-150"},
        )

        result = prepare_coc(source, 1)

        self.assertFalse(result.eligible)
        self.assertIn(
            "unsupported_wavelength_mode",
            {issue.code for issue in result.validation_issues},
        )

    def test_mm_data_is_evaluated_with_mm_limits(self):
        record = MeasurementRecord.from_wavelengths(
            1,
            {850: 2.8, 1300: 2.7},
            wavelength_mode="MM",
            measurement_classification="native",
            source_wavelengths_nm=(850, 1300),
        )
        run_data = RunData(
            Path("mm.csv"),
            [record],
            {"Wavelength mode": "MM"},
        )

        analysis = run_data.analysis_with_profile(
            default_limit_profiles()["OSX-150/MM"]
        )
        self.assertEqual(analysis["over_limit"], 1)
        summary = summarize_run(
            [record],
            {"Wavelength mode": "MM"},
            2.5,
        )
        self.assertTrue(summary.limits_evaluated)
        self.assertEqual(summary.over_limit_channel_count, 1)

    def test_mm_diagnostic_analysis_and_export_use_mm_wavelength_labels(self):
        readings = [
            DiagnosticReading(
                reading_number=index,
                timestamp="2026-10-07 12:00:0%d.000" % index,
                method=MONITORING_METHOD,
                channel=1,
                physical_port=1,
                measured_1310=-0.7,
                reference_1310=-0.1,
                insertion_loss_1310=first,
                measured_1550=-0.6,
                reference_1550=-0.1,
                insertion_loss_1550=second,
                wavelength_mode="MM",
                opm_wavelengths_nm=(850, 1300),
                source_wavelengths_nm=(850, 1300),
                measurement_classification="native",
            )
            for index, first, second in ((1, 0.60, 0.50), (2, 0.62, 0.51))
        ]

        analysis = analyze_diagnostic_readings(readings, MONITORING_METHOD)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mm-diagnostic.csv"
            export_diagnostic_history(path, readings)
            with path.open("r", newline="", encoding="utf-8-sig") as stream:
                header = next(csv.reader(stream))

            json_path = Path(directory) / "mm-diagnostic.json"
            export_diagnostic_history(json_path, readings)
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(set(analysis.by_wavelength), {850, 1300})
        self.assertIn("850 IL (dB)", header)
        self.assertIn("1300 IL (dB)", header)
        self.assertNotIn("1310 IL (dB)", header)
        self.assertEqual(
            set(payload["readings"][0]["losses_by_wavelength"]),
            {"850", "1300"},
        )
        self.assertNotIn("insertion_loss_1310", payload["readings"][0])


class WavelengthModeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_mm_selection_updates_operator_labels_without_warning(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            window.mm_mode_radio.setChecked(True)
            self.assertEqual(window.reference_first_label.text(), "850 ref:")
            self.assertEqual(window.reference_second_label.text(), "1300 ref:")
            self.assertFalse(hasattr(window, "wavelength_mode_warning"))
            self.assertEqual(window.reading_filter.itemText(3), "850 nm over limit")
            self.assertEqual(window.reading_filter.itemText(4), "1300 nm over limit")
        finally:
            window.close()

    def test_connected_hardware_does_not_overwrite_manual_mode(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            window._hardware_device_status_changed(
                DeviceInfo(
                    category=DeviceCategory.POWER_METER,
                    model="Future MM ILM",
                    serial_number="MM-001",
                    state=ConnectionState.CONNECTED,
                    source_profile_id="future-mm",
                    source_profile_origin="adapter_defined",
                    source_mode="MM",
                    source_ids=(0, 1),
                    source_wavelengths_nm=(850, 1300),
                )
            )
            self.assertEqual(
                window.measurement_configuration.wavelength_profile.code,
                "SM",
            )

            window.mm_mode_radio.setChecked(True)

            self.assertEqual(
                window.measurement_configuration.classification,
                MeasurementClassification.NATIVE,
            )
            self.assertEqual(window.measurement_configuration.classification, MeasurementClassification.NATIVE)
        finally:
            window.close()

    def test_wavelength_mode_controls_are_in_header_and_stacked(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            window.show()
            self.application.processEvents()
            mode_widget = window.sm_mode_radio.parentWidget()
            self.assertEqual(mode_widget.objectName(), "wavelength_mode_header")
            self.assertIs(window.mm_mode_radio.parentWidget(), mode_widget)
            self.assertIsNot(
                mode_widget,
                window.hardware_setup_box,
            )
            self.assertLess(
                window.sm_mode_radio.geometry().top(),
                window.mm_mode_radio.geometry().top(),
            )
            self.assertLess(
                mode_widget.geometry().right(),
                window.hardware_status_panel.geometry().left(),
            )
            self.assertFalse(hasattr(window, "wavelength_mode_warning"))
        finally:
            window.close()

    def test_warning_indicator_was_removed(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            window.mm_mode_radio.setChecked(True)
            self.assertFalse(hasattr(window, "wavelength_mode_warning"))
        finally:
            window.close()

    def test_mode_change_selects_a_separate_session_reference(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            window.reference_session.apply(
                new_reference_snapshot(
                    -0.1,
                    -0.2,
                    method=ReferenceMethod.CALCULATED,
                    measurement_configuration=window.measurement_configuration,
                )
            )
            window.mm_mode_radio.setChecked(True)

            self.assertFalse(window.reference_session.is_valid)
            self.assertIn("Connect measurement hardware", window.reference_session.reason)
        finally:
            window.close()

    def test_reference_controls_are_in_right_column_panel(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            self.assertIs(
                window.reference_1310_spin.parentWidget(),
                window.reference_first_label.parentWidget(),
            )
            self.assertIs(
                window.reference_1310_spin.parentWidget(),
                window.reference_box,
            )
            self.assertIsNot(
                window.reference_1310_spin.parentWidget(),
                window.hardware_setup_box,
            )
            self.assertIs(
                window.reference_box.parentWidget(),
                window.controls_reference_row,
            )
            self.assertIs(
                window.hardware_controls_box.parentWidget(),
                window.controls_reference_row,
            )
        finally:
            window.close()

    def test_mm_compatibility_completed_reading_reaches_the_main_ui(self):
        from ilm_app import MainWindow

        window = MainWindow()
        try:
            window.mm_mode_radio.setChecked(True)
            window.hardware_reading_ready(1, 1, 0.65, 0.50)

            self.assertEqual(window.demo_1310_label.text(), "850 nm: 0.6500 dB")
            self.assertEqual(window.demo_1550_label.text(), "1300 nm: 0.5000 dB")
            self.assertTrue(window.write_hardware_button.isEnabled())
            self.assertEqual(window.hardware_pending_reading[2:], (0.65, 0.50))
        finally:
            window.close()


class WavelengthAwareDiagnosticWorkerTests(unittest.TestCase):
    def test_mm_diagnostic_worker_calculates_using_850_and_1300(self):
        meter = Mock()
        meter.measure_both_wavelengths.return_value = {850: -0.7, 1300: -0.5}
        configuration = measurement_configuration("MM", SM_SOURCE_PROFILE)
        worker = PowerDiagnosticsWorker(meter, configuration)
        readings = []
        worker.reading_ready.connect(lambda *values: readings.append(values))

        worker.read(-0.1, 0.1)

        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0][0], {850: -0.7, 1300: -0.5})
        self.assertAlmostEqual(readings[0][3], 0.6)
        self.assertAlmostEqual(readings[0][4], 0.6)
        trace = meter.set_trace_context.call_args.kwargs
        self.assertEqual(trace["reference_850_dbm"], -0.1)
        self.assertEqual(trace["reference_1300_dbm"], 0.1)


if __name__ == "__main__":
    unittest.main()
