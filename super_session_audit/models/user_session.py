from datetime import timedelta
from odoo import models, fields, api
from odoo.http import root, request


class ResUsersSession(models.Model):
    _name = "res.users.session"
    _description = "User Session"
    _order = "login_date desc"

    name = fields.Char(compute="_compute_name")
    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", index=True, default=lambda self: self.env.company)
    session_token = fields.Char("Session ID", required=True, index=True)
    ip_address = fields.Char("IP Address")
    browser = fields.Char()
    browser_version = fields.Char()
    operating_system = fields.Char()
    device_type = fields.Char()
    login_date = fields.Datetime(default=fields.Datetime.now)
    last_activity = fields.Datetime(default=fields.Datetime.now)
    logout_date = fields.Datetime()
    state = fields.Selection(
        [("active", "Active"), ("closed", "Closed"), ("killed", "Killed")],
        default="active", index=True,
    )
    is_new_device = fields.Boolean()
    audit_log_ids = fields.One2many("audit.log", "session_id", string="Activities")
    audit_count = fields.Integer(compute="_compute_audit_count")

    _sql_constraints = [
        ("session_token_uniq", "unique(session_token)", "A session with this token already exists."),
    ]

    def _compute_name(self):
        for rec in self:
            rec.name = "S%04d" % rec.id if rec.id else "New"

    def _compute_audit_count(self):
        for rec in self:
            rec.audit_count = len(rec.audit_log_ids)

    def action_kill_session(self):
        killed_own_session = False
        for rec in self:
            if rec.state != "active":
                continue
            is_current = bool(request and request.session.sid == rec.session_token)
            if not is_current:
                try:
                    stored_session = root.session_store.get(rec.session_token)
                    root.session_store.delete(stored_session)
                except Exception:
                    pass
            else:
                killed_own_session = True
            rec.write({"state": "killed", "logout_date": fields.Datetime.now()})

        if killed_own_session and request:
            request.session.logout(keep_db=True)
            root.session_store.save(request.session)
            return {"type": "ir.actions.act_url", "url": "/web/login", "target": "self"}
        return True

    def action_view_activities(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": "Session Activities",
            "res_model": "audit.log", "view_mode": "list,form",
            "domain": [("session_id", "=", self.id)],
        }

    def _notify_new_login(self):
        template = self.env.ref("super_session_audit.mail_template_new_session", raise_if_not_found=False)
        if template and self.user_id.email:
            template.sudo().send_mail(self.id, force_send=True)

    @api.model
    def _cron_kill_idle_sessions(self, idle_minutes=60):
        limit = fields.Datetime.now() - timedelta(minutes=idle_minutes)
        idle_sessions = self.sudo().search([("state", "=", "active"), ("last_activity", "<", limit)])
        for session in idle_sessions:
            try:
                stored_session = root.session_store.get(session.session_token)
                root.session_store.delete(stored_session)
            except Exception:
                pass
        idle_sessions.write({"state": "killed", "logout_date": fields.Datetime.now()})

    @api.model
    def _cron_purge_old_sessions(self, retention_days=90):
        limit = fields.Datetime.now() - timedelta(days=retention_days)
        self.sudo().search([("state", "!=", "active"), ("logout_date", "<", limit)]).unlink()

    @api.model
    def _cron_dedupe_recent_sessions(self):
        """Safety net: merge any near-duplicate session rows (same user, IP,
        browser, OS, created within a few seconds of each other) that may
        slip through despite the should_rotate guard in ir_http.py."""
        self.env.cr.execute("""
            SELECT array_agg(id ORDER BY id) as ids
            FROM res_users_session
            WHERE state = 'active'
            GROUP BY user_id, ip_address, browser, operating_system,
                     date_trunc('minute', login_date)
            HAVING COUNT(*) > 1
        """)
        for row in self.env.cr.dictfetchall():
            ids = row["ids"]
            keep_id, *dupe_ids = ids
            self.browse(dupe_ids).unlink()