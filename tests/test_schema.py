import unittest

from infrastructure.schema import (
    CURRENT_RUN_SCHEMA_VERSION,
    CURRENT_UNIT_SCHEMA_VERSION,
    migrate_run_payload,
    migrate_unit_payload,
)


class SchemaMigrationTests(unittest.TestCase):
    def test_legacy_run_payload_gets_current_defaults(self):
        payload = migrate_run_payload({"measurements": []})

        self.assertEqual(payload["schema_version"], CURRENT_RUN_SCHEMA_VERSION)
        self.assertEqual(payload["metadata"], {})
        self.assertEqual(payload["switch_test_sessions"], [])
        self.assertEqual(payload["measurement_attempts"], [])

    def test_legacy_attempts_key_is_mapped_to_new_history_key(self):
        legacy = [{"channel": 1, "loss_1310_db": 1.0, "loss_1550_db": 0.9}]

        payload = migrate_run_payload({"attempts": legacy})

        self.assertEqual(payload["measurement_attempts"], legacy)

    def test_legacy_unit_payload_gets_current_defaults(self):
        payload = migrate_unit_payload({})

        self.assertEqual(payload["schema_version"], CURRENT_UNIT_SCHEMA_VERSION)
        self.assertEqual(payload["runs"], [])

    def test_newer_payloads_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "newer"):
            migrate_run_payload({"schema_version": CURRENT_RUN_SCHEMA_VERSION + 1})
        with self.assertRaisesRegex(ValueError, "newer"):
            migrate_unit_payload({"schema_version": CURRENT_UNIT_SCHEMA_VERSION + 1})


if __name__ == "__main__":
    unittest.main()
