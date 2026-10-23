import base64
import calendar
import io
import logging
import re
from datetime import date as pydate

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.l10n_pe_sunat_beta.models.account_tax import sunat_guess_from_tax
from odoo.addons.l10n_pe_sunat_beta.services.ubl_builder import analyze_line, partner_doc_code

from ..services import ple_common as pc

_logger = logging.getLogger(__name__)
SERIES_NUM_RE = re.compile(r"([A-Z0-9]{1,4})-(\d{1,20})\s*$")

LABELS_14_1 = [
    "Periodo", "CUO", "Correlativo asiento", "Fecha emisión", "Fecha vencimiento", "Tipo CP", "Serie", "Número",
    "Número final", "Tipo doc. cliente", "N.º doc. cliente", "Cliente", "Valor exportación", "Base gravada",
    "Dscto. base", "IGV/IPM", "Dscto. IGV", "Exonerada", "Inafecta", "ISC", "Base IVAP", "IVAP", "ICBPER",
    "Otros cargos", "Total", "Moneda", "Tipo cambio", "Fecha CP modificado", "Tipo CP modificado",
    "Serie CP modificado", "N.º CP modificado", "Contrato", "Error T.C.", "Medio de pago", "Estado"]
LABELS_8_1 = [
    "Periodo", "CUO", "Correlativo asiento", "Fecha emisión", "Fecha vencimiento", "Tipo CP", "Serie",
    "Año DUA/DSI", "Número", "Número final", "Tipo doc. proveedor", "N.º doc. proveedor", "Proveedor",
    "Base gravada (op. gravadas)", "IGV 1", "Base gravada (mixtas)", "IGV 2", "Base gravada (no gravadas)",
    "IGV 3", "No gravadas", "ISC", "ICBPER", "Otros", "Total", "Moneda", "Tipo cambio", "Fecha CP modificado",
    "Tipo CP modificado", "Serie CP modificado", "Cód. aduana", "N.º CP modificado", "Fecha constancia detracción",
    "N.º constancia detracción", "Retención", "Clasificación bienes", "Contrato", "Error 1", "Error 2",
    "Error 3", "Error 4", "Medio de pago", "Estado"]
LABELS_5_1 = [
    "Periodo", "CUO", "Correlativo asiento", "Cuenta", "Unidad operación", "Centro de costos", "Moneda",
    "Tipo doc. emisor", "N.º doc. emisor", "Tipo CP", "Serie", "Número", "Fecha contable", "Fecha vencimiento",
    "Fecha operación", "Glosa", "Glosa referencial", "Debe", "Haber", "Dato estructurado", "Estado"]
LABELS_5_3 = [
    "Periodo", "Cuenta", "Descripción", "Código plan", "Descripción plan", "Cuenta corporativa",
    "Descripción cuenta corp.", "Estado"]


def tax_code(tax):
    return getattr(tax, "sunat_tax_code", False) or sunat_guess_from_tax(tax.name, tax.amount)[0] or False


class PleReport(models.Model):
    _name = "l10n_pe.ple.report"
    _description = "Libro electrónico PLE generado"
    _order = "id desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    book = fields.Selection(
        [("140100", "14.1 Registro de Ventas e Ingresos"),
         ("080100", "8.1 Registro de Compras"),
         ("050100", "5.1 Libro Diario"),
         ("050300", "5.3 Detalle del plan contable")],
        string="Libro", required=True, default="140100")
    year = fields.Integer(string="Año", required=True, default=lambda s: fields.Date.today().year)
    month = fields.Selection([(str(i), "%02d" % i) for i in range(1, 13)], string="Mes", required=True,
                             default=lambda s: str(fields.Date.today().month))
    state = fields.Selection([("draft", "Borrador"), ("done", "Generado")], default="draft", readonly=True)
    record_count = fields.Integer(string="Registros", readonly=True)
    txt_file = fields.Binary(string="Archivo TXT (PLE)", attachment=True, readonly=True)
    txt_filename = fields.Char(readonly=True)
    xlsx_file = fields.Binary(string="Excel de respaldo", attachment=True, readonly=True)
    xlsx_filename = fields.Char(readonly=True)
    notes = fields.Text(string="Observaciones", readonly=True)

    @api.depends("book", "year", "month")
    def _compute_name(self):
        labels = dict(self._fields["book"].selection)
        for rec in self:
            rec.name = "%s %s-%s" % (labels.get(rec.book, rec.book), rec.year, (rec.month or "").zfill(2))

    # ------------------------------------------------------------------ utilidades
    def _period_dates(self):
        self.ensure_one()
        month = int(self.month)
        start = pydate(self.year, month, 1)
        end = pydate(self.year, month, calendar.monthrange(self.year, month)[1])
        return start, end

    def _period_code(self):
        return pc.period(self.year, int(self.month))

    @staticmethod
    def _cuo(move):
        return str(move.id), "M%s" % move.id

    @staticmethod
    def _split_doc_number(move):
        """(serie, número) del comprobante, sin ceros a la izquierda en el número."""
        texts = []
        if "l10n_latam_document_number" in move._fields:
            texts.append(move.l10n_latam_document_number or "")
        texts += [move.ref or "", move.name or ""]
        for text in texts:
            match = SERIES_NUM_RE.search(text.strip().upper())
            if match:
                return match.group(1), str(int(match.group(2)))
        return "", ""

    @staticmethod
    def _currency_factor(move):
        """Factor para llevar los importes del comprobante a soles."""
        if move.amount_total:
            return abs(move.amount_total_signed) / move.amount_total
        return 1.0

    # ------------------------------------------------------------------ generación
    def action_generate(self):
        for rep in self:
            builder = getattr(rep, "_build_book_%s" % rep.book, None)
            if not builder:
                raise UserError(_("Libro %s no soportado.", rep.book))
            labels, rows, notes = builder()
            lines = [pc.record(r) for r in rows]
            content = "\r\n".join(lines) + ("\r\n" if lines else "")
            ruc = rep.company_id.vat or ""
            if len(ruc) != 11:
                raise UserError(_("Configure el RUC de 11 dígitos en la compañía."))
            fname = pc.file_name(ruc, rep.year, int(rep.month), rep.book, bool(rows))
            rep.write({
                "txt_file": base64.b64encode(content.encode("cp1252", errors="replace")),
                "txt_filename": fname,
                "xlsx_file": base64.b64encode(rep._to_xlsx(labels, rows)),
                "xlsx_filename": fname.replace(".txt", ".xlsx"),
                "record_count": len(rows),
                "notes": "\n".join(notes) if notes else False,
                "state": "done",
            })
        return True

    def _to_xlsx(self, labels, rows):
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet(self.book)
        head = wb.add_format({"bold": True, "bg_color": "#DDEBF7", "border": 1})
        for col, label in enumerate(labels):
            ws.write(0, col, label, head)
            ws.set_column(col, col, max(12, len(label) + 2))
        for r, row in enumerate(rows, 1):
            for c, value in enumerate(row):
                ws.write(r, c, value)
        ws.freeze_panes(1, 0)
        wb.close()
        return buf.getvalue()

    # ------------------------------------------------------------------ 14.1 Ventas
    def _build_book_140100(self):
        self.ensure_one()
        start, end = self._period_dates()
        company = self.company_id
        moves = self.env["account.move"].search([
            ("company_id", "=", company.id), ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("sunat_doc_type", "in", ("01", "03", "07", "08")),
            ("invoice_date", ">=", start), ("invoice_date", "<=", end)], order="invoice_date, name")
        per, rows, notes = self._period_code(), [], []
        if company.ple_sire:
            notes.append(_("La compañía está marcada como incorporada al SIRE: este archivo es de respaldo."))
        for move in moves:
            try:
                series, number = move._sunat_series_number()
            except UserError:
                notes.append(_("Omitido %s: no se pudo obtener serie y número.", move.name))
                continue
            number = str(int(number))
            factor = self._currency_factor(move)
            sign = -1.0 if move.sunat_doc_type == "07" else 1.0
            voided = bool(getattr(move, "sunat_voided", False))
            acc = dict(base=0.0, igv=0.0, exo=0.0, ina=0.0, exp=0.0, isc=0.0, ivap_b=0.0, ivap=0.0)
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
                info = analyze_line(line)
                if info["code"] == "9996":
                    continue  # las operaciones gratuitas no se anotan en los importes del registro
                base, tax = info["base"] * factor, info["tax"] * factor
                code = info["code"]
                if code in ("1000", "2000"):
                    acc["base"] += base
                    acc["igv" if code == "1000" else "isc"] += tax
                elif code == "1016":
                    acc["ivap_b"] += base
                    acc["ivap"] += tax
                elif code == "9997":
                    acc["exo"] += base
                elif code == "9995":
                    acc["exp"] += base
                else:
                    acc["ina"] += base
            total = abs(move.amount_total_signed)
            if voided:
                acc = {k: 0.0 for k in acc}
                total = 0.0
            sign_amount = lambda v: pc.amount(sign * v)  # noqa: E731
            partner = move.partner_id
            has_vat = bool(partner.vat)
            orig = move.reversed_entry_id or move.debit_origin_id if move.sunat_doc_type in ("07", "08") else False
            o_date = o_type = o_series = o_number = ""
            if orig:
                try:
                    o_s, o_n = orig._sunat_series_number()
                    o_date, o_type, o_series, o_number = (
                        pc.date(orig.invoice_date), orig.sunat_doc_type, o_s, str(int(o_n)))
                except UserError:
                    pass
            cuo, corr = self._cuo(move)
            cur = move.currency_id.name
            rows.append([
                per, cuo, corr, pc.date(move.invoice_date), "", move.sunat_doc_type, series, number, "",
                partner_doc_code(partner) if has_vat else "", partner.vat or "",
                pc.clean(partner.name, 100) if has_vat else "",
                sign_amount(acc["exp"]), sign_amount(acc["base"]), "0.00", sign_amount(acc["igv"]), "0.00",
                sign_amount(acc["exo"]), sign_amount(acc["ina"]), sign_amount(acc["isc"]),
                sign_amount(acc["ivap_b"]), sign_amount(acc["ivap"]), "0.00", "0.00",
                sign_amount(total), cur, "%.3f" % factor if cur != company.currency_id.name else "1.000",
                o_date, o_type, o_series, o_number, "", "", "", "2" if voided else "1"])
        return LABELS_14_1, rows, notes

    # ------------------------------------------------------------------ 8.1 Compras
    def _build_book_080100(self):
        self.ensure_one()
        start, end = self._period_dates()
        company = self.company_id
        moves = self.env["account.move"].search([
            ("company_id", "=", company.id), ("state", "=", "posted"),
            ("move_type", "in", ("in_invoice", "in_refund")),
            ("invoice_date", ">=", start), ("invoice_date", "<=", end)], order="invoice_date, name")
        per, rows, notes = self._period_code(), [], []
        if company.ple_sire:
            notes.append(_("La compañía está marcada como incorporada al SIRE: este archivo es de respaldo."))
        for move in moves:
            series, number = self._split_doc_number(move)
            if not number:
                notes.append(_("Omitido %s: falta serie-número en la referencia del proveedor.", move.name))
                continue
            doc_type = "07" if move.move_type == "in_refund" else "01"
            if "l10n_latam_document_type_id" in move._fields and move.l10n_latam_document_type_id:
                doc_type = move.l10n_latam_document_type_id.code or doc_type
            factor = self._currency_factor(move)
            sign = -1.0 if move.move_type == "in_refund" else 1.0
            base = igv = nogr = isc = 0.0
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
                amt = line.price_subtotal * factor
                tax_amt = (line.price_total - line.price_subtotal) * factor
                codes = [tax_code(t) for t in line.tax_ids]
                if "2000" in codes:
                    isc += tax_amt
                    base += amt
                elif "1000" in codes:
                    base += amt
                    igv += tax_amt
                else:
                    nogr += amt
            total = abs(move.amount_total_signed)
            partner = move.partner_id
            orig = move.reversed_entry_id if move.move_type == "in_refund" else False
            o_date = o_type = o_series = o_number = ""
            if orig:
                o_series, o_number = self._split_doc_number(orig)
                o_date, o_type = pc.date(orig.invoice_date), "01"
            in_period = (move.invoice_date.year, move.invoice_date.month) == (self.year, int(self.month))
            if in_period:
                state = "1" if igv else "0"
            else:
                months = (self.year - move.invoice_date.year) * 12 + int(self.month) - move.invoice_date.month
                state = "6" if months <= 12 else "7"
            cuo, corr = self._cuo(move)
            cur = move.currency_id.name
            s = lambda v: pc.amount(sign * v)  # noqa: E731
            rows.append([
                per, cuo, corr, pc.date(move.invoice_date),
                pc.date(move.invoice_date_due) if doc_type == "14" else "", doc_type, series, "", number, "",
                partner_doc_code(partner) if partner.vat else "", partner.vat or "", pc.clean(partner.name, 100),
                s(base), s(igv), "0.00", "0.00", "0.00", "0.00", s(nogr), s(isc), "0.00", "0.00", s(total),
                cur, "%.3f" % factor if cur != company.currency_id.name else "1.000",
                o_date, o_type, o_series, "", o_number,
                pc.date(getattr(move, "sunat_detraction_deposit_date", False)),
                getattr(move, "sunat_detraction_deposit_number", "") or "",
                "", "", "", "", "", "", "", "", state])
        return LABELS_8_1, rows, notes

    # ------------------------------------------------------------------ 5.1 Libro Diario
    def _move_doc_info(self, move):
        """(tipo CP, serie, número) para una línea del diario."""
        doc_type = "00"
        if getattr(move, "sunat_doc_type", False) and move.sunat_doc_type != "NV":
            doc_type = move.sunat_doc_type
        elif "l10n_latam_document_type_id" in move._fields and move.l10n_latam_document_type_id:
            doc_type = move.l10n_latam_document_type_id.code or "00"
        series, number = self._split_doc_number(move)
        return doc_type, series or "0", number or "0"

    def _build_book_050100(self):
        self.ensure_one()
        start, end = self._period_dates()
        company = self.company_id
        lines = self.env["account.move.line"].search([
            ("company_id", "=", company.id), ("parent_state", "=", "posted"),
            ("date", ">=", start), ("date", "<=", end), ("display_type", "not in", ("line_section", "line_note"))],
            order="date, move_id, id")
        per, rows, notes = self._period_code(), [], []
        for line in lines:
            move = line.move_id
            cuo, corr = self._cuo(move)
            partner = line.partner_id or move.partner_id
            doc_type, series, number = self._move_doc_info(move)
            structured = ""
            if not company.ple_sire:
                if move.move_type in ("out_invoice", "out_refund"):
                    structured = "140100&%s&%s&%s" % (per, cuo, corr)
                elif move.move_type in ("in_invoice", "in_refund"):
                    structured = "080100&%s&%s&%s" % (per, cuo, corr)
            rows.append([
                per, cuo, corr, pc.clean(line.account_id.code, 24), "", "",
                (line.currency_id or company.currency_id).name,
                partner_doc_code(partner) if partner.vat else "", partner.vat or "",
                doc_type, series, number, pc.date(move.date), pc.date(line.date_maturity),
                pc.date(move.invoice_date or move.date),
                pc.clean(line.name or move.ref or move.name, 200), "",
                pc.amount(line.debit), pc.amount(line.credit), structured, "1"])
        notes.append(_("Todos los asientos se informan con correlativo 'M' (movimientos del mes). "
                       "Los asientos de apertura/cierre (A/C) deben ajustarse manualmente."))
        return LABELS_5_1, rows, notes

    # ------------------------------------------------------------------ 5.3 Plan contable
    def _build_book_050300(self):
        self.ensure_one()
        start, end = self._period_dates()
        lines = self.env["account.move.line"].search([
            ("company_id", "=", self.company_id.id), ("parent_state", "=", "posted"),
            ("date", ">=", start), ("date", "<=", end), ("display_type", "not in", ("line_section", "line_note"))])
        accounts = lines.mapped("account_id").sorted("code")
        per = self._period_code()
        rows = [[per, pc.clean(a.code, 24), pc.clean(a.name, 100), "01", "PLAN CONTABLE GENERAL EMPRESARIAL",
                 "", "", "1"] for a in accounts]
        notes = [_("Estructura 5.3 según la última versión conocida; valide con el PLE oficial.")]
        return LABELS_5_3, rows, notes
