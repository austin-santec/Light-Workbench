import unittest

from domain.models import (
    ChannelMode,
    MeasurementRecord,
    OperatingBand,
    ReferenceValues,
    RunIdentity,
    RunState,
    UnitIdentity,
)
from domain.run_data import RunData
from run_data import MeasurementRecord as CompatibilityMeasurementRecord
from run_data import RunData as CompatibilityRunData


class DomainModelTests(unittest.TestCase):
    def test_measurement_record_remains_available_from_legacy_module(self):
        self.assertIs(MeasurementRecord, CompatibilityMeasurementRecord)

    def test_run_data_remains_available_from_legacy_module(self):
        self.assertIs(RunData, CompatibilityRunData)

    def test_reference_values_round_trip_worker_mapping(self):
        values = ReferenceValues.from_mapping({1310: 0.72, 1550: 0.28})

        self.assertEqual(values.as_mapping(), {1310: 0.72, 1550: 0.28})

    def test_unit_and_run_identity_preserve_existing_metadata_names(self):
        metadata = {
            "Main board serial": "17688",
            "Part number": "OSX-150-1A-048",
            "Run number": "2",
            "Switch serial": "SW-123",
            "Operating band": "C band",
            "Tested by": "AJ",
        }

        self.assertEqual(
            UnitIdentity.from_metadata(metadata).as_metadata(),
            {
                "Main board serial": "17688",
                "Part number": "OSX-150-1A-048",
            },
        )
        self.assertEqual(
            RunIdentity.from_metadata(metadata).as_metadata(),
            {
                "Run number": "2",
                "Switch serial": "SW-123",
                "Operating band": "C band",
                "Tested by": "AJ",
            },
        )

    def test_invalid_operating_band_uses_current_default(self):
        identity = RunIdentity.from_metadata({"Operating band": "invalid"})
        self.assertEqual(identity.operating_band, OperatingBand.O_BAND)

    def test_finite_workflow_values_are_explicit(self):
        self.assertEqual(ChannelMode.FULL_CONFIGURED_PASS.value, "Full configured pass")
        self.assertEqual(RunState.READY_TO_WRITE.value, "ready_to_write")


if __name__ == "__main__":
    unittest.main()
