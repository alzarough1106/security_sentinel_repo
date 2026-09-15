odoo.define('security_sentinel_360.audit_dashboard', function (require) {
    "use strict";

    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');
    const rpc = require('web.rpc');
    const ajax = require('web.ajax');

    const { Component, hooks } = owl;
    const { useState, onWillStart, onWillUnmount, useRef } = hooks;

    const COLORS = {
        green: "#2ecc71", red: "#e74c3c", blue: "#3498db", orange: "#f39c12",
        purple: "#9b59b6", teal: "#1abc9c", grey: "#95a5a6", yellow: "#f1c40f",
    };

    const STATE_COLOR_MAP = { active: COLORS.green, closed: COLORS.grey, killed: COLORS.red };
    const METHOD_COLOR_MAP = {
        create: COLORS.teal, write: COLORS.blue, unlink: COLORS.red,
        read: COLORS.grey, module_install: COLORS.purple, module_uninstall: COLORS.orange,
    };

    class AuditSessionDashboard extends Component {
        setup() {
            this.state = useState({ data: null, loading: true });

            this.trendRef = useRef("trendChart");
            this.stateRef = useRef("stateChart");
            this.actionsRef = useRef("actionsChart");
            this.usersRef = useRef("usersChart");
            this.modelsRef = useRef("modelsChart");
            this.charts = [];

            this.openActiveSessions = this.openActiveSessions.bind(this);
            this.openKilledSessions = this.openKilledSessions.bind(this);
            this.openNewDevicesToday = this.openNewDevicesToday.bind(this);
            this.openLogsToday = this.openLogsToday.bind(this);
            this.openCreates7d = this.openCreates7d.bind(this);
            this.openWrites7d = this.openWrites7d.bind(this);
            this.openDeletes7d = this.openDeletes7d.bind(this);
            this.openSessions = this.openSessions.bind(this);
            this.openAuditLogs = this.openAuditLogs.bind(this);
            this.openSessionRecord = this.openSessionRecord.bind(this);
            this.openAuditLogRecord = this.openAuditLogRecord.bind(this);

            onWillStart(async () => {
                if (typeof window.Chart === "undefined") {
                    await ajax.loadJS("/web/static/lib/Chart/Chart.js");
                }
                await this.loadData();
            });

            onWillUnmount(() => this._destroyCharts());
        }

        _destroyCharts() {
            this.charts.forEach((c) => c && c.destroy());
            this.charts = [];
        }

        async loadData() {
            this.state.data = await rpc.query({
                model: "audit.dashboard",
                method: "get_dashboard_data",
                args: [],
            });
            this.state.loading = false;
        }

        _openWindow(resModel, domain = [], name = "") {
            this.props.doAction({
                type: "ir.actions.act_window",
                name: name,
                res_model: resModel,
                views: [[false, "list"], [false, "form"]],
                domain: domain || [],
                target: "current",
            });
        }

        _openSessions(domain = [], name = "Sessions") {
            this._openWindow("res.users.session", domain, name);
        }

        _openAuditLogs(domain = [], name = "Audit Log") {
            this._openWindow("audit.log", domain, name);
        }

        _todayRange(fieldName) {
            const start = new Date();
            start.setHours(0, 0, 0, 0);
            const end = new Date();
            end.setHours(23, 59, 59, 999);
            return [
                [fieldName, ">=", start.toISOString().slice(0, 19).replace("T", " ")],
                [fieldName, "<=", end.toISOString().slice(0, 19).replace("T", " ")],
            ];
        }

        _daysAgoRange(fieldName, days) {
            const since = new Date();
            since.setDate(since.getDate() - days);
            return [[fieldName, ">=", since.toISOString().slice(0, 19).replace("T", " ")]];
        }

        openActiveSessions() { this._openSessions([["state", "=", "active"]], "Active Sessions"); }
        openKilledSessions() { this._openSessions([["state", "=", "killed"]], "Killed Sessions"); }
        openNewDevicesToday() {
            const domain = [["is_new_device", "=", true], ...this._todayRange("login_date")];
            this._openSessions(domain, "New Devices Today");
        }
        openLogsToday() { this._openAuditLogs(this._todayRange("create_date"), "Audit Logs Today"); }
        openCreates7d() {
            const domain = [["method", "=", "create"], ...this._daysAgoRange("create_date", 7)];
            this._openAuditLogs(domain, "Creates (Last 7 Days)");
        }
        openWrites7d() {
            const domain = [["method", "=", "write"], ...this._daysAgoRange("create_date", 7)];
            this._openAuditLogs(domain, "Updates (Last 7 Days)");
        }
        openDeletes7d() {
            const domain = [["method", "=", "unlink"], ...this._daysAgoRange("create_date", 7)];
            this._openAuditLogs(domain, "Deletes (Last 7 Days)");
        }
        openSessions() { this.props.doAction("security_sentinel_360.action_user_session"); }
        openAuditLogs() { this.props.doAction("security_sentinel_360.action_audit_log"); }

        openSessionRecord(id) {
            if (!id) return;
            this.props.doAction({
                type: "ir.actions.act_window",
                res_model: "res.users.session",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
        }

        openAuditLogRecord(id) {
            if (!id) return;
            this.props.doAction({
                type: "ir.actions.act_window",
                res_model: "audit.log",
                res_id: id,
                views: [[false, "form"]],
                target: "current",
            });
        }

        renderCharts() {
            if (!this.state.data || !this.trendRef.el) return;
            this._destroyCharts();
            const d = this.state.data;

            if (this.trendRef.el) {
                this.charts.push(new Chart(this.trendRef.el.getContext("2d"), {
                    type: "line",
                    data: {
                        labels: d.activity_trend.labels,
                        datasets: [{
                            label: "Activities",
                            data: d.activity_trend.data,
                            borderColor: COLORS.blue,
                            backgroundColor: "rgba(52,152,219,0.15)",
                            fill: true,
                            lineTension: 0.35,
                            pointRadius: 4,
                            pointHoverRadius: 6,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        legend: { display: false },
                        hover: {
                            onHover: (evt, elements) => {
                                if (evt && evt.target) {
                                    evt.target.style.cursor = elements.length ? "pointer" : "default";
                                }
                            },
                        },
                        onClick: (evt, elements) => {
                            if (!elements || !elements.length) return;
                            const idx = elements[0]._index;
                            const isoDay = d.activity_trend.keys[idx];
                            if (!isoDay) return;
                            this._openAuditLogs(
                                [["create_date", ">=", `${isoDay} 00:00:00`], ["create_date", "<=", `${isoDay} 23:59:59`]],
                                `Activity on ${d.activity_trend.labels[idx]}`
                            );
                        },
                    },
                }));
            }

            if (this.stateRef.el) {
                this.charts.push(new Chart(this.stateRef.el.getContext("2d"), {
                    type: "doughnut",
                    data: {
                        labels: d.sessions_by_state.labels,
                        datasets: [{
                            data: d.sessions_by_state.data,
                            backgroundColor: d.sessions_by_state.keys.map((k) => STATE_COLOR_MAP[k] || COLORS.grey),
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        hover: {
                            onHover: (evt, elements) => {
                                if (evt && evt.target) {
                                    evt.target.style.cursor = elements.length ? "pointer" : "default";
                                }
                            },
                        },
                        onClick: (evt, elements) => {
                            if (!elements || !elements.length) return;
                            const idx = elements[0]._index;
                            const key = d.sessions_by_state.keys ? d.sessions_by_state.keys[idx] : undefined;
                            if (key === undefined) return;
                            this._openSessions([["state", "=", key]], `Sessions — ${d.sessions_by_state.labels[idx] || key}`);
                        },
                    },
                }));
            }

            if (this.actionsRef.el) {
                this.charts.push(new Chart(this.actionsRef.el.getContext("2d"), {
                    type: "doughnut",
                    data: {
                        labels: d.actions_by_type.labels,
                        datasets: [{
                            data: d.actions_by_type.data,
                            backgroundColor: d.actions_by_type.keys.map((k) => METHOD_COLOR_MAP[k] || COLORS.grey),
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        hover: {
                            onHover: (evt, elements) => {
                                if (evt && evt.target) {
                                    evt.target.style.cursor = elements.length ? "pointer" : "default";
                                }
                            },
                        },
                        onClick: (evt, elements) => {
                            if (!elements || !elements.length) return;
                            const idx = elements[0]._index;
                            const key = d.actions_by_type.keys ? d.actions_by_type.keys[idx] : undefined;
                            if (key === undefined) return;
                            const domain = [["method", "=", key], ...this._daysAgoRange("create_date", 7)];
                            this._openAuditLogs(domain, `Actions — ${d.actions_by_type.labels[idx] || key} (7d)`);
                        },
                    },
                }));
            }

            if (this.usersRef.el) {
                this.charts.push(new Chart(this.usersRef.el.getContext("2d"), {
                    type: "horizontalBar",
                    data: {
                        labels: d.top_users.labels,
                        datasets: [{
                            label: "Activities",
                            data: d.top_users.data,
                            backgroundColor: COLORS.purple,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        legend: { display: false },
                        hover: {
                            onHover: (evt, elements) => {
                                if (evt && evt.target) {
                                    evt.target.style.cursor = elements.length ? "pointer" : "default";
                                }
                            },
                        },
                        onClick: (evt, elements) => {
                            if (!elements || !elements.length) return;
                            const idx = elements[0]._index;
                            const userId = d.top_users.keys[idx];
                            if (!userId) return;
                            const domain = [["user_id", "=", userId], ...this._daysAgoRange("create_date", 30)];
                            this._openAuditLogs(domain, `Activity — ${d.top_users.labels[idx]} (30d)`);
                        },
                    },
                }));
            }

            if (this.modelsRef.el) {
                this.charts.push(new Chart(this.modelsRef.el.getContext("2d"), {
                    type: "horizontalBar",
                    data: {
                        labels: d.top_models.labels,
                        datasets: [{
                            label: "Touches",
                            data: d.top_models.data,
                            backgroundColor: COLORS.teal,
                        }],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        legend: { display: false },
                        hover: {
                            onHover: (evt, elements) => {
                                if (evt && evt.target) {
                                    evt.target.style.cursor = elements.length ? "pointer" : "default";
                                }
                            },
                        },
                        onClick: (evt, elements) => {
                            if (!elements || !elements.length) return;
                            const idx = elements[0]._index;
                            const modelName = d.top_models.keys[idx];
                            if (!modelName) return;
                            const domain = [["model_name", "=", modelName], ...this._daysAgoRange("create_date", 30)];
                            this._openAuditLogs(domain, `${d.top_models.labels[idx]} — Activity (30d)`);
                        },
                    },
                }));
            }
        }
    }

    AuditSessionDashboard.template = "security_sentinel_360.dashboard";

    const AuditDashboardAction = AbstractAction.extend({
        hasControlPanel: false,

        start: async function () {
            await this._super(...arguments);

            // Align this action's own root to the top.
            this.$el.addClass(
                'o_audit_dashboard_action w-100 h-100 d-flex flex-column justify-content-start align-items-stretch'
            );

            // Fix the real ancestor containers too (see _alignParents doc).
            this._alignParents();

            this.component = new AuditSessionDashboard(null, {
                doAction: this.do_action.bind(this)
            });
            await this.component.mount(this.el);
        },

        /**
         * Odoo vertically centers the `.o_content` of client actions that
         * have no control panel (hasControlPanel: false). Because
         * `.o_audit_dashboard` is actually a GRANDCHILD of `.o_content`
         * (.o_content > .o_action > .o_audit_dashboard), a CSS
         * `:has(> .o_audit_dashboard)` direct-child selector never
         * matches `.o_content`, so it kept centering our (shorter than
         * viewport) dashboard, leaving a large blank gap above it.
         *
         * We fix this reliably from JS by marking + styling the actual
         * ancestor nodes, which also works on browsers without CSS
         * `:has()` support.
         */
        _alignParents: function () {
            const $content = this.$el.closest('.o_content');
            const $manager = this.$el.closest('.o_action_manager');

            $content.addClass('o_audit_dashboard_content').css({
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'flex-start',
                alignItems: 'stretch',
                height: '100%',
            });

            $manager.addClass('o_audit_dashboard_manager').css({
                display: 'flex',
                flexDirection: 'column',
            });
        },

        on_attach_callback: function () {
            this._super(...arguments);
            // Re-apply: when returning via breadcrumbs the action can be
            // re-attached to a freshly built .o_content/.o_action wrapper.
            this._alignParents();
            if (this.component) {
                setTimeout(() => this.component.renderCharts(), 0);
            }
        },

        destroy: function () {
            if (this.component) {
                this.component.destroy();
            }
            this._super(...arguments);
        }
    });

    core.action_registry.add('security_sentinel_360.dashboard', AuditDashboardAction);

    return AuditDashboardAction;
});