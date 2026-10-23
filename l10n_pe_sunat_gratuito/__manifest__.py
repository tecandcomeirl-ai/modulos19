{
    "name": "SUNAT Perú - Operaciones gratuitas",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations/EDI",
    "summary": "Bonificaciones, retiros, muestras y transferencias gratuitas: valor referencial, tributo 9996 y leyenda 1002",
    "description": """
Marca líneas de factura/boleta como operación gratuita (Catálogo 07: 11-16, 21, 31-37):
- Valor referencial unitario (PriceTypeCode 02), precio y valor de venta en 0.00
- Tributo 9996 (GRA) con el IGV teórico informado pero NO sumado al total
- Leyenda 1002 cuando todo el comprobante es gratuito
- Resumen diario (instrucción 05) y registros PLE consistentes
""",
    "depends": ["l10n_pe_sunat_beta"],
    "data": ["views/account_move_views.xml"],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
