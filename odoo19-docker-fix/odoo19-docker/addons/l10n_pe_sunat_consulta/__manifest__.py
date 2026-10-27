{
    "name": "SUNAT Perú - Consulta de comprobantes",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Consulta integrada de validez de CPE (API SUNAT) y consulta de CDR; valida facturas de proveedores",
    "depends": ["l10n_pe_sunat_beta"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/consulta_views.xml",
        "views/account_move_views.xml",
        "views/sunat_document_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
