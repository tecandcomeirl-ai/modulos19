{
    "name": "SUNAT Perú - Facturación electrónica (Factura, Boleta, NC, ND, Nota de venta)",
    "version": "19.0.2.0.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Envío y recepción de CPE a SUNAT (SEE-SOL beta/producción) sobre la contabilidad peruana l10n_pe",
    "description": """
Módulo base de facturación electrónica SUNAT para Odoo 19 Community:
- Factura (01), Boleta (03), Nota de crédito (07) y Nota de débito (08) en UBL 2.1
- Firma XMLDSig, envío SOAP (sendBill) y recepción/lectura del CDR
- Nota de venta (documento interno, no se envía a SUNAT)
- Integrado con l10n_pe / l10n_latam_invoice_document (tipos de documento, tipos de identificación, impuestos)
""",
    "depends": ["account", "l10n_pe", "l10n_latam_invoice_document"],
    "external_dependencies": {"python": ["lxml", "signxml", "cryptography", "requests", "num2words"]},
    "data": [
        "security/ir.model.access.csv",
        "data/sunat_data.xml",
        "views/res_company_views.xml",
        "views/account_tax_views.xml",
        "views/sunat_document_views.xml",
        "views/account_move_views.xml",
        "report/nota_venta_report.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
