{
    "name": "Perú - EDI Inventario (Guías de remisión integradas a Inventario)",
    "version": "19.0.1.0.0",
    "category": "Inventory/Localizations/EDI",
    "summary": "Conductores, vehículos, transportistas, almacenes anexos y GRE automática al validar traslados",
    "description": """
Capa de inventario para la guía de remisión electrónica (Community):
- Maestros de conductores y vehículos
- Datos de transporte en la operación de inventario
- Código de establecimiento anexo y ubigeo por almacén
- GRE automática al validar entregas/traslados (opcional por tipo de operación)
- Códigos de unidad de medida SUNAT y tipo de existencia de producto
- Referencia de la factura/boleta en la guía
No usa el nombre de Enterprise para el EDI: depende de l10n_pe_sunat_gre.
""",
    "depends": ["l10n_pe_sunat_gre", "product", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/uom_data.xml",
        "views/transport_views.xml",
        "views/stock_views.xml",
        "views/sunat_gre_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
