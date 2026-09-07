/** @odoo-module **/

import { Component, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

const COLORS = {
    green: "#2E9B6B", greenBg: "rgba(46, 155, 107, 0.15)",
    red: "#D6463D", redBg: "rgba(214, 70, 61, 0.15)",
    orange: "#E6A23C", orangeBg: "rgba(230, 162, 60, 0.15)",
    teal: "#2E86AB", tealBg: "rgba(46, 134, 171, 0.15)",
    purple: "#7C6CFF",
    grey: "#9AA3AE",
};

function nextIsoDay(isoDate) {
    const d = new Date(isoDate + "T00:00:00");
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
}

export class DeletionGuardDashboard extends Component {
    static template = "deletion_guard_pro.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({ loading: true, data: null });

        this.trendRef = useRef("trendChart");
        this.stateRef = useRef("stateChart");
        this.requesterRef = useRef("requesterChart");
        this.modelRef = useRef("modelChart");
        this._charts = {};

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadData();
        });

        onMounted(() => this.renderCharts());
        onWillUnmount(() => {
            Object.values(this._charts).forEach((c) => c && c.destroy());
        });
    }

    async loadData() {
        const data = await this.orm.call("deletion.request", "get_dashboard_data", []);
        this.state.data = data;
        this.state.loading = false;
    }

    async refresh() {
        this.state.loading = true;
        Object.values(this._charts).forEach((c) => c && c.destroy());
        this._charts = {};
        await this.loadData();
        this.renderCharts();
    }

    renderCharts() {
        if (!this.state.data) return;
        this._renderTrend();
        this._renderStateBreakdown();
        this._renderRequesterBar();
        this._renderModelBar();
    }

    _renderTrend() {
        const el = this.trendRef.el;
        if (!el) return;
        const d = this.state.data.trend;
        this._charts.trend = new Chart(el.getContext("2d"), {
            type: "line",
            data: {
                labels: d.labels,
                datasets: [
                    {
                        label: "Requested",
                        data: d.requested,
                        borderColor: COLORS.teal,
                        backgroundColor: COLORS.tealBg,
                        fill: true,
                        tension: 0.35,
                    },
                    {
                        label: "Confirmed / Deleted",
                        data: d.confirmed,
                        borderColor: COLORS.red,
                        backgroundColor: COLORS.redBg,
                        fill: true,
                        tension: 0.35,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    const dateFrom = d.dates[idx];
                    const dateTo = nextIsoDay(dateFrom);
                    this.openFiltered(
                        [["requested_date", ">=", `${dateFrom} 00:00:00`],
                         ["requested_date", "<", `${dateTo} 00:00:00`]],
                        `Deletion Requests - ${d.labels[idx]}`
                    );
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                },
                plugins: { legend: { position: "bottom" } },
            },
        });
    }

    _renderStateBreakdown() {
        const el = this.stateRef.el;
        if (!el) return;
        const d = this.state.data.state_breakdown;
        this._charts.state = new Chart(el.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: d.labels,
                datasets: [{
                    data: d.values,
                    backgroundColor: [COLORS.teal, COLORS.green, COLORS.red, COLORS.grey, COLORS.orange],
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    const stateKey = d.keys[idx];
                    this.openFiltered([["state", "=", stateKey]], `Deletion Requests - ${d.labels[idx]}`);
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                },
                plugins: { legend: { position: "bottom" } },
            },
        });
    }

    _renderRequesterBar() {
        const el = this.requesterRef.el;
        if (!el) return;
        const d = this.state.data.top_requesters;
        this._charts.requester = new Chart(el.getContext("2d"), {
            type: "bar",
            data: {
                labels: d.labels,
                datasets: [{ data: d.values, backgroundColor: COLORS.purple, borderRadius: 6 }],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    this.openFiltered(
                        [["requested_by", "=", d.ids[idx]]],
                        `Deletion Requests - ${d.labels[idx]}`
                    );
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    _renderModelBar() {
        const el = this.modelRef.el;
        if (!el) return;
        const d = this.state.data.top_models;
        this._charts.model = new Chart(el.getContext("2d"), {
            type: "bar",
            data: {
                labels: d.labels,
                datasets: [{ data: d.values, backgroundColor: COLORS.teal, borderRadius: 6 }],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                onClick: (evt, elements) => {
                    if (!elements.length) return;
                    const idx = elements[0].index;
                    this.openFiltered(
                        [["model_id", "=", d.ids[idx]]],
                        `Deletion Requests - ${d.labels[idx]}`
                    );
                },
                onHover: (evt, elements) => {
                    evt.native.target.style.cursor = elements.length ? "pointer" : "default";
                },
                plugins: { legend: { display: false } },
            },
        });
    }

    cellStyle(value, maxValue) {
        const max = Math.max(1, maxValue);
        const ratio = value / max;
        const alpha = value === 0 ? 0.05 : 0.15 + ratio * 0.75;
        const cursor = value > 0 ? "pointer" : "default";
        return `background-color: rgba(214, 70, 61, ${alpha}); color:${ratio > 0.55 ? "#fff" : "#333"}; cursor:${cursor};`;
    }

    maxInMatrix(matrix) {
        let max = 0;
        for (const row of matrix) {
            for (const v of row) {
                if (v > max) max = v;
            }
        }
        return max;
    }

    onHeatmapCellClick(dayIndex, modelIndex) {
        const h = this.state.data.heatmap;
        const value = h.matrix[dayIndex][modelIndex];
        if (!value) return;
        const dateFrom = h.day_dates[dayIndex];
        const dateTo = nextIsoDay(dateFrom);
        const modelId = h.model_ids[modelIndex];
        this.openFiltered(
            [["requested_date", ">=", `${dateFrom} 00:00:00`],
             ["requested_date", "<", `${dateTo} 00:00:00`],
             ["model_id", "=", modelId]],
            `Deletion Requests - ${h.day_labels[dayIndex]} - ${h.model_labels[modelIndex]}`
        );
    }

    openFiltered(domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: "deletion.request",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }

    openAll() { this.openFiltered([], "Deletion Requests"); }
    openPending() { this.openFiltered([["state", "=", "pending"]], "Pending Requests"); }
    openRejected() { this.openFiltered([["state", "=", "rejected"]], "Rejected Requests"); }
    openCompleted() { this.openFiltered([["state", "=", "done"]], "Completed Deletions"); }
    openCancelled() { this.openFiltered([["state", "=", "cancelled"]], "Cancelled Requests"); }
    openRestored() { this.openFiltered([["state", "=", "restored"]], "Restored Records"); }
    openDecided() {
        this.openFiltered([["state", "in", ["done", "rejected"]]], "Decided Requests (Done + Rejected)");
    }
    openRecycleBin() {
        this.openFiltered(
            [["is_recycle_bin", "=", true], ["restored", "=", false], ["purged", "=", false]],
            "Recycle Bin");
    }
}

registry.category("actions").add("deletion_guard_pro.dashboard", DeletionGuardDashboard);