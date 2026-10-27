"""Cliente REST de la plataforma GRE de SUNAT (OAuth2 password grant + envío por ticket)."""
import base64
import hashlib

import requests


class GreError(Exception):
    def __init__(self, code, message):
        super().__init__("%s - %s" % (code, message))
        self.code, self.message = code, message


def _raise_for(resp):
    if resp.status_code < 400:
        return
    try:
        data = resp.json()
    except ValueError:
        raise GreError(resp.status_code, resp.text[:300])
    errors = data.get("errors") or []
    if errors:
        raise GreError(errors[0].get("codError", resp.status_code), errors[0].get("desError", ""))
    raise GreError(data.get("cod", resp.status_code), data.get("msg") or data.get("error_description") or "")


def get_token(company):
    if not (company.sunat_gre_client_id and company.sunat_gre_client_secret):
        raise GreError("CFG", "Configure Client ID y Client Secret de la API SUNAT en la compañía.")
    token_url, _api = company._gre_urls()
    data = {
        "grant_type": "password",
        "scope": "https://api-cpe.sunat.gob.pe",
        "client_id": company.sunat_gre_client_id,
        "client_secret": company.sunat_gre_client_secret,
        "username": "%s%s" % (company.vat, company.sunat_sol_user),
        "password": company.sunat_sol_password,
    }
    resp = requests.post(token_url, data=data, timeout=30)
    _raise_for(resp)
    return resp.json()["access_token"]


def send_gre(company, base_name, zip_bytes):
    """Envía el ZIP firmado; devuelve el número de ticket."""
    token = get_token(company)
    _t, api = company._gre_urls()
    payload = {"archivo": {
        "nomArchivo": base_name + ".zip",
        "arcGreZip": base64.b64encode(zip_bytes).decode(),
        "hashZip": hashlib.sha256(zip_bytes).hexdigest(),
    }}
    resp = requests.post(api + base_name, json=payload, timeout=60,
                         headers={"Authorization": "Bearer %s" % token})
    _raise_for(resp)
    return resp.json()["numTicket"]


def get_status(company, ticket):
    """Devuelve (codRespuesta, cdr_bytes|None, mensaje_error|None). 0=ok, 98=en proceso, 99=error."""
    token = get_token(company)
    _t, api = company._gre_urls()
    resp = requests.get(api + "envios/" + ticket, timeout=30,
                        headers={"Authorization": "Bearer %s" % token})
    _raise_for(resp)
    data = resp.json()
    cdr = base64.b64decode(data["arcCdr"]) if data.get("arcCdr") else None
    err = data.get("error") or {}
    msg = ("%s - %s" % (err.get("numError"), err.get("desError"))) if err else None
    return str(data.get("codRespuesta")), cdr, msg
