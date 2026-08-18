# models/audit_rule.py
from odoo import models, fields, api, tools

EXCLUDED_MODELS = {
    "audit.log", "res.users.session", "ir.logging", "bus.bus",
    "mail.message", "mail.tracking.value", "mail.followers",
    "ir.cron", "ir.cron.trigger", "ir.attachment",
    "ir.model.data", "ir.model.fields", "ir.model.fields.selection",
    "ir.model.access", "ir.rule",
}

TECHNICAL_PREFIXES = ("ir.", "bus.", "base_import.", "report.", "web_editor.", "web_tour.")

ALWAYS_INCLUDED = {"ir.ui.view", "ir.module.module"}

# High-cardinality "line"/child models that cascade heavily off a single
# business action (e.g. confirming one Sales Order can create 10-30+ rows
# across sale.order.line, stock.move, stock.move.line, account.move.line).
# These are excluded from audit tracking BY DEFAULT to keep audit.log
# growth manageable -- parent document state changes (sale.order,
# account.move, stock.picking, etc.) remain fully tracked regardless.
# Admins can re-enable any of these per-model via an explicit, active
# Audit Rule (Session & Audit > Audit Rules), which always takes priority
# over this default list -- see resolve_effective_flags() below.
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
        help="This rule was pre-seeded by the module as a recommended "
             "default (e.g. to disable tracking on high-volume line "
             "models). You can freely change its settings above.",
    )
    note = fields.Char(readonly=True)

    _sql_constraints = [("model_uniq", "unique(model_id)", "A rule already exists for this model.")]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Registry-wide clear (Odoo 18 API). This is intentionally coarse:
        # audit.rule writes are rare, admin-only actions, so the small
        # extra invalidation cost across other ormcache-decorated methods
        # is a non-issue in practice, and it matches the pattern used
        # throughout Odoo 18 core (ir_rule.py, ir_default.py, etc.).
        self.env.registry.clear_cache()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    @tools.ormcache("model_name")
    def _get_rule_values(self, model_name):
        """Cached lookup -- avoids a DB search on every single CRUD call.
        Cache is explicitly invalidated on create/write/unlink above."""
        rule = self.sudo().search([("model_name", "=", model_name), ("active", "=", True)], limit=1)
        if not rule:
            return False
        return (rule.log_create, rule.log_write, rule.log_unlink, rule.log_read)

    # ------------------------------------------------------------------
    # Recommended-rules sync (see Part 2 below)
    # ------------------------------------------------------------------
    @api.model
    def _sync_recommended_rules(self):
        """Idempotently pre-seed a visible, toggle-able audit.rule row
        (all logging disabled) for every model in NOISY_LINE_MODELS that
        currently exists in this database. Safe to call repeatedly --
        e.g. after installing Sale/Stock/MRP/Purchase/POS at any point
        after this module, since those models won't exist yet at initial
        install time otherwise."""
        IrModel = self.env["ir.model"].sudo()
        for model_name in NOISY_LINE_MODELS:
            model = IrModel.search([("model", "=", model_name)], limit=1)
            if not model:
                continue  # that app isn't installed in this database
            existing = self.sudo().search([("model_id", "=", model.id)], limit=1)
            if existing:
                continue  # don't overwrite a rule the admin already configured
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

    # An explicit, active audit.rule ALWAYS wins -- whether it's one the
    # admin created manually, or one pre-seeded by _sync_recommended_rules.
    rule_values = env["audit.rule"]._get_rule_values(model_name)
    if rule_values:
        return {"create": rule_values[0], "write": rule_values[1],
                "unlink": rule_values[2], "read": rule_values[3]}

    if model_name in ALWAYS_INCLUDED:
        return {"create": True, "write": True, "unlink": True, "read": False}

    # Fallback safety net: even if _sync_recommended_rules hasn't run yet
    # (e.g. right after installing Stock post-launch, before a manual
    # re-sync), noisy line models default to NOT tracked regardless.
    if model_name in NOISY_LINE_MODELS:
        return None

    if any(model_name.startswith(p) for p in TECHNICAL_PREFIXES):
        return None

    return {"create": True, "write": True, "unlink": True, "read": False}