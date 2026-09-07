from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

FORBIDDEN_MODELS = {
    'deletion.request',
    'deletion.guard.config',
    'deletion.password.wizard',
    'ir.model', 'ir.model.fields', 'ir.model.access', 'ir.rule',
    'ir.sequence', 'ir.attachment',
    'mail.message', 'mail.followers', 'mail.notification', 'mail.tracking.value',
}


class DeletionGuardConfig(models.Model):
    _name = 'deletion.guard.config'
    _description = 'Deletion Guard Configuration'
    _rec_name = 'model_id'

    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', required=True, ondelete='cascade',
        domain=[('transient', '=', False)],
    )
    confirmation_method = fields.Selection([
        ('password', 'Password Only'),
        ('totp_optional', 'Password OR 2FA Code'),
        ('password_and_totp', 'Password AND 2FA Code (Strict 2FA)'),
    ], default='password', required=True, string="Confirmation Method",
        help="Requires the auth_totp module to be installed and the user to "
             "have 2FA enabled on their account for the TOTP options to apply. "
             "Falls back to password-only automatically if unavailable.")
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)

    mode = fields.Selection([
        ('direct_password', 'Password confirmation only (self-delete)'),
        ('approval_required', 'Approval workflow required (4-eyes principle)'),
    ], default='direct_password', required=True)

    approver_group_id = fields.Many2one(
        'res.groups', string='Approver Group',
        help="Users in this group can approve deletion requests on this model. "
             "Leave empty to use the default 'Deletion Approver' group.")
    approver_user_ids = fields.Many2many(
        'res.users', string='Specific Approvers',
        help="Optional extra approvers, in addition to the group above.")

    require_reason = fields.Boolean(default=True, string="Require Reason")
    snapshot_field_ids = fields.Many2many(
        'ir.model.fields', string='Fields to Snapshot',
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        help="Fields captured in the audit log before deletion. "
             "Leave empty to snapshot all stored fields automatically.")
    allow_bulk = fields.Boolean(default=True, string="Allow Bulk Deletion Requests")

    recycle_bin_enabled = fields.Boolean(
        default=True, string="Enable Recycle Bin",
        help="If enabled, deleted records are archived (or fully backed up) "
             "instead of being permanently removed immediately, and can be "
             "restored within the retention period below.")
    retention_days = fields.Integer(
        default=30, string="Retention Period (days)",
        help="Number of days a deleted record stays recoverable in the "
             "Recycle Bin before being permanently purged.")

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('model_uniq', 'unique(model_id, company_id)',
         'A Deletion Guard configuration already exists for this model / company.'),
        ('retention_days_positive', 'CHECK(retention_days > 0)',
         'Retention period must be at least 1 day.'),
    ]

    @api.model
    def is_model_protected(self, model_name):
        """Returns True if the model has an active protection configuration."""
        config = self._get_config(model_name)
        return bool(config)

    @api.constrains('model_id')
    def _check_model_allowed(self):
        for rec in self:
            if rec.model_id.model in FORBIDDEN_MODELS or rec.model_id.model.startswith('ir.'):
                raise ValidationError(_(
                    "The Deletion Guard cannot be enabled on the technical model '%s'.",
                    rec.model_id.model,
                ))

    @api.model
    def _get_config(self, model_name):
        return self.sudo().search([
            ('model_id.model', '=', model_name),
            ('active', '=', True),
            ('company_id', 'in', [False, self.env.company.id]),
        ], limit=1)

    # deletion_guard_config.py
    def _user_is_approver(self, user):
        self.ensure_one()
        if user.has_group('deletion_guard_pro.group_deletion_guard_manager'):
            return True
        if user.has_group('deletion_guard_pro.group_deletion_guard_approver'):
            return True
        if self.approver_user_ids and user in self.approver_user_ids:
            return True
        if self.approver_group_id and self.approver_group_id in user.group_ids:
            return True
        # Primary rule: whoever already has native unlink rights on the
        # protected business model IS its deletion approver.
        return bool(
            self.env['ir.model.access'].sudo().with_user(user)
            .check(self.model_name, 'unlink', raise_exception=False)
        )