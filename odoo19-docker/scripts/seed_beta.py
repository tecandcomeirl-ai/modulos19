# Datos de prueba para el ambiente BETA de SUNAT.
# Uso (dentro del contenedor):
#   docker compose exec -T odoo odoo shell -d TU_BD < scripts/seed_beta.py
# Es idempotente: puede ejecutarse varias veces.
import base64

company = env.company
vals = {
    "name": "EMPRESA DE PRUEBA SAC",
    "vat": "20000000001",
    "sunat_env": "beta",
    "sunat_sol_user": "MODDATOS",
    "sunat_sol_password": "moddatos",
    "sunat_cert_password": "beta1234",
    "sunat_ubigeo": "150101",
}
try:
    with open("/mnt/certs/beta_test.pfx", "rb") as fh:
        vals["sunat_cert"] = base64.b64encode(fh.read())
        vals["sunat_cert_filename"] = "beta_test.pfx"
except OSError:
    print("AVISO: no se encontró /mnt/certs/beta_test.pfx; cargue el certificado manualmente.")
company.write(vals)
if "sunat_auto_send" in company._fields:
    company.sunat_auto_send = "off"          # envío manual para controlar cada caso
    company.sunat_boleta_mode = "individual"  # cambie a 'summary' para el caso CP-11
if "sunat_detraction_account" in company._fields:
    company.sunat_detraction_account = "00-000-000000"

# Dirección del emisor (ubigeo/dirección se informan en el XML y la GRE)
company.partner_id.write({"street": "AV. PRUEBA 123", "city": "LIMA", "country_id": env.ref("base.pe").id})

Partner = env["res.partner"]
IdType = env["l10n_latam.identification.type"]
ruc_type = IdType.search([("l10n_pe_vat_code", "=", "6")], limit=1)
dni_type = IdType.search([("l10n_pe_vat_code", "=", "1")], limit=1)


def partner(name, vat, id_type, street):
    rec = Partner.search([("vat", "=", vat)], limit=1)
    vals = {"name": name, "vat": vat, "street": street, "country_id": env.ref("base.pe").id,
            "email": "pruebas@example.com"}
    if id_type:
        vals["l10n_latam_identification_type_id"] = id_type.id
    if rec:
        rec.write(vals)
        return rec
    return Partner.create(vals)


cli_ruc = partner("SUPERINTENDENCIA NACIONAL DE ADUANAS Y DE ADMINISTRACION TRIBUTARIA", "20131312955",
                  ruc_type, "AV. GARCILASO DE LA VEGA 1472")
cli_dni = partner("JUAN PEREZ GOMEZ", "12345678", dni_type, "JR. LAS FLORES 456")
print("Clientes:", cli_ruc.name, "|", cli_dni.name)

# Productos
Tmpl = env["product.template"]
igv = env["account.tax"].search([("type_tax_use", "=", "sale"), ("amount", "=", 18.0),
                                 ("company_id", "=", company.id)], limit=1)
exo = env["account.tax"].search([("type_tax_use", "=", "sale"), ("amount", "=", 0.0),
                                 ("name", "ilike", "exo"), ("company_id", "=", company.id)], limit=1)
print("Impuestos:", igv.name or "FALTA IGV 18%", "|", exo.name or "FALTA exonerado (créelo y marque Tributo 9997)")


def product(name, code, price, ptype, taxes):
    rec = Tmpl.search([("default_code", "=", code)], limit=1)
    vals = {"name": name, "default_code": code, "list_price": price, "type": ptype,
            "taxes_id": [(6, 0, taxes.ids)]}
    if rec:
        rec.write(vals)
        return rec
    return Tmpl.create(vals)


prod_a = product("PRODUCTO A", "PROD-A", 100.0, "consu", igv)
serv = product("SERVICIO DE CONSULTORIA", "SERV-CONS", 1000.0, "service", igv)
serv_exo = product("SERVICIO EXONERADO", "SERV-EXO", 500.0, "service", exo)
if "sunat_detraction_code_id" in Tmpl._fields:
    code = env.ref("l10n_pe_sunat_detraccion.detraction_037", raise_if_not_found=False)
    if code:
        serv.sunat_detraction_code_id = code.id
if "is_storable" in Tmpl._fields:
    prod_a.is_storable = True
print("Productos:", prod_a.name, "|", serv.name, "|", serv_exo.name)

# Vehículo y conductor de prueba (GRE)
if "l10n_pe.vehicle" in env:
    if not env["l10n_pe.vehicle"].search([("plate", "=", "ABC123")]):
        env["l10n_pe.vehicle"].create({"plate": "ABC123", "brand": "TOYOTA HILUX"})
    if not env["l10n_pe.driver"].search([("doc_number", "=", "45678912")]):
        env["l10n_pe.driver"].create({"first_name": "CARLOS", "last_name": "RAMIREZ DIAZ",
                                      "doc_number": "45678912", "license": "Q45678912"})
env.cr.commit()
print("Listo. Siguiente paso: configure el diario de ventas con 'Usar documentos' y siga docs/GUIA_PRUEBAS_BETA.md")
