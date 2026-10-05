import unittest

from application.reference_session import ReferenceSession
from domain.reference import ReferenceMethod, new_reference_snapshot


class ReferenceTests(unittest.TestCase):
    def test_calculated_snapshot_is_valid_and_serializable(self):
        snapshot = new_reference_snapshot(
            -0.04,
            0.14,
            method=ReferenceMethod.CALCULATED,
            meter_model="OP815",
            meter_serial="METER-1",
        )
        self.assertTrue(snapshot.is_valid)
        self.assertEqual(snapshot.method, "calculated")
        self.assertEqual(snapshot.as_dict()["reference_1310_dbm"], -0.04)

    def test_reference_session_invalidates_and_requires_reauthorization(self):
        session = ReferenceSession()
        snapshot = new_reference_snapshot(
            0.1,
            0.2,
            method=ReferenceMethod.CALCULATED,
        )
        session.apply(snapshot)
        self.assertTrue(session.is_valid)
        session.invalidate("Hardware changed")
        self.assertFalse(session.is_valid)
        self.assertEqual(session.reason, "Hardware changed")

    def test_manual_snapshot_has_distinct_admin_method(self):
        snapshot = new_reference_snapshot(
            -0.04,
            0.14,
            method=ReferenceMethod.MANUAL_ADMIN,
        )
        session = ReferenceSession()
        session.apply(snapshot)
        self.assertTrue(session.is_valid)
        self.assertEqual(session.state, "valid_manual_admin")


if __name__ == "__main__":
    unittest.main()
