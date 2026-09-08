from odoo import models, fields, http
from odoo.http import Session

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
                "logout_date": fields.Datetime.now(),
            })
        except Exception:
            pass
    return _original_logout(self, keep_db=keep_db)


Session.logout = _audit_logout