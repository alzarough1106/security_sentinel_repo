from odoo import models


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _audit(self, method):
        for module in self:
            self.env["audit.log"].sudo().create_log(
                "ir.module.module", module.id, method, None, module.shortdesc or module.name
            )

    def button_immediate_install(self):
        res = super().button_immediate_install()
        self._audit("module_install")
        return res

    def button_install(self):
        res = super().button_install()
        self._audit("module_install")
        return res

    def button_immediate_uninstall(self):
        # Delegated to super to avoid redundant duplicate audit logging
        return super().button_immediate_uninstall()

    def module_uninstall(self):
        res = super().module_uninstall()
        self._audit("module_uninstall")
        return res