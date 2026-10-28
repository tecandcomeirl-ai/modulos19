/* global Chart, luxon */
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const REFRESH_INTERVAL = 60000;

export class EaWhatsappDashboard extends Component {
    static template = "ea_whatsapp_connector.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rootRef = useRef("root");
        this.canvasRef = useRef("chart");
        this.periods = [
            { days: 1, label: _t("Today") },
            { days: 7, label: _t("7 days") },
            { days: 30, label: _t("30 days") },
            { days: 90, label: _t("90 days") },
        ];
        this.state = useState({ days: 7, accountId: false, data: null, showTable: false, loading: false });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        useEffect(
            () => this.renderChart(),
            () => [this.state.data]
        );
        this.timer = setInterval(() => this.load(), REFRESH_INTERVAL);
        onWillUnmount(() => {
            clearInterval(this.timer);
            this.chart?.destroy();
        });
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("ea.whatsapp.message", "get_dashboard_data", [], {
                days: this.state.days,
                account_id: this.state.accountId,
            });
        } finally {
            this.state.loading = false;
        }
    }

    async setPeriod(days) {
        this.state.days = days;
        await this.load();
    }

    async onAccountChange(ev) {
        this.state.accountId = parseInt(ev.target.value) || false;
        await this.load();
    }

    get kpis() {
        const k = this.state.data.kpis;
        return [
            { key: "sent", label: _t("Sent"), value: k.sent, icon: "fa-paper-plane",
              domain: [["direction", "=", "out"], ["state", "in", ["sent", "delivered", "read"]]] },
            { key: "delivered", label: _t("Delivered"), value: k.delivered, icon: "fa-check",
              sub: `${k.delivery_rate}% ` + _t("of sent"),
              domain: [["direction", "=", "out"], ["state", "in", ["delivered", "read"]]] },
            { key: "read", label: _t("Read"), value: k.read, icon: "fa-eye",
              sub: `${k.read_rate}% ` + _t("of sent"),
              domain: [["direction", "=", "out"], ["state", "=", "read"]] },
            { key: "received", label: _t("Received"), value: k.received, icon: "fa-inbox",
              domain: [["direction", "=", "in"]] },
            { key: "failed", label: _t("Failed"), value: k.failed, icon: "fa-exclamation-triangle",
              sub: k.failed ? `${k.failure_rate}% ` + _t("failure rate") : _t("All good"),
              alert: k.failed > 0, domain: [["state", "=", "failed"]] },
            { key: "contacts", label: _t("Contacts"), value: k.contacts, icon: "fa-users",
              sub: _t("active in period"), domain: [["partner_id", "!=", false]] },
        ];
    }

    get funnel() {
        const k = this.state.data.kpis;
        const base = k.sent || 1;
        return [
            { label: _t("Sent"), value: k.sent, pct: k.sent ? 100 : 0 },
            { label: _t("Delivered"), value: k.delivered, pct: Math.round((100 * k.delivered) / base) },
            { label: _t("Read"), value: k.read, pct: Math.round((100 * k.read) / base) },
        ];
    }

    get dailyRows() {
        const d = this.state.data.daily;
        return d.labels.map((label, i) => ({
            label: this.formatDay(label, "d MMM yyyy"),
            outgoing: d.outgoing[i],
            incoming: d.incoming[i],
        }));
    }

    get hasActivity() {
        const d = this.state.data.daily;
        return d.outgoing.some(Boolean) || d.incoming.some(Boolean);
    }

    formatDay(iso, fmt = "d MMM") {
        return luxon.DateTime.fromISO(iso).setLocale(luxon.Settings.defaultLocale || "en").toFormat(fmt);
    }

    formatDateTime(value) {
        return luxon.DateTime.fromSQL(value, { zone: "utc" }).toLocal().toFormat("d MMM, HH:mm");
    }

    stateBadge(state) {
        return {
            read: "text-bg-success", delivered: "text-bg-success", received: "text-bg-info",
            sent: "text-bg-secondary", queued: "text-bg-light", failed: "text-bg-danger",
            connected: "text-bg-success", qr: "text-bg-warning", connecting: "text-bg-warning",
            disconnected: "text-bg-danger", draft: "text-bg-secondary",
        }[state] || "text-bg-secondary";
    }

    token(name) {
        return getComputedStyle(this.rootRef.el).getPropertyValue(name).trim();
    }

    renderChart() {
        if (!this.canvasRef.el || !this.state.data) {
            return;
        }
        const d = this.state.data.daily;
        const useBars = d.labels.length <= 14;
        const series = (label, data, color) => ({
            label, data,
            borderColor: color,
            backgroundColor: color,
            borderWidth: useBars ? 0 : 2,
            borderRadius: 4,
            maxBarThickness: 28,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointHoverBorderWidth: 2,
            pointHoverBorderColor: this.token("--ea-wa-surface"),
            tension: 0.25,
        });
        const muted = this.token("--ea-wa-muted");
        const text = this.token("--ea-wa-text");
        const config = {
            type: useBars ? "bar" : "line",
            data: {
                labels: d.labels.map((l) => this.formatDay(l)),
                datasets: [
                    series(_t("Sent"), d.outgoing, this.token("--ea-wa-series-out")),
                    series(_t("Received"), d.incoming, this.token("--ea-wa-series-in")),
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 250 },
                interaction: { mode: "index", intersect: false },
                datasets: { bar: { categoryPercentage: 0.7, barPercentage: 0.9 } },
                plugins: {
                    legend: {
                        position: "top", align: "end",
                        labels: { color: text, usePointStyle: true, pointStyle: "rectRounded", boxWidth: 10, boxHeight: 10 },
                    },
                    tooltip: {
                        backgroundColor: this.token("--ea-wa-tooltip-bg"),
                        titleColor: this.token("--ea-wa-tooltip-text"),
                        bodyColor: this.token("--ea-wa-tooltip-text"),
                        padding: 10, boxPadding: 4, usePointStyle: true,
                    },
                },
                scales: {
                    x: { grid: { display: false }, border: { color: this.token("--ea-wa-grid") },
                         ticks: { color: muted, maxTicksLimit: 12, maxRotation: 0 } },
                    y: { beginAtZero: true, border: { display: false },
                         grid: { color: this.token("--ea-wa-grid") },
                         ticks: { color: muted, precision: 0, maxTicksLimit: 6 } },
                },
            },
        };
        this.chart?.destroy();
        this.chart = new Chart(this.canvasRef.el, config);
    }

    openMessages(domain = [], name = _t("WhatsApp Messages")) {
        const base = [["message_date", ">=", this.state.data.start]];
        if (this.state.accountId) {
            base.push(["account_id", "=", this.state.accountId]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "ea.whatsapp.message",
            views: [[false, "list"], [false, "form"]],
            domain: [...base, ...domain],
        });
    }

    openRecord(model, id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false, "form"]] });
    }

    openContactMessages(contact) {
        this.openMessages([["partner_id", "=", contact.id]], contact.name);
    }
}

registry.category("actions").add("ea_whatsapp_dashboard", EaWhatsappDashboard);
