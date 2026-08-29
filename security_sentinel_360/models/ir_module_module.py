from odoo import models


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def _audit(self, method):
        for module in self:
            self.env["audit.log"].sudo().create_log(
                "ir.module.module", module.id, method, None, module.shortdesc or module.name
            )

    def button_immediate_install(self):
        self._audit("module_install")
        return super().button_immediate_install()

    def button_install(self):
        self._audit("module_install")
        return super().button_install()

    def button_immediate_uninstall(self):
        self._audit("module_uninstall")
        return super().button_immediate_uninstall()

    def module_uninstall(self):
        self._audit("module_uninstall")
        return super().module_uninstall()