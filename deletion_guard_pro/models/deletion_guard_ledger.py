import json
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

_SKIP_SNAPSHOT_TYPES = ('binary', 'one2many', 'many2many')
_TODO_ACTIVITY_XMLID = 'mail.mail_activity_data_todo'


class DeletionRequest(models.Model):
    _name = 'deletion.request'
    _description = 'Deletion Request / Audit Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _('New'))

    model_id = fields.Many2one('ir.model', required=True, readonly=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)
    res_id = fields.Integer(readonly=True, string='Record ID')
    record_display_name = fields.Char(readonly=True, string='Record')

    field_snapshot = fields.Text(readonly=True, string='Record Data Snapshot (raw)')
    field_snapshot_html = fields.Html(compute='_compute_field_snapshot_html', sanitize=False)

    reason = fields.Text(string='Deletion Reason')
    rejection_reason = fields.Text(readonly=True)

    requires_approval = fields.Boolean(readonly=True)

    state = fields.Selection([
        ('pending', 'Pending Confirmation'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('done', 'Deleted'),
        ('restored', 'Restored'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, tracking=True)

    requested_by = fields.Many2one('res.users', required=True, readonly=True,
                                    default=lambda self: self.env.user)
    requested_date = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)

    confirmed_by = fields.Many2one('res.users', readonly=True, string='Confirmed / Approved By')
    confirmed_date = fields.Datetime(readonly=True)
    confirmation_method = fields.Selection([
        ('password', 'Password Re-authentication'),
    ], default='password', readonly=True)

    self_confirmed = fields.Boolean(
        compute='_compute_self_confirmed', store=True,
        help="True if requester and confirmer are the same person.")

    # -------------------- Impact / cascade warning --------------------
    impact_count = fields.Integer(readonly=True, string="Related Records")
    impact_summary = fields.Char(readonly=True, string="Impact Summary")

    # -------------------- Recycle bin --------------------
    is_recycle_bin = fields.Boolean(readonly=True, string="In Recycle Bin")
    deletion_method = fields.Selection([
        ('archived', 'Archived (Soft Delete)'),
        ('hard', 'Hard Deleted (Serialized Backup)'),
    ], readonly=True)
    restore_data = fields.Text(readonly=True, string="Restore Data (internal)")
    restore_deadline = fields.Datetime(readonly=True, string="Recoverable Until")
    restored = fields.Boolean(readonly=True, default=False)
    restored_by = fields.Many2one('res.users', readonly=True)
    restored_date = fields.Datetime(readonly=True)
    purged = fields.Boolean(readonly=True, default=False)
    purge_date = fields.Datetime(readonly=True)

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.depends('requested_by', 'confirmed_by')
    def _compute_self_confirmed(self):
        for rec in self:
            rec.self_confirmed = bool(rec.confirmed_by) and rec.confirmed_by == rec.requested_by

    def _compute_field_snapshot_html(self):
        for rec in self:
            try:
                data = json.loads(rec.field_snapshot or '{}')
            except ValueError:
                data = {}
            if not data:
                rec.field_snapshot_html = _('No data captured.')
                continue
            rows = ''.join(
                '<tr><td style="padding:2px 8px;"><b>%s</b></td>'
                '<td style="padding:2px 8px;">%s</td></tr>' % (
                    fname, value if value not in (False, None) else ''
                )
                for fname, value in data.items()
            )
            rec.field_snapshot_html = '<table class="table table-sm">%s</table>' % rows

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('deletion.request') or _('New')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Tamper-proofing: this audit log can NEVER be deleted, by anyone,
    # through any code path - including sudo()/superuser calls.
    # ------------------------------------------------------------------
    def unlink(self):
        raise AccessError(_(
            "Deletion Guard audit log entries cannot be deleted under any "
            "circumstances, including by system or superuser calls. This is "
            "enforced to guarantee the integrity of the audit trail."
        ))

    # ------------------------------------------------------------------
    # Snapshot & impact introspection (run BEFORE the record is touched)
    # ------------------------------------------------------------------
    @api.model
    def _build_snapshot(self, record, field_names=None):
        if not field_names:
            field_names = [
                fname for fname, field in record._fields.items()
                if field.store and fname != 'id' and field.type not in _SKIP_SNAPSHOT_TYPES
            ]
        data = {}
        for fname in field_names:
            try:
                value = record[fname]
            except Exception:  # noqa: BLE001
                continue
            if isinstance(value, models.BaseModel):
                value = value.display_name if value else False
            data[fname] = value
        return data

    @api.model
    def _serialize_full_record(self, record):
        """Full backup used for Recycle Bin restore of hard-deleted records.
        many2one -> stored as id, many2many -> stored as list of ids,
        one2many -> intentionally skipped (child records are not restored
        automatically; safest default to avoid duplicating/orphaning data)."""
        vals = {}
        for fname, field in record._fields.items():
            if not field.store or fname == 'id' or field.type == 'one2many':
                continue
            try:
                if field.type == 'many2one':
                    value = record[fname].id if record[fname] else False
                elif field.type == 'many2many':
                    value = record[fname].ids
                else:
                    value = record[fname]
            except Exception:  # noqa: BLE001
                continue
            vals[fname] = value
        return vals

    @api.model
    def _compute_impact_info_for_record(self, record):
        """Count how many OTHER records reference this one, across all
        models, via any stored many2one/many2many field pointing to it."""
        lines = []
        total = 0
        pointing_fields = self.env['ir.model.fields'].sudo().search([
            ('relation', '=', record._name),
            ('ttype', 'in', ('many2one', 'many2many')),
            ('store', '=', True),
        ])
        for f in pointing_fields:
            try:
                Model = self.env[f.model].sudo()
            except KeyError:
                continue
            try:
                if f.ttype == 'many2one':
                    count = Model.search_count([(f.name, '=', record.id)])
                else:
                    count = Model.search_count([(f.name, 'in', [record.id])])
            except Exception:  # noqa: BLE001 - never let introspection break the flow
                continue
            if count:
                total += count
                lines.append(f"{count} {Model._description or f.model}")
        summary = ', '.join(lines) if lines else _('No related records found.')
        return total, summary

    # ------------------------------------------------------------------
    # Registration (called from the global unlink() override)
    # ------------------------------------------------------------------
    @api.model
    def _register_deletion(self, records, config=None, reason=False):
        """Create one deletion.request per record, on a SEPARATE cursor so
        the log survives the UserError/rollback that immediately follows
        in base.py's unlink() override."""
        Config = self.env['deletion.guard.config']
        config = config or Config._get_config(records._name)
        model_rec = self.env['ir.model']._get(records._name)
        snapshot_fields = (
            config.snapshot_field_ids.mapped('name')
            if config and config.snapshot_field_ids else None
        )

        vals_list = []
        for record in records:
            impact_count, impact_summary = self._compute_impact_info_for_record(record)
            vals_list.append({
                'model_id': model_rec.id,
                'res_id': record.id,
                'record_display_name': record.display_name or f"{records._name},{record.id}",
                'field_snapshot': json.dumps(
                    self._build_snapshot(record, snapshot_fields),
                    default=str, ensure_ascii=False, indent=2,
                ),
                'reason': reason,
                'requested_by': self.env.uid,
                'requires_approval': bool(config and config.mode == 'approval_required'),
                'impact_count': impact_count,
                'impact_summary': impact_summary,
                'state': 'pending',
            })

        with self.pool.cursor() as new_cr:
            new_env = api.Environment(new_cr, self.env.uid, self.env.context)
            requests = new_env['deletion.request'].sudo().create(vals_list)
            requests._notify_approvers()
            request_names = requests.mapped('name')
            request_ids = requests.ids

        return request_names, request_ids

    def _notify_approvers(self):
        for rec in self:
            approvers = self.env['res.users']
            if rec.requires_approval:
                config = self.env['deletion.guard.config']._get_config(rec.model_name)
                if config:
                    approvers |= config.approver_user_ids
                    group = config.approver_group_id or self.env.ref(
                        'deletion_guard_pro.group_deletion_guard_approver')
                else:
                    group = self.env.ref('deletion_guard_pro.group_deletion_guard_manager')
                approvers |= self.env['res.users'].search([('group_ids', 'in', group.id)])

                if approvers:
                    rec.message_subscribe(partner_ids=approvers.mapped('partner_id').ids)
                rec.message_post(body=_(
                    '%(user)s requested deletion of "%(rec)s". Awaiting approval.',
                    user=rec.requested_by.name, rec=rec.record_display_name,
                ))
                for user in approvers:
                    rec.activity_schedule(
                        _TODO_ACTIVITY_XMLID,
                        summary=_('Deletion request awaiting your approval'),
                        note=_('%(user)s requested deletion of "%(rec)s". Please review and approve or reject.',
                               user=rec.requested_by.name, rec=rec.record_display_name),
                        user_id=user.id,
                    )
            else:
                rec.message_post(body=_(
                    '%(user)s requested deletion of "%(rec)s". Self-confirmation with '
                    'password required to proceed.',
                    user=rec.requested_by.name, rec=rec.record_display_name,
                ))

    # ------------------------------------------------------------------
    # Bulk authorization helper
    # ------------------------------------------------------------------
    def _is_current_user_authorized_approver(self):
        self.ensure_one()
        config = self.env['deletion.guard.config']._get_config(self.model_name)
        if not config:
            return self.env.user.has_group('deletion_guard_pro.group_deletion_guard_manager')
        return config._user_is_approver(self.env.user)

    def _check_bulk_authorization(self, action_type):
        """Raise if the current user is not allowed to confirm/reject ALL
        pending records in this recordset (kept strict for simplicity: a
        batch action must be fully authorized, not partially)."""
        unauthorized = self.env['deletion.request']
        for rec in self.filtered(lambda r: r.state == 'pending'):
            if action_type == 'confirm':
                if rec.requires_approval and not rec._is_current_user_authorized_approver():
                    unauthorized |= rec
                elif not rec.requires_approval and self.env.uid != rec.requested_by.id \
                        and not self.env.user.has_group('deletion_guard_pro.group_deletion_guard_manager'):
                    unauthorized |= rec
            else:  # reject
                if not rec._is_current_user_authorized_approver():
                    unauthorized |= rec
        if unauthorized:
            raise AccessError(_(
                "You are not authorized to %(action)s the following request(s): %(names)s",
                action=action_type, names=', '.join(unauthorized.mapped('name')),
            ))

    # ------------------------------------------------------------------
    # Wizard-opening actions (single record, form view buttons)
    # ------------------------------------------------------------------
    def action_open_confirm_wizard(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("This request has already been processed."))
        self._check_bulk_authorization('confirm')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirm Deletion'),
            'res_model': 'deletion.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_deletion_request_ids': [self.id], 'default_action_type': 'confirm'},
        }

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("This request has already been processed."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Deletion Request'),
            'res_model': 'deletion.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_deletion_request_ids': [self.id], 'default_action_type': 'reject'},
        }

    # ------------------------------------------------------------------
    # Wizard-opening actions (bulk, from list view multi-select)
    # ------------------------------------------------------------------
    def action_open_bulk_confirm_wizard(self):
        pending = self.filtered(lambda r: r.state == 'pending')
        if not pending:
            raise UserError(_("No pending requests selected."))
        pending._check_bulk_authorization('confirm')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirm & Delete Selected'),
            'res_model': 'deletion.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_deletion_request_ids': pending.ids, 'default_action_type': 'confirm'},
        }

    def action_open_bulk_reject_wizard(self):
        pending = self.filtered(lambda r: r.state == 'pending')
        if not pending:
            raise UserError(_("No pending requests selected."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Selected'),
            'res_model': 'deletion.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_deletion_request_ids': pending.ids, 'default_action_type': 'reject'},
        }

    # ------------------------------------------------------------------
    # Actions (called by the password wizard AFTER a successful check)
    # ------------------------------------------------------------------
    def action_confirm_delete(self):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("This request has already been processed."))
        if self.requires_approval and not self._is_current_user_authorized_approver():
            raise AccessError(_("You are not authorized to approve this deletion request."))
        if not self.requires_approval and self.env.uid != self.requested_by.id \
                and not self.env.user.has_group('deletion_guard_pro.group_deletion_guard_manager'):
            raise AccessError(_("Only the original requester can confirm this deletion."))

        self.write({
            'state': 'approved',
            'confirmed_by': self.env.uid,
            'confirmed_date': fields.Datetime.now(),
        })
        self._execute_deletion()
        self.activity_ids.action_feedback(feedback=_('Deletion confirmed and executed.'))

    def action_reject(self, rejection_reason):
        self.ensure_one()
        if self.state != 'pending':
            raise UserError(_("This request has already been processed."))
        self.write({
            'state': 'rejected',
            'rejection_reason': rejection_reason,
            'confirmed_by': self.env.uid,
            'confirmed_date': fields.Datetime.now(),
        })
        self.message_post(body=_(
            'Deletion request rejected by %(user)s.<br/><b>Reason:</b> %(reason)s',
            user=self.env.user.name, reason=rejection_reason,
        ))
        self.activity_ids.action_feedback(feedback=_('Request rejected.'))

    def action_cancel(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_("Only pending requests can be cancelled."))
            if rec.requested_by.id != self.env.uid \
                    and not self.env.user.has_group('deletion_guard_pro.group_deletion_guard_manager'):
                raise AccessError(_("Only the requester or a manager can cancel this request."))
            rec.state = 'cancelled'
            rec.activity_ids.action_feedback(feedback=_('Request cancelled.'))

    # ------------------------------------------------------------------
    # Deletion execution (soft-archive OR hard-delete-with-backup)
    # ------------------------------------------------------------------
    def _execute_deletion(self):
        self.ensure_one()
        config = self.env['deletion.guard.config']._get_config(self.model_name)
        recycle_enabled = bool(config and config.recycle_bin_enabled)
        retention_days = config.retention_days if config else 30

        Model = self.env[self.model_name].sudo().with_context(
            deletion_guard_bypass=True, deletion_guard_verified=True,
        )
        record = Model.browse(self.res_id)

        if not record.exists():
            _logger.info("Deletion request %s: record already gone.", self.name)
            self.write({'state': 'done'})
            return

        if recycle_enabled:
            deadline = fields.Datetime.now() + timedelta(days=retention_days)
            has_active_field = 'active' in record._fields
            if has_active_field:
                record.write({'active': False})
                self.write({
                    'state': 'done',
                    'is_recycle_bin': True,
                    'deletion_method': 'archived',
                    'restore_deadline': deadline,
                })
                self.message_post(body=_(
                    'Record archived (soft-deleted). Recoverable until %s.', deadline,
                ))
            else:
                restore_vals = self._serialize_full_record(record)
                record.unlink()
                self.write({
                    'state': 'done',
                    'is_recycle_bin': True,
                    'deletion_method': 'hard',
                    'restore_deadline': deadline,
                    'restore_data': json.dumps(restore_vals, default=str, ensure_ascii=False),
                })
                self.message_post(body=_(
                    'Record permanently deleted, backup kept for restore until %s.', deadline,
                ))
        else:
            record.unlink()
            self.write({'state': 'done'})
            self.message_post(body=_('Record permanently deleted (Recycle Bin disabled for this model).'))

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------
    def action_restore(self):
        self.ensure_one()
        if not self.is_recycle_bin or self.restored or self.purged:
            raise UserError(_("This record cannot be restored."))
        if self.restore_deadline and fields.Datetime.now() > self.restore_deadline:
            raise UserError(_("The restore window for this record has expired."))
        if not self._is_current_user_authorized_approver():
            raise AccessError(_("You are not authorized to restore this record."))

        Model = self.env[self.model_name].sudo().with_context(deletion_guard_bypass=True)

        if self.deletion_method == 'archived':
            record = Model.browse(self.res_id)
            if not record.exists():
                raise UserError(_("The archived record no longer exists; it may have been purged."))
            record.write({'active': True})
        else:
            try:
                vals = json.loads(self.restore_data or '{}')
            except ValueError:
                vals = {}
            clean_vals = {}
            for fname, value in vals.items():
                field = Model._fields.get(fname)
                if not field:
                    continue
                if field.type == 'many2one' and value:
                    if not self.env[field.comodel_name].sudo().browse(value).exists():
                        continue
                elif field.type == 'many2many' and value:
                    value = self.env[field.comodel_name].sudo().browse(value).exists().ids
                clean_vals[fname] = value
            new_record = Model.create(clean_vals)
            self.write({'res_id': new_record.id})

        self.write({
            'restored': True,
            'restored_by': self.env.uid,
            'restored_date': fields.Datetime.now(),
            'state': 'restored',
        })
        self.message_post(body=_('Record restored by %s.', self.env.user.name))

    def _purge_now(self):
        """Immediately, permanently erase this Recycle Bin entry: deletes
        the archived record (if any) and scrubs the stored backup/snapshot.
        Shared by the daily cron AND the manual 'Delete Permanently' button.
        """
        self.ensure_one()
        if not self.is_recycle_bin or self.restored or self.purged:
            raise UserError(_("This request has nothing left to purge."))

        if self.deletion_method == 'archived':
            Model = self.env[self.model_name].sudo().with_context(deletion_guard_bypass=True)
            record = Model.browse(self.res_id)
            if record.exists():
                record.unlink()

        self.write({
            'purged': True,
            'purge_date': fields.Datetime.now(),
            'restore_data': False,
            'field_snapshot': json.dumps({
                '_purged': True,
                'note': 'Snapshot purged (manual permanent delete or retention policy).',
            }),
        })
        self.message_post(body=_(
            'Record permanently purged by %s. Personal data snapshot erased.',
            self.env.user.name,
        ))

    def action_open_purge_wizard(self):
        self.ensure_one()
        if not self.env.user.has_group('deletion_guard_pro.group_deletion_guard_manager'):
            raise AccessError(_("Only a Deletion Guard Administrator can permanently delete a Recycle Bin entry."))
        if not self.is_recycle_bin or self.restored or self.purged:
            raise UserError(_("This request has nothing left to purge."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Permanently Delete'),
            'res_model': 'deletion.password.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_deletion_request_ids': [self.id], 'default_action_type': 'purge'},
        }

    # ------------------------------------------------------------------
    # Cron: purge expired Recycle Bin entries
    # ------------------------------------------------------------------
    @api.model
    def _cron_purge_recycle_bin(self):
        now = fields.Datetime.now()
        to_purge = self.sudo().search([
            ('is_recycle_bin', '=', True),
            ('restored', '=', False),
            ('purged', '=', False),
            ('restore_deadline', '<=', now),
        ])
        for rec in to_purge:
            rec._purge_now()