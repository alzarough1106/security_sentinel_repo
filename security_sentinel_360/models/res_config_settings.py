from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    audit_log_retention_days = fields.Integer(
        string="Audit Log Retention (days)",
        config_parameter="security_sentinel_360.log_retention_days", default=365,
    )
    session_idle_timeout_minutes = fields.Integer(
        string="Idle Session Timeout (minutes)",
        config_parameter="security_sentinel_360.idle_timeout_minutes", default=60,
    )
    notify_new_login_email = fields.Boolean(
        string="Email Alert on New Device/IP Login",
        config_parameter="security_sentinel_360.notify_email", default=True,
    )
    notify_new_login_inbox = fields.Boolean(
        string="Inbox Alert on New Device/IP Login",
        config_parameter="security_sentinel_360.notify_inbox", default=True,
    )