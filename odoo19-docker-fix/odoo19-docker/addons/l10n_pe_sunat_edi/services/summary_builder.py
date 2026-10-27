"""UBL 2.0 de SUNAT: Resumen diario de boletas (RC) y Comunicación de baja (RA)."""
from lxml import etree

from odoo.addons.l10n_pe_sunat_beta.services.ubl_builder import (
    NS_BASE, analyze_line, partner_doc_code)

SAC = "urn:sunat:names:specification:ubl:peru:schema:xsd:SunatAggregateComponents-1"
SUMMARY = "urn:sunat:names:specification:ubl:peru:schema:xsd:SummaryDocuments-1"
VOIDED = "urn:sunat:names:specification:ubl:peru:schema:xsd:VoidedDocuments-1"
INSTRUCTION = {"1000": "01", "1016": "01", "2000": "01", "9997": "02",
               "9998": "03", "9995": "04", "9999": "03"}


def _q(prefix, tag):
    ns = SAC if prefix == "sac" else NS_BASE[prefix]
    return "{%s}%s" % (ns, tag)


def _sub(parent, prefix, tag, text=None, **attrs):
    el = etree.SubElement(parent, _q(prefix, tag), **attrs)
    if text is not None:
        el.text = str(text)
    return el


def _num(value):
    return "%.2f" % (value or 0.0)


def _header(root_tag, root_ns, customization, summary):
    nsmap = {None: root_ns, "sac": SAC}
    nsmap.update(NS_BASE)
    root = etree.Element("{%s}%s" % (root_ns, root_tag), nsmap=nsmap)
    company = summary.company_id
    ext = _sub(_sub(root, "ext", "UBLExtensions"), "ext", "UBLExtension")
    _sub(ext, "ext", "ExtensionContent")
    _sub(root, "cbc", "UBLVersionID", "2.0")
    _sub(root, "cbc", "CustomizationID", customization)
    _sub(root, "cbc", "ID", summary.name)
    _sub(root, "cbc", "ReferenceDate", summary.reference_date.isoformat())
    _sub(root, "cbc", "IssueDate", summary.issue_date.isoformat())

    sig = _sub(root, "cac", "Signature")
    _sub(sig, "cbc", "ID", "SignSUNAT")
    signatory = _sub(sig, "cac", "SignatoryParty")
    _sub(_sub(signatory, "cac", "PartyIdentification"), "cbc", "ID", company.vat)
    _sub(_sub(signatory, "cac", "PartyName"), "cbc", "Name", company.name)
    att = _sub(sig, "cac", "DigitalSignatureAttachment")
    _sub(_sub(att, "cac", "ExternalReference"), "cbc", "URI", "#SignSUNAT")

    sup = _sub(root, "cac", "AccountingSupplierParty")
    _sub(sup, "cbc", "CustomerAssignedAccountID", company.vat)
    _sub(sup, "cbc", "AdditionalAccountID", "6")
    _sub(_sub(_sub(sup, "cac", "Party"), "cac", "PartyLegalEntity"), "cbc", "RegistrationName", company.name)
    return root


def build_summary(summary):
    """Resumen diario (RC) de boletas; cada línea: condición 1=adicionar, 3=anular."""
    root = _header("SummaryDocuments", SUMMARY, "1.1", summary)
    for idx, line in enumerate(summary.line_ids, 1):
        move = line.move_id
        series, number = move._sunat_series_number()
        cur = move.currency_id.name
        sl = _sub(root, "sac", "SummaryDocumentsLine")
        _sub(sl, "cbc", "LineID", idx)
        _sub(sl, "cbc", "DocumentTypeCode", move.sunat_doc_type)
        _sub(sl, "cbc", "ID", "%s-%d" % (series, int(number)))
        cust = _sub(sl, "cac", "AccountingCustomerParty")
        vat = (move.partner_id.vat or "").strip()
        code = partner_doc_code(move.partner_id) if vat else "0"
        _sub(cust, "cbc", "CustomerAssignedAccountID", vat or "0")
        _sub(cust, "cbc", "AdditionalAccountID", code)
        _sub(_sub(sl, "cac", "Status"), "cbc", "ConditionCode", line.condition)
        _sub(sl, "sac", "TotalAmount", _num(move.amount_total), currencyID=cur)

        groups = {}
        for ml in move.invoice_line_ids:
            if ml.display_type != "product":
                continue
            info = analyze_line(ml)
            groups[INSTRUCTION.get(info["code"], "03")] = groups.get(
                INSTRUCTION.get(info["code"], "03"), 0.0) + info["base"]
        for instruction, paid in sorted(groups.items()):
            bp = _sub(sl, "sac", "BillingPayment")
            _sub(bp, "cbc", "PaidAmount", _num(paid), currencyID=cur)
            _sub(bp, "cbc", "InstructionID", instruction)

        tt = _sub(sl, "cac", "TaxTotal")
        _sub(tt, "cbc", "TaxAmount", _num(move.amount_tax), currencyID=cur)
        ts = _sub(tt, "cac", "TaxSubtotal")
        _sub(ts, "cbc", "TaxAmount", _num(move.amount_tax), currencyID=cur)
        scheme = _sub(_sub(ts, "cac", "TaxCategory"), "cac", "TaxScheme")
        _sub(scheme, "cbc", "ID", "1000")
        _sub(scheme, "cbc", "Name", "IGV")
        _sub(scheme, "cbc", "TaxTypeCode", "VAT")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)


def build_voided(summary):
    """Comunicación de baja (RA) de facturas / notas."""
    root = _header("VoidedDocuments", VOIDED, "1.0", summary)
    for idx, line in enumerate(summary.line_ids, 1):
        move = line.move_id
        series, number = move._sunat_series_number()
        vl = _sub(root, "sac", "VoidedDocumentsLine")
        _sub(vl, "cbc", "LineID", idx)
        _sub(vl, "cbc", "DocumentTypeCode", move.sunat_doc_type)
        _sub(vl, "sac", "DocumentSerialID", series)
        _sub(vl, "sac", "DocumentNumberID", str(int(number)))
        _sub(vl, "sac", "VoidReasonDescription", (line.reason or "ANULACION DE LA OPERACION")[:100])
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)
