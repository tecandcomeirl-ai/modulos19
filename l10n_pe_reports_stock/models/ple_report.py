import re

from odoo import _, fields, models

from odoo.addons.l10n_pe_reports.services import ple_common as pc

from ..services import stock_ledger

LABELS_12_1 = [
    "Periodo", "CUO", "Correlativo asiento", "Establecimiento anexo", "Cód. catálogo", "Tipo existencia",
    "Código existencia", "Cód. catálogo 2", "Código existencia 2", "Fecha", "Tipo doc.", "Serie", "Número",
    "Tipo operación", "Descripción", "Unidad", "Entradas", "Salidas", "Estado"]
LABELS_13_1 = [
    "Periodo", "CUO", "Correlativo asiento", "Establecimiento anexo", "Cód. catálogo", "Tipo existencia",
    "Código existencia", "Cód. catálogo 2", "Código existencia 2", "Fecha", "Tipo doc.", "Serie", "Número",
    "Tipo operación", "Descripción", "Unidad", "Método valuación", "Cant. ingreso", "Costo unit. ingreso",
    "Costo total ingreso", "Cant. retiro", "Costo unit. retiro", "Costo total retiro", "Saldo cantidad",
    "Saldo costo unit.", "Saldo costo total", "Estado"]
COST_METHOD = {"fifo": "3", "average": "2", "standard": "2"}  # Tabla 14: verificar con la versión vigente


def _in_location(location, root):
    return bool(location and root and (location.parent_path or "").startswith(root.parent_path or "~"))


class PleReport(models.Model):
    _inherit = "l10n_pe.ple.report"

    book = fields.Selection(
        selection_add=[("120100", "12.1 Inventario permanente en unidades físicas"),
                       ("130100", "13.1 Inventario permanente valorizado")],
        ondelete={"120100": "set default", "130100": "set default"})

    # ------------------------------------------------------------------ eventos de stock
    @staticmethod
    def _operation_type(src, dst, is_in):
        if is_in:
            return {"supplier": "02", "customer": "05"}.get(src.usage, "99")
        return {"customer": "01", "supplier": "06"}.get(dst.usage, "99")

    @staticmethod
    def _transfer_doc(move):
        """(tipo doc, serie, número) del documento de traslado de un movimiento."""
        picking = move.picking_id
        if picking:
            gre = picking.sunat_gre_ids.filtered(lambda g: g.state == "accepted")[:1] \
                if "sunat_gre_ids" in picking._fields else False
            if gre:
                return "09", gre.series, gre.number
            number = re.sub(r"[^A-Za-z0-9]", "", picking.name or "")[:20] or "0"
            return "00", "0", number
        return "00", "0", "0"

    @staticmethod
    def _move_value(move, qty):
        value = abs(getattr(move, "value", 0.0) or 0.0)
        if not value:
            value = (move.product_id.standard_price or 0.0) * qty
        return value

    def _stock_cuo(self, move):
        accounting = move.account_move_ids[:1] if "account_move_ids" in move._fields else False
        if accounting:
            return str(accounting.id), "M%s" % accounting.id
        return "S%s" % move.id, "M%s" % move.id

    def _warehouse_ledger(self, warehouse, start, end):
        """{product: (opening_qty, opening_val, [eventos])} para un almacén."""
        Move = self.env["stock.move"]
        root = warehouse.view_location_id
        domain = [("state", "=", "done"), ("company_id", "=", self.company_id.id),
                  ("date", "<=", fields.Datetime.to_datetime(end).replace(hour=23, minute=59, second=59)),
                  "|", ("location_id", "child_of", root.id), ("location_dest_id", "child_of", root.id)]
        if "is_storable" in self.env["product.template"]._fields:
            domain.append(("product_id.is_storable", "=", True))
        result = {}
        for move in Move.search(domain, order="date, id"):
            is_in = _in_location(move.location_dest_id, root) and not _in_location(move.location_id, root)
            is_out = _in_location(move.location_id, root) and not _in_location(move.location_dest_id, root)
            if not (is_in or is_out):
                continue  # traslado interno dentro del mismo almacén
            qty = move.product_qty
            value = self._move_value(move, qty)
            entry = result.setdefault(move.product_id, [0.0, 0.0, []])
            move_date = move.date.date()
            if move_date < start:
                entry[0] += qty if is_in else -qty
                entry[1] += value if is_in else -value
                continue
            doc_type, series, number = self._transfer_doc(move)
            cuo, corr = self._stock_cuo(move)
            entry[2].append({
                "date": move_date, "cuo": cuo, "corr": corr, "doc_type": doc_type, "series": series,
                "number": number, "op": self._operation_type(move.location_id, move.location_dest_id, is_in),
                "qty_in": qty if is_in else 0.0, "qty_out": 0.0 if is_in else qty,
                "val_in": value if is_in else 0.0, "val_out": 0.0 if is_in else value})
        return {p: v for p, v in result.items() if v[2]}

    def _inventory_rows(self, valued):
        self.ensure_one()
        start, end = self._period_dates()
        per, rows, notes = self._period_code(), [], []
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", self.company_id.id)])
        for wh in warehouses:
            for product, (open_qty, open_val, events) in sorted(
                    self._warehouse_ledger(wh, start, end).items(), key=lambda kv: kv[0].display_name):
                tmpl = product.product_tmpl_id
                uom = product.uom_id
                common = {
                    "per": per, "pid": product.id, "estab": wh.sunat_annex_code or "0000",
                    "existence": getattr(tmpl, "sunat_existence_type", "01") or "01",
                    "code": pc.clean(product.default_code or "P%s" % product.id, 24),
                    "unspsc": getattr(tmpl, "sunat_unspsc_code", False),
                    "desc": pc.clean(product.name, 80),
                    "uom": getattr(uom, "sunat_ple_uom_code", False) or "07"}
                if valued:
                    method = COST_METHOD.get(getattr(product.categ_id, "property_cost_method", "average"), "2")
                    rows += stock_ledger.valued_rows(common, method, open_qty, open_val, events, start)
                else:
                    rows += stock_ledger.physical_rows(common, open_qty, events, start)
        if not warehouses:
            notes.append(_("No hay almacenes en la compañía."))
        notes.append(_("Tipos de operación: se asignan 01 venta, 02 compra, 05/06 devoluciones, 16 saldo inicial y "
                       "99 otros. Ajuste la Tabla 12 y la Tabla 14 (método de valuación) según su operación."))
        return rows, notes

    def _build_book_120100(self):
        rows, notes = self._inventory_rows(valued=False)
        return LABELS_12_1, rows, notes

    def _build_book_130100(self):
        rows, notes = self._inventory_rows(valued=True)
        notes.append(_("Valores tomados de stock.move.value (Odoo 19). Concilie contra la cuenta 20/21 del Libro Mayor."))
        return LABELS_13_1, rows, notes
