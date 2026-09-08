from datetime import timedelta
from odoo import models, fields
from odoo.http import request, root
import psycopg2

from .lib import ua_parser


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _dispatch(cls, endpoint):
        cls._enforce_killed_session()
        result = super()._dispatch(endpoint)
        cls._track_session()
        return result

    @classmethod
    def _enforce_killed_session(cls):
        if not (request and request.session.uid and request.session.sid):
            return
        if "res.users.session" not in request.env:
            return

        killed = request.env["res.users.session"].sudo().search([
            ("session_token", "=", request.session.sid), ("state", "=", "killed"),
        ], limit=1)
        if killed:
            request.session.logout(keep_db=True)
            root.session_store.save(request.session)

    @classmethod
    def _track_session(cls):
        if not (request and request.session.uid and request.session.sid):
            return
        if getattr(request.session, "should_rotate", False):
            return

        if "res.users.session" not in request.env:
            return

        SessionModel = request.env["res.users.session"].sudo()
        existing = SessionModel.search([("session_token", "=", request.session.sid)], limit=1)
        if existing:
            if existing.state == "active":
                now = fields.Datetime.now()
                threshold = now - timedelta(seconds=60)
                request.env.cr.execute("""
                    UPDATE res_users_session
                    SET last_activity = %s
                    WHERE id = %s
                      AND (last_activity IS NULL OR last_activity < %s)
                """, (now, existing.id, threshold))
            return
        cls._create_session_record(request.session.uid)

    @classmethod
    def _create_session_record(cls, uid):
        env = request.env
        if "res.users.session" not in env:
            return

        SessionModel = env["res.users.session"].sudo()

        ip = request.httprequest.environ.get("REMOTE_ADDR")
        ua_string = request.httprequest.headers.get("User-Agent", "")
        parsed = ua_parser.parse(ua_string)
        device_type = "Mobile" if parsed.is_mobile else "Tablet" if parsed.is_tablet else "PC"

        user = env["res.users"].sudo().browse(uid)

        is_new_device = not bool(
            SessionModel.search_count([
                ("user_id", "=", uid), ("ip_address", "=", ip),
                ("browser", "=", parsed.browser_family), ("operating_system", "=", parsed.os_family),
            ])
        )

        values = {
            "user_id": uid, "session_token": request.session.sid, "ip_address": ip,
            "browser": parsed.browser_family, "browser_version": parsed.browser_version,
            "operating_system": parsed.os_family, "device_type": device_type,
            "is_new_device": is_new_device,
            "company_id": user.company_id.id,
        }

        try:
            with env.cr.savepoint():
                session = SessionModel.create(values)
        except psycopg2.errors.UniqueViolation:
            session = SessionModel.search([("session_token", "=", request.session.sid)], limit=1)
            if not session:
                return
            return

        if is_new_device:
            session._notify_new_login()