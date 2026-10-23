from odoo import api, fields, models

# nombre (minúsculas) -> (código UN/ECE Rec.20 para GRE/UBL, código Tabla 6 PLE)
UOM_GUESS = {
    "unidades": ("NIU", "07"), "unidad": ("NIU", "07"), "unit": ("NIU", "07"), "units": ("NIU", "07"),
    "kg": ("KGM", "01"), "g": ("GRM", "06"), "t": ("TNE", "04"), "tonne": ("TNE", "04"),
    "lb": ("LBR", "02"), "l": ("LTR", "08"), "litro": ("LTR", "08"), "m": ("MTR", "15"),
    "m³": ("MTQ", "14"), "docena": ("DZN", "99"), "dozen": ("DZN", "99"),
    "caja": ("BX", "12"), "box": ("BX", "12"), "millar": ("MIL", "13"),
}


def guess_uom_codes(name):
    return UOM_GUESS.get((name or "").strip().lower(), ("NIU", "99"))


class UomUom(models.Model):
    _inherit = "uom.uom"

    sunat_uom_code = fields.Char(
        string="Código SUNAT (UN/ECE)", size=3,
        help="Código de unidad de medida para GRE y comprobantes (ej. NIU, KGM, LTR).")
    sunat_ple_uom_code = fields.Char(
        string="Código PLE (Tabla 6)", size=3,
        help="Código de unidad de medida de la Tabla 6 del PLE (07 = unidad, 01 = kilogramo...). "
             "Verifique contra la tabla vigente.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("sunat_uom_code") or not vals.get("sunat_ple_uom_code"):
                gre_code, ple_code = guess_uom_codes(vals.get("name"))
                vals.setdefault("sunat_uom_code", gre_code)
                vals.setdefault("sunat_ple_uom_code", ple_code)
        return super().create(vals_list)
