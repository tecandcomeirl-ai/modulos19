/** ************************************************************************
 *  MM Solutions
 *  Copyright (C) 2026 MM Solutions
 *  https://apps.odoo.com/apps/modules/browse?author=MM%20Solutions
 *  Distributed under the GNU Lesser General Public License v3 (LGPL-3).
 ************************************************************************* */
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { PdfPreviewDialog } from "./pdf_preview_dialog";
import { getResponseFileName } from "./utils";

/**
 * Build the /report/pdf/... URL for a report action, mirroring the way the
 * standard action service builds its download URL.
 */
function buildReportUrl(action) {
    let url = `/report/pdf/${action.report_name}`;
    const actionContext = action.context || {};
    if (action.data && JSON.stringify(action.data) !== "{}") {
        // Wizard-driven reports pass their payload through `data`.
        const options = encodeURIComponent(JSON.stringify(action.data));
        const context = encodeURIComponent(JSON.stringify(actionContext));
        url += `?options=${options}&context=${context}`;
    } else {
        if (actionContext.active_ids) {
            url += `/${actionContext.active_ids.join(",")}`;
        }
        const context = encodeURIComponent(JSON.stringify(user.context || {}));
        url += `?context=${context}`;
    }
    return url;
}

async function pdfPreviewHandler(action, options, env) {
    if (action.report_type !== "qweb-pdf") {
        return false;
    }
    let response;
    try {
        response = await fetch(buildReportUrl(action));
    } catch {
        return false; // network issue -> let the standard flow handle it
    }
    const contentType = response.headers.get("Content-Type") || "";
    if (!response.ok || !contentType.includes("pdf")) {
        // wkhtmltopdf missing, access error, html fallback... let Odoo's
        // default behaviour take over so nothing ever breaks.
        return false;
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    env.services.dialog.add(
        PdfPreviewDialog,
        {
            blob,
            blobUrl,
            fileName: getResponseFileName(response, action.name || action.report_name),
            title: action.name || "Report Preview",
        },
        {
            onClose: () => {
                if (action.close_on_report_download) {
                    env.services.action.doAction(
                        { type: "ir.actions.act_window_close" },
                        { onClose: options.onClose }
                    );
                } else if (options.onClose) {
                    options.onClose();
                }
            },
        }
    );
    return true;
}

registry
    .category("ir.actions.report handlers")
    .add("pdf_preview_direct_print_handler", pdfPreviewHandler, { sequence: 20 });
