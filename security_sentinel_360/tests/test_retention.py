from datetime import timedelta
from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRetention(TransactionCase):

    def test_purge_old_logs(self):
        Log = self.env["audit.log"]
        old_log = Log.create({"user_id": self.env.uid, "method": "create", "res_id": 1, "record_name": "Old"})

        # Force update system field create_date via SQL
        past_date = fields.Datetime.now() - timedelta(days=400)
        self.env.cr.execute(
            "UPDATE audit_log SET create_date = %s WHERE id = %s",
            (past_date, old_log.id)
        )
        old_log.invalidate_recordset(["create_date"])

        Log._cron_purge_old_logs(retention_days=365)
        self.assertFalse(old_log.exists())

    def test_purge_keeps_recent_logs(self):
        Log = self.env["audit.log"]
        recent_log = Log.create({"user_id": self.env.uid, "method": "create", "res_id": 2, "record_name": "Recent"})
        Log._cron_purge_old_logs(retention_days=365)
        self.assertTrue(recent_log.exists())

    def test_purge_zero_retention_keeps_everything(self):
        Log = self.env["audit.log"]
        old_log = Log.create({"user_id": self.env.uid, "method": "create", "res_id": 3, "record_name": "VeryOld"})

        # Force update system field create_date via SQL
        past_date = fields.Datetime.now() - timedelta(days=4000)
        self.env.cr.execute(
            "UPDATE audit_log SET create_date = %s WHERE id = %s",
            (past_date, old_log.id)
        )
        old_log.invalidate_recordset(["create_date"])

        Log._cron_purge_old_logs(retention_days=0)
        self.assertTrue(old_log.exists())