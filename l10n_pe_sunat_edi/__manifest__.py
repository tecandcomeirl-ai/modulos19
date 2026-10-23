{
    "name": "SUNAT Perú - EDI para Community (automatización completa)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Capa EDI Community: envío automático, reintentos, resumen diario, bajas, PDF con QR y correo",
    "description": """
Une los módulos SUNAT (CPE, GRE y consulta) y agrega:
- Envío automático al publicar o programado (cron) con reintentos
- Resumen diario de boletas (RC) y comunicación de baja (RA)
- Representación impresa con QR y hash de firma
- Correo automático al cliente con PDF, XML y CDR
No usa el nombre l10n_pe_edi para no chocar con el módulo Enterprise de Odoo.
""",
    "depends": ["l10n_pe_sunat_beta", "l10n_pe_sunat_gre", "l10n_pe_sunat_consulta", "mail"],
    "external_dependencies": {"python": ["lxml", "signxml", "cryptography", "requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/edi_data.xml",
        "views/res_company_views.xml",
        "views/sunat_summary_views.xml",
        "views/account_move_views.xml",
        "wizard/void_wizard_views.xml",
        "report/cpe_report.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
