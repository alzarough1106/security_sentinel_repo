from odoo import models, fields, http

try:
    from odoo.http import Session
except ImportError:
    from odoo.http import OpenERPSession as Session

_original_logout = Session.logout


def _audit_logout(self, keep_db=False):
    sid = getattr(self, 'sid', None)
    if sid and http.request and getattr(http.request, 'db', None) and getattr(http.request, 'env', None):
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