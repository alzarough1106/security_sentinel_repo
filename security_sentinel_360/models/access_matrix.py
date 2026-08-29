"""
User Access Matrix Engine
Computes effective permissions for users on models.
"""
import logging
from collections import defaultdict
from odoo import models, fields, api, _
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)


class AccessMatrix(models.AbstractModel):
    _name = 'audit.access.matrix'
    _description = 'User Access Matrix Engine'

    def _check_audit_access(self):
        """Raise AccessError unless the calling user is in the Audit & Compliance group or System Admin."""
        user = self.env.user
        if not (user.has_group('security_sentinel_360.group_session_audit_manager') or user.has_group('base.group_system')):
            raise AccessError(_(
                "You do not have access to the Audit & Compliance access matrix."
            ))

    @api.model
    def get_matrix_data(self, options=None):
        self._check_audit_access()
        options = options or {}

        def _safe_int(val, default=None):
            if val in (None, '', 'null', 'undefined', False):
                return default
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        group_id = _safe_int(options.get('group_id'))
        company_id = _safe_int(options.get('company_id'))
        limit_users = _safe_int(options.get('limit_users'), 50)
        limit_models = _safe_int(options.get('limit_models'), 100)

        Users = self.env['res.users'].sudo()
        Models = self.env['ir.model'].sudo()
        Access = self.env['ir.model.access'].sudo()

        # ----- USER FILTERING -----
        user_domain = [('active', '=', True)]
        if not options.get('show_share_users'):
            user_domain.append(('share', '=', False))
        if group_id:
            user_domain.append(('group_ids', 'in', [group_id]))  # was groups_id
        if company_id:
            user_domain.append(('company_ids', 'in', [company_id]))

        users = Users.search(user_domain, limit=limit_users, order='login')

        # ----- MODEL FILTERING -----
        model_domain = [('transient', '=', False)]
        model_domain += [
            '!', ('model', '=like', 'ir.%'),
            '!', ('model', '=like', 'base_%'),
            '!', ('model', '=like', 'mail.%'),
            '!', ('model', '=like', 'bus.%'),
            '!', ('model', '=like', 'web_%'),
            '!', ('model', '=like', 'audit.%'),
        ]
        if options.get('sensitive_only'):
            model_domain.append(('model', 'in', list(self._get_sensitive_models())))

        models_recs = Models.search(model_domain, limit=limit_models, order='model')
        sensitive_set = self._get_sensitive_models()

        # ----- BUILD USER LIST -----
        admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
        user_list = []
        for u in users:
            user_list.append({
                'id': u.id,
                'login': u.login,
                'name': u.name,
                'is_admin': bool(admin_group and admin_group in u.group_ids),  # was groups_id
                'company_ids': u.company_ids.ids,
            })

        # ----- BUILD MODEL LIST -----
        model_list = []
        for m in models_recs:
            model_list.append({
                'id': m.id,
                'model': m.model,
                'name': m.name,
                'sensitive': m.model in sensitive_set,
            })

        # ----- COMPUTE MATRIX -----
        all_access = Access.search([('model_id', 'in', models_recs.ids)])
        access_by_model = defaultdict(list)
        for a in all_access:
            access_by_model[a.model_id.id].append({
                'group_id': a.group_id.id if a.group_id else None,
                'group_name': a.group_id.display_name if a.group_id else 'Public',
                'read': a.perm_read,
                'write': a.perm_write,
                'create': a.perm_create,
                'unlink': a.perm_unlink,
            })

        user_groups = {u.id: set(u.group_ids.ids) for u in users}  # was groups_id

        matrix = {}
        for u in users:
            matrix[u.id] = {}
            user_group_set = user_groups[u.id]
            is_admin = admin_group and admin_group.id in user_group_set

            for m in models_recs:
                if is_admin:
                    matrix[u.id][m.id] = {
                        'read': True, 'write': True,
                        'create': True, 'unlink': True,
                        'admin': True,
                        'sources': ['Administrator (full access)'],
                    }
                    continue

                rules = access_by_model.get(m.id, [])
                perms = {'read': False, 'write': False, 'create': False, 'unlink': False}
                sources = []

                for rule in rules:
                    if rule['group_id'] is None or rule['group_id'] in user_group_set:
                        granted = []
                        if rule['read'] and not perms['read']:
                            perms['read'] = True
                            granted.append('R')
                        if rule['write'] and not perms['write']:
                            perms['write'] = True
                            granted.append('W')
                        if rule['create'] and not perms['create']:
                            perms['create'] = True
                            granted.append('C')
                        if rule['unlink'] and not perms['unlink']:
                            perms['unlink'] = True
                            granted.append('D')
                        if granted:
                            sources.append(f"{rule['group_name']} → {''.join(granted)}")

                matrix[u.id][m.id] = {
                    **perms,
                    'admin': False,
                    'sources': sources,
                }

        return {
            'users': user_list,
            'models': model_list,
            'matrix': matrix,
            'sensitive_models': list(sensitive_set),
            'options': options,
            'stats': {
                'user_count': len(user_list),
                'model_count': len(model_list),
                'admin_count': sum(1 for u in user_list if u['is_admin']),
            },
        }

    @api.model
    def _get_sensitive_models(self):
        """Return set of model technical names that are considered sensitive."""
        return {
            'res.users', 'res.groups', 'res.partner',
            'ir.rule', 'ir.model.access', 'ir.model', 'ir.model.fields',
            'ir.config_parameter', 'res.company', 'res.config.settings',
            'account.account', 'account.move', 'account.payment',
            'account.journal', 'account.tax',
            'hr.employee', 'hr.contract', 'hr.payslip',
            'audit.config', 'audit.rule', 'audit.alert.rule',
        }

    @api.model
    def explain_user_access(self, user_id, model_id):
        """Return detailed explanation of access rules."""
        self._check_audit_access()
        user = self.env['res.users'].sudo().browse(user_id)
        model = self.env['ir.model'].sudo().browse(model_id)
        if not user.exists() or not model.exists():
            return {'error': 'User or model not found'}

        admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
        is_admin = admin_group and admin_group in user.group_ids  # was groups_id

        access_rules = self.env['ir.model.access'].sudo().search([
            ('model_id', '=', model_id),
        ])
        applicable = []
        not_applicable = []
        for rule in access_rules:
            entry = {
                'rule_name': rule.name or '',
                'group': rule.group_id.display_name if rule.group_id else 'Public (no group)',
                'read': bool(rule.perm_read),
                'write': bool(rule.perm_write),
                'create': bool(rule.perm_create),
                'unlink': bool(rule.perm_unlink),
            }
            if not rule.group_id or rule.group_id in user.group_ids:  # was groups_id
                applicable.append(entry)
            else:
                not_applicable.append(entry)

        record_rule_info = []
        try:
            record_rules = self.env['ir.rule'].sudo().search([
                ('model_id', '=', model_id),
                ('active', '=', True),
            ])
            for r in record_rules:
                try:
                    is_global = not bool(r.groups)
                    record_rule_info.append({
                        'name': r.name or 'Unnamed Rule',
                        'global': is_global,
                        'groups': r.groups.mapped('display_name') if r.groups else [],
                        'domain': r.domain_force or '[]',
                        'perm_read': bool(r.perm_read),
                        'perm_write': bool(r.perm_write),
                        'perm_create': bool(r.perm_create),
                        'perm_unlink': bool(r.perm_unlink),
                    })
                except Exception as e:
                    _logger.warning("Failed to read ir.rule %s: %s", r.id, e)
                    continue
        except Exception as e:
            _logger.warning("Failed to fetch record rules: %s", e)

        return {
            'user': {
                'id': user.id,
                'login': user.login,
                'name': user.name,
            },
            'model': {
                'id': model.id,
                'model': model.model,
                'name': model.name,
            },
            'is_admin': bool(is_admin),
            'user_groups': user.group_ids.mapped('display_name'),  # was groups_id
            'applicable_rules': applicable,
            'not_applicable_rules': not_applicable,
            'record_rules': record_rule_info,
        }

    @api.model
    def find_users_with_permission(self, model_name, permission='unlink'):
        """Reverse search: find all users with a specific permission on a model."""
        self._check_audit_access()
        model = self.env['ir.model'].sudo().search([('model', '=', model_name)], limit=1)
        if not model:
            return []

        Access = self.env['ir.model.access'].sudo()
        perm_field = f'perm_{permission}'
        access_rules = Access.search([
            ('model_id', '=', model.id),
            (perm_field, '=', True),
        ])

        groups_with_perm = self.env['res.groups']
        global_grant = False
        for rule in access_rules:
            if not rule.group_id:
                global_grant = True
            else:
                groups_with_perm |= rule.group_id

        Users = self.env['res.users'].sudo()
        if global_grant:
            users = Users.search([('active', '=', True), ('share', '=', False)])
        else:
            users = Users.search([
                ('active', '=', True),
                ('group_ids', 'in', groups_with_perm.ids),  # was groups_id
            ])

        admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
        if admin_group:
            users |= Users.search([('group_ids', 'in', [admin_group.id])])  # was groups_id, also fix scalar->list bug

        return [{
            'id': u.id,
            'login': u.login,
            'name': u.name,
            'groups': u.group_ids.mapped('display_name'),  # was groups_id
        } for u in users]

    @api.model
    def compare_users(self, user_id_a, user_id_b, limit_models=200):
        """Compare permissions of two users — return diff."""
        self._check_audit_access()
        Users = self.env['res.users'].sudo()
        user_a = Users.browse(user_id_a)
        user_b = Users.browse(user_id_b)
        if not user_a.exists() or not user_b.exists():
            return {'error': 'User not found'}

        Models = self.env['ir.model'].sudo()
        models_recs = Models.search([
            ('transient', '=', False),
            '!', ('model', '=like', 'ir.%'),
            '!', ('model', '=like', 'base_%'),
        ], limit=limit_models, order='model')

        admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
        Access = self.env['ir.model.access'].sudo()
        all_rules = Access.search([('model_id', 'in', models_recs.ids)])
        rules_by_model = defaultdict(list)
        for r in all_rules:
            rules_by_model[r.model_id.id].append(r)

        def compute_perms(user):
            is_admin = admin_group and admin_group in user.group_ids  # was groups_id
            user_group_ids = set(user.group_ids.ids)
            result = {}
            for m in models_recs:
                if is_admin:
                    result[m.model] = {'read': True, 'write': True, 'create': True, 'unlink': True}
                    continue
                perms = {'read': False, 'write': False, 'create': False, 'unlink': False}
                rules = rules_by_model.get(m.id, [])
                for r in rules:
                    if not r.group_id or r.group_id.id in user_group_ids:
                        if r.perm_read: perms['read'] = True
                        if r.perm_write: perms['write'] = True
                        if r.perm_create: perms['create'] = True
                        if r.perm_unlink: perms['unlink'] = True
                result[m.model] = perms
            return result

        perms_a = compute_perms(user_a)
        perms_b = compute_perms(user_b)

        diff = []
        for m in models_recs:
            pa = perms_a[m.model]
            pb = perms_b[m.model]
            if pa != pb:
                diff.append({
                    'model': m.model,
                    'name': m.name,
                    'a': pa,
                    'b': pb,
                })

        return {
            'user_a': {'id': user_a.id, 'login': user_a.login, 'name': user_a.name},
            'user_b': {'id': user_b.id, 'login': user_b.login, 'name': user_b.name},
            'differences': diff,
            'total_models_compared': len(models_recs),
            'identical_count': len(models_recs) - len(diff),
        }