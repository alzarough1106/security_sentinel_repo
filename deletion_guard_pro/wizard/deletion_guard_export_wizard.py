from odoo import api, fields, models, _
from odoo.exceptions import AccessDenied, UserError


class DeletionPasswordWizard(models.TransientModel):
    _name = 'deletion.password.wizard'
    _description = 'Deletion Confirmation Wizard'

    deletion_request_ids = fields.Many2many('deletion.request', string='Deletion Requests')
    action_type = fields.Selection([
        ('confirm', 'Confirm & Delete'),
        ('reject', 'Reject Request'),
        ('purge', 'Permanently Delete'),
    ], required=True, default='confirm')

    password = fields.Char(string='Your Password')
    totp_code = fields.Char(string='2FA Code (TOTP)')
    rejection_reason = fields.Text(string='Rejection Reason')

    request_count = fields.Integer(compute='_compute_display_info')
    record_names_preview = fields.Text(compute='_compute_display_info', string='Records')
    combined_impact_summary = fields.Text(compute='_compute_display_info', string='Impact Warning')
    has_impact_warning = fields.Boolean(compute='_compute_display_info')

    confirmation_mode = fields.Selection([
        ('password', 'Password Only'),
        ('totp_optional', 'Password OR 2FA Code'),
        ('password_and_totp', 'Password AND 2FA Code'),
    ], compute='_compute_confirmation_requirements')
    totp_available_for_user = fields.Boolean(compute='_compute_confirmation_requirements')

    @api.depends('deletion_request_ids')
    def _compute_display_info(self):
        for wiz in self:
            pending = wiz.deletion_request_ids.filtered(lambda r: r.state == 'pending')
            wiz.request_count = len(pending)
            wiz.record_names_preview = '\n'.join(
                f"- {r.record_display_name} ({r.model_id.name})" for r in pending
            ) or _('No pending records.')
            impacted = pending.filtered(lambda r: r.impact_count)
            wiz.has_impact_warning = bool(impacted)
            wiz.combined_impact_summary = '\n'.join(
                f"- {r.record_display_name}: {r.impact_summary}" for r in impacted
            ) or _('No related records found for the selected item(s).')

    @api.depends('deletion_request_ids')
    def _compute_confirmation_requirements(self):
        user = self.env.user
        has_totp_field = 'totp_secret' in user._fields
        for wiz in self:
            wiz.totp_available_for_user = has_totp_field and bool(user.sudo().totp_secret)
            modes = []
            for model_name in wiz.deletion_request_ids.mapped('model_id.model'):
                config = self.env['deletion.guard.config']._get_config(model_name)
                modes.append(config.confirmation_method if config else 'password')
            if 'password_and_totp' in modes:
                wiz.confirmation_mode = 'password_and_totp'
            elif 'totp_optional' in modes:
                wiz.confirmation_mode = 'totp_optional'
            else:
                wiz.confirmation_mode = 'password'

    # ------------------------------------------------------------------
    # Credential verification helpers
    # ------------------------------------------------------------------
    def _verify_password(self, user):
        if not self.password:
            raise UserError(_("Please enter your password."))
        credential = {'login': user.login, 'password': self.password, 'type': 'password'}
        try:
            user._check_credentials(credential, {'interactive': True})
        except AccessDenied:
            raise UserError(_("Incorrect password."))

    def _verify_totp(self, user):
        if 'totp_secret' not in user._fields:
            raise UserError(_(
                "Two-factor authentication is not available: the 'auth_totp' "
                "module is not installed on this system."))
        if not self.totp_code:
            raise UserError(_("Please enter your 2FA code."))
        credential = {'login': user.login, 'token': self.totp_code, 'type': 'totp'}
        try:
            user._check_credentials(credential, {'interactive': True})
        except AccessDenied:
            raise UserError(_("Invalid 2FA code."))

    def _authenticate(self):
        self.ensure_one()
        user = self.env.user
        mode = self.confirmation_mode

        if mode == 'password_and_totp':
            if not self.totp_available_for_user:
                raise UserError(_(
                    "Strict 2FA confirmation is required for this deletion, but "
                    "you do not have 2FA enabled on your account. Please enable "
                    "it in My Profile > Account Security first."))
            self._verify_password(user)
            self._verify_totp(user)
        elif mode == 'totp_optional':
            if self.totp_code:
                self._verify_totp(user)
            elif self.password:
                self._verify_password(user)
            else:
                raise UserError(_("Please enter your password or a 2FA code."))
        else:
            self._verify_password(user)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def action_submit(self):
        self.ensure_one()

        if self.action_type == 'purge':
            requests = self.deletion_request_ids.filtered(
                lambda r: r.is_recycle_bin and not r.restored and not r.purged)
            if not requests:
                raise UserError(_("Nothing to purge."))
            self._authenticate()
            for req in requests:
                req._purge_now()
            return {'type': 'ir.actions.act_window_close'}

        requests = self.deletion_request_ids.filtered(lambda r: r.state == 'pending')
        if not requests:
            raise UserError(_("No pending requests to process."))

        if self.action_type == 'reject':
            if not self.rejection_reason:
                raise UserError(_("Please provide a rejection reason."))
            requests._check_bulk_authorization('reject')
            for req in requests:
                req.action_reject(self.rejection_reason)
            return {'type': 'ir.actions.act_window_close'}

        # action_type == 'confirm'
        requests._check_bulk_authorization('confirm')
        self._authenticate()

        errors = []
        for req in requests:
            try:
                req.action_confirm_delete()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{req.name}: {exc}")
        if errors:
            raise UserError(_(
                "Some deletions could not be completed:\n%s", '\n'.join(errors)))
        return {'type': 'ir.actions.act_window_close'}