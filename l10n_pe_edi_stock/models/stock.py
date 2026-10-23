import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    sunat_annex_code = fields.Char(
        string="Código de establecimiento anexo", default="0000", size=7,
        help="Código del establecimiento según el RUC (0000 = domicilio fiscal; 9999 = almacén de tercero).")
    sunat_ubigeo = fields.Char(string="Ubigeo del almacén", size=6)


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    sunat_auto_gre = fields.Boolean(
        string="Generar GRE al validar",
        help="Crea automáticamente la guía de remisión cuando se valida la operación "
             "(y la envía si el envío automático a SUNAT está activo en la compañía).")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    sunat_transport_mode = fields.Selection(
        [("01", "01 - Transporte público"), ("02", "02 - Transporte privado")],
        string="Modalidad de traslado", default="02")
    sunat_driver_id = fields.Many2one("l10n_pe.driver", string="Conductor")
    sunat_vehicle_id = fields.Many2one("l10n_pe.vehicle", string="Vehículo")
    sunat_carrier_id = fields.Many2one("res.partner", string="Transportista (RUC)")
    sunat_gre_reason = fields.Selection(
        [("01", "01 - Venta"), ("02", "02 - Compra"), ("04", "04 - Traslado entre establecimientos"),
         ("06", "06 - Devolución"), ("08", "08 - Importación"), ("09", "09 - Exportación"),
         ("13", "13 - Otros")], string="Motivo de traslado (GRE)")
    sunat_packages = fields.Integer(string="N.º de bultos", default=1)
    sunat_gross_weight = fields.Float(string="Peso bruto (kg)", digits=(12, 3),
                                      compute="_compute_sunat_gross_weight", store=True, readonly=False)

    @api.depends("move_ids.product_id", "move_ids.quantity", "move_ids.product_uom_qty")
    def _compute_sunat_gross_weight(self):
        for picking in self:
            picking.sunat_gross_weight = sum(
                (m.product_id.weight or 0.0) * (m.quantity or m.product_uom_qty) for m in picking.move_ids)

    def _sunat_related_invoice(self):
        """Factura/boleta publicada vinculada (si el módulo de ventas está instalado)."""
        self.ensure_one()
        sale = getattr(self, "sale_id", False)
        if sale:
            return sale.invoice_ids.filtered(
                lambda m: m.state == "posted" and m.move_type == "out_invoice"
                and m.sunat_doc_type in ("01", "03"))[:1]
        return self.env["account.move"]

    def _prepare_sunat_gre_vals(self):
        vals = super()._prepare_sunat_gre_vals()
        warehouse = self.picking_type_id.warehouse_id
        if warehouse.sunat_ubigeo:
            vals["origin_ubigeo"] = warehouse.sunat_ubigeo
        vals.update({
            "transport_mode": self.sunat_transport_mode or "02",
            "packages": self.sunat_packages or 0,
        })
        if self.sunat_gre_reason:
            vals["reason"] = self.sunat_gre_reason
        if self.sunat_gross_weight:
            vals["gross_weight"] = self.sunat_gross_weight
        if self.sunat_driver_id:
            vals["driver_id"] = self.sunat_driver_id.id
        if self.sunat_vehicle_id:
            vals["vehicle_id"] = self.sunat_vehicle_id.id
        if self.sunat_carrier_id:
            vals["carrier_id"] = self.sunat_carrier_id.id
        invoice = self._sunat_related_invoice()
        if invoice:
            vals["move_id"] = invoice.id
        return vals

    def _sunat_auto_gre(self):
        self.ensure_one()
        try:
            gre = self.env["sunat.gre"].create(self._prepare_sunat_gre_vals())
            gre._onchange_driver_id()
            gre._onchange_vehicle_id()
            gre._onchange_carrier_id()
            company = self.company_id
            if getattr(company, "sunat_auto_send", "off") in ("post", "cron"):
                gre.action_send()
        except Exception as e:  # noqa: BLE001
            _logger.exception("GRE automática falló para %s", self.name)
            self.message_post(body=_("No se pudo generar la GRE automática: %s", e))

    def button_validate(self):
        res = super().button_validate()
        for picking in self.filtered(
                lambda p: p.state == "done" and p.picking_type_id.sunat_auto_gre and not p.sunat_gre_ids):
            picking._sunat_auto_gre()
        return res
