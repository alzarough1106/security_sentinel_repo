from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    audit_log_retention_days = fields.Integer(
        string="Audit Log Retention (days)",
        config_parameter="super_session_audit.log_retention_days", default=365,
    )
    session_idle_timeout_minutes = fields.Integer(
        string="Idle Session Timeout (minutes)",
        config_parameter="super_session_audit.idle_timeout_minutes", default=60,
    )