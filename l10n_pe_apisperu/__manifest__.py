{
    "name": "Perú - Consulta DNI y RUC (APIsPERU)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": "Consulta nombres por DNI y datos por RUC con la API de apisperu.com y completa los contactos",
    "description": """
Conecta Odoo con la API de APIsPERU (https://apisperu.com):
- Completa el nombre de un contacto al escribir su DNI (8 dígitos) o RUC (11 dígitos)
- Botón «Consultar» en el contacto, asistente «Consultar DNI/RUC» y acción masiva en la lista de contactos
- Validación local del número antes de gastar una consulta (incluye dígito verificador del RUC)
- Historial de consultas SIN datos personales (números enmascarados) y contador mensual
- El token se guarda solo para administradores y nunca aparece en mensajes ni logs
""",
    "depends": ["base"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/apisperu_data.xml",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
        "views/lookup_wizard_views.xml",
        "views/apisperu_log_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
