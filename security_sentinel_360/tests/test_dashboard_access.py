from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDashboardAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user_a = self.env["res.users"].create({
            "name": "User A", "login": "dashboard_user_a", "email": "a@example.com",
        })
        self.user_b = self.env["res.users"].create({
            "name": "User B", "login": "dashboard_user_b", "email": "b@example.com",
        })
        self.env["audit.log"].create({"user_id": self.user_a.id, "method": "create", "res_id": 1, "record_name": "A's record"})
        self.env["audit.log"].create({"user_id": self.user_b.id, "method": "create", "res_id": 2, "record_name": "B's record"})

    def test_regular_user_only_sees_own_logs(self):
        own_logs = self.env["audit.log"].with_user(self.user_a).search_count([])
        self.assertEqual(own_logs, 1)

    def test_manager_sees_all_logs(self):
        manager_group = self.env.ref("security_sentinel_360.group_session_audit_manager")
        self.user_a.write({"groups_id": [(4, manager_group.id)]})
        visible = self.env["audit.log"].with_user(self.user_a).search_count([])
        self.assertGreaterEqual(visible, 2)