from odoo import models, api, _
from odoo.exceptions import UserError

ALWAYS_EXCLUDED_MODELS = {
    'deletion.request',
    'deletion.guard.config',
    'deletion.password.wizard',
    'mail.message', 'mail.followers', 'mail.notification', 'mail.tracking.value',
}
TECHNICAL_MODEL_PREFIXES = ('ir.', 'bus.', 'base_import.', 'report.')


class Base(models.AbstractModel):
    _inherit = 'base'

    def unlink(self):
        if self:
            self.check_access('unlink')

        if self._skip_guard():
            return super().unlink()

        config = self.env['deletion.guard.config']._get_config(self._name)
        if not config:
            return super().unlink()

        if self.env.context.get('deletion_guard_verified'):
            return super().unlink()

        if len(self) > 1 and not config.allow_bulk:
            raise UserError(_(
                "Bulk deletion is not allowed for '%(model)s'. Please delete "
                "records one at a time.",
                model=self._description or self._name,
            ))

        DeletionRequest = self.env['deletion.request']
        reason = self.env.context.get('deletion_guard_reason')
        request_names, request_ids = DeletionRequest._register_deletion(self, config=config, reason=reason)

        if config.mode == 'direct_password':
            raise UserError(_(
                "Password confirmation is required before deleting %(count)s "
                "record(s) of '%(model)s'.\n\n"
                "A deletion request has been logged (%(names)s). Open Deletion "
                "Guard > Deletion Requests, then click 'Confirm & Delete' and "
                "enter your password to complete the deletion.",
                count=len(self), model=self._description or self._name,
                names=', '.join(request_names),
            ))
        raise UserError(_(
            "Deletion of %(count)s record(s) of '%(model)s' requires approval. "
            "A deletion request has been submitted (%(names)s) and the "
            "record(s) have NOT been deleted.",
            count=len(self), model=self._description or self._name,
            names=', '.join(request_names),
        ))

    def _skip_guard(self):
        return (
            not self
            or self._transient
            or self.env.su
            or self._name in ALWAYS_EXCLUDED_MODELS
            or self._name.startswith(TECHNICAL_MODEL_PREFIXES)
            or self.env.context.get('deletion_guard_bypass')
            or self.env.user.has_group('deletion_guard_pro.group_deletion_guard_bypass')
        )