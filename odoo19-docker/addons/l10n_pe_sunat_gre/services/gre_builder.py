"""UBL 2.1 DespatchAdvice (GRE remitente, tipo 09) según guía SUNAT."""
from lxml import etree

DESPATCH = "urn:oasis:names:specification:ubl:schema:xsd:DespatchAdvice-2"
NS_BASE = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
CAT = "urn:pe:gob:sunat:cpe:see:gem:catalogos:catalogo"


def _q(prefix, tag):
    return "{%s}%s" % (NS_BASE[prefix], tag)


def _sub(parent, prefix, tag, text=None, **attrs):
    el = etree.SubElement(parent, _q(prefix, tag), **attrs)
    if text is not None:
        el.text = str(text)
    return el


def _address(parent, tag, ubigeo, line):
    addr = _sub(parent, "cac", tag)
    _sub(addr, "cbc", "ID", ubigeo, schemeAgencyName="PE:INEI", schemeName="Ubigeos")
    _sub(_sub(addr, "cac", "AddressLine"), "cbc", "Line", line)
    return addr


def build_despatch(gre):
    company = gre.company_id
    nsmap = {None: DESPATCH}
    nsmap.update(NS_BASE)
    root = etree.Element("{%s}DespatchAdvice" % DESPATCH, nsmap=nsmap)

    ext = _sub(_sub(root, "ext", "UBLExtensions"), "ext", "UBLExtension")
    _sub(ext, "ext", "ExtensionContent")

    _sub(root, "cbc", "UBLVersionID", "2.1")
    _sub(root, "cbc", "CustomizationID", "2.0")
    _sub(root, "cbc", "ID", "%s-%s" % (gre.series, gre.number))
    _sub(root, "cbc", "IssueDate", gre.date_issue.isoformat())
    _sub(root, "cbc", "IssueTime", gre.time_issue or "00:00:00")
    _sub(root, "cbc", "DespatchAdviceTypeCode", "09", listAgencyName="PE:SUNAT",
         listName="Tipo de Documento", listURI=CAT + "01")
    if gre.note:
        _sub(root, "cbc", "Note", gre.note)

    # Documento relacionado (factura/boleta) - lo aporta l10n_pe_edi_stock
    related = getattr(gre, "related_doc_number", False)
    if related:
        ref = _sub(root, "cac", "AdditionalDocumentReference")
        _sub(ref, "cbc", "ID", related)
        _sub(ref, "cbc", "DocumentTypeCode", getattr(gre, "related_doc_type", False) or "01")

    sig = _sub(root, "cac", "Signature")
    _sub(sig, "cbc", "ID", "SignSUNAT")
    signatory = _sub(sig, "cac", "SignatoryParty")
    _sub(_sub(signatory, "cac", "PartyIdentification"), "cbc", "ID", company.vat)
    _sub(_sub(signatory, "cac", "PartyName"), "cbc", "Name", company.name)
    att = _sub(sig, "cac", "DigitalSignatureAttachment")
    _sub(_sub(att, "cac", "ExternalReference"), "cbc", "URI", "#SignSUNAT")

    # Remitente
    sup = _sub(root, "cac", "DespatchSupplierParty")
    _sub(sup, "cbc", "CustomerAssignedAccountID", company.vat, schemeID="6")
    _sub(_sub(_sub(sup, "cac", "Party"), "cac", "PartyLegalEntity"), "cbc", "RegistrationName", company.name)

    # Destinatario
    cus = _sub(root, "cac", "DeliveryCustomerParty")
    cparty = _sub(cus, "cac", "Party")
    _sub(_sub(cparty, "cac", "PartyIdentification"), "cbc", "ID", gre.partner_vat, schemeID=gre.partner_doc_type)
    _sub(_sub(cparty, "cac", "PartyLegalEntity"), "cbc", "RegistrationName", gre.partner_id.name)

    # Envío
    ship = _sub(root, "cac", "Shipment")
    _sub(ship, "cbc", "ID", "SUNAT_Envio")
    _sub(ship, "cbc", "HandlingCode", gre.reason, listAgencyName="PE:SUNAT",
         listName="Motivo de traslado", listURI=CAT + "20")
    _sub(ship, "cbc", "GrossWeightMeasure", "%.3f" % gre.gross_weight, unitCode="KGM")
    if gre.packages:
        _sub(ship, "cbc", "TotalTransportHandlingUnitQuantity", int(gre.packages))
    _sub(ship, "cbc", "SplitConsignmentIndicator", "false")

    stage = _sub(ship, "cac", "ShipmentStage")
    _sub(stage, "cbc", "TransportModeCode", gre.transport_mode, listAgencyName="PE:SUNAT",
         listName="Modalidad de traslado", listURI=CAT + "18")
    _sub(_sub(stage, "cac", "TransitPeriod"), "cbc", "StartDate", gre.transfer_date.isoformat())
    if gre.transport_mode == "01":  # transporte público
        carrier = _sub(stage, "cac", "CarrierParty")
        _sub(_sub(carrier, "cac", "PartyIdentification"), "cbc", "ID", gre.carrier_vat, schemeID="6")
        _sub(_sub(carrier, "cac", "PartyLegalEntity"), "cbc", "RegistrationName", gre.carrier_name)
    else:  # transporte privado
        driver = _sub(stage, "cac", "DriverPerson")
        _sub(driver, "cbc", "ID", gre.driver_doc, schemeID=gre.driver_doc_type)
        _sub(driver, "cbc", "FirstName", gre.driver_first_name)
        _sub(driver, "cbc", "FamilyName", gre.driver_last_name)
        _sub(driver, "cbc", "JobTitle", "Principal")
        _sub(_sub(driver, "cac", "IdentityDocumentReference"), "cbc", "ID", gre.driver_license)

    delivery = _sub(ship, "cac", "Delivery")
    _address(delivery, "DeliveryAddress", gre.dest_ubigeo, gre.dest_address)
    despatch = _sub(delivery, "cac", "Despatch")
    _address(despatch, "DespatchAddress", gre.origin_ubigeo, gre.origin_address)

    if gre.transport_mode == "02":
        unit = _sub(ship, "cac", "TransportHandlingUnit")
        _sub(_sub(unit, "cac", "TransportEquipment"), "cbc", "ID", gre.vehicle_plate)

    for idx, line in enumerate(gre.line_ids, 1):
        dl = _sub(root, "cac", "DespatchLine")
        _sub(dl, "cbc", "ID", idx)
        _sub(dl, "cbc", "DeliveredQuantity", "%.3f" % line.quantity, unitCode=line.uom_code or "NIU")
        _sub(_sub(dl, "cac", "OrderLineReference"), "cbc", "LineID", idx)
        item = _sub(dl, "cac", "Item")
        _sub(item, "cbc", "Description", (line.description or "").replace("\n", " ").strip() or "Item")
        if line.product_code:
            _sub(_sub(item, "cac", "SellersItemIdentification"), "cbc", "ID", line.product_code)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=False)
