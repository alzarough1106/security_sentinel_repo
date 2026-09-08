import base64
import csv
import io
from odoo import models, fields, api


class AuditExportWizard(models.TransientModel):
    _name = 'audit.export.wizard'
    _description = 'Export Audit Logs to CSV'

    date_from = fields.Datetime(string='From', required=True,
                                default=lambda self: fields.Datetime.now().replace(day=1))
    date_to = fields.Datetime(string='To', required=True,
                              default=fields.Datetime.now)
    user_ids = fields.Many2many('res.users', string='Filter Users (optional)')
    event_types = fields.Char(string='Event Types (comma-separated, optional)',
                              help="E.g.: login,login_failed,unlink")
    min_risk_score = fields.Integer(string='Minimum Risk Score', default=0)

    file_data = fields.Binary(string='CSV File', readonly=True)
    file_name = fields.Char(string='File Name', readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft')

    def action_export(self):
        self.ensure_one()
        domain = [
            ('create_date', '>=', self.date_from),
            ('create_date', '<=', self.date_to),
            ('risk_score', '>=', self.min_risk_score),
        ]
        if self.user_ids:
            domain.append(('user_id', 'in', self.user_ids.ids))
        if self.event_types:
            types = [t.strip() for t in self.event_types.split(',') if t.strip()]
            if types:
                domain.append(('event_type', 'in', types))

        logs = self.env['audit.log'].search(domain, order='create_date desc')

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_ALL)
        writer.writerow([
            'Timestamp', 'User', 'Event Type', 'Model', 'Record ID',
            'Description', 'IP Address', 'Risk Score', 'Risk Level',
            'Field Changes',
        ])
        for log in logs:
            writer.writerow([
                log.create_date.strftime('%Y-%m-%d %H:%M:%S') if log.create_date else '',
                log.user_id.login if log.user_id else '',
                log.event_type or '',
                log.model_name or '',
                log.record_id or '',
                (log.description or '')[:500],
                log.ip_address or '',
                log.risk_score or 0,
                log.risk_level or '',
                (log.field_changes or '')[:1000],
            ])

        data = output.getvalue().encode('utf-8')
        output.close()

        self.write({
            'file_data': base64.b64encode(data),
            'file_name': f'audit_logs_{self.date_from.strftime("%Y%m%d")}_{self.date_to.strftime("%Y%m%d")}.csv',
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'audit.export.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }