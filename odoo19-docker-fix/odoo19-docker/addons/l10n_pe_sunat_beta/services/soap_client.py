"""Cliente SOAP mínimo para billService de SUNAT (sin dependencias extra)."""
import base64
import io
import zipfile

import requests
from lxml import etree

ENVELOPE = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
 xmlns:ser="http://service.sunat.gob.pe"
 xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
 <soapenv:Header><wsse:Security><wsse:UsernameToken>
  <wsse:Username>{user}</wsse:Username><wsse:Password>{pwd}</wsse:Password>
 </wsse:UsernameToken></wsse:Security></soapenv:Header>
 <soapenv:Body>{body}</soapenv:Body></soapenv:Envelope>"""


class SunatError(Exception):
    def __init__(self, code, message):
        super().__init__("%s - %s" % (code, message))
        self.code, self.message = code, message


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_zip(filename_xml, xml_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename_xml, xml_bytes)
    return buf.getvalue()


def post(url, user, pwd, body, timeout=60):
    data = ENVELOPE.format(user=_esc(user), pwd=_esc(pwd), body=body).encode("utf-8")
    resp = requests.post(url, data=data, timeout=timeout,
                         headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""})
    root = etree.fromstring(resp.content)
    fault = root.find(".//{*}Fault")
    if fault is not None:
        code = (fault.findtext("faultcode") or "").split(".")[-1]
        raise SunatError(code, fault.findtext("faultstring") or "Error SUNAT")
    return root


def send_bill(url, user, pwd, zip_name, zip_bytes):
    body = "<ser:sendBill><fileName>%s</fileName><contentFile>%s</contentFile></ser:sendBill>" % (
        zip_name, base64.b64encode(zip_bytes).decode())
    root = post(url, user, pwd, body)
    return base64.b64decode(root.findtext(".//applicationResponse"))  # ZIP con el CDR


def send_summary(url, user, pwd, zip_name, zip_bytes):
    body = "<ser:sendSummary><fileName>%s</fileName><contentFile>%s</contentFile></ser:sendSummary>" % (
        zip_name, base64.b64encode(zip_bytes).decode())
    return post(url, user, pwd, body).findtext(".//ticket")


def get_status(url, user, pwd, ticket):
    body = "<ser:getStatus><ticket>%s</ticket></ser:getStatus>" % ticket
    root = post(url, user, pwd, body)
    code = root.findtext(".//statusCode")
    content = root.findtext(".//content")
    return code, (base64.b64decode(content) if content else None)


def parse_cdr(cdr_zip_bytes):
    """Devuelve (codigo, descripcion) del ApplicationResponse dentro del CDR."""
    with zipfile.ZipFile(io.BytesIO(cdr_zip_bytes)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        root = etree.fromstring(z.read(name))
    ns = {"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
          "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"}
    code = root.findtext(".//cac:DocumentResponse/cac:Response/cbc:ResponseCode", namespaces=ns)
    desc = root.findtext(".//cac:DocumentResponse/cac:Response/cbc:Description", namespaces=ns)
    return code, desc
