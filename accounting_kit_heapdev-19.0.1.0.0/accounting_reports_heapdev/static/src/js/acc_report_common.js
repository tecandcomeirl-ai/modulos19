/** @odoo-module **/
/* Shared DOM helpers for the server rendered report screen (folding, filters). */
function accCollectFilters(root) {
    var data = {journal_ids: [], analytic_ids: [], partner_ids: []};
    var form = root.querySelector("form.o_acc_filters");
    if (!form) {
        return data;
    }
    var els = form.querySelectorAll("input[name], select[name]");
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        if (el.type === "checkbox") {
            if (el.dataset.multi) {
                if (el.checked) {
                    data[el.name].push(parseInt(el.value, 10));
                }
            } else {
                data[el.name] = el.checked;
            }
        } else if (el.dataset.int) {
            data[el.name] = parseInt(el.value || "0", 10);
        } else {
            data[el.name] = el.value || false;
        }
    }
    return data;
}

function accSetFold(root, rowId, fold) {
    var rows = root.querySelectorAll('tr[data-parent="' + rowId + '"]');
    for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        if (fold) {
            r.classList.add("o_acc_hidden");
            accSetFold(root, r.dataset.id, true);
        } else {
            r.classList.remove("o_acc_hidden");
            if (!r.classList.contains("o_acc_folded")) {
                accSetFold(root, r.dataset.id, false);
            }
        }
    }
}

function accToggleRow(root, row) {
    if (!row || !row.classList.contains("o_acc_foldable")) {
        return;
    }
    var fold = !row.classList.contains("o_acc_folded");
    row.classList.toggle("o_acc_folded", fold);
    accSetFold(root, row.dataset.id, fold);
}

function accFoldAll(root, fold) {
    var rows = root.querySelectorAll("tr.o_acc_foldable");
    for (var i = 0; i < rows.length; i++) {
        rows[i].classList.toggle("o_acc_folded", fold);
    }
    var all = root.querySelectorAll("tr[data-parent]");
    for (var j = 0; j < all.length; j++) {
        all[j].classList.toggle("o_acc_hidden", fold);
    }
}

function accFilterList(input) {
    var q = (input.value || "").toLowerCase();
    var menu = input.closest(".o_acc_dd_menu");
    var labels = menu ? menu.querySelectorAll("label.o_acc_opt") : [];
    for (var i = 0; i < labels.length; i++) {
        labels[i].style.display = labels[i].textContent.toLowerCase().indexOf(q) >= 0 ? "" : "none";
    }
}

function accXlsxUrl(options) {
    return "/accounting_reports_heapdev/xlsx?options=" + encodeURIComponent(JSON.stringify(options));
}

export const accReportDom = {accCollectFilters, accSetFold, accToggleRow, accFoldAll, accFilterList, accXlsxUrl};
