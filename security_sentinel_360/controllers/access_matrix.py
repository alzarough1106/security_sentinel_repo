from odoo import http, _
from odoo.exceptions import AccessError
from odoo.http import request


class AccessMatrixController(http.Controller):

    def _check_audit_manager(self):
        if not request.env.user.has_group('security_sentinel_360.group_session_audit_manager'):
            raise AccessError(_("You don't have access to the Access Matrix."))

    @http.route('/security_sentinel_360/matrix_data', type='json', auth='user')
    def get_matrix_data(self, options=None, **kwargs):
        self._check_audit_manager()
        return request.env['audit.access.matrix'].sudo().get_matrix_data(options or {})

    @http.route('/security_sentinel_360/matrix_explain', type='json', auth='user')
    def explain_access(self, user_id, model_id, **kwargs):
        self._check_audit_manager()
        return request.env['audit.access.matrix'].sudo().explain_user_access(
            int(user_id), int(model_id)
        )

    @http.route('/security_sentinel_360/matrix_find_users', type='json', auth='user')
    def find_users(self, model_name, permission='unlink', **kwargs):
        self._check_audit_manager()
        if permission not in ('read', 'write', 'create', 'unlink'):
            permission = 'unlink'
        return request.env['audit.access.matrix'].sudo().find_users_with_permission(
            model_name, permission
        )

    @http.route('/security_sentinel_360/matrix_compare', type='json', auth='user')
    def compare_users(self, user_id_a, user_id_b, **kwargs):
        self._check_audit_manager()
        return request.env['audit.access.matrix'].sudo().compare_users(
            int(user_id_a), int(user_id_b)
        )

    @http.route('/security_sentinel_360/matrix_filter_options', type='json', auth='user')
    def filter_options(self, **kwargs):
        self._check_audit_manager()
        env = request.env
        groups = env['res.groups'].sudo().search([], limit=200)
        companies = env['res.company'].sudo().search([])
        return {
            'groups': [{'id': g.id, 'name': g.display_name} for g in groups],
            'companies': [{'id': c.id, 'name': c.name} for c in companies],
        }