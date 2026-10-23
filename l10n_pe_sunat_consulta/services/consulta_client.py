"""Consulta integrada de validez de CPE (REST) y consulta de CDR (SOAP, solo producción)."""
import base64

import requests

from odoo.addons.l10n_pe_sunat_beta.services import soap_client

TOKEN_URL = "https://api-seguridad.sunat.gob.pe/v1/clientesextranet/%s/oauth2/token/"
SCOPE = "https://api.sunat.gob.pe/v1/contribuyente/contribuyentes"
VALIDAR_URL = "https://api.sunat.gob.pe/v1/contribuyente/contribuyentes/%s/validarcomprobante"
CONSULT_CDR_URL = "https://e-factura.sunat.gob.pe/ol-it-wsconscpegem/billConsultService"

ESTADO_CP = [
    ("0", "NO EXISTE (comprobante no informado)"),
    ("1", "ACEPTADO"),
    ("2", "ANULADO"),
    ("3", "AUTORIZADO"),
    ("4", "NO AUTORIZADO"),
]
ESTADO_RUC = {
    "00": "ACTIVO", "01": "BAJA PROVISIONAL", "02": "BAJA PROV. POR OFICIO",
    "03": "SUSPENSIÓN TEMPORAL", "10": "BAJA DEFINITIVA", "11": "BAJA DE OFICIO",
    "22": "INHABILITADO - VENT. ÚNICA",
}
COND_DOMI = {
    "00": "HABIDO", "09": "PENDIENTE", "11": "POR VERIFICAR", "12": "NO HABIDO", "20": "NO HALLADO",
}


class ConsultaError(Exception):
    pass


def get_token(company):
    if not (company.sunat_api_client_id and company.sunat_api_client_secret):
        raise ConsultaError("Configure Client ID y Client Secret de la API SUNAT (pestaña SUNAT de la compañía).")
    resp = requests.post(TOKEN_URL % company.sunat_api_client_id, timeout=30, data={
        "grant_type": "client_credentials", "scope": SCOPE,
        "client_id": company.sunat_api_client_id, "client_secret": company.sunat_api_client_secret,
    })
    if resp.status_code != 200:
        raise ConsultaError("No se pudo obtener el token SUNAT (%s): %s" % (resp.status_code, resp.text[:200]))
    return resp.json()["access_token"]


def validar_comprobante(company, ruc_emisor, doc_code, series, number, issue_date, amount):
    """Devuelve dict con estadoCp, estadoRuc, condDomiRuc y observaciones."""
    token = get_token(company)
    payload = {
        "numRuc": ruc_emisor,
        "codComp": doc_code,
        "numeroSerie": series,
        "numero": str(int(number)),
        "fechaEmision": issue_date.strftime("%d/%m/%Y"),
        "monto": "%.2f" % amount,
    }
    resp = requests.post(VALIDAR_URL % company.vat, json=payload, timeout=30,
                         headers={"Authorization": "Bearer %s" % token})
    if resp.status_code >= 400:
        raise ConsultaError("SUNAT respondió %s: %s" % (resp.status_code, resp.text[:300]))
    body = resp.json()
    if not body.get("success", True) or "data" not in body:
        raise ConsultaError(body.get("message") or "Respuesta inesperada de SUNAT")
    data = body["data"]
    return {
        "estado_cp": str(data.get("estadoCp", "")),
        "estado_ruc": str(data.get("estadoRuc") or ""),
        "cond_domi": str(data.get("condDomiRuc") or ""),
        "observaciones": "; ".join(data.get("observaciones") or []),
        "raw": resp.text,
    }


def get_status_cdr(company, user, pwd, ruc, doc_code, series, number):
    """billConsultService.getStatusCdr (solo producción). Devuelve (statusCode, mensaje, cdr_bytes)."""
    body = ("<ser:getStatusCdr><rucComprobante>%s</rucComprobante><tipoComprobante>%s</tipoComprobante>"
            "<serieComprobante>%s</serieComprobante><numeroComprobante>%s</numeroComprobante>"
            "</ser:getStatusCdr>") % (ruc, doc_code, series, int(number))
    root = soap_client.post(CONSULT_CDR_URL, user, pwd, body)
    content = root.findtext(".//content")
    return (root.findtext(".//statusCode"), root.findtext(".//statusMessage"),
            base64.b64decode(content) if content else None)
