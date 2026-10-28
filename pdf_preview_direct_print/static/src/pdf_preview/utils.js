/** ************************************************************************
 *  MM Solutions
 *  Copyright (C) 2026 MM Solutions
 *  https://apps.odoo.com/apps/modules/browse?author=MM%20Solutions
 *  Distributed under the GNU Lesser General Public License v3 (LGPL-3).
 ************************************************************************* */
/**
 * Extract a sensible file name from a fetch Response, falling back to a
 * sanitized default.
 */
export function getResponseFileName(response, fallbackName) {
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
    if (match) {
        try {
            return decodeURIComponent(match[1]);
        } catch {
            return match[1];
        }
    }
    const base = (fallbackName || "report").replace(/[/\\]/g, "_");
    return base.endsWith(".pdf") ? base : `${base}.pdf`;
}
