import unittest

from application.admin_session import AdminSession


class AdminSessionTests(unittest.TestCase):
    def test_password_is_exact_and_session_only(self):
        session = AdminSession()
        self.assertFalse(session.authenticate("LWB"))
        self.assertFalse(session.is_active)
        self.assertTrue(session.authenticate("lwb"))
        self.assertTrue(session.is_active)
        session.exit()
        self.assertFalse(session.is_active)


if __name__ == "__main__":
    unittest.main()
