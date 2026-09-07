/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class DeletionReasonDialog extends Component {
    static template = "deletion_guard.DeletionReasonDialog";
    static components = { Dialog };
    static props = {
        confirm: Function,
        cancel: Function,
        close: Function,
        title: String,
        body: String,
    };

    setup() {
        this.state = useState({ reason: "" });
    }

    onConfirm() {
        this.props.confirm(this.state.reason);
        this.props.close();
    }

    onCancel() {
        if (this.props.cancel) {
            this.props.cancel();
        }
        this.props.close();
    }
}