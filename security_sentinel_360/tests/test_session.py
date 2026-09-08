from datetime import timedelta
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestUserSession(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env["res.users"].create({
            "name": "Test Session User", "login": "session_test_user",
            "email": "session_test_user@example.com",
        })
        self.session = self.env["res.users.session"].create({
            "user_id": self.user.id, "session_token": "test-token-123",
            "ip_address": "10.0.0.1", "browser": "Chrome",
            "operating_system": "Linux", "device_type": "PC",
        })

    def test_session_created_active(self):
        self.assertEqual(self.session.state, "active")
        self.assertTrue(self.session.name.startswith("S"))

    def test_kill_session_marks_killed(self):
        self.session.action_kill_session()
        self.assertEqual(self.session.state, "killed")
        self.assertTrue(self.session.logout_date)

    def test_kill_already_killed_session_is_noop(self):
        self.session.action_kill_session()
        logout_first = self.session.logout_date
        self.session.action_kill_session()  # must not error
        self.assertEqual(self.session.logout_date, logout_first)

    def test_idle_session_cron_kills_inactive(self):
        self.session.write({"last_activity": fields.Datetime.now() - timedelta(minutes=120)})
        self.env["res.users.session"]._cron_kill_idle_sessions(idle_minutes=60)
        self.session.invalidate_recordset()
        self.assertEqual(self.session.state, "killed")

    def test_company_id_defaults(self):
        self.assertEqual(self.session.company_id, self.env.company)

    # tests/test_session.py — add this test
    def test_concurrent_session_creation_no_duplicates(self):
        """Simulates the race condition: two near-simultaneous attempts to
        create a session record for the same sid must not produce duplicates."""
        from odoo.addons.security_sentinel_360.models.ir_http import IrHttp
        import psycopg2

        token = "race-condition-test-token"
        SessionModel = self.env["res.users.session"].sudo()

        first = SessionModel.create({"user_id": self.user.id, "session_token": token})

        with self.assertRaises(psycopg2.errors.UniqueViolation):
            with self.env.cr.savepoint():
                SessionModel.create({"user_id": self.user.id, "session_token": token})

        count = SessionModel.search_count([("session_token", "=", token)])
        self.assertEqual(count, 1)