/** ************************************************************************
 *  MM Solutions
 *  Copyright (C) 2026 MM Solutions
 *  https://apps.odoo.com/apps/modules/browse?author=MM%20Solutions
 *  Distributed under the GNU Lesser General Public License v3 (LGPL-3).
 ************************************************************************* */
import { Component, onWillUnmount, useRef } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class PdfPreviewDialog extends Component {
    static template = "pdf_preview_direct_print.PdfPreviewDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        blob: { type: Object },
        blobUrl: { type: String },
        fileName: { type: String },
        title: { type: String },
    };

    setup() {
        this.pdfFrame = useRef("pdfFrame");
        onWillUnmount(() => {
            // Free the object URL once the dialog is gone.
            URL.revokeObjectURL(this.props.blobUrl);
        });
    }

    get frameSrc() {
        // Hide the sidebar of the built-in browser PDF viewer, keep the toolbar.
        return `${this.props.blobUrl}#pagemode=none&navpanes=0`;
    }
}
