from datetime import timedelta
from odoo import models, fields, api


class GdprReportWizard(models.TransientModel):
    _name = 'gdpr.report.wizard'
    _description = 'Generate GDPR Report'

    report_type = fields.Selection([
        ('art30', 'Records of Processing Activities (Art. 30)'),
        ('subject_access', 'Data Subject Access Report (Art. 15)'),
    ], string='Report Type', required=True, default='art30')

    date_from = fields.Date(string='Period From', required=True,
                            default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string='Period To', required=True,
                          default=fields.Date.today)

    subject_partner_id = fields.Many2one('res.partner', string='Data Subject',
                                         help="Required for Subject Access Reports")

    name = fields.Char(string='Report Name', required=True,
                       default=lambda self: f"GDPR Report — {fields.Date.today()}")

    def action_generate(self):
        self.ensure_one()
        if self.report_type == 'subject_access' and not self.subject_partner_id:
            raise models.UserError("Please select a data subject for Subject Access Reports.")

        report = self.env['gdpr.report'].create({
            'name': self.name,
            'report_type': self.report_type,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'subject_partner_id': self.subject_partner_id.id if self.subject_partner_id else False,
        })
        return report.action_generate()