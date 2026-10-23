{
    "name": "SUNAT Perú - Detracciones (SPOT)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Catálogo de detracciones, cálculo automático y bloque de detracción en el XML UBL 2.1",
    "depends": ["l10n_pe_sunat_beta"],
    "data": [
        "security/ir.model.access.csv",
        "data/detraction_codes.xml",
        "views/detraction_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
