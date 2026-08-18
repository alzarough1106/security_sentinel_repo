import base64
import csv
import io
import json
from odoo import models, fields, api


class AccessMatrixExportWizard(models.TransientModel):
    _name = 'audit.access.matrix.export.wizard'
    _description = 'Export Access Matrix to CSV'

    group_id = fields.Many2one('res.groups', string='Filter Group')
    company_id = fields.Many2one('res.company', string='Filter Company')
    sensitive_only = fields.Boolean(string='Sensitive Models Only')
    show_share_users = fields.Boolean(string='Include Portal Users')

    file_data = fields.Binary(readonly=True)
    file_name = fields.Char(readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft')

    def action_export(self):
        self.ensure_one()
        data = self.env['audit.access.matrix'].get_matrix_data({
            'group_id': self.group_id.id if self.group_id else None,
            'company_id': self.company_id.id if self.company_id else None,
            'sensitive_only': self.sensitive_only,
            'show_share_users': self.show_share_users,
            'limit_users': 500,
            'limit_models': 500,
        })

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)

        # Header row: User Login | User Name | Model | Sensitive | Read | Write | Create | Delete | Sources
        writer.writerow([
            'User Login', 'User Name', 'Is Admin',
            'Model (Technical)', 'Model (Display)', 'Sensitive',
            'Read', 'Write', 'Create', 'Delete',
            'Permission Sources',
        ])

        users_by_id = {u['id']: u for u in data['users']}
        models_by_id = {m['id']: m for m in data['models']}

        for user_id, user_perms in data['matrix'].items():
            user = users_by_id.get(user_id, {})
            for model_id, perms in user_perms.items():
                m = models_by_id.get(model_id, {})
                writer.writerow([
                    user.get('login', ''),
                    user.get('name', ''),
                    'Yes' if user.get('is_admin') else 'No',
                    m.get('model', ''),
                    m.get('name', ''),
                    'Yes' if m.get('sensitive') else 'No',
                    'Yes' if perms.get('read') else 'No',
                    'Yes' if perms.get('write') else 'No',
                    'Yes' if perms.get('create') else 'No',
                    'Yes' if perms.get('unlink') else 'No',
                    ' | '.join(perms.get('sources', [])),
                ])

        csv_data = output.getvalue().encode('utf-8')
        output.close()

        self.write({
            'file_data': base64.b64encode(csv_data),
            'file_name': f'access_matrix_{fields.Date.today()}.csv',
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'audit.access.matrix.export.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }