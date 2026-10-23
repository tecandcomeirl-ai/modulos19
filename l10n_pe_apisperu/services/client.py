"""Cliente HTTP de APIsPERU (https://dniruc.apisperu.com) para consultar DNI y RUC.

Sin dependencias de Odoo: se puede probar de forma aislada.
Contrato (documentación oficial, dniruc.apisperu.com/doc):
    GET {base}/dni/{numero}?token=TOKEN -> dni, nombres, apellidoPaterno, apellidoMaterno, codVerifica
    GET {base}/ruc/{numero}?token=TOKEN -> ruc, razonSocial, nombreComercial, telefonos, estado,
                                         condicion, direccion, departamento, provincia, distrito, ubigeo
SEGURIDAD: el token viaja como parámetro de la URL, por eso NUNCA se incluye la URL ni la excepción
original de `requests` en los mensajes de error ni en los logs.
"""
import re

import requests

DEFAULT_BASE_URL = "https://dniruc.apisperu.com/api/v1"
DEFAULT_TIMEOUT = 15
RUC_PREFIXES = ("10", "15", "16", "17", "20")


class ApisPeruError(Exception):
    """code: config | invalid | auth | not_found | quota | network | server | response"""

    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def digits(value):
    return re.sub(r"\D", "", value or "")


def ruc_checksum_ok(ruc):
    """Dígito verificador del RUC (módulo 11)."""
    weights = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    total = sum(int(d) * w for d, w in zip(ruc[:10], weights))
    check = 11 - (total % 11)
    check = {10: 0, 11: 1}.get(check, check)
    return check == int(ruc[10])


def validate_number(kind, number):
    clean = digits(number)
    if kind == "dni":
        if len(clean) != 8:
            raise ApisPeruError("invalid", "El DNI debe tener 8 dígitos.")
    elif kind == "ruc":
        if len(clean) != 11 or clean[:2] not in RUC_PREFIXES or not ruc_checksum_ok(clean):
            raise ApisPeruError("invalid", "El RUC no es válido (11 dígitos y dígito verificador correcto).")
    else:
        raise ApisPeruError("invalid", "Tipo de documento no soportado: %s." % kind)
    return clean


def mask(number):
    """Número enmascarado para el historial (no se guardan DNI/RUC completos)."""
    number = number or ""
    if len(number) <= 4:
        return "*" * len(number)
    return number[:2] + "*" * (len(number) - 4) + number[-2:]


def _message(data):
    if isinstance(data, dict):
        return str(data.get("message") or data.get("error") or data.get("msg") or "").strip()
    return ""


def _call(kind, number, token, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT):
    if not token:
        raise ApisPeruError("config", "Falta el token de APIsPERU. Configúrelo en la pestaña «APIsPERU» "
                                      "de la compañía (obtenga su token en https://apisperu.com/admin).")
    url = "%s/%s/%s" % ((base_url or DEFAULT_BASE_URL).rstrip("/"), kind, number)
    try:
        resp = requests.get(url, params={"token": token}, headers={"Accept": "application/json"}, timeout=timeout)
    except requests.Timeout:
        raise ApisPeruError("network", "APIsPERU no respondió a tiempo. Intente nuevamente.") from None
    except requests.RequestException:
        # No se incluye str(e): contiene la URL con el token.
        raise ApisPeruError("network", "No se pudo conectar con APIsPERU. Revise la conexión a internet.") from None

    status = resp.status_code
    try:
        data = resp.json()
    except ValueError:
        data = None
    api_msg = _message(data)

    if status in (401, 403):
        raise ApisPeruError("auth", "Token de APIsPERU inválido, vencido o sin permisos.", status)
    if status == 404:
        raise ApisPeruError("not_found", "No se encontraron datos para el %s consultado." % kind.upper(), status)
    if status == 429:
        raise ApisPeruError("quota", "Se alcanzó el límite de consultas de su plan en APIsPERU.", status)
    if status in (400, 422):
        raise ApisPeruError("invalid", api_msg or "APIsPERU rechazó el número consultado.", status)
    if status >= 500:
        raise ApisPeruError("server", "APIsPERU no está disponible en este momento (error %s)." % status, status)
    if status != 200:
        raise ApisPeruError("response", api_msg or "Respuesta inesperada de APIsPERU (HTTP %s)." % status, status)
    if not isinstance(data, dict):
        raise ApisPeruError("response", "APIsPERU devolvió una respuesta que no se pudo interpretar.", status)
    if data.get("success") is False:
        low = api_msg.lower()
        if "token" in low:
            raise ApisPeruError("auth", "Token de APIsPERU inválido, vencido o sin permisos.", status)
        if "encontr" in low or "not found" in low:
            raise ApisPeruError("not_found", "No se encontraron datos para el %s consultado." % kind.upper(), status)
        raise ApisPeruError("response", api_msg or "APIsPERU indicó un error en la consulta.", status)
    return data


def lookup_dni(number, token, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT):
    clean = validate_number("dni", number)
    data = _call("dni", clean, token, base_url, timeout)
    first = (data.get("nombres") or "").strip()
    paternal = (data.get("apellidoPaterno") or "").strip()
    maternal = (data.get("apellidoMaterno") or "").strip()
    if not (first or paternal or maternal):
        raise ApisPeruError("not_found", "No se encontraron datos para el DNI consultado.", 200)
    return {
        "document": clean, "first_names": first, "last_name_paternal": paternal,
        "last_name_maternal": maternal, "check_digit": str(data.get("codVerifica") or ""),
    }


def lookup_ruc(number, token, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT):
    clean = validate_number("ruc", number)
    data = _call("ruc", clean, token, base_url, timeout)
    name = (data.get("razonSocial") or "").strip()
    if not name:
        raise ApisPeruError("not_found", "No se encontraron datos para el RUC consultado.", 200)
    trade = (data.get("nombreComercial") or "").strip()
    return {
        "document": clean, "name": name, "trade_name": "" if trade in ("-", "") else trade,
        "status": (data.get("estado") or "").strip(), "condition": (data.get("condicion") or "").strip(),
        "address": (data.get("direccion") or "").strip(), "department": (data.get("departamento") or "").strip(),
        "province": (data.get("provincia") or "").strip(), "district": (data.get("distrito") or "").strip(),
        "ubigeo": str(data.get("ubigeo") or ""), "phones": list(data.get("telefonos") or []),
    }


def build_full_name(data, fmt="last_first"):
    """'last_first' -> APELLIDO_P APELLIDO_M NOMBRES (formato SUNAT); 'first_last' -> NOMBRES APELLIDOS."""
    if fmt == "first_last":
        parts = (data["first_names"], data["last_name_paternal"], data["last_name_maternal"])
    else:
        parts = (data["last_name_paternal"], data["last_name_maternal"], data["first_names"])
    return " ".join(p for p in parts if p)
