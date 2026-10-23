"""UBL 2.1 SUNAT: Factura (01), Boleta (03), Nota de crédito (07) y Nota de débito (08)."""
from lxml import etree

NS_BASE = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
INV = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
CN = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
DN = "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2"

# tipo -> (raíz, namespace, línea, cantidad, totales)
ROOTS = {
    "01": ("Invoice", INV, "InvoiceLine", "InvoicedQuantity", "LegalMonetaryTotal"),
    "03": ("Invoice", INV, "InvoiceLine", "InvoicedQuantity", "LegalMonetaryTotal"),
    "07": ("CreditNote", CN, "CreditNoteLine", "CreditedQuantity", "LegalMonetaryTotal"),
    "08": ("DebitNote", DN, "DebitNoteLine", "DebitedQuantity", "RequestedMonetaryTotal"),
}
# código tributo -> (nombre, código internacional)
TAX_SCHEMES = {
    "1000": ("IGV", "VAT"), "1016": ("IVAP", "VAT"), "2000": ("ISC", "EXC"),
    "9995": ("EXP", "FRE"), "9996": ("GRA", "FRE"), "9997": ("EXO", "VAT"),
    "9998": ("INA", "FRE"), "9999": ("OTROS", "OTH"),
}
# código tributo -> categoría de impuesto UN/ECE 5305
TAX_CATEGORY = {"1000": "S", "1016": "S", "2000": "S", "9995": "G", "9996": "Z",
                "9997": "E", "9998": "O", "9999": "S"}
FREE_LEGEND = "TRANSFERENCIA GRATUITA DE UN BIEN Y/O SERVICIO PRESTADO GRATUITAMENTE"
DEFAULT_AFECT = {"1000": "10", "1016": "10", "2000": "10", "9995": "40",
                 "9997": "20", "9998": "30", "9999": "30"}
CURRENCY_NAMES = {"PEN": "SOLES", "USD": "DÓLARES AMERICANOS", "EUR": "EUROS"}


def _q(prefix, tag):
    return "{%s}%s" % (NS_BASE[prefix], tag)


def _sub(parent, prefix, tag, text=None, **attrs):
    el = etree.SubElement(parent, _q(prefix, tag), **attrs)
    if text is not None:
        el.text = str(text)
    return el


def _num(value):
    return "%.2f" % (value or 0.0)


def _price(value):
    s = ("%.10f" % (value or 0.0)).rstrip("0")
    whole, _dot, dec = s.partition(".")
    return "%s.%s" % (whole or "0", dec.ljust(2, "0"))


def _amt(parent, tag, value, currency):
    return _sub(parent, "cbc", tag, _num(value), currencyID=currency)


def amount_in_words(amount, currency):
    """Leyenda 1000: SON <monto en letras> CON xx/100 <moneda>."""
    try:
        from num2words import num2words
        ent = int(amount)
        cents = int(round((amount - ent) * 100))
        words = num2words(ent, lang="es").upper()
        return "SON: %s CON %02d/100 %s" % (words, cents, CURRENCY_NAMES.get(currency, currency))
    except Exception:  # noqa: BLE001
        return "SON: %.2f %s" % (amount, currency)


def partner_doc_code(partner):
    """Catálogo 06: 6 RUC, 1 DNI, 4 CE, 7 Pasaporte, 0 sin documento."""
    ident = getattr(partner, "l10n_latam_identification_type_id", False)
    code = getattr(ident, "l10n_pe_vat_code", False) if ident else False
    if code:
        return str(code)
    vat = (partner.vat or "").strip()
    return "6" if len(vat) == 11 else "1" if len(vat) == 8 else "0"


def analyze_line(line):
    taxes = [t for t in line.tax_ids if getattr(t, "sunat_tax_code", False)]
    free = getattr(line, "sunat_free_afect", False)
    if free:
        # Operación gratuita (aporta l10n_pe_sunat_gratuito): el valor referencial reemplaza al valor de venta
        base = getattr(line, "sunat_free_total", 0.0)
        tax_amt = getattr(line, "sunat_free_tax", 0.0)
        percent = taxes[0].amount if taxes and taxes[0].amount_type == "percent" else 0.0
        return {"code": "9996", "afect": free, "percent": percent, "base": base, "tax": tax_amt,
                "free": True, "unit": getattr(line, "sunat_free_unit_value", 0.0)}
    base = line.price_subtotal
    tax_amt = line.price_total - line.price_subtotal
    if taxes:
        tax = taxes[0]
        code = tax.sunat_tax_code
        afect = tax.sunat_afectacion or DEFAULT_AFECT[code]
        if tax.amount_type == "percent":
            percent = tax.amount
        else:
            percent = (tax_amt / base * 100) if base else 0.0
    else:
        code, afect, percent = "9998", "30", 0.0
    return {"code": code, "afect": afect, "percent": percent, "base": base, "tax": tax_amt,
            "free": False, "unit": 0.0}


def _party(parent, role, vat, name, id_type):
    wrapper = _sub(parent, "cac", role)
    party = _sub(wrapper, "cac", "Party")
    _sub(_sub(party, "cac", "PartyIdentification"), "cbc", "ID", vat or "-", schemeID=id_type)
    _sub(_sub(party, "cac", "PartyName"), "cbc", "Name", name)
    legal = _sub(party, "cac", "PartyLegalEntity")
    _sub(legal, "cbc", "RegistrationName", name)
    return legal


def build_document(move, doc_type, series, number, original=None):
    """Devuelve el XML (sin firmar) del comprobante.

    original: dict(series, number, doc_type) del comprobante modificado (NC/ND).
    """
    root_tag, root_ns, line_tag, qty_tag, total_tag = ROOTS[doc_type]
    company = move.company_id
    cur = move.currency_id.name
    nsmap = {None: root_ns}
    nsmap.update(NS_BASE)
    root = etree.Element("{%s}%s" % (root_ns, root_tag), nsmap=nsmap)

    ext = _sub(_sub(root, "ext", "UBLExtensions"), "ext", "UBLExtension")
    _sub(ext, "ext", "ExtensionContent")  # aquí se inserta la firma

    _sub(root, "cbc", "UBLVersionID", "2.1")
    _sub(root, "cbc", "CustomizationID", "2.0")
    _sub(root, "cbc", "ID", "%s-%s" % (series, number))
    _sub(root, "cbc", "IssueDate", move.invoice_date.isoformat())
    _sub(root, "cbc", "IssueTime", "00:00:00")
    lines = [l for l in move.invoice_line_ids if l.display_type == "product"]
    infos = [analyze_line(l) for l in lines]
    all_free = bool(infos) and all(i["free"] for i in infos)

    # Detracción (SPOT): lo aporta el módulo l10n_pe_sunat_detraccion (si está instalado)
    detr = getattr(move, "sunat_detraction_code_id", False) if doc_type == "01" else False
    if doc_type in ("01", "03"):
        _sub(root, "cbc", "InvoiceTypeCode", doc_type, listID="1001" if detr else "0101")
    _sub(root, "cbc", "Note", amount_in_words(move.amount_total, cur), languageLocaleID="1000")
    if all_free:  # leyenda 1002: solo si TODAS las operaciones son gratuitas
        _sub(root, "cbc", "Note", FREE_LEGEND, languageLocaleID="1002")
    if detr:
        _sub(root, "cbc", "Note", "Operación sujeta a detracción", languageLocaleID="2006")
    _sub(root, "cbc", "DocumentCurrencyCode", cur)

    if doc_type in ("07", "08"):
        reason = move.sunat_credit_reason if doc_type == "07" else move.sunat_debit_reason
        desc = move.sunat_note_description or (move.ref or move.name or "Nota")
        resp = _sub(root, "cac", "DiscrepancyResponse")
        _sub(resp, "cbc", "ReferenceID", "%s-%s" % (original["series"], original["number"]))
        _sub(resp, "cbc", "ResponseCode", reason)
        _sub(resp, "cbc", "Description", desc)
        ref = _sub(_sub(root, "cac", "BillingReference"), "cac", "InvoiceDocumentReference")
        _sub(ref, "cbc", "ID", "%s-%s" % (original["series"], original["number"]))
        _sub(ref, "cbc", "DocumentTypeCode", original["doc_type"])

    # Referencia a la firma
    sig = _sub(root, "cac", "Signature")
    _sub(sig, "cbc", "ID", "SignSUNAT")
    signatory = _sub(sig, "cac", "SignatoryParty")
    _sub(_sub(signatory, "cac", "PartyIdentification"), "cbc", "ID", company.vat)
    _sub(_sub(signatory, "cac", "PartyName"), "cbc", "Name", company.name)
    att = _sub(sig, "cac", "DigitalSignatureAttachment")
    _sub(_sub(att, "cac", "ExternalReference"), "cbc", "URI", "#SignSUNAT")

    # Emisor
    legal = _party(root, "AccountingSupplierParty", company.vat, company.name, "6")
    addr = _sub(legal, "cac", "RegistrationAddress")
    _sub(addr, "cbc", "ID", company.sunat_ubigeo or "150101")
    _sub(addr, "cbc", "AddressTypeCode", company.sunat_estab_code or "0000")

    # Cliente
    partner = move.partner_id
    pname = partner.name or "CLIENTES VARIOS"
    _party(root, "AccountingCustomerParty", partner.vat, pname, partner_doc_code(partner))

    # Forma de pago (obligatoria en facturas)
    if doc_type == "01":
        if detr:
            pm = _sub(root, "cac", "PaymentMeans")
            _sub(pm, "cbc", "ID", "Detraccion")
            _sub(pm, "cbc", "PaymentMeansCode", company.sunat_detraction_means or "001")
            _sub(_sub(pm, "cac", "PayeeFinancialAccount"), "cbc", "ID", company.sunat_detraction_account)
            dt = _sub(root, "cac", "PaymentTerms")
            _sub(dt, "cbc", "ID", "Detraccion")
            _sub(dt, "cbc", "PaymentMeansID", detr.code)
            _sub(dt, "cbc", "PaymentPercent", _num(move.sunat_detraction_rate))
            _sub(dt, "cbc", "Amount", _num(move.sunat_detraction_amount), currencyID="PEN")
        due = move.invoice_date_due
        if due and due > move.invoice_date:
            pt = _sub(root, "cac", "PaymentTerms")
            _sub(pt, "cbc", "ID", "FormaPago")
            _sub(pt, "cbc", "PaymentMeansID", "Credito")
            _amt(pt, "Amount", move.amount_total, cur)
            pt2 = _sub(root, "cac", "PaymentTerms")
            _sub(pt2, "cbc", "ID", "FormaPago")
            _sub(pt2, "cbc", "PaymentMeansID", "Cuota001")
            _amt(pt2, "Amount", move.amount_total, cur)
            _sub(pt2, "cbc", "PaymentDueDate", due.isoformat())
        else:
            pt = _sub(root, "cac", "PaymentTerms")
            _sub(pt, "cbc", "ID", "FormaPago")
            _sub(pt, "cbc", "PaymentMeansID", "Contado")

    # Totales de impuestos agrupados por tributo
    groups = {}
    for info in infos:
        g = groups.setdefault(info["code"], {"base": 0.0, "tax": 0.0})
        g["base"] += info["base"]
        g["tax"] += info["tax"]
    taxt = _sub(root, "cac", "TaxTotal")
    _amt(taxt, "TaxAmount", sum(g["tax"] for code, g in groups.items() if code != "9996"), cur)
    for code, g in groups.items():
        sub = _sub(taxt, "cac", "TaxSubtotal")
        _amt(sub, "TaxableAmount", g["base"], cur)
        _amt(sub, "TaxAmount", g["tax"], cur)
        category = _sub(sub, "cac", "TaxCategory")
        _sub(category, "cbc", "ID", TAX_CATEGORY[code])
        scheme = _sub(category, "cac", "TaxScheme")
        name, intl = TAX_SCHEMES[code]
        _sub(scheme, "cbc", "ID", code)
        _sub(scheme, "cbc", "Name", name)
        _sub(scheme, "cbc", "TaxTypeCode", intl)

    mon = _sub(root, "cac", total_tag)
    _amt(mon, "LineExtensionAmount", move.amount_untaxed, cur)
    _amt(mon, "TaxInclusiveAmount", move.amount_total, cur)
    _amt(mon, "PayableAmount", move.amount_total, cur)

    # Líneas
    for idx, (line, info) in enumerate(zip(lines, infos), 1):
        qty = line.quantity or 1.0
        l_el = _sub(root, "cac", line_tag)
        _sub(l_el, "cbc", "ID", idx)
        _sub(l_el, "cbc", qty_tag, "%.4f" % qty, unitCode=getattr(line, "sunat_uom_code", None) or "NIU")
        _amt(l_el, "LineExtensionAmount", 0.0 if info["free"] else line.price_subtotal, cur)
        pref = _sub(_sub(l_el, "cac", "PricingReference"), "cac", "AlternativeConditionPrice")
        if info["free"]:  # valor referencial unitario en operaciones no onerosas (Cat. 16 = 02)
            _sub(pref, "cbc", "PriceAmount", _price(info["unit"]), currencyID=cur)
            _sub(pref, "cbc", "PriceTypeCode", "02")
        else:
            _sub(pref, "cbc", "PriceAmount", _price(line.price_total / qty), currencyID=cur)
            _sub(pref, "cbc", "PriceTypeCode", "01")
        lt = _sub(l_el, "cac", "TaxTotal")
        _amt(lt, "TaxAmount", info["tax"], cur)
        ls = _sub(lt, "cac", "TaxSubtotal")
        _amt(ls, "TaxableAmount", info["base"], cur)
        _amt(ls, "TaxAmount", info["tax"], cur)
        tc = _sub(ls, "cac", "TaxCategory")
        _sub(tc, "cbc", "ID", TAX_CATEGORY[info["code"]])
        _sub(tc, "cbc", "Percent", _num(info["percent"]))
        _sub(tc, "cbc", "TaxExemptionReasonCode", info["afect"])
        ts = _sub(tc, "cac", "TaxScheme")
        name, intl = TAX_SCHEMES[info["code"]]
        _sub(ts, "cbc", "ID", info["code"])
        _sub(ts, "cbc", "Name", name)
        _sub(ts, "cbc", "TaxTypeCode", intl)
        item = _sub(l_el, "cac", "Item")
        _sub(item, "cbc", "Description", (line.name or "").replace("\n", " ").strip() or "Item")
        price = _sub(l_el, "cac", "Price")
        _sub(price, "cbc", "PriceAmount", _price(0.0 if info["free"] else line.price_subtotal / qty),
             currencyID=cur)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)
