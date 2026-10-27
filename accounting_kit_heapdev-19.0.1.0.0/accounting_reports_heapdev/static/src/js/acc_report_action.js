/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillStart, onMounted, markup, useRef } from "@odoo/owl";
import { accReportDom } from "./acc_report_common";

export class AccReportAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.root = useRef("root");
        const action = this.props.action || {};
        const params = action.params || {};
        this.options = Object.assign({report: params.report || "pl"}, params.options || {});
        this.state = useState({html: markup(""), loading: true});
        onWillStart(() => this.load());
        onMounted(() => {
            if (this.root.el) {
                this.root.el.addEventListener("input", (ev) => {
                    if (ev.target.classList.contains("o_acc_dd_search")) {
                        accReportDom.accFilterList(ev.target);
                    }
                });
            }
        });
    }

    async load() {
        this.state.loading = true;
        const res = await this.orm.call("acc.report.engine", "get_report_html", [this.options]);
        this.options = res.options;
        this.state.html = markup(res.html);
        this.state.loading = false;
    }

    async onClick(ev) {
        const el = ev.target.closest("[data-acc]");
        const root = this.root.el;
        if (!el) {
            const row = ev.target.closest("tr.o_acc_foldable");
            if (row && !ev.target.closest("a")) {
                accReportDom.accToggleRow(root, row);
            }
            return;
        }
        const act = el.dataset.acc;
        if (el.tagName === "A" || el.tagName === "BUTTON") {
            ev.preventDefault();
        }
        if (act === "fold") {
            accReportDom.accToggleRow(root, el.closest("tr"));
        } else if (act === "fold_all" || act === "unfold_all") {
            accReportDom.accFoldAll(root, act === "fold_all");
        } else if (act === "apply") {
            Object.assign(this.options, accReportDom.accCollectFilters(root));
            await this.load();
        } else if (act === "preset") {
            Object.assign(this.options, accReportDom.accCollectFilters(root), {preset: el.dataset.preset, date_from: false, date_to: false});
            await this.load();
        } else if (act === "drill") {
            const params = JSON.parse(el.dataset.params || "{}");
            const action = await this.orm.call("acc.report.engine", "action_drill", [this.options, params]);
            if (action) {
                await this.actionService.doAction(action);
            }
        } else if (act === "pdf") {
            const action = await this.orm.call("acc.report.engine", "action_print_pdf", [this.options]);
            await this.actionService.doAction(action);
        } else if (act === "xlsx") {
            window.location.href = accReportDom.accXlsxUrl(this.options);
        }
    }

    onSubmit(ev) {
        ev.preventDefault();
    }
}
AccReportAction.template = "accounting_reports_heapdev.AccReportAction";
AccReportAction.props = ["*"];

registry.category("actions").add("acc_report_heapdev", AccReportAction);
