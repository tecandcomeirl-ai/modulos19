/** ************************************************************************
 *  MM Solutions
 *  Copyright (C) 2026 MM Solutions
 *  https://apps.odoo.com/apps/modules/browse?author=MM%20Solutions
 *  Distributed under the GNU Lesser General Public License v3 (LGPL-3).
 ************************************************************************* */
import { registry } from "@web/core/registry";
import { PdfPreviewDialog } from "./pdf_preview_dialog";
import { getResponseFileName } from "./utils";

/**
 * Enterprise financial reports (P&L, Balance Sheet, Aged Partner, ...) do not
 * use the standard `ir.actions.report` flow. Their PDF/XLSX buttons trigger an
 * `ir.actions.account_report_download` action whose handler POSTs to
 * `/account_reports` and downloads the file.
 *
 * We wrap that handler at runtime (only if it exists) so PDF exports open in
 * our preview dialog instead. XLSX and any other file type keep the default
 * download behaviour, and any error falls back to the original handler.
 *
 * The wrapping is done inside a service `start()` because services start only
 * after every module's JS has executed - this guarantees the original handler
 * is already registered, regardless of asset ordering, and avoids duplicate
 * registry keys on Community databases where the handler does not exist.
 */
// account_reports has historically registered this handler with underscores
// ("ir_actions_account_report_download"); some versions use the dotted form.
// We wrap whichever variant is present.
const ACTION_TYPE_CANDIDATES = [
    "ir_actions_account_report_download",
    "ir.actions.account_report_download",
];

const accountReportPreviewService = {
    start() {
        const handlers = registry.category("action_handlers");
        for (const actionType of ACTION_TYPE_CANDIDATES) {
            if (handlers.contains(actionType)) {
                wrapHandler(handlers, actionType);
            }
        }
    },
};

function wrapHandler(handlers, actionType) {
    const originalHandler = handlers.get(actionType);

    handlers.add(
        actionType,
            async (params) => {
                const { action, env } = params;
                const data = action.data || {};
                if (data.file_generator !== "export_to_pdf") {
                    return originalHandler(params); // XLSX etc.
                }
                env.services.ui.block();
                let response;
                try {
                    const body = new FormData();
                    body.append("csrf_token", odoo.csrf_token);
                    for (const [key, value] of Object.entries(data)) {
                        body.append(
                            key,
                            typeof value === "string" ? value : JSON.stringify(value)
                        );
                    }
                    response = await fetch("/account_reports", { method: "POST", body });
                } catch {
                    env.services.ui.unblock();
                    return originalHandler(params);
                }
                const contentType = response.headers.get("Content-Type") || "";
                if (!response.ok || !contentType.includes("pdf")) {
                    env.services.ui.unblock();
                    return originalHandler(params);
                }
                const blob = await response.blob();
                env.services.ui.unblock();
                const blobUrl = URL.createObjectURL(blob);
                env.services.dialog.add(PdfPreviewDialog, {
                    blob,
                    blobUrl,
                    fileName: getResponseFileName(response, action.name || "report"),
                    title: action.name || "Report Preview",
                });
            },
        { force: true }
    );
}

registry
    .category("services")
    .add("pdf_preview_account_report_patch", accountReportPreviewService);
