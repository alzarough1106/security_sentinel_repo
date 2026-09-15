from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAuditLog(TransactionCase):

    def test_create_partner_generates_log(self):
        Log = self.env["audit.log"]
        partner = self.env["res.partner"].create({"name": "Audit Test Partner"})
        log = Log.search([
            ("model_name", "=", "res.partner"), ("res_id", "=", partner.id), ("method", "=", "create"),
        ], limit=1)
        self.assertTrue(log)
        self.assertEqual(log.record_name, "Audit Test Partner")

    def test_write_partner_generates_log_with_diff(self):
        partner = self.env["res.partner"].create({"name": "Before Name"})
        partner.write({"name": "After Name"})
        log = self.env["audit.log"].search([
            ("model_name", "=", "res.partner"), ("res_id", "=", partner.id), ("method", "=", "write"),
        ], order="id desc", limit=1)
        self.assertTrue(log)
        self.assertIn("After Name", log.field_changes)

    def test_unlink_partner_generates_log(self):
        partner = self.env["res.partner"].create({"name": "To Delete"})
        partner_id = partner.id
        partner.unlink()
        log = self.env["audit.log"].search([
            ("model_name", "=", "res.partner"), ("res_id", "=", partner_id), ("method", "=", "unlink"),
        ], limit=1)
        self.assertTrue(log)

    def test_excluded_model_not_logged(self):
        before = self.env["audit.log"].search_count([("model_name", "=", "audit.log")])
        self.env["audit.log"].create_log("res.partner", 999999, "create", {"old": {}, "new": {}}, "Fake")
        after = self.env["audit.log"].search_count([("model_name", "=", "audit.log")])
        self.assertEqual(before, after)

    def test_disabled_rule_stops_logging(self):
        model = self.env["ir.model"].search([("model", "=", "res.partner")], limit=1)
        rule = self.env["audit.rule"].create({
            "model_id": model.id, "log_create": False, "log_write": False, "log_unlink": False,
        })
        try:
            partner = self.env["res.partner"].create({"name": "Should Not Be Logged"})
            log = self.env["audit.log"].search([
                ("model_name", "=", "res.partner"), ("res_id", "=", partner.id), ("method", "=", "create"),
            ])
            self.assertFalse(log)
        finally:
            rule.unlink()