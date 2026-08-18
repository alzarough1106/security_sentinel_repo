from odoo import models, api

from .audit_rule import EXCLUDED_MODELS, resolve_effective_flags

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


class Base(models.AbstractModel):
    """Adds audit-trail hooks to EVERY model in the registry.

    `_inherit = "base"` is Odoo's own, officially-supported mechanism for
    extending all models (the same technique core modules like `mail` use
    to add methods everywhere). It is composed through the normal
    registry/MRO system, so it plays correctly with any number of other
    modules doing the same thing -- unlike directly monkey-patching
    `odoo.models.BaseModel`, which silently depends on Python import
    order and is not a supported extension point.
    """
    _inherit = "base"

    def _audit_flags(self):
        if self._name in EXCLUDED_MODELS:
            return None
        if getattr(self.pool, "_init", False):
            # Skip logging during module install/upgrade (demo/data loads)
            return None
        if self.pool.get("audit.rule") is None:
            return None
        return resolve_effective_flags(self.env, self._name)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        flags = self._audit_flags()
        if flags and flags["create"]:
            for rec, vals in zip(records, vals_list):
                safe_new = {k: _redact(rec, k, v) for k, v in vals.items()}
                self.env["audit.log"].sudo().create_log(
                    self._name, rec.id, "create", {"old": {}, "new": safe_new}, rec.display_name,
                )
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
                self.env["audit.log"].sudo().create_log(
                    self._name, rec.id, "write",
                    {"old": old_values.get(rec.id, {}), "new": safe_new}, rec.display_name,
                )
        return result

    def unlink(self):
        flags = self._audit_flags()
        deleted = [(r.id, r.display_name) for r in self] if flags and flags["unlink"] else []
        result = super().unlink()
        for res_id, name in deleted:
            self.env["audit.log"].sudo().create_log(self._name, res_id, "unlink", None, name)
        return result

    def read(self, fields=None, load="_classic_read"):
        flags = self._audit_flags()
        if flags and flags["read"]:
            for rec in self:
                self.env["audit.log"].sudo().create_log(
                    self._name, rec.id, "read", {"old": {}, "new": {"fields": fields}}, rec.display_name,
                )
        return super().read(fields=fields, load=load)