/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class AccessMatrix extends Component {
    static template = "security_sentinel_360.AccessMatrix";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.rpc = useService("rpc");

        this.state = useState({
            loading: true,
            data: { users: [], models: [], matrix: {}, stats: {} },
            filters: {
                group_id: null,
                company_id: null,
                sensitive_only: false,
                show_share_users: false,
                search: "",
            },
            filterOptions: { groups: [], companies: [] },
            // Modal state
            explainModal: { visible: false, data: null, loading: false },
            compareModal: { visible: false, data: null, loading: false, userA: null, userB: null },
            findModal: { visible: false, data: null, loading: false, modelName: "", permission: "unlink" },
        });

        onWillStart(async () => {
            await this.loadFilterOptions();
            await this.loadMatrix();
        });
    }

    async loadFilterOptions() {
        try {
            const opts = await this.rpc("/security_sentinel_360/matrix_filter_options", {});
            this.state.filterOptions = opts;
        } catch (e) {
            console.error("Filter options load error:", e);
        }
    }

    async loadMatrix() {
        this.state.loading = true;
        try {
            const data = await this.rpc("/security_sentinel_360/matrix_data", {
                options: {
                    group_id: this.state.filters.group_id,
                    company_id: this.state.filters.company_id,
                    sensitive_only: this.state.filters.sensitive_only,
                    show_share_users: this.state.filters.show_share_users,
                    limit_users: 80,
                    limit_models: 60,
                },
            });
            this.state.data = data;
        } catch (e) {
            console.error("Matrix load error:", e);
            this.notification.add("Error loading matrix: " + e.message, { type: "danger" });
        }
        this.state.loading = false;
    }

    onFilterChange() {
        this.loadMatrix();
    }

    onSearchInput(ev) {
        this.state.filters.search = ev.target.value.toLowerCase();
    }

    get filteredModels() {
        const search = this.state.filters.search;
        if (!search) return this.state.data.models;
        return this.state.data.models.filter(m =>
            m.model.toLowerCase().includes(search) ||
            (m.name || "").toLowerCase().includes(search)
        );
    }

    getCellClass(perms) {
        if (!perms) return "matrix-cell-none";
        if (perms.admin) return "matrix-cell-admin";
        if (perms.unlink) return "matrix-cell-full";
        if (perms.write || perms.create) return "matrix-cell-write";
        if (perms.read) return "matrix-cell-read";
        return "matrix-cell-none";
    }

    getCellLabel(perms) {
        if (!perms || perms.admin) return perms?.admin ? "★" : "—";
        const flags = [];
        if (perms.read) flags.push("R");
        if (perms.write) flags.push("W");
        if (perms.create) flags.push("C");
        if (perms.unlink) flags.push("D");
        return flags.length ? flags.join("") : "—";
    }

    getCellTooltip(user, model, perms) {
        if (!perms) return "";
        const lines = [
            `User: ${user.login}`,
            `Model: ${model.model}`,
            "",
        ];
        if (perms.admin) {
            lines.push("Administrator (full access)");
        } else {
            lines.push(`Read: ${perms.read ? "✓" : "✗"}`);
            lines.push(`Write: ${perms.write ? "✓" : "✗"}`);
            lines.push(`Create: ${perms.create ? "✓" : "✗"}`);
            lines.push(`Delete: ${perms.unlink ? "✓" : "✗"}`);
            if (perms.sources && perms.sources.length) {
                lines.push("");
                lines.push("Sources:");
                perms.sources.forEach(s => lines.push("  • " + s));
            }
        }
        return lines.join("\n");
    }

    // ----- EXPLAIN MODAL -----
    async openExplainModal(userId, modelId) {
        this.state.explainModal = { visible: true, data: null, loading: true };
        try {
            const data = await this.rpc("/security_sentinel_360/matrix_explain", {
                user_id: userId, model_id: modelId,
            });
            this.state.explainModal.data = data;
        } catch (e) {
            this.notification.add("Error: " + e.message, { type: "danger" });
        }
        this.state.explainModal.loading = false;
    }

    closeExplainModal() {
        this.state.explainModal.visible = false;
    }

    // ----- COMPARE MODAL -----
    openCompareModal() {
        this.state.compareModal = {
            visible: true, data: null, loading: false,
            userA: null, userB: null,
        };
    }

    closeCompareModal() {
        this.state.compareModal.visible = false;
    }

    async runCompare() {
        const m = this.state.compareModal;
        if (!m.userA || !m.userB) {
            this.notification.add("Select both users", { type: "warning" });
            return;
        }
        m.loading = true;
        try {
            m.data = await this.rpc("/security_sentinel_360/matrix_compare", {
                user_id_a: parseInt(m.userA), user_id_b: parseInt(m.userB),
            });
        } catch (e) {
            this.notification.add("Error: " + e.message, { type: "danger" });
        }
        m.loading = false;
    }

    // ----- FIND MODAL -----
    openFindModal() {
        this.state.findModal = {
            visible: true, data: null, loading: false,
            modelName: "res.partner", permission: "unlink",
        };
    }

    closeFindModal() {
        this.state.findModal.visible = false;
    }

    async runFind() {
        const m = this.state.findModal;
        if (!m.modelName) return;
        m.loading = true;
        try {
            m.data = await this.rpc("/security_sentinel_360/matrix_find_users", {
                model_name: m.modelName, permission: m.permission,
            });
        } catch (e) {
            this.notification.add("Error: " + e.message, { type: "danger" });
        }
        m.loading = false;
    }

    // ----- ACTIONS -----
    openExport() {
        this.action.doAction("security_sentinel_360.action_access_matrix_export_wizard");
    }

    openSnapshots() {
        this.action.doAction("security_sentinel_360.action_access_matrix_snapshot");
    }

    refresh() {
        this.loadMatrix();
    }
}

registry.category("actions").add("security_sentinel_360.access_matrix", AccessMatrix);