from datetime import timedelta
from odoo import models, fields, api
from odoo.exceptions import AccessError


class AuditDashboard(models.AbstractModel):
    _name = "audit.dashboard"
    _description = "Audit & Session Dashboard Data Provider"

    @api.model
    def get_dashboard_data(self):
        Session = self.env["res.users.session"]
        Log = self.env["audit.log"]

        today = fields.Date.context_today(self)
        since_7d = fields.Datetime.now() - timedelta(days=7)
        since_30d = fields.Datetime.now() - timedelta(days=30)

        try:
            kpis = {
                "active_sessions": Session.search_count([("state", "=", "active")]),
                "killed_sessions": Session.search_count([("state", "=", "killed")]),
                "new_devices_today": Session.search_count([
                    ("is_new_device", "=", True), ("login_date", ">=", f"{today} 00:00:00"),
                ]),
                "logs_today": Log.search_count([("create_date", ">=", f"{today} 00:00:00")]),
                "creates_7d": Log.search_count([("method", "=", "create"), ("create_date", ">=", since_7d)]),
                "writes_7d": Log.search_count([("method", "=", "write"), ("create_date", ">=", since_7d)]),
                "deletes_7d": Log.search_count([("method", "=", "unlink"), ("create_date", ">=", since_7d)]),
            }

            state_rows = Session.read_group([], ["state"], ["state"])
            state_labels_map = dict(Session._fields["state"].selection)
            sessions_by_state = {
                "labels": [state_labels_map.get(r["state"], r["state"]) for r in state_rows],
                "keys": [r["state"] for r in state_rows],
                "data": [r["state_count"] for r in state_rows],
            }

            method_rows = Log.read_group([("create_date", ">=", since_7d)], ["method"], ["method"])
            method_labels_map = dict(Log._fields["method"].selection)
            actions_by_type = {
                "labels": [method_labels_map.get(r["method"], r["method"]) for r in method_rows],
                "keys": [r["method"] for r in method_rows],
                "data": [r["method_count"] for r in method_rows],
            }

            days = [(fields.Date.today() - timedelta(days=i)) for i in range(13, -1, -1)]
            daily_counts = [
                Log.search_count([
                    ("create_date", ">=", f"{day} 00:00:00"), ("create_date", "<=", f"{day} 23:59:59"),
                ]) for day in days
            ]
            activity_trend = {
                "labels": [d.strftime("%b %d") for d in days],
                "keys": [fields.Date.to_string(d) for d in days],
                "data": daily_counts,
            }

            user_rows = Log.read_group(
                [("create_date", ">=", since_30d)], ["user_id"], ["user_id"], limit=5, orderby="user_id_count desc"
            )
            top_users = {
                "labels": [r["user_id"][1] if r["user_id"] else "Unknown" for r in user_rows],
                "keys": [r["user_id"][0] if r["user_id"] else False for r in user_rows],
                "data": [r["user_id_count"] for r in user_rows],
            }

            model_rows = Log.read_group(
                [("create_date", ">=", since_30d)], ["model_name"], ["model_name"], limit=5,
                orderby="model_name_count desc"
            )
            top_models = {
                "labels": [r["model_name"] or "Unknown" for r in model_rows],
                "keys": [r["model_name"] for r in model_rows],
                "data": [r["model_name_count"] for r in model_rows],
            }

            recent_logs = Log.search([], order="create_date desc", limit=8)
            recent = [{
                "id": rec.id, "user": rec.user_id.name, "model": rec.model_name,
                "record": rec.record_name, "method": rec.method,
                "date": fields.Datetime.to_string(rec.create_date),
            } for rec in recent_logs]

            active_sessions = Session.search([("state", "=", "active")], order="last_activity desc", limit=8)
            active_list = [{
                "id": s.id, "user": s.user_id.name, "ip": s.ip_address, "browser": s.browser,
                "os": s.operating_system, "device": s.device_type,
                "last_activity": fields.Datetime.to_string(s.last_activity), "is_new_device": s.is_new_device,
            } for s in active_sessions]

        except AccessError:
            # Should be unreachable in practice (the menu itself is
            # group-restricted), but fail soft rather than crash.
            empty = {"labels": [], "keys": [], "data": []}
            return {
                "kpis": {k: 0 for k in (
                    "active_sessions", "killed_sessions", "new_devices_today", "logs_today",
                    "creates_7d", "writes_7d", "deletes_7d")},
                "sessions_by_state": empty, "actions_by_type": empty, "activity_trend": empty,
                "top_users": empty, "top_models": empty, "recent_logs": [], "active_sessions": [],
            }

        return {
            "kpis": kpis, "sessions_by_state": sessions_by_state, "actions_by_type": actions_by_type,
            "activity_trend": activity_trend, "top_users": top_users, "top_models": top_models,
            "recent_logs": recent, "active_sessions": active_list,
        }
