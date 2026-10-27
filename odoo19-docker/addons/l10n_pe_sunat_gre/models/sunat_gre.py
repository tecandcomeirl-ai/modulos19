import base64
import logging
import re
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.l10n_pe_sunat_beta.services import signer, soap_client

from ..services import gre_builder, gre_client

_logger = logging.getLogger(__name__)

GRE_REASONS = [
    ("01", "01 - Venta"),
    ("02", "02 - Compra"),
    ("03", "03 - Venta con entrega a terceros"),
    ("04", "04 - Traslado entre establecimientos de la misma empresa"),
    ("05", "05 - Consignación"),
    ("06", "06 - Devolución"),
    ("07", "07 - Recojo de bienes transformados"),
    ("08", "08 - Importación"),
    ("09", "09 - Exportación"),
    ("13", "13 - Otros"),
    ("14", "14 - Venta sujeta a confirmación del comprador"),
    ("17", "17 - Traslado de bienes para transformación"),
    ("18", "18 - Traslado emisor itinerante CP"),
    ("19", "19 - Traslado a zona primaria"),
]
UOM_MAP = {"unidades": "NIU", "unit": "NIU", "units": "NIU", "kg": "KGM", "g": "GRM", "l": "LTR",
           "m": "MTR", "docena": "DZN", "dozen": "DZN", "caja": "BX", "t": "TNE"}
UBIGEO_RE = re.compile(r"^\d{6}$")


def partner_ubigeo(partner):
    district = getattr(partner, "l10n_pe_district", False)
    code = (district.code or "") if district else ""
    return code if UBIGEO_RE.match(code or "") else ""


def partner_doc_type(partner):
    ident = getattr(partner, "l10n_latam_identification_type_id", False)
    code = getattr(ident, "l10n_pe_vat_code", False) if ident else False
    if code:
        return str(code)
    vat = (partner.vat or "").strip()
    return "6" if len(vat) == 11 else "1" if len(vat) == 8 else "0"


class SunatGre(models.Model):
    _name = "sunat.gre"
    _description = "Guía de Remisión Electrónica - Remitente"
    _order = "id desc"

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    state = fields.Selection(
        [("draft", "Borrador"), ("sent", "Enviada (ticket)"), ("accepted", "Aceptada"),
         ("rejected", "Rechazada"), ("error", "Error")],
        default="draft", readonly=True, copy=False)
    series = fields.Char(required=True, size=4, copy=False,
                         default=lambda s: s.env.company.sunat_gre_series or "T001")
    number = fields.Char(copy=False, readonly=True)
    date_issue = fields.Date(string="Fecha de emisión", default=fields.Date.context_today, required=True)
    time_issue = fields.Char(string="Hora", copy=False)
    note = fields.Char(string="Observaciones")

    # Destinatario
    partner_id = fields.Many2one("res.partner", string="Destinatario", required=True)
    partner_vat = fields.Char(string="Documento destinatario")
    partner_doc_type = fields.Char(string="Tipo doc. (Cat. 06)", size=1)

    # Traslado
    reason = fields.Selection(GRE_REASONS, string="Motivo de traslado", default="01", required=True)
    transport_mode = fields.Selection(
        [("01", "01 - Transporte público"), ("02", "02 - Transporte privado")],
        string="Modalidad", default="02", required=True)
    transfer_date = fields.Date(string="Inicio de traslado", default=fields.Date.context_today, required=True)
    gross_weight = fields.Float(string="Peso bruto (kg)", digits=(12, 3))
    packages = fields.Integer(string="N.º de bultos")

    origin_ubigeo = fields.Char(string="Ubigeo partida", size=6)
    origin_address = fields.Char(string="Dirección de partida")
    dest_ubigeo = fields.Char(string="Ubigeo llegada", size=6)
    dest_address = fields.Char(string="Dirección de llegada")

    # Transporte público
    carrier_vat = fields.Char(string="RUC transportista")
    carrier_name = fields.Char(string="Razón social transportista")
    # Transporte privado
    driver_doc_type = fields.Selection([("1", "DNI"), ("4", "Carnet extranjería"), ("7", "Pasaporte")],
                                       string="Tipo doc. conductor", default="1")
    driver_doc = fields.Char(string="Documento conductor")
    driver_first_name = fields.Char(string="Nombres conductor")
    driver_last_name = fields.Char(string="Apellidos conductor")
    driver_license = fields.Char(string="Licencia de conducir")
    vehicle_plate = fields.Char(string="Placa del vehículo")

    line_ids = fields.One2many("sunat.gre.line", "gre_id", string="Bienes", copy=True)
    picking_id = fields.Many2one("stock.picking", string="Operación de inventario", copy=False)
    move_id = fields.Many2one("account.move", string="Factura relacionada", copy=False,
                              domain="[('move_type','=','out_invoice')]")

    # Resultado SUNAT
    ticket = fields.Char(readonly=True, copy=False)
    response_code = fields.Char(string="Código", readonly=True, copy=False)
    response_message = fields.Text(string="Mensaje SUNAT", readonly=True, copy=False)
    xml_file = fields.Binary(string="XML firmado", attachment=True, readonly=True, copy=False)
    zip_file = fields.Binary(string="ZIP enviado", attachment=True, readonly=True, copy=False)
    cdr_file = fields.Binary(string="CDR recibido (ZIP)", attachment=True, readonly=True, copy=False)
    sent_date = fields.Datetime(readonly=True, copy=False)

    @api.depends("series", "number")
    def _compute_name(self):
        for gre in self:
            gre.name = "%s-%s" % (gre.series, gre.number) if gre.number else _("Borrador GRE")

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        partner = self.partner_id
        if partner:
            self.partner_vat = partner.vat
            self.partner_doc_type = partner_doc_type(partner)
            if not self.dest_address:
                self.dest_address = partner.contact_address_complete if hasattr(
                    partner, "contact_address_complete") else partner.street
            if not self.dest_ubigeo:
                self.dest_ubigeo = partner_ubigeo(partner)

    @api.constrains("transport_mode", "carrier_vat", "driver_doc", "vehicle_plate")
    def _check_transport(self):
        for gre in self:
            if gre.state != "draft":
                continue
            if gre.transport_mode == "01" and gre.carrier_vat and len(gre.carrier_vat.strip()) != 11:
                raise ValidationError(_("El RUC del transportista debe tener 11 dígitos."))

    # ------------------------------------------------------------------
    def _validate_before_send(self):
        self.ensure_one()
        errors = []
        company = self.company_id
        if not company.vat or len(company.vat.strip()) != 11:
            errors.append(_("RUC de la compañía inválido."))
        if not company.sunat_cert:
            errors.append(_("Falta el certificado digital en la compañía."))
        if not self.partner_vat:
            errors.append(_("Falta el documento del destinatario."))
        for label, value in ((_("Ubigeo de partida"), self.origin_ubigeo),
                             (_("Ubigeo de llegada"), self.dest_ubigeo)):
            if not UBIGEO_RE.match(value or ""):
                errors.append(_("%s debe tener 6 dígitos.") % label)
        if not (self.origin_address and self.dest_address):
            errors.append(_("Complete las direcciones de partida y llegada."))
        if self.gross_weight <= 0:
            errors.append(_("El peso bruto debe ser mayor a cero."))
        if not self.line_ids:
            errors.append(_("Agregue al menos un bien a trasladar."))
        if self.transport_mode == "01" and not (self.carrier_vat and self.carrier_name):
            errors.append(_("Transporte público: indique RUC y razón social del transportista."))
        if self.transport_mode == "02" and not all(
                [self.driver_doc, self.driver_first_name, self.driver_last_name,
                 self.driver_license, self.vehicle_plate]):
            errors.append(_("Transporte privado: indique conductor (documento, nombres, apellidos, "
                            "licencia) y placa del vehículo."))
        if errors:
            raise UserError("\n".join(errors))

    def action_send(self):
        for gre in self:
            gre._validate_before_send()
            try:
                if not gre.number:
                    gre.number = self.env["ir.sequence"].next_by_code("sunat.gre")
                gre.time_issue = datetime.now().strftime("%H:%M:%S")
                base = "%s-09-%s-%s" % (gre.company_id.vat, gre.series, gre.number)
                xml = gre_builder.build_despatch(gre)
                xml = signer.sign_xml(xml, base64.b64decode(gre.company_id.sunat_cert),
                                      gre.company_id.sunat_cert_password)
                zip_bytes = soap_client.make_zip(base + ".xml", xml)
                gre.write({"xml_file": base64.b64encode(xml), "zip_file": base64.b64encode(zip_bytes),
                           "sent_date": fields.Datetime.now()})
                ticket = gre_client.send_gre(gre.company_id, base, zip_bytes)
                gre.write({"ticket": ticket, "state": "sent", "response_message": False})
                gre._fetch_status()
            except gre_client.GreError as e:
                gre.write({"state": "error", "response_code": str(e.code), "response_message": e.message})
            except Exception as e:  # noqa: BLE001
                _logger.exception("Error enviando GRE")
                gre.write({"state": "error", "response_message": str(e)})
        return True

    def _fetch_status(self):
        self.ensure_one()
        status, cdr, msg = gre_client.get_status(self.company_id, self.ticket)
        if status == "0":
            vals = {"state": "accepted", "response_code": "0"}
            if cdr:
                code, desc = soap_client.parse_cdr(cdr)
                vals.update({"cdr_file": base64.b64encode(cdr), "response_code": code,
                             "response_message": desc,
                             "state": "accepted" if code == "0" else "rejected"})
                self._attach_cdr(cdr)
            self.write(vals)
        elif status == "99":
            vals = {"state": "rejected", "response_code": "99", "response_message": msg}
            if cdr:
                vals["cdr_file"] = base64.b64encode(cdr)
            self.write(vals)
        # 98 = en proceso: se mantiene "sent"

    def action_check_ticket(self):
        for gre in self.filtered("ticket"):
            try:
                gre._fetch_status()
            except gre_client.GreError as e:
                raise UserError(str(e))
        return True

    @api.model
    def _cron_check_tickets(self):
        for gre in self.search([("state", "=", "sent"), ("ticket", "!=", False)], limit=50):
            try:
                gre._fetch_status()
            except Exception:  # noqa: BLE001
                _logger.exception("GRE %s: error consultando ticket", gre.name)

    def action_reset_draft(self):
        self.filtered(lambda g: g.state in ("error", "rejected")).write({"state": "draft"})

    def _attach_cdr(self, cdr):
        self.env["ir.attachment"].create({
            "name": "R-%s-09-%s.zip" % (self.company_id.vat, self.name), "datas": base64.b64encode(cdr),
            "res_model": "sunat.gre", "res_id": self.id})


class SunatGreLine(models.Model):
    _name = "sunat.gre.line"
    _description = "Bien trasladado en GRE"

    gre_id = fields.Many2one("sunat.gre", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Producto")
    product_code = fields.Char(string="Código")
    description = fields.Char(string="Descripción", required=True)
    quantity = fields.Float(string="Cantidad", digits=(12, 3), default=1.0)
    uom_code = fields.Char(string="Unidad (Cat. 03)", default="NIU", size=3)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.product_code = self.product_id.default_code
