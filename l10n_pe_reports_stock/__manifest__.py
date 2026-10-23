{
    "name": "Perú - Reportes de Inventario PLE (12.1 y 13.1)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations/Reporting",
    "summary": "Registro de Inventario Permanente en Unidades Físicas (12.1) y Valorizado (13.1) en formato PLE",
    "description": """
Extiende l10n_pe_reports con:
- 12.1 Registro del inventario permanente en unidades físicas (120100)
- 13.1 Registro del inventario permanente valorizado (130100)
Usa los movimientos de stock hechos por almacén (código de establecimiento anexo), los códigos de
existencia y unidad de medida de l10n_pe_edi_stock y el valor de stock.move (Odoo 19 eliminó
stock.valuation.layer).
""",
    "depends": ["l10n_pe_reports", "l10n_pe_edi_stock", "stock_account"],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
    "data": [],
}
