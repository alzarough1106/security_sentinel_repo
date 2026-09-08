from odoo import models, fields, api, tools

EXCLUDED_MODELS = {
    "audit.log", "res.users.session", "ir.logging", "bus.bus",
    "mail.message", "mail.tracking.value", "mail.followers",
    "mail.mail", "mail.notification",
    "ir.cron", "ir.cron.trigger", "ir.attachment",
    "ir.model.data", "ir.model.fields", "ir.model.fields.selection",
    "ir.model.access", "ir.rule",
}
TECHNICAL_PREFIXES = ("ir.", "bus.", "base_import.", "report.", "web_editor.", "web_tour.")

ALWAYS_INCLUDED = {"ir.ui.view", "ir.module.module"}

NOISY_LINE_MODELS = {
    "stock.move", "stock.move.line", "stock.quant",
    "account.move.line", "sale.order.line", "purchase.order.line",
    "mrp.workorder", "pos.order.line",
}


class AuditRule(models.Model):
    _name = "audit.rule"
    _description = "Audit Rule"
    _rec_name = "model_name"
    _order = "model_name asc"

    model_id = fields.Many2one("ir.model", string="Model", required=True, ondelete="cascade", index=True)
    model_name = fields.Char(string="Technical Model Name", related="model_id.model", store=True, index=True)
    log_create = fields.Boolean("Log Create", default=True)
    log_write = fields.Boolean("Log Update", default=True)
    log_unlink = fields.Boolean("Log Delete", default=True)
    log_read = fields.Boolean("Log Read", default=False)
    active = fields.Boolean(default=True)
    is_recommended = fields.Boolean(
        string="Recommended Default", readonly=True,
        help="This rule was pre-seeded by the module as a recommended default.",
    )
    note = fields.Char(readonly=True)

    _sql_constraints = [("model_uniq", "unique(model_id)", "A rule already exists for this model.")]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self.clear_caches()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.clear_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self.clear_caches()
        return res

    @tools.ormcache("model_name")
    def _get_rule_values(self, model_name):
        rule = self.sudo().search([("model_name", "=", model_name), ("active", "=", True)], limit=1)
        if not rule:
            return False
        return (rule.log_create, rule.log_write, rule.log_unlink, rule.log_read)

    @api.model
    def _sync_recommended_rules(self):
        IrModel = self.env["ir.model"].sudo()
        for model_name in NOISY_LINE_MODELS:
            model = IrModel.search([("model", "=", model_name)], limit=1)
            if not model:
                continue
            existing = self.sudo().search([("model_id", "=", model.id)], limit=1)
            if existing:
                continue
            self.sudo().create({
                "model_id": model.id,
                "log_create": False, "log_write": False,
                "log_unlink": False, "log_read": False,
                "active": True,
                "is_recommended": True,
                "note": "Disabled by default (high-volume line model). Toggle above to enable.",
            })


def resolve_effective_flags(env, model_name):
    if model_name in EXCLUDED_MODELS:
        return None

    rule_values = env["audit.rule"]._get_rule_values(model_name)
    if rule_values:
        return {"create": rule_values[0], "write": rule_values[1],
                "unlink": rule_values[2], "read": rule_values[3]}

    if model_name in ALWAYS_INCLUDED:
        return {"create": True, "write": True, "unlink": True, "read": False}

    if model_name in NOISY_LINE_MODELS:
        return None

    if any(model_name.startswith(p) for p in TECHNICAL_PREFIXES):
        return None

    return {"create": True, "write": True, "unlink": True, "read": False}