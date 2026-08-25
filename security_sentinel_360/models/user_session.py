from datetime import timedelta
from odoo import models, fields, api, _
from odoo.http import root, request
from markupsafe import Markup
from odoo.tools import str2bool


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

    # ------------------------------------------------------------------
    # New device / new IP notifications
    # ------------------------------------------------------------------
    def _notify_new_login(self):
        """Called when a session is flagged is_new_device=True (new
        browser/OS combo OR a never-seen-before IP address for this user).
        Sends BOTH an email and an in-app Inbox/bell notification."""
        self.ensure_one()
        self._send_new_login_email()
        self._send_new_login_inbox_notification()

    def _send_new_login_email(self):
        """Sends a formatted email using an email template."""
        self.ensure_one()
        param = self.env["ir.config_parameter"].sudo().get_param(
            "security_sentinel_360.notify_email", "True"
        )
        if not str2bool(param, default=True):
            return
        template = self.env.ref(
            "security_sentinel_360.mail_template_new_session", raise_if_not_found=False
        )
        if template and self.user_id.email:
            template.sudo().send_mail(self.id, force_send=True)

    def _send_new_login_inbox_notification(self):
        """Posts an in-app notification directly to the partner thread and
        triggers email notification delivery via Odoo 18 mail routing."""
        self.ensure_one()
        param = self.env["ir.config_parameter"].sudo().get_param(
            "security_sentinel_360.notify_inbox", "True"
        )
        if not str2bool(param, default=True):
            return

        partner = self.user_id.partner_id
        if not partner:
            return

        body = Markup(
            "<p><b>%(title)s</b></p>"
            "<ul>"
            "<li>%(date_label)s: %(date)s</li>"
            "<li>%(ip_label)s: %(ip)s</li>"
            "<li>%(browser_label)s: %(browser)s %(browser_version)s</li>"
            "<li>%(os_label)s: %(os)s</li>"
            "<li>%(device_label)s: %(device)s</li>"
            "</ul>"
            "<p>%(warning)s</p>"
        ) % {
                   "title": _("New login detected on your account"),
                   "date_label": _("Date"),
                   "date": self.login_date,
                   "ip_label": _("IP Address"),
                   "ip": self.ip_address or _("Unknown"),
                   "browser_label": _("Browser"),
                   "browser": self.browser or _("Unknown"),
                   "browser_version": self.browser_version or "",
                   "os_label": _("Operating System"),
                   "os": self.operating_system or _("Unknown"),
                   "device_label": _("Device"),
                   "device": self.device_type or _("Unknown"),
                   "warning": _(
                       "If this wasn't you, open Session & Audit \u2192 Sessions and "
                       "kill this session immediately, then change your password."
                   ),
               }

        partner.sudo().message_notify(
            body=body,
            subject=_("New login detected \u2014 %(browser)s on %(os)s") % {
                "browser": self.browser or _("Unknown"),
                "os": self.operating_system or _("Unknown"),
            },
            partner_ids=partner.ids,
            message_type="user_notification",
            email_layout_xmlid="mail.mail_notification_light",
            author_id=self.env.ref("base.partner_root").id,
        )
