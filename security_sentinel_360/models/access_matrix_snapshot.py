"""
Access Matrix Snapshots — for periodic access reviews (SOC2, ISO 27001).
"""
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AccessMatrixSnapshot(models.Model):
    _name = 'audit.access.matrix.snapshot'
    _description = 'Access Matrix Snapshot'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    snapshot_data = fields.Text(string='Snapshot (JSON)', readonly=True)
    user_count = fields.Integer(readonly=True)
    model_count = fields.Integer(readonly=True)
    admin_count = fields.Integer(readonly=True)

    create_date = fields.Datetime(readonly=True)
    create_uid = fields.Many2one('res.users', readonly=True)

    review_state = fields.Selection([
        ('draft', 'Draft'),
        ('reviewing', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    reviewed_by_id = fields.Many2one('res.users', readonly=True)
    reviewed_date = fields.Datetime(readonly=True)
    review_notes = fields.Text()

    def action_take_snapshot(self):
        """Take a fresh snapshot of the current matrix."""
        self.ensure_one()
        data = self.env['audit.access.matrix'].sudo().get_matrix_data({
            'limit_users': 500, 'limit_models': 300})
        self.write({
            'snapshot_data': json.dumps(data),
            'user_count': data['stats']['user_count'],
            'model_count': data['stats']['model_count'],
            'admin_count': data['stats']['admin_count'],
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Snapshot Captured',
                'message': f"{data['stats']['user_count']} users × {data['stats']['model_count']} models",
                'type': 'success',
            }
        }

    def action_start_review(self):
        self.write({'review_state': 'reviewing'})

    def action_approve(self):
        self.write({
            'review_state': 'approved',
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    def action_reject(self):
        self.write({
            'review_state': 'rejected',
            'reviewed_by_id': self.env.uid,
            'reviewed_date': fields.Datetime.now(),
        })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.snapshot_data:
                rec.action_take_snapshot()
        return records