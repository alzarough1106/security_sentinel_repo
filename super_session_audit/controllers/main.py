# models/session_patch.py
from odoo import models
from odoo.http import Session
from odoo import http

_original_logout = Session.logout


def _audit_logout(self, keep_db=False):
    sid = self.sid
    if sid and http.request and http.request.env:
        try:
            http.request.env["res.users.session"].sudo().search([
                ("session_token", "=", sid),
                ("state", "=", "active"),
            ]).write({
                "state": "closed",
                "logout_date": http.request.env.cr.now(),
            })
        except Exception:
            # never block logout because of an audit failure
            pass
    return _original_logout(self, keep_db=keep_db)


Session.logout = _audit_logout