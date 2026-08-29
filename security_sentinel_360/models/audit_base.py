import logging
from odoo import models, api

from .audit_rule import EXCLUDED_MODELS, resolve_effective_flags

_logger = logging.getLogger(__name__)

HEAVY_FIELD_TYPES = {"binary", "html"}
HEAVY_FIELD_NAMES = {
    "arch_db", "arch_fs", "arch_prev", "image_1920", "image_1024",
    "image_512", "image_256", "image_128", "password", "password_crypt",
}
MAX_VALUE_LENGTH = 300


def _redact(record, field_name, value):
    field = record._fields.get(field_name)
    ftype = field.type if field else False
    if ftype in HEAVY_FIELD_TYPES or field_name in HEAVY_FIELD_NAMES:
        return "*** changed ***"
    if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
        return value[:MAX_VALUE_LENGTH] + "…"
    return value


def _safe_log(env, *args, **kwargs):
    """Audit logging is best-effort and must NEVER break the caller's
    actual business operation (create/write/unlink already succeeded
    by the time this runs). Any failure here -- a bad redaction, an
    unexpected DB constraint, an env/context edge case -- is caught,
    logged as a warning, and swallowed."""
    try:
        env["audit.log"].sudo().create_log(*args, **kwargs)
    except Exception:
        _logger.warning(
            "Super Session Audit: failed to write audit.log entry "
            "(model=%s, method=%s) -- continuing without blocking the "
            "original operation.", args[0] if args else "?", args[2] if len(args) > 2 else "?",
            exc_info=True,
        )


class Base(models.AbstractModel):
    _inherit = "base"

    def _audit_flags(self):
        if self._name in EXCLUDED_MODELS:
            return None
        if getattr(self.pool, "_init", False):
            return None
        if self.pool.get("audit.rule") is None:
            return None
        try:
            return resolve_effective_flags(self.env, self._name)
        except Exception:
            # Even the rule-resolution lookup itself must not be able to
            # break a CRUD call -- fail closed (no audit) rather than
            # fail loud (broken business operation).
            _logger.warning(
                "Super Session Audit: failed to resolve audit rule for "
                "model=%s -- skipping audit for this call.", self._name, exc_info=True,
            )
            return None

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        flags = self._audit_flags()
        if flags and flags["create"]:
            for rec, vals in zip(records, vals_list):
                safe_new = {k: _redact(rec, k, v) for k, v in vals.items()}
                _safe_log(self.env, self._name, rec.id, "create",
                          {"old": {}, "new": safe_new}, rec.display_name)
        return records

    def write(self, vals):
        flags = self._audit_flags()
        old_values = {}
        if flags and flags["write"]:
            keys = [k for k in vals if k in self._fields]
            for rec in self:
                snapshot = {}
                for k in keys:
                    try:
                        snapshot[k] = _redact(rec, k, rec[k])
                    except Exception:
                        snapshot[k] = False
                old_values[rec.id] = snapshot

        result = super().write(vals)

        if flags and flags["write"]:
            for rec in self:
                safe_new = {k: _redact(rec, k, v) for k, v in vals.items() if k in self._fields}
                _safe_log(self.env, self._name, rec.id, "write",
                          {"old": old_values.get(rec.id, {}), "new": safe_new}, rec.display_name)
        return result

    def unlink(self):
        flags = self._audit_flags()
        deleted = [(r.id, r.display_name) for r in self] if flags and flags["unlink"] else []
        result = super().unlink()
        for res_id, name in deleted:
            _safe_log(self.env, self._name, res_id, "unlink", None, name)
        return result

    def read(self, fields=None, load="_classic_read"):
        flags = self._audit_flags()
        if flags and flags["read"]:
            for rec in self:
                _safe_log(self.env, self._name, rec.id, "read",
                          {"old": {}, "new": {"fields": fields}}, rec.display_name)
        return super().read(fields=fields, load=load)