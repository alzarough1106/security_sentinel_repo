/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { FormController } from "@web/views/form/form_controller";
import { DeletionReasonDialog } from "./deletion_reason_dialog";

patch(FormController.prototype, {
    async deleteRecord() {
        const record = this.model.root;

        this.dialogService.add(DeletionReasonDialog, {
            title: _t("Bye-bye, record!"),
            body: _t("Are you sure you want to delete this record?"),
            confirm: async (reason) => {
                const context = {
                    ...record.context,
                    deletion_guard_reason: reason || false,
                };
                await this.orm.unlink(record.resModel, [record.resId], { context });
                this.env.config.historyBack();
            },
            cancel: () => {},
        });
    },
});