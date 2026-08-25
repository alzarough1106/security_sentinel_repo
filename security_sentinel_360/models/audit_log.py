import json
from odoo import models, fields, api
from odoo.http import request
from datetime import timedelta


class AuditLog(models.Model):
    _name = "audit.log"
    _description = "Audit Log"
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name")
    user_id = fields.Many2one("res.users", required=True, index=True)
    session_id = fields.Many2one("res.users.session", index=True, ondelete="set null")
    company_id = fields.Many2one("res.company", index=True, default=lambda self: self.env.company)
    model_id = fields.Many2one("ir.model", string="Model", index=True)
    model_name = fields.Char(string="Technical Model Name", related="model_id.model", store=True)
    res_id = fields.Integer(index=True)
    record_name = fields.Char()
    method = fields.Selection([
        ("create", "Create"),
        ("write", "Modify"),
        ("unlink", "Delete"),
        ("read", "Read"),
        ("module_install", "Module Install"),
        ("module_uninstall", "Module Uninstall"),
    ], required=True, index=True)
    field_changes = fields.Text("Change Details (JSON)")
    ip_address = fields.Char()

    changes_summary = fields.Html(compute="_compute_changes", sanitize=False)
    changes_detail = fields.Html(compute="_compute_changes", sanitize=False)

    def _compute_name(self):
        for rec in self:
            rec.name = f"{(rec.method or '').title()} — {rec.model_name} #{rec.res_id}"

    def _field_label(self, field_name):
        self.ensure_one()
        if not self.model_name:
            return field_name
        field = self.env["ir.model.fields"].sudo().search(
            [("model", "=", self.model_name), ("name", "=", field_name)], limit=1
        )
        return field.field_description if field else field_name

    def _compute_changes(self):
        for rec in self:
            try:
                data = json.loads(rec.field_changes) if rec.field_changes else {}
            except Exception:
                data = {}
            old = data.get("old", {}) or {}
            new = data.get("new", {}) or {}
            field_names = sorted(set(old.keys()) | set(new.keys()))

            summary_items = []
            detail_rows = []

            if rec.method == "create":
                summary_items.append("<li>Record is <b>Created</b>.</li>")
            elif rec.method == "unlink":
                summary_items.append("<li>Record is <b>Deleted</b>.</li>")
            elif rec.method in ("module_install", "module_uninstall"):
                label = "Installed" if rec.method == "module_install" else "Uninstalled"
                summary_items.append(f"<li>Module is <b>{label}</b>.</li>")
            else:
                for fname in field_names:
                    label = rec._field_label(fname)
                    summary_items.append(f"<li><b>{label}</b> is Changed.</li>")
                    detail_rows.append(
                        f"<tr><td><b>{label}</b></td>"
                        f"<td>{old.get(fname, '')}</td>"
                        f"<td>{new.get(fname, '')}</td></tr>"
                    )

            rec.changes_summary = (
                f"<ul>{''.join(summary_items)}</ul>" if summary_items
                else "<p>No field changes recorded.</p>"
            )
            rec.changes_detail = (
                "<table class='table table-sm table-bordered'>"
                "<thead><tr><th>Field</th><th>Old Value</th><th>New Value</th></tr></thead>"
                f"<tbody>{''.join(detail_rows)}</tbody></table>"
                if detail_rows else "<p>No detailed changes available.</p>"
            )

    def action_open_record(self):
        self.ensure_one()
        if not self.model_name or not self.res_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": self.model_name,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def _get_current_session(self):
        if request and request.session and request.session.sid:
            return self.env["res.users.session"].sudo().search(
                [("session_token", "=", request.session.sid), ("state", "=", "active")], limit=1
            )
        return False

    @api.model
    def create_log(self, model_name, res_id, method, changes=None, record_name=False):
        session = self._get_current_session()
        ip = request.httprequest.environ.get("REMOTE_ADDR") if request else False
        model = self.env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
        try:
            payload = json.dumps(changes, default=str) if changes else False
        except Exception:
            payload = str(changes)
        self.sudo().create({
            "user_id": self.env.uid or SUPERUSER_ID,  # <-- fallback, never NULL
            "session_id": session.id if session else False,
            "model_id": model.id if model else False,
            "res_id": res_id,
            "record_name": record_name,
            "method": method,
            "field_changes": payload,
            "ip_address": ip,
            "company_id": self.env.company.id,
        })

    @api.model
    def _cron_purge_old_logs(self, retention_days=None):
        if retention_days is None:
            retention_days = int(
                self.env["ir.config_parameter"].sudo().get_param("security_sentinel_360.log_retention_days",
                                                                 default=365)
            )
        if retention_days <= 0:
            return  # 0 or negative == keep forever
        limit = fields.Datetime.now() - timedelta(days=retention_days)
        self.sudo().search([("create_date", "<", limit)]).unlink()
