/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

const COLORS = {
    green: "#2ecc71",
    red: "#e74c3c",
    blue: "#3498db",
    orange: "#f39c12",
    purple: "#9b59b6",
    teal: "#1abc9c",
    grey: "#95a5a6",
    yellow: "#f1c40f",
};

const STATE_COLOR_MAP = { active: COLORS.green, closed: COLORS.grey, killed: COLORS.red };
const METHOD_COLOR_MAP = {
    create: COLORS.teal, write: COLORS.blue, unlink: COLORS.red,
    read: COLORS.grey, module_install: COLORS.purple, module_uninstall: COLORS.orange,
};

export class AuditSessionDashboard extends Component {
    static template = "security_sentinel_360.Dashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, loading: true });

        this.trendRef = useRef("trendChart");
        this.stateRef = useRef("stateChart");
        this.actionsRef = useRef("actionsChart");
        this.usersRef = useRef("usersChart");
        this.modelsRef = useRef("modelsChart");
        this.charts = [];

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadData();
        });

        onMounted(() => this.renderCharts());
        onWillUnmount(() => this.charts.forEach((c) => c.destroy()));
    }

    async loadData() {
        this.state.data = await this.orm.call("audit.dashboard", "get_dashboard_data", []);
        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Generic window-action openers
    // ------------------------------------------------------------------
    _openWindow(resModel, domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    _openSessions(domain, name = "Sessions") {
        this._openWindow("res.users.session", domain, name);
    }

    _openAuditLogs(domain, name = "Audit Log") {
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

    // ------------------------------------------------------------------
    // KPI card handlers
    // ------------------------------------------------------------------
    openActiveSessions() {
        this._openSessions([["state", "=", "active"]], "Active Sessions");
    }

    openKilledSessions() {
        this._openSessions([["state", "=", "killed"]], "Killed Sessions");
    }

    openNewDevicesToday() {
        const domain = [["is_new_device", "=", true], ...this._todayRange("login_date")];
        this._openSessions(domain, "New Devices Today");
    }

    openLogsToday() {
        this._openAuditLogs(this._todayRange("create_date"), "Audit Logs Today");
    }

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

    // ------------------------------------------------------------------
    // Generic "view all" buttons (unfiltered)
    // ------------------------------------------------------------------
    openSessions() {
        this.action.doAction("security_sentinel_360.action_user_session");
    }

    openAuditLogs() {
        this.action.doAction("security_sentinel_360.action_audit_log");
    }

    // ------------------------------------------------------------------
    // Row click-throughs
    // ------------------------------------------------------------------
    openSessionRecord(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.users.session",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAuditLogRecord(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "audit.log",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ------------------------------------------------------------------
    // Chart rendering + click-through handlers
    // ------------------------------------------------------------------
    renderCharts() {
        if (!this.state.data) return;
        const d = this.state.data;

        // --- Activity Trend (line)
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
                        tension: 0.35,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    onHover: (evt, elements) => {
                        evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                    },
                    onClick: (evt, elements) => {
                        if (!elements.length) return;
                        const idx = elements[0].index;
                        const isoDay = d.activity_trend.keys[idx];
                        this._openAuditLogs(
                            [["create_date", ">=", `${isoDay} 00:00:00`], ["create_date", "<=", `${isoDay} 23:59:59`]],
                            `Activity on ${d.activity_trend.labels[idx]}`
                        );
                    },
                },
            }));
        }

        // --- Sessions by State (doughnut)
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
                    responsive: true, maintainAspectRatio: false,
                    onHover: (evt, elements) => {
                        evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                    },
                    onClick: (evt, elements) => {
                        if (!elements.length) return;
                        const idx = elements[0].index;
                        const key = d.sessions_by_state.keys[idx];
                        this._openSessions([["state", "=", key]], `Sessions — ${d.sessions_by_state.labels[idx]}`);
                    },
                },
            }));
        }

        // --- Actions by Type (doughnut)
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
                    responsive: true, maintainAspectRatio: false,
                    onHover: (evt, elements) => {
                        evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                    },
                    onClick: (evt, elements) => {
                        if (!elements.length) return;
                        const idx = elements[0].index;
                        const key = d.actions_by_type.keys[idx];
                        const domain = [["method", "=", key], ...this._daysAgoRange("create_date", 7)];
                        this._openAuditLogs(domain, `Actions — ${d.actions_by_type.labels[idx]} (7d)`);
                    },
                },
            }));
        }

        // --- Top Users (horizontal bar)
        if (this.usersRef.el) {
            this.charts.push(new Chart(this.usersRef.el.getContext("2d"), {
                type: "bar",
                data: {
                    labels: d.top_users.labels,
                    datasets: [{
                        label: "Activities",
                        data: d.top_users.data,
                        backgroundColor: COLORS.purple,
                        borderRadius: 6,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    onHover: (evt, elements) => {
                        evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                    },
                    onClick: (evt, elements) => {
                        if (!elements.length) return;
                        const idx = elements[0].index;
                        const userId = d.top_users.keys[idx];
                        if (!userId) return;
                        const domain = [["user_id", "=", userId], ...this._daysAgoRange("create_date", 30)];
                        this._openAuditLogs(domain, `Activity — ${d.top_users.labels[idx]} (30d)`);
                    },
                },
            }));
        }

        // --- Top Models (horizontal bar)
        if (this.modelsRef.el) {
            this.charts.push(new Chart(this.modelsRef.el.getContext("2d"), {
                type: "bar",
                data: {
                    labels: d.top_models.labels,
                    datasets: [{
                        label: "Touches",
                        data: d.top_models.data,
                        backgroundColor: COLORS.teal,
                        borderRadius: 6,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    onHover: (evt, elements) => {
                        evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                    },
                    onClick: (evt, elements) => {
                        if (!elements.length) return;
                        const idx = elements[0].index;
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

registry.category("actions").add("security_sentinel_360.dashboard", AuditSessionDashboard);