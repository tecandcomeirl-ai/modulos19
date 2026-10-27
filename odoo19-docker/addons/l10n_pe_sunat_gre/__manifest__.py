{
    "name": "SUNAT Perú - Guía de Remisión Electrónica (GRE Remitente)",
    "version": "19.0.1.0.0",
    "category": "Inventory/Localizations/EDI",
    "summary": "Genera, firma y envía la GRE remitente (09) por la API REST de SUNAT y recibe el CDR",
    "depends": ["l10n_pe_sunat_beta", "stock"],
    "external_dependencies": {"python": ["lxml", "signxml", "cryptography", "requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/gre_data.xml",
        "views/res_company_views.xml",
        "views/sunat_gre_views.xml",
        "views/stock_picking_views.xml",
        "report/gre_report.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
