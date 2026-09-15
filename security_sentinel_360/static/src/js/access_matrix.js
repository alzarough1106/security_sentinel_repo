odoo.define('security_sentinel_360.access_matrix', function (require) {
    "use strict";

    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');
    const rpc = require('web.rpc');

    const { Component, hooks } = owl;
    const { useState, onWillStart } = hooks;

    class AccessMatrix extends Component {
        setup() {
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

        showNotification(message, type = "info") {
            core.bus.trigger('display_notification', {
                message: message,
                type: type,
                sticky: false,
            });
        }

        async loadFilterOptions() {
            try {
                const opts = await rpc.query({
                    route: "/security_sentinel_360/matrix_filter_options",
                    params: {},
                });
                this.state.filterOptions = opts || { groups: [], companies: [] };
            } catch (e) {
                console.error("Filter options load error:", e);
            }
        }

        async loadMatrix() {
            this.state.loading = true;
            try {
                const data = await rpc.query({
                    route: "/security_sentinel_360/matrix_data",
                    params: {
                        options: {
                            group_id: this.state.filters.group_id ? parseInt(this.state.filters.group_id) : null,
                            company_id: this.state.filters.company_id ? parseInt(this.state.filters.company_id) : null,
                            sensitive_only: this.state.filters.sensitive_only,
                            show_share_users: this.state.filters.show_share_users,
                            limit_users: 80,
                            limit_models: 60,
                        },
                    },
                });
                this.state.data = data || { users: [], models: [], matrix: {}, stats: {} };
            } catch (e) {
                console.error("Matrix load error:", e);
                this.showNotification("Error loading matrix: " + (e.message || e), "danger");
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
            if (!search || !this.state.data || !this.state.data.models) {
                return (this.state.data && this.state.data.models) || [];
            }
            return this.state.data.models.filter(m =>
                m.model.toLowerCase().includes(search) ||
                (m.name || "").toLowerCase().includes(search)
            );
        }

        getMatrixCell(userId, modelId) {
            if (!this.state.data || !this.state.data.matrix) return null;
            const userMatrix = this.state.data.matrix[userId] || {};
            return userMatrix[modelId] || null;
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
            if (!perms || perms.admin) return perms && perms.admin ? "★" : "—";
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

        stopEventPropagation(ev) {
            if (ev && ev.stopPropagation) {
                ev.stopPropagation();
            }
        }

        // ----- EXPLAIN MODAL -----
        async openExplainModal(userId, modelId) {
            this.state.explainModal = { visible: true, data: null, loading: true };
            try {
                const data = await rpc.query({
                    route: "/security_sentinel_360/matrix_explain",
                    params: {
                        user_id: userId,
                        model_id: modelId,
                    },
                });
                this.state.explainModal.data = data;
            } catch (e) {
                this.showNotification("Error: " + (e.message || e), "danger");
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
                this.showNotification("Select both users", "warning");
                return;
            }
            m.loading = true;
            try {
                m.data = await rpc.query({
                    route: "/security_sentinel_360/matrix_compare",
                    params: {
                        user_id_a: parseInt(m.userA),
                        user_id_b: parseInt(m.userB),
                    },
                });
            } catch (e) {
                this.showNotification("Error: " + (e.message || e), "danger");
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
                m.data = await rpc.query({
                    route: "/security_sentinel_360/matrix_find_users",
                    params: {
                        model_name: m.modelName,
                        permission: m.permission,
                    },
                });
            } catch (e) {
                this.showNotification("Error: " + (e.message || e), "danger");
            }
            m.loading = false;
        }

        // ----- ACTIONS -----
        openExport() {
            this.props.doAction("security_sentinel_360.action_access_matrix_export_wizard");
        }

        openSnapshots() {
            this.props.doAction("security_sentinel_360.action_access_matrix_snapshot");
        }

        refresh() {
            this.loadMatrix();
        }
    }

    AccessMatrix.template = "security_sentinel_360.AccessMatrix";

    const AccessMatrixAction = AbstractAction.extend({
        hasControlPanel: false,

        start: async function () {
            await this._super(...arguments);
            this.component = new AccessMatrix(null, {
                doAction: this.do_action.bind(this),
            });
            await this.component.mount(this.el);
        },

        destroy: function () {
            if (this.component) {
                this.component.destroy();
            }
            this._super(...arguments);
        }
    });

    core.action_registry.add('security_sentinel_360.access_matrix', AccessMatrixAction);

    return AccessMatrixAction;
});