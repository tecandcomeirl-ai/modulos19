{
    "name": "Perú - Reportes contables y Libros Electrónicos PLE (Community)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations/Reporting",
    "summary": "Genera los TXT del PLE (Registro de Ventas 14.1, Compras 8.1, Libro Diario 5.1, Plan contable 5.3) y Excel de respaldo",
    "description": """
Alternativa Community a l10n_pe_reports de Enterprise:
- Registro de Ventas e Ingresos 14.1 (140100) y Registro de Compras 8.1 (080100)
- Libro Diario 5.1 (050100) y Detalle del plan contable 5.3 (050300)
- Nombre de archivo oficial LE+RUC+AAAAMM00+libro+00+O+I+M+1
- Exportación a Excel de respaldo/conciliación
IMPORTANTE: el Registro de Ventas y el de Compras han migrado al SIRE; los TXT 14.1/8.1 sirven
a quien aún no está incorporado y como base de conciliación. Valide siempre con el PLE oficial.
""",
    "depends": ["account", "l10n_pe", "l10n_pe_sunat_beta"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "views/ple_report_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
